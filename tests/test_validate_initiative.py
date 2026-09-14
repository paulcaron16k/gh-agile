"""`validate` at the initiative level, and the findings it deliberately does not make.

An initiative is a level above epic, and most of what `validate` already knows
generalises upward unchanged. Two things do not.

**Roll-up is per level, not transitive.** Measured before the level was designed:
closing a story took its epic to `1/1` while the initiative stayed `0/1`, because
`subIssuesSummary` counts direct children. An initiative's tally is epics closed,
not stories, and a check written as if it reached the whole tree would report a
number nobody could reconcile with the board.

**An epic with no initiative is not a finding.** Initiatives are optional and most
epics will never belong to one. Reporting that would make the common case a
finding, which is how a validator gets ignored.
"""

from __future__ import annotations

import pytest

FINISHED = "is finished with a sub-issue still open"
STRANDED = "every sub-issue is closed but the"


def item(*, number=9, labels="type:initiative;key:AGILE", state="OPEN", status="Todo",
         total=0, closed=0, title="a thing"):
    return {
        "number": number, "title": title, "repository": "o/r", "state": state,
        "state_reason": "COMPLETED" if state == "CLOSED" else "",
        "labels": labels + ";sprint:2026-08-31",
        "field_status": status, "field_sprint": "", "epic_number": None,
        "sub_issues_total": total, "sub_issues_done": closed,
        "started_at": "", "done_at": "",
    }


@pytest.fixture
def validate(monkeypatch, tool, capsys):
    def go(*rows, only=None):
        import argparse
        monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
        monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
            [{"title": "Sprint 2", "startDate": "2026-08-31", "duration": 14}], []))
        args = argparse.Namespace(owner="o", project=1, _config={}, id=only)
        tool.cmd_validate(args)
        return capsys.readouterr().out
    return go


class TestAnInitiativeWithNoEpics:
    def test_it_is_reported(self, tool, validate):
        """A list of the epics a large feature requires, with none in it."""
        assert "initiative has no epics" in validate(item(total=0))

    def test_one_with_epics_is_not(self, tool, validate):
        assert "initiative has no epics" not in validate(item(total=2, closed=1))


class TestRollUpOneLevelUp:
    def test_an_initiative_finished_over_an_open_epic(self, tool, validate):
        out = validate(item(total=3, closed=2, state="CLOSED", status="Done"))
        assert f"initiative {FINISHED}" in out

    def test_an_initiative_stranded_over_closed_epics(self, tool, validate):
        out = validate(item(total=2, closed=2, state="OPEN", status="Todo"))
        assert f"{STRANDED} initiative is not" in out

    def test_the_heading_says_which_level(self, tool, validate):
        """`epic` and `initiative` are different findings and a reader has to be
        able to tell them apart without opening the issue."""
        out = validate(item(number=9, total=2, closed=2),
                       item(number=10, labels="type:epic;key:AGILE", total=2, closed=2))
        assert f"{STRANDED} initiative is not" in out
        assert f"{STRANDED} epic is not" in out

    def test_an_initiative_in_step_is_silent(self, tool, validate):
        out = validate(item(total=2, closed=2, state="CLOSED", status="Done"))
        assert FINISHED not in out and STRANDED not in out


class TestWhatIsDeliberatelyNotReported:
    def test_an_epic_with_no_initiative(self, tool, validate):
        """Initiatives are optional. Most epics will never belong to one."""
        out = validate(item(labels="type:epic;key:AGILE", total=1, closed=0))
        assert "initiative" not in out.lower() or "has no epics" not in out

    def test_a_story_with_no_initiative_label(self, tool, validate):
        out = validate(item(labels="type:story;key:AGILE", total=0, closed=0))
        assert "names no initiative" not in out


class TestSlugsAcrossTheBoard:
    def test_two_initiatives_claiming_one_slug(self, tool, validate):
        """Two trees behind one board filter, looking entirely correct -- what
        `initiative create` refuses, and which a hand-applied label can still
        produce."""
        out = validate(item(number=9, labels="type:initiative;initiative:big"),
                       item(number=10, labels="type:initiative;initiative:big"))
        assert "two initiatives claim initiative:big" in out
        assert "#9" in out and "#10" in out

    def test_one_initiative_per_slug_is_silent(self, tool, validate):
        out = validate(item(number=9, labels="type:initiative;initiative:big", total=1),
                       item(number=10, labels="type:epic;initiative:big", total=1))
        assert "two initiatives claim" not in out

    def test_a_label_naming_no_initiative(self, tool, validate):
        """A detached subtree whose label was never cleaned up, or an initiative
        that is not on the board. The filter shows these as part of an initiative
        the board does not know about."""
        out = validate(item(number=10, labels="type:epic;initiative:ghost", total=1))
        assert "initiative:ghost names no initiative on this board" in out
        assert "initiative reconcile" in out

    def test_it_points_at_the_command_that_fixes_it(self, tool, validate):
        out = validate(item(number=10, labels="type:story;initiative:ghost"))
        assert "reconcile" in out

    def test_the_board_wide_checks_are_skipped_under_id(self, tool, validate):
        """Properties of the set, not of any issue -- reporting them from a
        command aimed at one issue reads as a finding about that issue."""
        out = validate(item(number=9, labels="type:initiative;initiative:big", total=1),
                       item(number=10, labels="type:initiative;initiative:big", total=1),
                       only=9)
        assert "two initiatives claim" not in out
