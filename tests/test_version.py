"""`gh agile --version` -- what is actually running. AGILE-196.

**A script extension tracks `main`**, so every consumer is on whatever it was at
their last `gh extension upgrade` and no two need agree (#197). Until this, a bug
report, a pasted measurement and a `validate` run were all anonymous as to which
build produced them -- and the tool's whole discipline is measurements somebody
can check later.

Three facts, each of which has cost an afternoon: the build, the interpreter
(this runs under the user's `python3`, and a `target-version` drift once passed
lint and every test under 3.12 then crashed on first use under the system 3.10),
and the profile actually resolved (`config_from` means the file in front of you
may not be the file in use).

Offline, and that is also a requirement rather than a convenience: `--version`
must work with no network, no token and no board, because it is what somebody
runs when those are what is broken.
"""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Stub:
    def __init__(self, returncode=0, stdout=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, ""


def answers(tool, monkeypatch, **by_subcommand):
    """Stub `git`, keyed on the subcommand asked for."""
    def run(command, **kwargs):
        for key, value in by_subcommand.items():
            if key in command:
                return Stub(0, value) if value is not None else Stub(1, "")
        return Stub(1, "")
    monkeypatch.setattr(tool.subprocess, "run", run)


class TestTheBuildComesFromTheCheckout:
    def test_a_tagged_build_reads_as_a_version(self, tool, monkeypatch):
        answers(tool, monkeypatch, describe="v0.3.0-2-ge160178", **{"rev-parse": "main"})
        assert tool.checkout_version() == ("v0.3.0-2-ge160178", "main")

    def test_an_untagged_clone_falls_back_to_the_commit(self, tool, monkeypatch):
        """Every clone was in this state before #197 cut the first tag."""
        answers(tool, monkeypatch, describe="e160178", **{"rev-parse": "main"})
        assert tool.checkout_version()[0] == "e160178"

    def test_a_working_tree_with_edits_says_so(self, tool, monkeypatch):
        """What is running is then not any commit."""
        answers(tool, monkeypatch, describe="v0.3.0-2-ge160178-dirty",
                **{"rev-parse": "story/x"})
        assert tool.checkout_version() == ("v0.3.0-2-ge160178-dirty", "story/x")

    def test_not_a_checkout_is_unknown_rather_than_an_error(self, tool, monkeypatch):
        """A file lifted out of its clone still gets the rest of the report."""
        answers(tool, monkeypatch, describe=None, **{"rev-parse": None})
        assert tool.checkout_version() == ("unknown", "")

    def test_no_git_at_all_is_unknown_too(self, tool, monkeypatch):
        def missing(*a, **k):
            raise OSError("git not found")
        monkeypatch.setattr(tool.subprocess, "run", missing)
        assert tool.checkout_version() == ("unknown", "")

    def test_nothing_is_declared_in_the_file(self, tool):
        """If this story ever adds a constant somebody has to bump, it has
        become the thing it was filed against.

        Asked of the loaded module rather than the source text: the docstring
        above names `VERSION = "0.3.1"` as the thing it rejects, and a grep over
        prose matches its own explanation -- the same trap `test_duration.py`
        fell into over the word velocity."""
        assert not hasattr(tool, "VERSION")
        assert not hasattr(tool, "__version__")


class TestWhatItPrints:
    @pytest.fixture
    def lines(self, tool, monkeypatch, tmp_path):
        def go(*, profile=None, describe="v0.3.0-2-ge160178", branch="main"):
            answers(tool, monkeypatch, describe=describe, **{"rev-parse": branch})
            monkeypatch.setattr(tool, "find_config", lambda *a, **k: profile)
            return tool.version_lines()
        return go

    def test_the_build_is_first(self, lines):
        assert lines()[0].strip().startswith("gh-agile v0.3.0-2-ge160178")

    def test_the_branch_is_named(self, lines):
        assert "(main)" in lines()[0]

    def test_an_unknown_branch_leaves_no_empty_brackets(self, lines):
        assert "()" not in lines(branch="")[0]

    def test_the_interpreter_and_its_floor(self, tool, lines):
        import platform
        line = lines()[1]
        assert platform.python_version() in line
        assert "floor 3.10+" in line

    def test_the_interpreter_is_named_by_path(self, tool, lines):
        """Which `python3` matters: the extension runs under the user's, not a
        venv's, and the two have disagreed."""
        import sys
        assert sys.executable in lines()[1]

    def test_no_profile_says_where_it_looked(self, lines, tool):
        line = lines()[2]
        assert "none found" in line
        for candidate in tool.CONFIG_PATHS:
            assert candidate in line

    def test_a_profile_is_named_by_path(self, lines, tmp_path):
        path = tmp_path / "agile.json"
        path.write_text('{"keys": []}')
        assert str(path) in lines(profile=path)[2]

    def test_a_config_from_pointer_is_reported(self, lines, tmp_path):
        """`config_from` means the file in front of you may not be the file in
        use, which is exactly what somebody running --version wants to know."""
        path = tmp_path / "agile.json"
        path.write_text('{"config_from": "acme/main-repo"}')
        assert "acme/main-repo" in lines(profile=path)[2]

    def test_and_is_not_followed(self, lines, tmp_path, tool, monkeypatch):
        """Following it is an API call. `--version` is what somebody runs when
        the network, the token or the board is what is broken."""
        path = tmp_path / "agile.json"
        path.write_text('{"config_from": "acme/main-repo"}')
        monkeypatch.setattr(tool, "gh", lambda *a, **k: pytest.fail("--version called gh"))
        monkeypatch.setattr(tool, "graphql",
                            lambda *a, **k: pytest.fail("--version called the API"))
        assert "not followed" in lines(profile=path)[2]

    def test_an_unreadable_profile_does_not_raise(self, lines, tmp_path):
        path = tmp_path / "agile.json"
        path.write_text("{ not json")
        assert "unreadable" in lines(profile=path)[2]

    def test_it_is_three_lines(self, lines):
        assert len(lines()) == 3


class TestTheFlagItself:
    def test_it_works_although_a_subcommand_is_required(self, tool, monkeypatch, capsys):
        """The whole point: `gh agile --version` was an argparse error listing
        the subcommands, which is the least useful possible answer."""
        answers(tool, monkeypatch, describe="v0.3.0", **{"rev-parse": "main"})
        monkeypatch.setattr(tool, "find_config", lambda *a, **k: None)
        with pytest.raises(SystemExit) as caught:
            tool.build_parser().parse_args(["--version"])
        assert caught.value.code == 0
        assert "gh-agile v0.3.0" in capsys.readouterr().out

    def test_it_is_not_computed_unless_asked(self, tool, monkeypatch):
        """argparse's own `action="version"` takes a finished string, so the
        build would be worked out while the parser is built -- a subprocess on
        every invocation of every command, to serve one flag."""
        monkeypatch.setattr(tool, "checkout_version", lambda *a, **k: pytest.fail(
            "the build was computed while building the parser"))
        tool.build_parser()

    def test_the_guide_documents_it(self):
        assert "gh agile --version" in (ROOT / "USER_GUIDE.md").read_text()
