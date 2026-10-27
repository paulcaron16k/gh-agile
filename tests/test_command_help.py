"""Every command's help in `gh`'s layout, each flag described once. AGILE-222.

v0.4.0 gave group help `gh`'s sections, but a command's own help was still
argparse's -- `usage:`, `options:`, "show this help message and exit" -- and
many listed every flag twice, under `options:` and again in a `fields:` table.
The two copies disagreed: `story create` and `epic create` marked `--repo`
"required" in the table while the parser took it as optional and fell back to
the clone. The help is now rendered from the parser, so it cannot.

This walks the real parser, so a command added later is held to the same rule.
"""

from __future__ import annotations

import argparse

import pytest


def leaves(tool):
    found = []

    def walk(parser, path=()):
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for shown in action._choices_actions:
                    child = action.choices[shown.dest]
                    if child.subcommands() is None:
                        found.append(((*path, shown.dest), child))
                    walk(child, (*path, shown.dest))
    walk(tool.build_parser())
    return found


def section(text, heading):
    """The lines under `heading`, up to the next blank line."""
    lines = text.splitlines()
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if not lines[i].strip()), len(lines))
    return lines[start:end]


@pytest.fixture(scope="module")
def commands(tool):
    return [(" ".join(path), parser, parser.format_help()) for path, parser in leaves(tool)]


def test_the_walk_finds_the_commands(commands):
    assert len(commands) > 30


class TestTheSections:
    def test_gh_s_sections_in_gh_s_order(self, commands):
        for name, _parser, text in commands:
            headings = [line for line in text.splitlines() if line.isupper()]
            order = [h for h in ("USAGE", "FLAGS", "INHERITED FLAGS", "ARGUMENTS",
                                 "LEARN MORE") if h in headings]
            assert [h for h in headings if h in order] == order, name
            assert {"USAGE", "INHERITED FLAGS", "LEARN MORE"} <= set(headings), name

    def test_no_argparse_headings_remain(self, commands):
        for name, _parser, text in commands:
            assert "usage:" not in text and "options:" not in text, name
            assert "fields:" not in text, name
            assert "show this help message" not in text, name

    def test_it_opens_with_its_description(self, commands):
        for name, parser, text in commands:
            assert text.splitlines()[0] == (parser.description or "").rstrip(), name
            assert text.splitlines()[0], name

    def test_usage_names_the_command_and_its_arguments(self, tool):
        move = {" ".join(p): c for p, c in leaves(tool)}["issue move"]
        assert section(move.format_help(), "USAGE") == [
            "  gh agile issue move <issue> <status> [flags]"]

    def test_arguments_appear_exactly_when_the_command_takes_one(self, commands):
        for name, parser, text in commands:
            takes = any(not a.option_strings for a in parser._actions)
            assert ("ARGUMENTS" in text.splitlines()) == takes, name


class TestEachFlagOnceWithText:
    def test_every_flag_has_one_row_with_a_description(self, commands, tool):
        for name, parser, text in commands:
            rows = section(text, "FLAGS") if "FLAGS" in text.splitlines() else []
            rows += section(text, "INHERITED FLAGS")
            # `gh` flags refused on purpose have their own section (#268).
            if "GH FLAGS NOT SUPPORTED" in text.splitlines():
                rows += section(text, "GH FLAGS NOT SUPPORTED")
            for action in parser._actions:
                if not action.option_strings:
                    continue
                long = next(o for o in action.option_strings if o.startswith("--"))
                mine = [r for r in rows if r.split()[0].rstrip(",") in action.option_strings
                        and long in r.split()[:2]]
                assert len(mine) == 1, (name, long, mine)
                described = mine[0].split(long, 1)[1].strip()
                assert described, (name, long)

    def test_inherited_flags_are_not_repeated_under_flags(self, commands):
        for name, _parser, text in commands:
            if "FLAGS" not in text.splitlines():
                continue
            # The flag column only: a description may mention `--project`.
            own = {word.rstrip(",") for row in section(text, "FLAGS")
                   for word in row.split()[:2]}
            for flag in ("--owner", "--project", "--config", "--help"):
                assert flag not in own, (name, flag)

    def test_every_argument_is_described(self, commands):
        for name, _parser, text in commands:
            if "ARGUMENTS" in text.splitlines():
                for row in section(text, "ARGUMENTS"):
                    assert len(row.split()) > 1, (name, row)


class TestRequiredMatchesTheParser:
    def test_required_is_said_exactly_for_required_flags(self, commands):
        for name, parser, text in commands:
            rows = section(text, "FLAGS") if "FLAGS" in text.splitlines() else []
            for action in parser._actions:
                if not action.option_strings or "--help" in action.option_strings:
                    continue
                long = next(o for o in action.option_strings if o.startswith("--"))
                row = next((r for r in rows if long in r.split()[:2]), "")
                if not row:
                    continue
                assert ("(required)" in row) == bool(action.required), (name, long)

    @pytest.mark.parametrize("command", ["story create", "epic create", "initiative create",
                                         "task create"])
    def test_repo_on_create_defaults_to_the_clone(self, commands, command):
        text = next(t for n, _p, t in commands if n == command)
        row = next(r for r in section(text, "FLAGS") if "--repo" in r)
        assert "(required)" not in row
        assert "defaults to the current clone" in row
