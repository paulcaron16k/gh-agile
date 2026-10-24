"""Epic roll-up: an epic and its children have to agree, in both directions.

Ported from another team's markdown suite's
`test_an_epic_is_only_done_when_all_its_stories_are`, which was the one check of
its five with no equivalent here.

The two directions are not equally visible, which is why only one of them was
ever noticed. **An epic marked finished over open children is a claim visibly too
strong** -- the open children are right there under it. **An epic left open with
every child closed looks like nothing at all**: no field disagrees, no child is in
the wrong state, the epic simply persists. Another team using the tool reported three at
once as the single largest source of stale board state (#72), and this board had
one of its own -- `#26`, open with six of six closed -- found by running the
check the first time.

Offline: `rows` and `iterations` are stubbed, so nothing here reaches GitHub.
"""

from __future__ import annotations

import pytest

FINISHED = "epic is finished with a sub-issue still open"
STRANDED = "every sub-issue is closed but the epic is not"


def epic(*, total=3, closed=3, state="OPEN", status="Todo", labels="type:epic;key:AGILE",
         number=9, sprint_label=True):
    row = {
        "number": number, "title": "an epic", "repository": "o/r", "state": state,
        "state_reason": "COMPLETED" if state == "CLOSED" else "",
        "labels": labels + (";sprint:2026-08-31" if sprint_label else ""),
        "field_status": status, "field_sprint": "", "epic_number": None,
        "sub_issues_total": total, "sub_issues_done": closed,
        "started_at": "", "done_at": "",
        # Assigned, so the assignee check stays out of tests that are
        # not about it -- an In Progress row with nobody on it is now a
        # finding of its own.
        "assignees": "dev",
    }
    return row


@pytest.fixture
def validate(monkeypatch, tool, capsys):
    def go(*rows):
        import argparse
        monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
        monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
            [{"title": "Sprint 2", "startDate": "2026-08-31", "duration": 14}], []))
        args = argparse.Namespace(owner="o", project=1, _config={}, id=None)
        tool.cmd_validate(args)
        return capsys.readouterr().out
    return go


class TestAnEpicFinishedOverOpenChildren:
    def test_closed_with_a_child_still_open(self, tool, validate):
        assert FINISHED in validate(epic(total=3, closed=2, state="CLOSED", status="Done"))

    def test_status_done_while_still_open_counts_as_finished(self, tool, validate):
        """Either signal. The status is what the board shows; the state is what
        GitHub shows; an epic claiming to be finished by either is claiming it."""
        assert FINISHED in validate(epic(total=3, closed=2, state="OPEN", status="Done"))

    def test_finished_with_everything_closed_is_silent(self, tool, validate):
        assert FINISHED not in validate(
            epic(total=3, closed=3, state="CLOSED", status="Done"))


class TestAnEpicStrandedOverClosedChildren:
    def test_open_with_every_child_closed(self, tool, validate):
        """The direction nothing surfaced. `#26` on this board, six of six."""
        assert STRANDED in validate(epic(total=6, closed=6, state="OPEN", status="Todo"))

    def test_in_progress_counts_as_not_finished(self, tool, validate):
        assert STRANDED in validate(
            epic(total=2, closed=2, state="OPEN", status="In Progress"))

    def test_open_with_work_still_open_is_silent(self, tool, validate):
        assert STRANDED not in validate(epic(total=3, closed=2, state="OPEN"))

    def test_closed_with_everything_closed_is_silent(self, tool, validate):
        assert STRANDED not in validate(
            epic(total=3, closed=3, state="CLOSED", status="Done"))


class TestNeitherRuleFiresWhereItShouldNot:
    def test_an_epic_with_no_children_is_reported_once_and_by_the_older_rule(
            self, tool, validate):
        """`epic has no stories` already covers it. Two headings for one issue is
        noise, not a second finding -- and 0 == 0 would otherwise strand it."""
        out = validate(epic(total=0, closed=0, state="OPEN"))
        assert "epic has no stories" in out
        assert STRANDED not in out and FINISHED not in out

    def test_a_story_is_not_an_epic_even_with_sub_issues(self, tool, validate):
        out = validate(epic(total=2, closed=2, labels="type:story;key:AGILE",
                            state="OPEN", number=5))
        assert STRANDED not in out and FINISHED not in out

    def test_an_untyped_issue_is_left_to_the_type_rule(self, tool, validate):
        out = validate(epic(total=2, closed=2, labels="key:AGILE", state="OPEN"))
        assert "no type: label" in out
        assert STRANDED not in out


class TestTheReport:
    def test_it_names_the_epic_and_the_tally(self, tool, validate):
        out = validate(epic(total=6, closed=6, number=26, state="OPEN"))
        assert "#26" in out and "6/6 sub-issue(s) closed" in out

    def test_the_other_direction_names_the_tally_too(self, tool, validate):
        out = validate(epic(total=7, closed=6, state="CLOSED", status="Done"))
        assert "6/7 sub-issue(s) closed" in out

    def test_both_directions_can_be_reported_in_one_run(self, tool, validate):
        out = validate(epic(number=9, total=3, closed=2, state="CLOSED", status="Done"),
                       epic(number=26, total=6, closed=6, state="OPEN"))
        assert FINISHED in out and STRANDED in out


class TestWhatCompletedCounts:
    def test_a_child_closed_as_not_planned_still_counts_as_closed(self, tool, validate):
        """`subIssuesSummary.completed` is GitHub's name for the count of *closed*
        children, not of ones closed as completed -- measured on `#9`, which
        reported 6 of 7 with six closed, one of those `NOT_PLANNED`. That is the
        count this wants: an epic waits on what is still open, whatever reason the
        rest were closed for."""
        assert STRANDED in validate(epic(total=4, closed=4, state="OPEN"))
