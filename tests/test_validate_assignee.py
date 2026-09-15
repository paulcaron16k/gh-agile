"""`validate` checks the assignee half of starting work, not only the sprint half.

Starting work sets three things -- Status, sprint, assignee -- and `validate`
checked two. Reported by the Zamboni team: *"the sprint half gets caught and the
assignee half never does. The `Closes #n` automation closes the issue and sets
nothing."*

**The check that was not built, and why, because it is the more useful half of
this story.** Two shapes of "closed with nobody on it" were measured on a real
board and both were wrong:

- `closed with no assignee` reports 23 of 47, including six epics closed on the
  roll-up and two closed `NOT_PLANNED` -- all correct states.
- `closed, carries a sprint: label, no assignee` reports 16, every one a true
  historical instance from before starting work claimed the issue, and every one
  unfixable: who did the work is not recoverable from the issue.

Sixteen permanent notes on every run is the same disease as a check that fails
forever. And it buys nothing for the case it was proposed for: an issue closed by
an automation without ever being started has no `sprint:` label either, so
`closed with no sprint: label` already reports it.

So one check, on the live and actionable state.
"""

from __future__ import annotations

import argparse

import pytest

UNASSIGNED = "In Progress but unassigned"


def row(*, kind="story", status="In Progress", state="OPEN", assignees="",
        number=9, sprint="Sprint 2", labels_extra="", started="", sprint_stamp=True):
    labels = f"type:{kind};key:AGILE" + labels_extra
    if sprint_stamp:
        labels += ";sprint:2026-08-31"
    return {
        "number": number, "title": f"a {kind}", "repository": "o/r", "state": state,
        "state_reason": "COMPLETED" if state == "CLOSED" else "",
        "labels": labels, "field_status": status, "field_sprint": sprint,
        "epic_number": 1, "sub_issues_total": 0, "sub_issues_done": 0,
        "assignees": assignees, "started_at": started, "done_at": "",
    }


@pytest.fixture
def validate(monkeypatch, tool, capsys):
    def go(*rows):
        monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
        monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
            [{"title": "Sprint 2", "startDate": "2026-08-31", "duration": 14}], []))
        code = tool.cmd_validate(
            argparse.Namespace(owner="o", project=1, _config={}, id=None))
        return code, capsys.readouterr().out
    return go


class TestInProgressButUnassigned:
    def test_it_is_reported(self, tool, validate):
        assert UNASSIGNED in validate(row())[1]

    def test_an_assigned_one_is_not(self, tool, validate):
        assert UNASSIGNED not in validate(row(assignees="dev"))[1]

    def test_it_is_a_problem_not_a_note(self, tool, validate):
        """Live and actionable: somebody is meant to have this right now, and
        nobody does. That is a state standup exists to fix."""
        code, out = validate(row())
        assert code == 1 and "problem(s) across" in out

    def test_it_mirrors_the_sprint_check(self, tool, validate):
        """`In Progress but in no sprint` and `In Progress but unassigned` are the
        same sentence about the other two thirds of starting work."""
        _, out = validate(row(sprint=""))
        assert "In Progress but in no sprint" in out and UNASSIGNED in out

    @pytest.mark.parametrize("status", ["Todo", "Blocked", "In Review", "Done"])
    def test_no_other_status_is_asked(self, tool, validate, status):
        """Only the transition that claims the issue is held to it."""
        assert UNASSIGNED not in validate(row(status=status))[1]


class TestSpanningLevelsAreNotExempt:
    """An epic is exempt from the *sprint* -- one field cannot say "all of them"
    for a level running across several -- but `move` claims it like anything
    else, on the reasoning that an epic still starts even though it joins no
    iteration. Exempting it here would report less than the tool already does."""

    @pytest.mark.parametrize("kind", ["epic", "initiative"])
    def test_a_started_one_with_nobody_on_it_is_reported(self, tool, validate, kind):
        assert UNASSIGNED in validate(row(kind=kind, sprint=""))[1]

    @pytest.mark.parametrize("kind", ["epic", "initiative"])
    def test_but_it_is_still_exempt_from_the_sprint(self, tool, validate, kind):
        _, out = validate(row(kind=kind, sprint="", assignees="dev"))
        assert "In Progress but in no sprint" not in out


class TestWhatStaysQuiet:
    """The eight closed issues on the real board that carry no assignee and are
    every one of them right to."""

    @pytest.mark.parametrize("kind", ["epic", "initiative"])
    def test_a_spanning_level_closed_on_the_roll_up(self, tool, validate, kind):
        """Never reached In Progress; nobody individually held it."""
        _, out = validate(row(kind=kind, status="Done", state="CLOSED",
                              sprint="", sprint_stamp=False))
        assert UNASSIGNED not in out and "unassigned" not in out

    def test_an_issue_closed_as_not_planned(self, tool, validate):
        _, out = validate(row(status="Done", state="CLOSED", sprint_stamp=False))
        assert "unassigned" not in out

    def test_a_closed_story_that_was_worked_and_never_assigned(self, tool, validate):
        """Historical and unfixable. Reported by nothing, on purpose: sixteen
        permanent notes is the same disease as a check that fails forever."""
        _, out = validate(row(status="Done", state="CLOSED",
                              started="2026-08-15T00:00:00Z"))
        assert "unassigned" not in out

    def test_a_board_with_everything_assigned_is_clean(self, tool, validate):
        code, out = validate(row(assignees="dev"), row(number=10, assignees="bea"))
        assert code == 0 and "no problems found" in out
