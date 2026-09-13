"""Closing an issue as *not planned*, on a project that would rather it were done.

`move --status Done --not-planned --close` recorded `COMPLETED`. Measured on the
sandbox 2026-09-13, one probe at a time:

- Setting Status to `Done` and issuing **no close at all** left the issue CLOSED
  as `COMPLETED` one second later. The project carries a built-in *auto-close
  when Status is Done* workflow, and GitHub attributes that close to the
  **project owner** rather than to `github-project-automation` -- which is why
  the timeline looked like ours and the mechanism was mis-read at first.
- `gh issue close --reason` on an already-closed issue prints `already closed`,
  changes nothing, and **exits 0**. So arriving second discarded `--not-planned`
  and still reported success.
- The reason cannot be repaired afterwards. There is no second chance.
- Closing *first* and setting Status after keeps `NOT_PLANNED`, on the same
  project that loses it the other way round.

Hence two things: the close goes before the Status write, and the reason GitHub
recorded is read back rather than assumed. `abandoned` and `completed` are not
interchangeable -- `validate` and `sprint backfill` both decide whether to demand
a `sprint:` label from `state_reason`, so a reason downgraded to `COMPLETED` puts
a false *worked in this sprint* label on an issue nobody worked.

Offline: every `gh` call is captured.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def closing(monkeypatch, tool, capsys):
    """`close_issue` with `gh` stubbed, and the reason GitHub 'recorded' settable."""
    calls = []
    state = {"recorded": None}

    def fake_gh(args, **kwargs):
        calls.append(args)
        if args[:2] == ["issue", "view"]:
            return json.dumps({"state": "CLOSED", "stateReason": state["recorded"]})
        return ""

    monkeypatch.setattr(tool, "gh", fake_gh)

    def go(*, not_planned, recorded):
        state["recorded"] = recorded
        calls.clear()
        tool.close_issue("o/r", 7, not_planned=not_planned)
        return calls, capsys.readouterr()
    return go


class TestTheReasonItAsksFor:
    def test_not_planned(self, tool, closing):
        calls, _ = closing(not_planned=True, recorded="NOT_PLANNED")
        assert calls[0] == ["issue", "close", "7", "--repo", "o/r",
                            "--reason", "not planned"]

    def test_completed(self, tool, closing):
        calls, _ = closing(not_planned=False, recorded="COMPLETED")
        assert calls[0][-1] == "completed"

    def test_it_says_which(self, tool, closing):
        _, out = closing(not_planned=True, recorded="NOT_PLANNED")
        assert "closed as not planned" in out.out and out.err == ""


class TestItChecksWhatGitHubRecorded:
    def test_a_downgraded_reason_is_reported(self, tool, closing):
        """The exit code cannot be trusted: `gh` exits 0 for a close that changed
        nothing, so a discarded `--not-planned` looked like a successful one."""
        _, out = closing(not_planned=True, recorded="COMPLETED")
        assert "COMPLETED" in out.err and "NOT_PLANNED" in out.err
        assert "closed as not planned" not in out.out

    def test_it_names_the_likely_cause_and_the_way_out(self, tool, closing):
        _, out = closing(not_planned=True, recorded="COMPLETED")
        assert "Status=Done" in out.err
        assert "Reopen" in out.err

    def test_no_reason_at_all_is_reported_too(self, tool, closing):
        _, out = closing(not_planned=True, recorded=None)
        assert "no reason" in out.err

    def test_it_is_not_fatal(self, tool, closing):
        """The issue *is* closed and the status is about to be set; raising here
        would leave the caller worse off than telling them."""
        closing(not_planned=True, recorded="COMPLETED")   # no SystemExit

    def test_a_completed_close_that_records_completed_is_silent(self, tool, closing):
        _, out = closing(not_planned=False, recorded="COMPLETED")
        assert out.err == ""


class TestTheOrderIsTheFix:
    @pytest.fixture
    def move(self, monkeypatch, tool):
        """`cmd_move`, recording the sequence of writes that reach GitHub."""
        order = []

        def fake_gh(args, **kwargs):
            if args[:2] == ["issue", "close"]:
                order.append("close")
            if args[:2] == ["issue", "view"]:
                return json.dumps({"state": "CLOSED", "stateReason": "NOT_PLANNED",
                                   "body": "## Evidence\nwhy\n", "assignees": []})
            return ""

        monkeypatch.setattr(tool, "gh", fake_gh)
        monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 7))
        monkeypatch.setattr(tool, "board_item_for", lambda *a, **k: {"id": "PVTI_7"})
        monkeypatch.setattr(tool, "sprint_assignments", lambda *a, **k: {"PVTI_7": "s"})
        monkeypatch.setattr(tool, "record_sprint_label", lambda *a, **k: None)
        monkeypatch.setattr(tool, "set_field",
                            lambda login, project, item, field, value:
                                order.append(f"field:{field}"))

        def go(**flags):
            import argparse
            args = argparse.Namespace(
                issue="7", repo="o/r", owner="o", project=1, status="Done",
                close=False, not_planned=False, evidence="done", evidence_file=None,
                add_assignee=None, _config={"sprint": {"cadence_days": 14}})
            for name, value in flags.items():
                setattr(args, name, value)
            order.clear()
            tool.cmd_move(args)
            return order
        return go

    def test_the_close_precedes_the_status_write(self, tool, move):
        """A project workflow that closes on Status=Done gets there first
        otherwise, and there is no repair afterwards."""
        order = move(close=True, not_planned=True)
        assert order.index("close") < order.index("field:Status")

    def test_the_status_is_still_written(self, tool, move):
        assert "field:Status" in move(close=True, not_planned=True)

    def test_nothing_closes_without_the_flag(self, tool, move):
        assert "close" not in move(close=False)
