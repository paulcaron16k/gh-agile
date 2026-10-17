"""No profile must be reported as no profile. #111.

`find_config` resolves `CONFIG_PATHS` relative to the working directory, so
outside a clone nothing is found, `read_config` returns `{}` and `--project` --
which deliberately has no argparse default -- stays `None`. Nothing checked it,
so the `None` travelled into a GraphQL variable and came back as

    no project None found for 'paulcaron16k' as either a user or an organization

which names a project the caller never named, blames the lookup when the profile
is what is missing, and leaks a Python repr into user-facing output. Measured
2026-09-14 on `board list`, `sprint list`, `validate` and `export`.

This is the first thing a new installation does, not an edge case: `gh extension
install` clones the repository, profile included, into gh's extension directory,
`find_config` never looks there, and the operator can then *see* a perfectly good
profile the tool is not using.

The sibling case in `apply_defaults` already did this properly -- "not inside a
GitHub repository, and no --repo given" -- so the fix is that shape, one branch
over.
"""

from __future__ import annotations

import argparse
import json

import pytest

WITH_NUMBER = {"project": {"number": 4, "owner": "boardowner"}}
WITHOUT_NUMBER = {"keys": [{"key": "AGILE", "repo": "o/r"}]}


#: A runnable command line for each command these tests name.
COMMAND_LINES = {
    "validate": ["validate"], "export": ["export"], "board": ["board", "list"],
    "sprint": ["sprint", "list"], "sync": ["sync"], "project": ["project", "owner"],
    "key": ["key"], "self-test": ["self-test", "--repo", "o/r"],
}


@pytest.fixture
def defaults(monkeypatch, tool):
    """`apply_defaults` on a real command line, the profile and the owner lookup
    stubbed. Parsed rather than built by hand, because whether a command needs a
    project is declared on its parser (#202)."""
    def go(command="validate", *, project=None, config=None):
        monkeypatch.setattr(tool, "read_config", lambda *a, **k: config or {})
        monkeypatch.setattr(tool, "resolve_owner", lambda args, cfg: None)
        monkeypatch.setattr(tool, "current_repo", lambda: "o/r")
        args = tool.build_parser().parse_args(COMMAND_LINES[command])
        args.project = project
        tool.apply_defaults(args)
        return args
    return go


@pytest.fixture
def outside(monkeypatch, tmp_path):
    """A directory with no profile in it, genuinely -- not a stub."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestTheRefusal:
    def test_no_profile_and_no_flag_is_refused(self, tool, defaults, outside):
        with pytest.raises(SystemExit) as exit_info:
            defaults("validate")
        assert "no profile found" in str(exit_info.value)

    def test_it_does_not_blame_the_project_lookup(self, tool, defaults, outside):
        """The defect: a missing profile reported as a missing project."""
        message = str(pytest.raises(SystemExit, defaults, "validate").value)
        assert "as either a user or an organization" not in message

    def test_no_message_renders_a_missing_number_as_none(self, tool, defaults, outside):
        """`None` in user-facing output is the tell that nothing checked."""
        message = str(pytest.raises(SystemExit, defaults, "validate").value)
        assert "None" not in message

    @pytest.mark.parametrize("command", ["validate", "export", "board", "sprint", "sync"])
    def test_every_command_that_needs_a_board_is_covered(
        self, tool, defaults, outside, command,
    ):
        """The check sits beside the `--repo` one, so this is one place, not five."""
        with pytest.raises(SystemExit) as exit_info:
            defaults(command)
        assert "no profile found" in str(exit_info.value)


class TestTheMessage:
    @pytest.fixture
    def message(self, tool, defaults, outside):
        return str(pytest.raises(SystemExit, defaults, "validate").value)

    def test_it_names_every_path_searched(self, tool, message):
        for candidate in tool.CONFIG_PATHS:
            assert candidate in message

    def test_it_names_the_directory_searched(self, message, outside):
        assert str(outside) in message

    def test_it_says_the_extension_copy_is_not_consulted(self, message):
        """The operator can see a profile in the extension directory. Say why not."""
        assert "extension" in message

    def test_it_offers_the_ways_out(self, message):
        assert "--config" in message
        assert "--project" in message
        assert "config_from" in message


class TestAProfileThatNamesNoNumber:
    @pytest.fixture
    def message(self, tool, defaults, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "agile.json").write_text(json.dumps(WITHOUT_NUMBER))
        return str(pytest.raises(SystemExit, defaults, "validate",
                                 config=WITHOUT_NUMBER).value)

    def test_it_is_told_apart_from_no_profile_at_all(self, message):
        """A readable profile missing a line is a different problem from no file."""
        assert "names no project.number" in message
        assert "no profile found" not in message

    def test_it_names_the_file_it_read(self, message):
        assert ".github/agile.json" in message

    def test_it_points_at_the_bootstrap(self, message):
        assert "gh agile project create" in message

    def test_it_renders_no_none(self, message):
        assert "None" not in message


class TestWhatMustStillWork:
    def test_a_profile_with_a_number_still_fills_the_flag(self, tool, defaults, outside):
        assert defaults("validate", config=WITH_NUMBER).project == 4

    def test_an_explicit_project_needs_no_profile(self, tool, defaults, outside):
        """The documented escape hatch for a directory with no profile."""
        assert defaults("validate", project=7).project == 7

    @pytest.mark.parametrize("command", ["project", "key", "self-test"])
    def test_the_projectless_commands_are_exempt(self, tool, defaults, outside, command):
        """`project create` is what *writes* project.number; demanding one here
        would mean needing a board before you could record the board."""
        assert defaults(command).project is None

    def test_the_exemptions_are_exactly_these(self, tool):
        """The exemption is declared on each parser now, so a typo can no longer
        name a command that does not exist -- the hazard the old name list had.
        What is left to guard is the list itself: a new command exempted by
        copy-paste would carry a `None` project into a GraphQL variable."""
        def walk(parser, path=()):
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    for name, child in action.choices.items():
                        yield (*path, name), child
                        yield from walk(child, (*path, name))

        exempt = {path[0] for path, parser in walk(tool.build_parser())
                  if parser.get_default("projectless")}
        assert exempt == {"project", "key", "self-test", "task", "init", "hooks"}


class TestItCostsNoNetworkCall:
    def test_nothing_is_asked_of_github_before_refusing(
        self, tool, monkeypatch, outside,
    ):
        """No preflight and no doomed query: the refusal is local."""
        def forbidden(*_a, **_k):
            raise AssertionError("apply_defaults reached the network")

        monkeypatch.setattr(tool, "graphql", forbidden)
        monkeypatch.setattr(tool, "read_config", lambda *a, **k: {})
        monkeypatch.setattr(tool, "resolve_owner", lambda args, cfg: None)
        args = argparse.Namespace(command="validate", project=None, owner=None,
                                  repo=None, key=None, config=None)
        with pytest.raises(SystemExit):
            tool.apply_defaults(args)
