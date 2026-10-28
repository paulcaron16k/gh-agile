"""An unknown flag is reported against the command it was given to. AGILE-221.

argparse hands what a subcommand did not recognise back to the top level, which
printed its own usage -- `gh agile [-h] [--owner OWNER] ... <command>` -- for
`issue close 1 --bogus`, so the flags `issue close` does take were never shown.
`gh issue close 1 --bogus` names the flag and prints the close command's usage.
"""

from __future__ import annotations

import pytest

#: One command from each group, and the top-level ones, with a bad flag.
LINES = [
    ["issue", "close", "1"], ["issue", "list"], ["epic", "view", "3"],
    ["story", "create", "-t", "T", "--epic", "none"], ["initiative", "list"],
    ["task", "list"], ["board", "view", "B"], ["sprint", "view"], ["project", "view"],
    ["key", "list"], ["init"], ["sync"], ["validate"], ["export"],
]


def name(line):
    """The command words: the line up to its first argument."""
    words = []
    for word in line:
        if word.startswith("-") or not (word.isalpha() and word.islower()):
            break
        words.append(word)
    return " ".join(words)


def failure(tool, capsys, argv):
    with pytest.raises(SystemExit) as caught:
        tool.build_parser().parse_args(argv)
    return caught.value.code, capsys.readouterr().err


@pytest.mark.parametrize("line", LINES, ids=" ".join)
class TestABadFlagNamesItsCommand:
    def test_the_message_names_the_command(self, tool, capsys, line):
        command = name(line)
        _code, err = failure(tool, capsys, [*line, "--bogus"])
        assert f"gh agile {command}: unknown flag: --bogus" in err

    def test_the_usage_is_the_commands_not_the_top_levels(self, tool, capsys, line):
        command = name(line)
        _code, err = failure(tool, capsys, [*line, "--bogus"])
        assert err.startswith(f"usage: gh agile {command}")
        assert "<command>" not in err.splitlines()[0]

    def test_it_points_at_that_commands_help(self, tool, capsys, line):
        command = name(line)
        _code, err = failure(tool, capsys, [*line, "--bogus"])
        assert f"gh agile {command} --help" in err

    def test_the_exit_code_is_usage(self, tool, capsys, line):
        code, _err = failure(tool, capsys, [*line, "--bogus"])
        assert code == 2


class TestTheOtherCases:
    def test_a_stray_positional_says_so(self, tool, capsys):
        _code, err = failure(tool, capsys, ["board", "list", "extra"])
        assert "gh agile board list: unexpected argument: extra" in err

    def test_a_misused_flag_is_still_the_commands(self, tool, capsys):
        """argparse already reports a bad *value* from the subcommand; held here."""
        _code, err = failure(tool, capsys, ["issue", "close", "1", "-r", "nope"])
        assert err.startswith("usage: gh agile issue close")

    def test_a_bad_flag_before_the_command_is_reported_against_it(self, tool, capsys):
        """The line still named a command, and that command's usage is the useful one."""
        _code, err = failure(tool, capsys, ["--bogus", "validate"])
        assert "gh agile validate: unknown flag: --bogus" in err

    def test_a_retired_flag_is_an_unknown_flag_like_any_other(self, tool, capsys):
        """Its hint went in #307; it is reported against its command."""
        _code, err = failure(tool, capsys, ["export", "--csv"])
        assert "gh agile export: unknown flag: --csv" in err
