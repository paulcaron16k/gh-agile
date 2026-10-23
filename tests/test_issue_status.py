"""`gh agile issue status`: what is yours in the current sprint. AGILE-205.

`gh issue status` answers *what needs me*. The agile form is the stand-up
question: in this sprint, what am I holding, what is waiting on review, and
what is in it with nobody holding it. Under `issue`, as `gh issue status` and
`gh pr status` sit under their noun.

Offline: the board, the iterations and the caller are stubbed.
"""

from __future__ import annotations

import json

import pytest

SPRINT = {"title": "0006 W42-2026", "startDate": "2026-10-12", "duration": 14}


def item(number, status, assignees=(), *, sprint="0006 W42-2026", state="OPEN",
         title=None, archived=False):
    values = [{"name": status, "field": {"name": "Status"}}] if status else []
    if sprint:
        values.append({"title": sprint, "field": {"name": "Sprint"}})
    return {
        "isArchived": archived,
        "fieldValues": {"nodes": values},
        "content": {
            "__typename": "Issue", "number": number, "state": state,
            "title": title or f"AGILE-{number} Story: work {number}",
            "url": f"https://github.com/o/r/issues/{number}",
            "repository": {"nameWithOwner": "o/r"},
            "labels": {"nodes": [{"name": "key:AGILE"}, {"name": "type:story"}]},
            "assignees": {"nodes": [{"login": a} for a in assignees]},
        },
    }


@pytest.fixture
def status(tool, monkeypatch, capsys):
    def go(items, *argv, active=(SPRINT,), me="me"):
        reads = {"board": [], "user": 0}
        monkeypatch.setattr(tool, "iterations", lambda *a: (list(active), []))
        monkeypatch.setattr(tool, "caller_login",
                            lambda: reads.__setitem__("user", reads["user"] + 1) or me)
        monkeypatch.setattr(tool, "fetch_items",
                            lambda owner, project: reads["board"].append(owner) or ("t", items))
        args = tool.build_parser().parse_args(["issue", "status", *argv])
        args.owner, args.project = "boardowner", 4
        args._config = {"keys": [{"key": "AGILE", "repo": "o/r"}]}
        go.reads = reads
        tool.cmd_issue_status(args)
        return capsys.readouterr().out
    return go


class TestItIsGhsShape:
    def test_it_is_a_general_command_under_issue(self, tool):
        args = tool.build_parser().parse_args(["issue", "status"])
        assert args.func is tool.cmd_issue_status

    def test_there_is_no_top_level_status(self, tool):
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args(["status"])


class TestTheSections:
    def test_yours_are_grouped_by_status_in_workflow_order(self, status):
        out = status([item(1, "In Review", ["me"]), item(2, "In Progress", ["me"]),
                      item(3, "Todo", ["me"])])
        mine = out.split("Assigned to you")[1].split("In Review, not yours")[0]
        assert mine.index("Todo") < mine.index("In Progress") < mine.index("In Review")
        assert "AGILE-2  work 2" in mine

    def test_in_review_and_not_yours_names_who_holds_it(self, status):
        out = status([item(4, "In Review", ["alice"])])
        assert "AGILE-4  work 4  (alice)" in out.split("In Review, not yours")[1]

    def test_unassigned_work_in_the_sprint(self, status):
        out = status([item(5, "Todo")])
        assert "AGILE-5" in out.split("nobody holds it")[1]

    def test_somebody_elses_work_in_progress_is_not_your_business(self, status):
        out = status([item(6, "In Progress", ["bob"])])
        assert "AGILE-6" not in out

    def test_done_and_unassigned_is_not_a_gap(self, status):
        out = status([item(7, "Done")])
        assert "AGILE-7" not in out

    def test_only_the_current_sprint(self, status):
        out = status([item(8, "Todo", ["me"], sprint="0007 W44-2026"),
                      item(9, "Todo", ["me"], sprint=None)])
        assert "AGILE-8" not in out and "AGILE-9" not in out

    def test_closed_and_archived_items_are_left_out(self, status):
        out = status([item(10, "Done", ["me"], state="CLOSED"),
                      item(11, "Todo", ["me"], archived=True)])
        assert "AGILE-10" not in out and "AGILE-11" not in out

    def test_login_case_does_not_matter(self, status):
        out = status([item(12, "Todo", ["Me"])])
        assert "AGILE-12" in out.split("Assigned to you")[1].split("In Review")[0]


class TestEmptySectionsAreNamed:
    def test_every_section_says_it_is_empty(self, tool, status):
        out = status([])
        for _name, title, empty in tool.STATUS_SECTIONS:
            assert title in out and empty in out

    def test_as_gh_words_it(self, status):
        assert "There are no issues assigned to you" in status([])


class TestJson:
    def test_the_same_sections_as_json(self, status):
        shown = json.loads(status([item(1, "Todo", ["me"]), item(2, "In Review", ["a"]),
                                   item(3, "Todo")], "--json", "sprint,me,yours,review,unheld"))
        assert [r["number"] for r in shown["yours"]] == [1]
        assert [r["number"] for r in shown["review"]] == [2]
        assert [r["number"] for r in shown["unheld"]] == [3]
        assert shown["sprint"]["title"] == "0006 W42-2026" and shown["me"] == "me"

    def test_empty_is_an_empty_list_not_absent(self, status):
        shown = json.loads(status([], "--json", "yours,review,unheld"))
        assert shown["yours"] == shown["review"] == shown["unheld"] == []


class TestWhatItReads:
    def test_one_board_read(self, status):
        status([item(1, "Todo", ["me"])])
        assert len(status.reads["board"]) == 1

    def test_the_board_is_the_profiles_owners_not_the_callers(self, status):
        """A teammate with project read access reads the owner's board."""
        status([], me="teammate")
        assert status.reads["board"] == ["boardowner"]

    def test_the_caller_comes_from_gh(self, status):
        status([])
        assert status.reads["user"] == 1

    def test_no_active_sprint_is_said(self, status):
        with pytest.raises(SystemExit) as caught:
            status([], active=())
        assert "no active sprint" in str(caught.value)
