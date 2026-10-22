"""Help splits General commands from Targeted commands, as `gh issue --help` does. AGILE-204.

`gh issue --help` sorts its subcommands into GENERAL COMMANDS -- no identifier
-- and TARGETED COMMANDS, every one taking the same `<number> | <url>`. A reader
learns the rule once and predicts the rest, and it is the rule that would have
made `epic list` impossible to misread as a title.

`gh` splits only where a group has both kinds; `gh label` and `gh project` print
one AVAILABLE COMMANDS list. Matching `gh` means matching where it does not
split as well as where it does.

**This file is what says every command conforms** (#200's acceptance): it walks
the real parser, so a command added later is held to the rule without anybody
remembering to add it here.
"""

from __future__ import annotations

import argparse

import pytest


def shown_commands(parser, path=()):
    """`(path, help, parser)` for every subcommand `--help` shows, nested ones too."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for shown in action._choices_actions:
                child = action.choices[shown.dest]
                yield (*path, shown.dest), shown.help, child
                yield from shown_commands(child, (*path, shown.dest))


def leaves(tool):
    return [(path, text, parser) for path, text, parser in shown_commands(tool.build_parser())
            if parser.subcommands() is None]


def positionals(parser):
    return [a for a in parser._actions
            if not a.option_strings and not isinstance(a, argparse._SubParsersAction)]


class TestTheWalkFindsSomething:
    def test_it_finds_the_leaves(self, tool):
        """A rule checked over an empty list passes for the wrong reason."""
        assert len(leaves(tool)) > 30


class TestEveryCommandIsDeclared:
    def test_every_leaf_says_which_kind_it_is(self, tool):
        undeclared = [" ".join(path) for path, _t, parser in leaves(tool)
                      if parser.command_kind not in (tool.GENERAL, tool.TARGETED)]
        assert undeclared == []

    def test_a_targeted_commands_first_positional_is_its_identifier(self, tool):
        for path, _text, parser in leaves(tool):
            if parser.command_kind != tool.TARGETED:
                continue
            first = positionals(parser)[0]
            assert first.metavar in tool.IDENTIFIERS, path
            assert first.metavar == parser.identifier, path

    def test_an_optional_identifier_has_one_declared_default_target(self, tool):
        """`sprint view` with nothing is the current sprint, as `gh pr view` is
        the current branch. It may never widen to the whole board."""
        for path, _text, parser in leaves(tool):
            if parser.command_kind != tool.TARGETED:
                continue
            first = positionals(parser)[0]
            if first.nargs == "?":
                assert first.default == tool.DEFAULT_TARGETS[parser.identifier], path
            else:
                assert parser.identifier not in tool.DEFAULT_TARGETS, path

    def test_a_general_command_takes_no_identifier(self, tool):
        for path, _text, parser in leaves(tool):
            if parser.command_kind == tool.GENERAL:
                named = [a.metavar or a.dest for a in positionals(parser)]
                assert not set(named) & set(tool.IDENTIFIERS), path

    def test_the_known_targets(self, tool):
        targeted = {" ".join(path) for path, _t, parser in leaves(tool)
                    if parser.command_kind == tool.TARGETED}
        assert {"issue view", "issue move", "issue edit", "issue close", "issue reopen",
                "issue reconcile", "epic view", "story view", "initiative view",
                "initiative reconcile", "board view", "sprint view"} == targeted


class TestDescriptionsAreGhs:
    def test_each_starts_with_a_capital(self, tool):
        lower = [" ".join(path) for path, text, _p in shown_commands(tool.build_parser())
                 if not text[:1].isupper()]
        assert lower == []

    def test_and_ends_without_a_full_stop(self, tool):
        stopped = [" ".join(path) for path, text, _p in shown_commands(tool.build_parser())
                   if text.rstrip().endswith(".")]
        assert stopped == []


def help_of(tool, *path):
    parser = tool.build_parser()
    for name in path:
        parser = {n: p for n, _t, p in parser.subcommands()}[name]
    return parser.format_help()


class TestTheSections:
    @pytest.mark.parametrize("group", ["epic", "story", "initiative", "issue", "board",
                                       "sprint"])
    def test_a_group_with_both_kinds_splits(self, tool, group):
        text = help_of(tool, group)
        assert "GENERAL COMMANDS" in text and "TARGETED COMMANDS" in text
        assert "AVAILABLE COMMANDS" not in text

    @pytest.mark.parametrize("group", ["task", "key", "project"])
    def test_a_group_with_one_kind_does_not(self, tool, group):
        """Not an empty section: `gh label --help` prints one list."""
        text = help_of(tool, group)
        assert "AVAILABLE COMMANDS" in text
        assert "GENERAL COMMANDS" not in text and "TARGETED COMMANDS" not in text

    def test_the_epic_help_reads_as_gh_writes_it(self, tool):
        text = help_of(tool, "epic")
        assert "GENERAL COMMANDS\n  create:        File an epic" in text
        assert "TARGETED COMMANDS\n  view:          View one epic" in text
        assert "ARGUMENTS\n  A targeted command takes an issue number" in text

    def test_the_view_is_under_targeted_and_list_under_general(self, tool):
        text = help_of(tool, "story")
        general, targeted = text.split("TARGETED COMMANDS")
        assert "  list:" in general and "  view:" in targeted

    def test_the_top_level_groups_like_gh(self, tool):
        text = tool.build_parser().format_help()
        work, rest = text.split("BOARD COMMANDS")
        board, general = rest.split("GENERAL COMMANDS")
        assert "WORK ITEM COMMANDS" in work and "  epic:" in work and "  issue:" in work
        assert "  sprint:" in board and "  key:" in board
        for name in ("init", "sync", "validate", "export"):
            assert f"  {name}:" in general.split("FLAGS")[0]

    def test_a_group_opens_with_what_it_is_listed_as(self, tool):
        """As `gh issue --help` opens with the line `gh --help` lists it by."""
        assert help_of(tool, "story").startswith("Stories: the unit of work")

    def test_a_default_target_is_said(self, tool):
        assert "omitted, @current" in help_of(tool, "sprint")


class TestHiddenCommands:
    @pytest.mark.parametrize("hidden", ["self-test", "unfinished"])
    def test_absent_from_help(self, tool, hidden):
        assert hidden not in tool.build_parser().format_help()

    def test_self_test_still_runs(self, tool):
        assert tool.build_parser().parse_args(["self-test", "-R", "o/r"]).func \
            is tool.cmd_self_test


class TestALeafKeepsItsFlags:
    def test_a_leaf_is_argparses_own_help(self, tool):
        text = help_of(tool, "issue", "move")
        assert text.startswith("usage: gh agile issue move")
        assert "--evidence" in text
