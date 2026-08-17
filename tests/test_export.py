"""Export identity and durations.

`event_hash` is the primary key every downstream consumer dedupes on, so a
collision is silent data loss rather than a visible error. It happened: a real
export produced 187 event rows carrying 181 distinct hashes.
"""

from __future__ import annotations

import pytest

ISSUE = {"id": "I_abc", "number": 15, "issue_key": "AGILE-15"}


def status_event(occurred: str, *, actor: str, prior: str, now: str) -> dict:
    return {
        "__typename": "ProjectV2ItemStatusChangedEvent",
        "createdAt": occurred,
        "actor": {"login": actor},
        "previousStatus": prior,
        "status": now,
    }


class TestEventHash:
    def test_two_transitions_in_the_same_second_do_not_collide(self, tool):
        """The regression. GitHub timestamps to the second, and a move to In
        Progress followed straight away by Done is ordinary; hashing only
        issue|kind|timestamp made them one row and dropped the other."""
        same = "2026-08-14T17:45:31Z"
        rows = tool.event_rows(ISSUE, [
            status_event(same, actor="alice", prior="Todo", now="In Progress"),
            status_event(same, actor="alice", prior="In Progress", now="Done"),
        ], "owner/1")
        assert len({r["event_hash"] for r in rows}) == 2

    def test_same_second_different_actor_does_not_collide(self, tool):
        same = "2026-08-14T17:45:31Z"
        rows = tool.event_rows(ISSUE, [
            status_event(same, actor="alice", prior="Todo", now="Done"),
            status_event(same, actor="bob", prior="Todo", now="Done"),
        ], "owner/1")
        assert len({r["event_hash"] for r in rows}) == 2

    def test_identical_events_share_a_hash(self, tool):
        """Stability is the point: an overlapping incremental run re-exports the
        same event and it must overwrite itself, not duplicate."""
        event = status_event("2026-08-14T17:45:31Z", actor="a", prior="Todo", now="Done")
        first = tool.event_rows(ISSUE, [event], "owner/1")
        second = tool.event_rows(ISSUE, [event], "owner/1")
        assert first[0]["event_hash"] == second[0]["event_hash"]

    def test_hash_is_stable_across_projects_but_not_issues(self, tool):
        event = status_event("2026-08-14T17:45:31Z", actor="a", prior="Todo", now="Done")
        mine = tool.event_rows(ISSUE, [event], "owner/1")[0]["event_hash"]
        other = tool.event_rows({**ISSUE, "id": "I_zzz"}, [event], "owner/1")[0]["event_hash"]
        assert mine != other

    def test_events_without_a_timestamp_are_dropped(self, tool):
        rows = tool.event_rows(ISSUE, [{"__typename": "X", "createdAt": None}], "owner/1")
        assert rows == []

    def test_state_changed_is_false_when_status_is_unchanged(self, tool):
        rows = tool.event_rows(ISSUE, [
            status_event("2026-08-14T17:45:31Z", actor="a", prior="Done", now="Done")
        ], "owner/1")
        assert rows[0]["state_changed"] is False


class TestDurations:
    """Every duration is seconds. No `_days`, no `_hours`, no exceptions."""

    def test_seconds_between(self, tool):
        assert tool.seconds_between("2026-08-14T00:00:00Z", "2026-08-14T00:01:30Z") == 90

    def test_a_whole_day(self, tool):
        assert tool.seconds_between("2026-08-14T00:00:00Z", "2026-08-15T00:00:00Z") == 86400

    def test_returns_an_integer_not_a_float(self, tool):
        """Seconds never need a fractional part, and a float invites a consumer
        to guess the unit from the magnitude."""
        assert isinstance(tool.seconds_between("2026-08-14T00:00:00Z",
                                               "2026-08-14T00:00:01Z"), int)

    def test_short_work_is_not_rounded_away(self, tool):
        """In days this was 0.0, indistinguishable from no elapsed time at all,
        and a median of 0.0 was reported as a measurement."""
        assert tool.seconds_between("2026-08-14T10:00:00Z", "2026-08-14T10:20:00Z") == 1200

    @pytest.mark.parametrize("start,end", [
        (None, "2026-08-14T00:00:00Z"), ("2026-08-14T00:00:00Z", None), (None, None), ("", ""),
    ])
    def test_missing_end_is_none_not_zero(self, tool, start, end):
        assert tool.seconds_between(start, end) is None

    def test_no_emitted_column_carries_a_unit_suffix(self, tool):
        """A name like `cycle_time_days` puts the unit in the schema, where it
        rots the moment the unit changes and every consumer keeps dividing by
        the old one. Asserted on the columns actually emitted, not on the source
        text -- the first version of this test scanned the source and failed on
        a *comment* about another system's schema."""
        rows = tool.event_rows(ISSUE, [
            status_event("2026-08-14T17:45:31Z", actor="a", prior="Todo", now="Done")
        ], "owner/1")
        emitted = set(rows[0])
        assert emitted, "no columns to check"
        for column in emitted:
            assert not column.endswith(("_days", "_hours", "_minutes", "_ms")), column

    def test_the_days_helper_is_gone(self, tool):
        """Not merely unused: still present, it is the obvious thing to reach
        for when adding the next duration."""
        assert hasattr(tool, "seconds_between")
        assert not hasattr(tool, "days_between")


class TestFileStamp:
    def test_iso_basic_has_no_colons(self, tool):
        """Colons are illegal in filenames on Windows and awkward everywhere."""
        stamped = tool.file_stamp("2026-08-14T18:48:50Z")
        assert ":" not in stamped and stamped == "20260814T184850Z"

    def test_stamps_sort_chronologically_as_strings(self, tool):
        stamps = [tool.file_stamp(f"2026-08-{d:02d}T00:00:00Z") for d in (9, 10, 14)]
        assert stamps == sorted(stamps)
