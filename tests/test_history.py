"""Parsing a timeline into `added_to_board_at`, `started_at` and `done_at`.

`history()` had no offline test, and it is the join that the whole export exists
for: GitHub keeps a history of `Status` and of nothing else, so every cycle time
and lead time in the Gold model comes through this function.

Its only cover was `make self-test`, which reads a real timeline and is therefore
timing-dependent — GitHub's timeline lags creation by a minute or more, and
observed lag has exceeded the self-test's 420-second budget. So the one guard on
this logic could fail for a reason that has nothing to do with the logic, and it
did: two runs in one afternoon, once on `added_to_board_at` and once on the
status transitions, both green on a re-run of identical code.

These tests fix the timeline as a fixture. The live test still earns its place —
it is the only thing that can catch GitHub changing what it emits — but it is no
longer the only thing standing between a parsing bug and an export full of nulls.
"""

from __future__ import annotations

import pytest


def event(kind: str, when: str, **extra) -> dict:
    return {"__typename": kind, "createdAt": when, **extra}


def status_change(when: str, status: str, previous: str | None = None) -> dict:
    return event("ProjectV2ItemStatusChangedEvent", when,
                 status=status, previousStatus=previous)


@pytest.fixture
def timeline(monkeypatch, tool):
    """Stub `graphql` so `history()` sees a fixed timeline and touches no network."""
    def install(events):
        monkeypatch.setattr(
            tool, "graphql",
            lambda *a, **k: {"data": {"node": {"timelineItems": {"nodes": events}}}},
        )
    return install


class TestHistory:
    def test_the_three_facts_are_extracted(self, tool, timeline):
        timeline([
            event("AddedToProjectV2Event", "2026-08-14T09:00:00Z"),
            status_change("2026-08-14T10:00:00Z", "In Progress", "Todo"),
            status_change("2026-08-14T12:00:00Z", "Done", "In Progress"),
        ])
        got = tool.history("PVTI_x")
        assert got["added_to_board_at"] == "2026-08-14T09:00:00Z"
        assert got["started_at"] == "2026-08-14T10:00:00Z"
        assert got["done_at"] == "2026-08-14T12:00:00Z"
        assert tool.seconds_between(got["started_at"], got["done_at"]) == 7200

    def test_the_first_start_wins_so_reopened_work_keeps_its_original_start(self, tool, timeline):
        timeline([
            status_change("2026-08-14T10:00:00Z", "In Progress", "Todo"),
            status_change("2026-08-14T11:00:00Z", "Blocked", "In Progress"),
            status_change("2026-08-14T13:00:00Z", "In Progress", "Blocked"),
        ])
        assert tool.history("x")["started_at"] == "2026-08-14T10:00:00Z"

    def test_the_last_done_wins_so_a_reopened_issue_reports_its_real_finish(self, tool, timeline):
        timeline([
            status_change("2026-08-14T10:00:00Z", "In Progress", "Todo"),
            status_change("2026-08-14T12:00:00Z", "Done", "In Progress"),
            status_change("2026-08-15T09:00:00Z", "In Progress", "Done"),
            status_change("2026-08-15T17:00:00Z", "Done", "In Progress"),
        ])
        assert tool.history("x")["done_at"] == "2026-08-15T17:00:00Z"

    def test_the_first_add_wins(self, tool, timeline):
        timeline([
            event("AddedToProjectV2Event", "2026-08-14T09:00:00Z"),
            event("RemovedFromProjectV2Event", "2026-08-14T09:30:00Z"),
            event("AddedToProjectV2Event", "2026-08-14T10:00:00Z"),
        ])
        assert tool.history("x")["added_to_board_at"] == "2026-08-14T09:00:00Z"

    @pytest.mark.parametrize("spelling", [
        "In Progress", "in progress", "IN PROGRESS", "In progress",
        # Accepted since statuses gained hyphen aliases; a board whose option was
        # renamed by hand should still register as the cycle start.
        "In-Progress", "in-progress", "In_Progress",
    ])
    def test_the_cycle_start_is_matched_regardless_of_case_or_separator(
        self, tool, timeline, spelling,
    ):
        """The bug that made every cycle time null was an exact-match comparison here.

        The transitions were in the timeline the whole time and the comparison
        silently missed them, so the export published a median of 0.0 as a
        measurement. No fixture would have caught it, which is why `self-test`
        exists — but this is the assertion that pins it cheaply.
        """
        timeline([status_change("2026-08-14T10:00:00Z", spelling, "Todo")])
        assert tool.history("x")["started_at"] == "2026-08-14T10:00:00Z"

    @pytest.mark.parametrize("spelling", ["Done", "done", "DONE"])
    def test_the_cycle_end_is_matched_regardless_of_case(self, tool, timeline, spelling):
        timeline([status_change("2026-08-14T12:00:00Z", spelling, "In Progress")])
        assert tool.history("x")["done_at"] == "2026-08-14T12:00:00Z"

    def test_an_empty_timeline_yields_nothing_rather_than_raising(self, tool, timeline):
        timeline([])
        got = tool.history("x")
        assert got["added_to_board_at"] is None
        assert got["started_at"] is None
        assert got["done_at"] is None
        assert got["_events"] == []

    def test_unrelated_events_do_not_set_the_cycle(self, tool, timeline):
        """An issue on the board that was never worked has no cycle time, not a zero."""
        timeline([
            event("AddedToProjectV2Event", "2026-08-14T09:00:00Z"),
            event("LabeledEvent", "2026-08-14T09:05:00Z", label={"name": "type:story"}),
            event("AssignedEvent", "2026-08-14T09:06:00Z", assignee={"login": "someone"}),
            event("ClosedEvent", "2026-08-14T18:00:00Z", stateReason="NOT_PLANNED"),
        ])
        got = tool.history("x")
        assert got["added_to_board_at"] == "2026-08-14T09:00:00Z"
        assert got["started_at"] is None
        assert got["done_at"] is None
        assert tool.seconds_between(got["started_at"], got["done_at"]) is None

    def test_a_status_that_is_neither_endpoint_is_ignored(self, tool, timeline):
        timeline([
            status_change("2026-08-14T10:00:00Z", "Todo", None),
            status_change("2026-08-14T11:00:00Z", "Blocked", "Todo"),
            status_change("2026-08-14T12:00:00Z", "In Review", "Blocked"),
        ])
        got = tool.history("x")
        assert got["started_at"] is None
        assert got["done_at"] is None

    def test_the_raw_events_come_back_for_the_event_grain(self, tool, timeline):
        """The timeline query is the expensive part of an export; it is read once."""
        events = [event("AddedToProjectV2Event", "2026-08-14T09:00:00Z")]
        timeline(events)
        assert tool.history("x")["_events"] == events

    def test_a_missing_node_does_not_raise(self, tool, monkeypatch):
        """A deleted or unreadable issue answers with a null node."""
        monkeypatch.setattr(tool, "graphql", lambda *a, **k: {"data": {"node": None}})
        got = tool.history("x")
        assert got["started_at"] is None and got["_events"] == []
