"""`--help` says each thing once. AGILE-268.

The beta product review found every list printing `At most this many (default
30) (default 30)` -- `flag_label` appends the default, and five help strings
stated it as well -- the refused `gh` flags listed among the flags a command
takes, `-R` described three ways for one meaning, and `task list` describing a
board read for what is a search.
"""

from __future__ import annotations

import argparse
import re

import pytest


def every_flag(parser, path=()):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, child in action.choices.items():
                yield from every_flag(child, (*path, name))
        elif action.option_strings and action.help not in (None, argparse.SUPPRESS):
            yield " ".join(path), action


def help_of(tool, *words, capsys):
    with pytest.raises(SystemExit):
        tool.build_parser().parse_args([*words, "--help"])
    return capsys.readouterr().out


def test_no_flag_states_its_default_twice(tool):
    for path, action in every_flag(tool.build_parser()):
        _left, text = tool.flag_label(action)
        assert len(re.findall(r"\bdefault\b", text)) <= 1, (path, text)


def test_no_help_string_states_the_default_by_hand(tool):
    """`flag_label` appends it; a hand-written one is the second copy."""
    for path, action in every_flag(tool.build_parser()):
        assert "%(default)" not in action.help, (path, action.option_strings)
        assert "(the default)" not in action.help, (path, action.option_strings)


def test_refused_flags_are_not_listed_as_flags(tool, capsys):
    text = help_of(tool, "story", "create", capsys=capsys)
    flags = text.split("\nFLAGS\n", 1)[1].split("\n\n", 1)[0]
    refused = text.split("\nGH FLAGS NOT SUPPORTED\n", 1)[1].split("\n\n", 1)[0]
    assert "--editor" not in flags and "--web" not in flags
    assert "Refused" not in flags
    assert "--editor" in refused and "does not prompt" in refused


@pytest.mark.parametrize("kind,expected", [
    ("create", "CREATE_REPO_HELP"),
    ("target", "TARGET_REPO_HELP"),
])
def test_repo_is_one_string_per_meaning(tool, kind, expected):
    """A command that files an issue says where; one that targets one says the
    same fallback the same way."""
    creates = {"initiative create", "epic create", "story create", "bug create",
               "task create"}
    targets = {"issue view", "issue edit", "issue move", "issue close", "issue reopen",
               "issue reconcile", "initiative reconcile"}
    wanted = getattr(tool, expected)
    for path, action in every_flag(tool.build_parser()):
        if "--repo" in action.option_strings and path in (creates if kind == "create"
                                                           else targets):
            assert action.help == wanted, path


def test_key_says_its_default_everywhere(tool):
    for path, action in every_flag(tool.build_parser()):
        if action.option_strings == ["--key"] and path.endswith("create"):
            assert action.help == tool.KEY_HELP, path


def test_task_list_says_what_it_does(tool, capsys):
    text = help_of(tool, "task", capsys=capsys)
    assert "List tasks in the profile's repositories" in text
    assert "on the board" not in text.split("list:", 1)[1].splitlines()[0]
    listed = help_of(tool, "task", "list", capsys=capsys)
    assert "GitHub search terms" in listed and "board view --filter" not in listed
