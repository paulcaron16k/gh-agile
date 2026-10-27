"""`sprint carryover`: a sprint's unfinished work, moved to the next. AGILE-283.

Jira's "complete sprint" moves open issues forward. Here that was `issue edit
A B C --field Sprint --value ...`, item by item, documented nowhere. The command
writes each unfinished item's Sprint field and nothing else: never the iteration
configuration, which would clear every assignment on the board.
"""

from __future__ import annotations

import pytest

ACTIVE = [
    {"id": "IT_6", "title": "Sprint 6", "startDate": "2026-10-26", "duration": 14},
    {"id": "IT_7", "title": "Sprint 7", "startDate": "2026-11-09", "duration": 14},
]
COMPLETED = [{"id": "IT_5", "title": "Sprint 5", "startDate": "2026-10-12", "duration": 14}]


def item(number, status, *, sprint="2026-10-26", state="OPEN", labels=("type:story",),
         archived=False):
    values = [{"name": status, "field": {"name": "Status"}}] if status else []
    if sprint:
        values.append({"title": "x", "startDate": sprint, "field": {"name": "Sprint"}})
    return {"id": f"PVTI_{number}", "isArchived": archived,
            "fieldValues": {"nodes": values},
            "content": {"__typename": "Issue", "number": number, "title": f"item {number}",
                        "state": state, "labels": {"nodes": [{"name": n} for n in labels]}}}


BOARD = [
    item(1, "In Progress"),
    item(2, "Todo"),
    item(3, "Done", state="CLOSED"),
    item(4, "In Review", state="CLOSED"),
    item(5, "Todo", labels=("type:epic",)),
    item(6, "Todo", sprint="2026-11-09"),
    item(7, "Todo", sprint=None),
    item(8, "Todo", archived=True),
]


@pytest.fixture
def carry(monkeypatch, tool, capsys):
    def go(*argv, board=BOARD):
        written = []
        monkeypatch.setattr(tool, "iterations", lambda login, project: (ACTIVE, COMPLETED))
        monkeypatch.setattr(tool, "fetch_items", lambda login, project: ("P", board))
        monkeypatch.setattr(tool, "set_iteration",
                            lambda login, project, item_id, it: written.append((item_id, it)))
        args = tool.build_parser().parse_args(["sprint", "carryover", *argv])
        args.owner, args.project, args._config = "o", 1, {}
        code = tool.cmd_sprint(args)
        return code, written, capsys.readouterr().out
    return go


class TestWhatMoves:
    def test_open_unfinished_work_moves_to_the_next_sprint(self, carry):
        _code, written, out = carry()
        assert written == [("PVTI_1", "IT_7"), ("PVTI_2", "IT_7")]
        assert "2 carried from Sprint 6 to Sprint 7; 1 finished stay in Sprint 6" in out

    def test_finished_work_stays_where_it_was_finished(self, carry):
        _code, written, _out = carry()
        assert "PVTI_3" not in dict(written)

    def test_closed_but_not_done_is_named_not_moved(self, carry):
        """A wrap-up nobody did, not work to carry."""
        _code, written, out = carry()
        assert "PVTI_4" not in dict(written)
        assert "closed but not Done" in out and "#4" in out

    def test_a_container_is_named_for_unstamp(self, carry):
        _code, written, out = carry()
        assert "PVTI_5" not in dict(written) and "sprint unstamp" in out

    def test_other_sprints_unassigned_and_archived_items_are_untouched(self, carry):
        _code, written, _out = carry()
        assert not {"PVTI_6", "PVTI_7", "PVTI_8"} & set(dict(written))


class TestWhereTo:
    def test_to_names_the_destination(self, carry):
        """On the Monday after: from the sprint that ended into the current one."""
        board = [item(1, "Todo", sprint="2026-10-12")]
        _code, written, _out = carry("2026-10-12", "--to", "@current", board=board)
        assert written == [("PVTI_1", "IT_6")]

    def test_a_completed_destination_is_refused(self, carry):
        with pytest.raises(SystemExit) as refused:
            carry("--to", "Sprint 5")
        assert "completed" in str(refused.value)

    def test_the_same_sprint_is_refused(self, carry):
        with pytest.raises(SystemExit) as refused:
            carry("--to", "@current")
        assert "itself" in str(refused.value)

    def test_no_next_sprint_names_ensure_rather_than_creating_one(self, carry):
        """Creating a sprint is an iteration write; that is `ensure`'s, with its
        save-and-restore, never this command's."""
        with pytest.raises(SystemExit) as refused:
            carry("Sprint 7")
        assert "sprint ensure" in str(refused.value)


def test_dry_run_moves_nothing(carry):
    _code, written, out = carry("--dry-run")
    assert written == []
    assert "would carry #1" in out and "2 would carry from Sprint 6 to Sprint 7" in out


def test_it_never_writes_the_iteration_configuration(tool):
    """The whole design: one item's field at a time."""
    import inspect

    source = inspect.getsource(tool.cmd_sprint_carryover)
    for destructive in ("ensure_sprints", "updateProjectV2Field", "sprint_assignments",
                        "restore_assignments"):
        assert destructive not in source
