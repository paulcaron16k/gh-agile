"""`validate` learns the task level, and stops punishing it. AGILE-136, under #132.

The finding that made #132 necessary. `validate` demands a `type:` label on every
issue, so a story broken into five task sub-issues was five `no type: label`
findings that never cleared -- the **check-that-fails-forever** failure this repo
has hit twice before, in #121 and #91. Both times the conclusion was the same: a
check that cannot be satisfied is a check people stop running, and then it stops
catching what it was written for.

The only way to clear it was `type:story` on a task, which is worse than the
finding: it is the mislabelling #135 exists to make unnecessary.

**What must keep working is the distinction.** An unlabelled sub-issue of a story
is still a real finding -- it might be an unlabelled task, and it might be a
story filed in the wrong place. `validate` cannot tell, which is why it reports
rather than guesses. So this recognises a labelled task; it does not stop
looking.
"""

from __future__ import annotations

import argparse

import pytest

NOTHING = "no type: label"


def row(number=9, *, kind="task", status="Todo", parent_type="story",
        sprint="S2", stamps=True, assignees="dev", state="OPEN"):
    labels = f"type:{kind};key:AGILE" if kind else "key:AGILE"
    if stamps:
        labels += ";sprint:2026-08-31"
    return {
        "number": number, "issue_key": f"A-{number}", "title": f"issue {number}",
        "repository": "o/r", "state": state,
        "state_reason": "COMPLETED" if state == "CLOSED" else "",
        "labels": labels, "field_status": status, "field_sprint": sprint,
        "epic_number": None, "parent_key": "A-1" if parent_type else "",
        "parent_type": parent_type or "", "assignees": assignees,
        "sub_issues_total": 0, "sub_issues_done": 0,
        "started_at": "", "done_at": "",
    }


@pytest.fixture
def validate(monkeypatch, tool, capsys):
    def go(*rows):
        monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
        monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
            [{"title": "S2", "startDate": "2026-08-31", "duration": 14}], []))
        code = tool.cmd_validate(argparse.Namespace(owner="o", project=1,
                                                    _config={}, id=None))
        return code, capsys.readouterr().out
    return go


class TestAWellFormedTaskIsSilent:
    def test_it_produces_no_finding_at_all(self, tool, validate):
        code, out = validate(row())
        assert "no problems found" in out

    def test_and_exits_zero(self, tool, validate):
        """The whole point. Asserted directly rather than by counting findings."""
        code, _out = validate(row())
        assert code == 0

    def test_five_of_them_are_still_silent(self, tool, validate):
        """A story broken into five was five permanent findings."""
        _code, out = validate(*[row(n) for n in range(10, 15)])
        assert "no problems found" in out


class TestItRecognisesRatherThanStopsLooking:
    def test_an_unlabelled_sub_issue_is_still_reported(self, tool, validate):
        """It might be an unlabelled task; it might be a story in the wrong
        place. A machine may not infer a type, so it reports."""
        _code, out = validate(row(kind=None))
        assert NOTHING in out

    def test_a_task_under_an_epic_is_reported(self, tool, validate):
        _code, out = validate(row(parent_type="epic"))
        assert "task is not under a story" in out
        assert "under epic" in out

    def test_a_task_under_nothing_is_reported(self, tool, validate):
        _code, out = validate(row(parent_type=None))
        assert "task is not under a story" in out
        assert "under nothing" in out

    def test_that_finding_is_fatal(self, tool, validate):
        """Unlike an orphan story, this is nobody's deliberate choice and
        relabelling clears it."""
        code, _out = validate(row(parent_type="epic"))
        assert code == 1


class TestNoStoryLevelCheckFires:
    def test_it_is_not_asked_for_a_sprint_when_started(self, tool, validate):
        _code, out = validate(row(status="In Progress", sprint=""))
        assert "in no sprint" not in out

    def test_it_is_not_asked_for_a_sprint_label_when_closed(self, tool, validate):
        _code, out = validate(row(status="Done", state="CLOSED", stamps=False))
        assert "closed with no sprint" not in out

    def test_it_is_not_asked_for_an_assignee(self, tool, validate):
        """The board does not track a task, so who holds it is the story's
        answer rather than its own."""
        _code, out = validate(row(status="In Progress", assignees=""))
        assert "but unassigned" not in out

    def test_it_is_not_reported_as_a_story_without_an_epic(self, tool, validate):
        _code, out = validate(row())
        assert "story has no epic" not in out

    def test_a_task_parent_does_not_trip_the_promotion_check(self, tool, validate):
        """A story is not a container, so a started task does not demand that
        its story be started too."""
        _code, out = validate(row(status="In Progress"))
        assert "with a child In Progress" not in out


class TestAStoryIsStillHeldToEverything:
    def test_a_started_story_in_no_sprint_is_reported(self, tool, validate):
        _code, out = validate(row(kind="story", parent_type="epic",
                                  status="In Progress", sprint=""))
        assert "in no sprint" in out

    def test_a_started_story_with_nobody_on_it_is_reported(self, tool, validate):
        _code, out = validate(row(kind="story", parent_type="epic",
                                  status="In Progress", assignees=""))
        assert "but unassigned" in out

    def test_a_closed_story_with_no_label_is_reported(self, tool, validate):
        _code, out = validate(row(kind="story", parent_type="epic", status="Done",
                                  state="CLOSED", stamps=False))
        assert "closed with no sprint" in out
