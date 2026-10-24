"""Load `gh-agile` as a module, and refuse to run outside the project venv.

The extension is a single executable file with no `.py` suffix, so it cannot be
imported by name. It is loaded here from its path, once, and every test module
takes its subject from this fixture.

**Nothing in this directory may touch the network**, and `offline` below makes
that a rule rather than a hope: no program runs unless a test names it. The tool's only other test
is `make self-test`, which needs a real GitHub account and exercises one happy
path; none of the defects found in review would have been caught by it. These
tests exist for the parts that are pure -- date placement, hashing, validation,
title construction -- which is where the bugs actually were.

Importing the tool must therefore have no side effects: it defines functions and
constants, and its `main()` only runs under `__name__ == "__main__"`, which is
not the case here.
"""

from __future__ import annotations

import importlib.util
import pathlib
import socket
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOL = ROOT / "gh-agile"


def _require_venv() -> None:
    """Fail loudly if this is the system interpreter.

    A test suite that silently runs against whatever packages happen to be
    installed globally is testing a different environment each machine it lands
    on. The Makefile targets check for the venv before invoking pytest; this is
    the backstop for anyone running pytest directly.
    """
    expected = ROOT / ".venv"
    prefix = pathlib.Path(sys.prefix).resolve()
    if prefix != expected.resolve():
        pytest.exit(
            f"tests must run in {expected}, not {prefix}.\n"
            f"  Create it:  make venv\n"
            f"  Run tests:  make test",
            returncode=2,
        )


_require_venv()


def _load():
    spec = importlib.util.spec_from_loader(
        "gh_agile", importlib.machinery.SourceFileLoader("gh_agile", str(TOOL))
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def tool():
    """The `gh-agile` module, loaded once for the session."""
    return _load()


@pytest.fixture(autouse=True)
def no_project_automation(monkeypatch, tool):
    """`validate` asks the API which project workflows are on. Not in here.

    Autouse and silent, because roughly a hundred tests drive `cmd_validate`
    to assert something about issues, and none of them has any business
    reaching GitHub for a project setting -- when this arrived unstubbed the
    suite went from nine seconds to three minutes and a third of it failed.

    The advice itself is tested through its own pieces, which are pure, and one
    test opts back in by stubbing `project_workflows` and `pull_request_items`
    and letting the real `automation_notes` run.
    """
    monkeypatch.setattr(tool, "automation_notes", lambda *a, **k: [])


#: `git` subcommands that reach another machine. Refused even in a test marked
#: `runs("git")`: the local repositories those tests build need none of them.
GIT_NETWORK = frozenset({"fetch", "pull", "push", "clone", "ls-remote", "remote"})


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        'runs(*programs): let this test start the named programs, e.g. runs("git"). '
        "Nothing else may run; see `offline` in conftest.py.")


@pytest.fixture(autouse=True)
def offline(request, monkeypatch):
    """**No test reaches GitHub, or anything else, unless it says so** (#242).

    `make test` was documented as offline and nothing enforced it. A
    `no_network` fixture existed, used by no test at all, and when #231 changed
    `board_item_for` to ask the issue, four tests that stubbed only the board
    read ran real `gh api graphql` calls from a developer's machine. They were
    read-only against names that do not exist, so they failed; with names that
    resolved they would have passed, and a write would have written. In CI,
    which has no token, the same tests fail for a reason that never mentions
    the network.

    So the default is refusal, at the one place every route out passes:
    `subprocess.Popen`, which `run`, `check_output` and the rest all call. That
    covers the tool's `gh()` and `graphql()`, its direct `["gh", ...]` calls,
    and anything added later. A test that needs a program -- real `git` in a
    temporary repository, `jq` to check `--jq` -- names it with
    `@pytest.mark.runs("git")`, and gets that and nothing more; `git`'s network
    subcommands stay refused even then. Internet sockets are refused for any
    other route out.

    A test that stubs `subprocess.run` itself never gets here, which is the
    point: it has said what the outside world answers.
    """
    allowed = {name for mark in request.node.iter_markers("runs") for name in mark.args}
    real_popen = subprocess.Popen

    class Guarded(real_popen):
        def __init__(self, args, *rest, **kwargs):
            argv = [str(a) for a in args] if isinstance(args, (list, tuple)) else str(args).split()
            program = pathlib.Path(argv[0]).name if argv else ""
            if program not in allowed:
                raise AssertionError(
                    f"a unit test tried to run {' '.join(argv)!r}. Stub it, or mark the "
                    f"test @pytest.mark.runs({program!r}) if it must really run.")
            if program == "git" and len(argv) > 1 and argv[1] in GIT_NETWORK:
                raise AssertionError(f"a unit test tried to reach a remote: {' '.join(argv)!r}")
            super().__init__(args, *rest, **kwargs)

    def no_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError(f"a unit test tried to open a connection to {address!r}")
        return real_connect(sock, address)

    real_connect = socket.socket.connect
    monkeypatch.setattr(subprocess, "Popen", Guarded)
    monkeypatch.setattr(socket.socket, "connect", no_connect)


@pytest.fixture
def edit_args(tool):
    """`issue edit ...` parsed by the real parser, with the board already resolved.

    Through the parser rather than a hand-built Namespace, so a test cannot pass
    an attribute the command line has no way to set -- `--number` lived on in
    tests for that reason after the flag was gone.
    """
    def build(*argv, config=None):
        args = tool.build_parser().parse_args(["issue", "edit", *argv])
        args.owner, args.project, args.repo = "o", 1, "o/r"
        args._config = config or {}
        return args
    return build
