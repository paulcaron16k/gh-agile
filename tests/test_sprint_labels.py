"""Which sprint a `sprint:` label may claim, and which it may not.

The label means **the sprint this was worked in**. Two ways that went wrong, both
measured on this project's own board:

An issue taken straight from `Todo` to `Done` never passes through the one
transition that fills the `Sprint` field, so `record_sprint_label` had nothing to
read and stamped nothing -- and `validate` then reported the state the tool had
just created, recommending the `sprint backfill` that recovers the same answer
from a board-wide read a moment later. #72, closed the day it was filed.

Then the repair asserted something false. #72 was a duplicate closed as
`NOT_PLANNED`, worked in no sprint at all, and `sprint:2026-08-31` said it was
worked in Sprint 2. `validate` never consulted `state_reason`, and neither did
`backfill`.

So: derive the label from the moment when the field is empty, and never derive
one for an issue that was abandoned. `validate` stops asking and `backfill` stops
answering -- both, because a repair pass that re-asserts what the validator gave
up demanding is the same bug wearing the other hat.

Offline: every `gh` call is captured.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

#: Two sprints with a deliberate gap between them: 2026-09-14..27 is nobody's.
ITERATIONS = [
    {"title": "Sprint 2", "startDate": "2026-08-31", "duration": 14},
    {"title": "Sprint 4", "startDate": "2026-09-28", "duration": 14},
]


def date(text):
    return dt.date.fromisoformat(text)


class TestSprintSpans:
    def test_a_span_covers_its_whole_window_inclusive(self, tool):
        spans = tool.sprint_spans(ITERATIONS)
        assert tool.sprint_covering(spans, date("2026-08-31"))[2] == "Sprint 2"
        assert tool.sprint_covering(spans, date("2026-09-13"))[2] == "Sprint 2"

    def test_the_day_after_belongs_to_no_sprint(self, tool):
        """A 14-day sprint from the 31st ends on the 13th, not the 14th."""
        spans = tool.sprint_spans(ITERATIONS)
        assert tool.sprint_covering(spans, date("2026-09-14")) is None

    def test_a_gap_is_a_gap_and_nothing_is_invented(self, tool):
        """Sprints are created on demand, so a quiet month has none."""
        spans = tool.sprint_spans(ITERATIONS)
        assert tool.sprint_covering(spans, date("2026-09-20")) is None

    def test_spans_come_back_in_date_order(self, tool):
        spans = tool.sprint_spans(list(reversed(ITERATIONS)))
        assert [sp[2] for sp in spans] == ["Sprint 2", "Sprint 4"]


class TestAbandoning:
    """`--not-planned` alone changes nothing: `cmd_move` reads it only inside
    `if args.close`, so on its own it is an intention that never reaches GitHub
    and must not withhold a label."""

    @pytest.mark.parametrize("not_planned,close,want", [
        (True, True, True),
        (True, False, False),
        (False, True, False),
        (False, False, False),
    ])
    def test_both_flags_are_needed(self, tool, not_planned, close, want):
        import argparse
        args = argparse.Namespace(not_planned=not_planned, close=close)
        assert tool.abandoning(args) is want

    def test_a_namespace_without_the_flags_is_not_abandoning(self, tool):
        import argparse
        assert tool.abandoning(argparse.Namespace()) is False


@pytest.fixture
def label_run(monkeypatch, tool):
    """`record_sprint_label` with the board stubbed, capturing `gh`."""
    calls = []
    state = {"assigned": None, "state_reason": None, "labels": [], "today": "2026-09-07"}

    def fake_gh(args, **kwargs):
        calls.append(args)
        if args[:2] == ["issue", "view"]:
            return json.dumps({"labels": [{"name": n} for n in state["labels"]],
                               "stateReason": state["state_reason"]})
        return ""

    monkeypatch.setattr(tool, "gh", fake_gh)
    monkeypatch.setattr(tool, "iterations", lambda *a, **k: (ITERATIONS, []))
    monkeypatch.setattr(tool, "sprint_assignments",
                        lambda *a, **k: {"PVTI_1": state["assigned"]})
    monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
    monkeypatch.setattr(tool, "today_utc", lambda: date(state["today"]))

    def go(**overrides):
        import argparse
        state.update({k: v for k, v in overrides.items() if k in state})
        args = argparse.Namespace(owner="o", project=1, _config={"sprint": {}})
        calls.clear()
        return tool.record_sprint_label(
            args, "o/r", 7, "PVTI_1", not_planned=overrides.get("not_planned", False))

    go.calls = calls
    go.added = lambda: [c[c.index("--add-label") + 1] for c in calls
                        if c[:2] == ["issue", "edit"] and "--add-label" in c]
    return go


class TestTheFieldStillWins:
    def test_a_field_value_is_used_as_before(self, tool, label_run):
        assert label_run(assigned="Sprint 2") == "sprint:2026-08-31"
        assert label_run.added() == ["sprint:2026-08-31"]

    def test_a_label_already_present_is_not_written_twice(self, tool, label_run):
        assert label_run(assigned="Sprint 2", labels=["sprint:2026-08-31"]) is None
        assert label_run.added() == []

    def test_a_field_backed_label_survives_an_abandoned_close(self, tool, label_run):
        """Worked in Sprint 2 and then given up on really was worked in Sprint 2.
        Only a *derived* label has to ask how the issue was closed."""
        assert label_run(assigned="Sprint 2", not_planned=True) == "sprint:2026-08-31"

    def test_nor_does_an_earlier_abandonment_erase_it(self, tool, label_run):
        assert label_run(assigned="Sprint 2",
                         state_reason="NOT_PLANNED") == "sprint:2026-08-31"


class TestDerivingFromTheMoment:
    def test_an_empty_field_derives_the_covering_sprint(self, tool, label_run):
        """Todo straight to Done: the field was never filled, and the tool had
        the moment in hand. It used to stamp nothing and let `validate` complain."""
        assert label_run(assigned=None, today="2026-09-07") == "sprint:2026-08-31"

    def test_the_derivation_agrees_with_backfill(self, tool, label_run):
        """Same `sprint_covering`, so the live stamp and the repair pass cannot
        disagree -- which is worse than either being wrong on its own."""
        spans = tool.sprint_spans(ITERATIONS)
        assert label_run(assigned=None, today="2026-09-07") == \
            f"sprint:{tool.sprint_covering(spans, date('2026-09-07'))[0].isoformat()}"

    def test_a_moment_in_no_sprint_stamps_nothing(self, tool, label_run):
        assert label_run(assigned=None, today="2026-09-20") is None
        assert label_run.added() == []

    def test_nothing_is_read_when_there_is_nothing_to_stamp(self, tool, label_run):
        """No field and no covering sprint: the old zero-call path stays free."""
        label_run(assigned=None, today="2026-09-20")
        assert label_run.calls == []


class TestAnAbandonedIssueGetsNoDerivedLabel:
    def test_the_flag_stops_the_derivation(self, tool, label_run):
        assert label_run(assigned=None, not_planned=True) is None
        assert label_run.added() == []

    def test_and_costs_no_call_at_all(self, tool, label_run):
        label_run(assigned=None, not_planned=True)
        assert label_run.calls == []

    def test_an_earlier_abandonment_stops_it_too(self, tool, label_run):
        """Closed as not planned in the web UI, then moved to Done here. The flag
        knows nothing about that close; `stateReason` does."""
        assert label_run(assigned=None, state_reason="NOT_PLANNED") is None
        assert label_run.added() == []

    def test_a_completed_close_is_unaffected(self, tool, label_run):
        assert label_run(assigned=None, state_reason="COMPLETED") == "sprint:2026-08-31"


def issue_row(**overrides):
    """A `rows()` result, trimmed to what the sprint checks read."""
    row = {
        "number": 7, "title": "a title", "repository": "o/r", "state": "CLOSED",
        "state_reason": "COMPLETED", "labels": "type:story;key:AGILE",
        "field_status": "Done", "field_sprint": "", "epic_number": 1,
        "sub_issues_total": 0, "started_at": "", "done_at": "2026-09-07T13:09:00Z",
    }
    row.update(overrides)
    return row


@pytest.fixture
def validate(monkeypatch, tool, capsys):
    def go(*rows):
        import argparse
        monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
        monkeypatch.setattr(tool, "iterations", lambda *a, **k: (ITERATIONS, []))
        args = argparse.Namespace(owner="o", project=1, _config={}, id=None)
        tool.cmd_validate(args)
        return capsys.readouterr().out
    return go


class TestValidateDoesNotAskAnAbandonedIssueForASprint:
    RULE = "closed with no sprint: label"

    def test_a_completed_close_with_no_label_is_still_reported(self, tool, validate):
        """The existing check, which is what `sprint backfill` exists for."""
        assert self.RULE in validate(issue_row(state_reason="COMPLETED"))

    def test_an_abandoned_close_with_no_label_is_not(self, tool, validate):
        """#72: a duplicate closed on sight, worked in no sprint. Demanding a
        label here is what put a false `sprint:2026-08-31` on it."""
        assert self.RULE not in validate(issue_row(state_reason="NOT_PLANNED"))

    def test_a_close_with_no_reason_at_all_is_still_reported(self, tool, validate):
        """Absent is not abandoned. An older issue, or one closed by a route that
        recorded nothing, is the case the original check was written for."""
        assert self.RULE in validate(issue_row(state_reason=""))

    def test_an_abandoned_issue_that_does_carry_a_label_is_fine_either_way(self, tool, validate):
        out = validate(issue_row(state_reason="NOT_PLANNED",
                                 labels="type:story;key:AGILE;sprint:2026-08-31"))
        assert self.RULE not in out


@pytest.fixture
def backfill(monkeypatch, tool, capsys):
    def go(*rows, dry_run=True):
        import argparse
        monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
        monkeypatch.setattr(tool, "iterations", lambda *a, **k: (ITERATIONS, []))
        monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
        monkeypatch.setattr(tool, "gh", lambda *a, **k: "")
        args = argparse.Namespace(owner="o", project=1, _config={},
                                  source="timeline", dry_run=dry_run)
        tool.backfill_sprint_labels(args)
        return capsys.readouterr().out
    return go


class TestBackfillLearnsTheSameRule:
    """A `validate` that stops asking without a `backfill` that stops answering
    gives a repair pass that re-asserts the false label -- and `backfill` is
    exactly what somebody runs *because* `validate` complained."""

    def test_an_abandoned_close_is_not_stamped(self, tool, backfill):
        out = backfill(issue_row(state_reason="NOT_PLANNED",
                                 done_at="2026-09-07T13:09:00Z"))
        assert "sprint:" not in out           # no label line, only the summary
        assert "would stamp 0," in out

    def test_a_completed_close_still_is(self, tool, backfill):
        out = backfill(issue_row(state_reason="COMPLETED",
                                 done_at="2026-09-07T13:09:00Z"))
        assert "sprint:2026-08-31" in out

    def test_an_abandoned_issue_keeps_the_sprint_it_was_worked_in(self, tool, backfill):
        """Started in Sprint 2 and then given up on. The start moment is a record
        of work that really happened; only the close asserts something it did not."""
        out = backfill(issue_row(state_reason="NOT_PLANNED",
                                 started_at="2026-09-02T09:00:00Z",
                                 done_at="2026-10-01T09:00:00Z"))
        assert "sprint:2026-08-31" in out
        assert "sprint:2026-09-28" not in out
