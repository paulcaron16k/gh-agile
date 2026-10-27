"""Starting work keeps `ahead` sprints beyond today. AGILE-288.

`issue move N "In Progress"` ran `ensure_sprints` only when no sprint was
active at all, and a future sprint counts as active. So once one existed
nothing topped up: project 4 went from `0005` current with two ahead to `0007`
current with none, while its profile said `ahead: 2`. The move now tops up
whenever the profile's requirement is not met, and only then -- creating a
sprint is an iteration write, which costs a save-and-restore of every
assignment on the board.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json

import pytest

TODAY = dt.date(2026, 10, 27)


def sprint(start, title=None):
    return {"id": f"IT_{start}", "title": title or f"S {start}", "startDate": start,
            "duration": 14}


CURRENT = sprint("2026-10-26")
NEXT = sprint("2026-11-09")
AFTER = sprint("2026-11-23")


@pytest.fixture
def move(monkeypatch, tool, capsys):
    """`cmd_move` against a board whose active sprints are `before`, and
    `after` once `ensure_sprints` has run."""
    def run(before, after=None, *, status="In Progress", labels=("type:story",),
            config=None, has_sprint=None):
        record = argparse.Namespace(ensured=[], order=[], sprint_writes=[])
        state = {"active": before}

        def ensure(login, project, cfg, ahead):
            record.ensured.append(ahead)
            record.order.append("ensure")
            state["active"] = after if after is not None else before

        def fake_gh(args, **kwargs):
            if args[:2] == ["issue", "view"] and "labels" in args:
                return json.dumps({"labels": [{"name": n} for n in labels]})
            if args[:2] == ["issue", "view"]:
                return json.dumps({"assignees": [{"login": "me"}]})
            return ""

        def set_field(login, project, item, name, value):
            if name == "Sprint":
                record.sprint_writes.append(value)
                record.order.append("sprint")

        monkeypatch.setattr(tool, "today_utc", lambda: TODAY)
        monkeypatch.setattr(tool, "gh", fake_gh)
        monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 7))
        monkeypatch.setattr(tool, "board_item_for", lambda *a, **k: {"id": "PVTI_7"})
        monkeypatch.setattr(tool, "set_field", set_field)
        monkeypatch.setattr(tool, "item_sprint", lambda *a, **k: has_sprint)
        monkeypatch.setattr(tool, "iterations", lambda *a, **k: (state["active"], []))
        monkeypatch.setattr(tool, "ensure_sprints", ensure)
        monkeypatch.setattr(tool, "record_sprint_label", lambda *a, **k: None)
        monkeypatch.setattr(tool, "claim_issue", lambda *a, **k: None)
        monkeypatch.setattr(tool, "promote_parents", lambda *a, **k: None)
        args = argparse.Namespace(
            issue="7", repo="o/r", owner="o", project=1, close=False, not_planned=False,
            evidence=None, evidence_file=None, add_assignee=None, status=status,
            _config=config if config is not None else {"sprint": {"template": "2-week"}})
        tool.cmd_move(args)
        record.out = capsys.readouterr().out
        return record
    return run


class TestWhenItTopsUp:
    def test_one_ahead_of_two_tops_up(self, move):
        """The case #288 found: active sprints exist, too few lie ahead."""
        run = move([CURRENT, NEXT], [CURRENT, NEXT, AFTER])
        assert run.ensured == [2]
        assert "fewer than 2 sprint(s) ahead" in run.out

    def test_none_ahead_tops_up(self, move):
        assert move([CURRENT]).ensured == [2]

    def test_no_active_sprint_still_creates_one(self, move):
        run = move([], [CURRENT, NEXT, AFTER])
        assert run.ensured == [2] and run.sprint_writes == ["@current"]
        assert "creating the one that covers today" in run.out

    def test_an_item_already_in_a_sprint_still_tops_up(self, move):
        """The board's shortfall is not the item's; only its field is left alone."""
        run = move([CURRENT], has_sprint="S")
        assert run.ensured == [2] and run.sprint_writes == []


class TestWhenItDoesNot:
    def test_enough_ahead_writes_no_sprint(self, move):
        """The ordinary case pays one field read and no iteration write."""
        run = move([CURRENT, NEXT, AFTER])
        assert run.ensured == [] and run.sprint_writes == ["@current"]

    def test_autocreate_off(self, move):
        run = move([CURRENT], config={"sprint": {"template": "none", "autocreate": False}})
        assert run.ensured == []

    @pytest.mark.parametrize("status", ["Todo", "In Review", "Blocked"])
    def test_other_statuses(self, move, status):
        assert move([CURRENT], status=status).ensured == []

    def test_an_epic(self, move):
        assert move([CURRENT], labels=("type:epic",)).ensured == []


def test_ensure_runs_before_the_sprint_is_set(move):
    """Ensure re-mints every iteration id; a Sprint set before it is cleared."""
    assert move([CURRENT]).order == ["ensure", "sprint"]


class TestSprintsShort:
    @pytest.fixture(autouse=True)
    def today(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "today_utc", lambda: TODAY)

    def test_nothing_active(self, tool):
        assert tool.sprints_short([], 0)

    def test_today_uncovered_though_sprints_lie_ahead(self, tool):
        """A series that starts after today: ensure places the covering one."""
        assert tool.sprints_short([NEXT, AFTER], 2)

    @pytest.mark.parametrize("active,ahead,short", [
        ([CURRENT], 0, False),
        ([CURRENT], 1, True),
        ([CURRENT, NEXT], 1, False),
        ([CURRENT, NEXT], 2, True),
        ([CURRENT, NEXT, AFTER], 2, False),
    ])
    def test_counts_what_lies_beyond_today(self, tool, active, ahead, short):
        assert tool.sprints_short(active, ahead) is short
