"""Load `gh-agile` as a module, and refuse to run outside the project venv.

The extension is a single executable file with no `.py` suffix, so it cannot be
imported by name. It is loaded here from its path, once, and every test module
takes its subject from this fixture.

**Nothing in this directory may touch the network.** The tool's only other test
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


@pytest.fixture
def no_network(monkeypatch, tool):
    """Make any accidental shell-out or API call a loud failure.

    Every function under test here is meant to be pure. If one reaches for
    `gh`, the test should fail on that fact rather than quietly succeeding on a
    developer's machine and failing in CI.
    """
    def forbidden(*args, **kwargs):
        raise AssertionError(f"a unit test attempted to run: {args!r}")

    monkeypatch.setattr(tool, "gh", forbidden)
    monkeypatch.setattr(tool, "graphql", forbidden)
    return forbidden
