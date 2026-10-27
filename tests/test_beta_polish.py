"""The smaller findings of the beta product review. AGILE-271.

Each is small, and each was something a newcomer meets early: a command that
said nothing where its neighbour explained itself, an exit status a scheduled
job depends on and no help that states it, a README that showed no board and
named no permission, five repair commands with no map between them.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
GUIDE = (ROOT / "USER_GUIDE.md").read_text()


class TestKeyListWithNoProfile:
    def test_it_refuses_as_project_view_does(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "find_config", lambda explicit: None)
        args = tool.build_parser().parse_args(["key", "list"])
        args._config = {}
        with pytest.raises(SystemExit) as refused:
            tool.cmd_key_list(args)
        assert "no profile found" in str(refused.value)

    def test_a_profile_with_no_keys_still_says_so(self, tool, monkeypatch, capsys):
        """An empty profile is a real state, with its own advice."""
        monkeypatch.setattr(tool, "find_config", lambda explicit: ".github/agile.json")
        monkeypatch.setattr(tool, "stdout_is_terminal", lambda: True)
        args = tool.build_parser().parse_args(["key", "list"])
        args._config = {"keys": []}
        assert tool.cmd_key_list(args) == 0
        assert "no keys recorded" in capsys.readouterr().out


def test_validate_states_its_exit_status(tool, capsys):
    with pytest.raises(SystemExit):
        tool.build_parser().parse_args(["validate", "--help"])
    text = capsys.readouterr().out
    status = text.split("EXIT STATUS", 1)[1]
    assert re.search(r"^  0  no problems found", status, re.MULTILINE)
    assert re.search(r"^  1  at least one problem", status, re.MULTILINE)


class TestTheReadmeFirstScreen:
    def test_install_says_what_github_access_is_needed(self):
        install = README.split("## Install\n", 1)[1].split("\n## ", 1)[0]
        assert "push on the repository" in install and "Team Usage" in install

    def test_see_the_work_shows_a_board(self):
        see = README.split("## See the work\n", 1)[1].split("\n## ", 1)[0]
        assert "filter: sprint:@current" in see and "In Progress (" in see

    def test_the_export_default_is_said(self):
        out = README.split("## Get the data out\n", 1)[1].split("\n## ", 1)[0]
        assert "JSON is the default format" in out


def test_every_repair_command_is_in_the_symptom_table(tool):
    table = GUIDE.split("### Which repair: symptom to command", 1)[1].split("\n### ", 1)[0]
    for command in ("sprint reconcile", "issue reconcile", "sprint backfill",
                    "sprint unstamp", "initiative reconcile"):
        assert f"`gh agile {command}" in table, command
