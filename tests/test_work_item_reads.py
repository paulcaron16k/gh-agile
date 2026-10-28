"""`list` and `view` for every level, and `issue` for any of them. #202.

`gh agile epic list` filed an epic called "list" (WIDG-185) because there was no
`epic list` -- the one command a `gh` user would reach for first. Now there is,
for each level, as `gh issue list` and `gh issue view` are.

**A list is a board read through `show_board`**, with a filter of its own, so a
list and a board cannot disagree about what an epic is. **A view comes from the
issue's side**, in one query, and a level's view refuses another level and names
the right command, as `gh pr view` refuses an issue.
"""

from __future__ import annotations

import argparse
import json

import pytest

KEYS = {"o/r": "AGILE"}


def node(**overrides):
    """An issue as `ISSUE_VIEW_QUERY` returns it."""
    base = {
        "number": 200, "title": "An epic", "url": "https://github.com/o/r/issues/200",
        "state": "OPEN", "stateReason": None, "body": "## Intent\nwhy\n",
        "repository": {"nameWithOwner": "o/r"},
        "labels": {"nodes": [{"name": "type:epic"}, {"name": "key:AGILE"},
                             {"name": "initiative:big"}]},
        "assignees": {"nodes": []},
        "parent": {"number": 119, "title": "An initiative",
                   "repository": {"nameWithOwner": "o/r"},
                   "labels": {"nodes": [{"name": "type:initiative"}]}},
        "subIssuesSummary": {"total": 2, "completed": 1},
        "subIssues": {"nodes": [
            {"number": 201, "title": "Done one", "state": "CLOSED",
             "repository": {"nameWithOwner": "o/r"},
             "labels": {"nodes": [{"name": "type:story"}]},
             "projectItems": {"nodes": [{"project": {"number": 4},
                                         "status": {"name": "Done"},
                                         "points": {"number": 3}}]}},
            {"number": 202, "title": "Open one", "state": "OPEN",
             "repository": {"nameWithOwner": "o/r"},
             "labels": {"nodes": [{"name": "type:story"}]},
             "projectItems": {"nodes": [{"project": {"number": 9},
                                         "status": {"name": "Todo"}}]}},
        ]},
        "projectItems": {"nodes": [{"project": {"number": 4},
                                    "status": {"name": "In Progress"},
                                    "sprint": None, "points": None, "priority": None,
                                    "start": {"date": "2026-10-01"}, "target": None}]},
    }
    base.update(overrides)
    return base


class TestViewFacts:
    def test_the_board_fields_come_from_this_project(self, tool):
        facts = tool.view_facts(node(), 4, KEYS)
        assert (facts["key"], facts["type"], facts["status"]) == ("AGILE-200", "epic",
                                                                  "In Progress")
        assert facts["start"] == "2026-10-01" and facts["on_board"]

    def test_another_project_is_not_this_one(self, tool):
        """An issue can be on several projects; the number decides."""
        facts = tool.view_facts(node(), 5, KEYS)
        assert not facts["on_board"] and facts["status"] is None

    def test_children_carry_their_own_status_from_this_project(self, tool):
        children = tool.view_facts(node(), 4, KEYS)["children"]
        assert [(c["key"], c["status"]) for c in children] == [("AGILE-201", "Done"),
                                                               ("AGILE-202", None)]

    def test_the_parent_is_named_with_its_level(self, tool):
        assert tool.view_facts(node(), 4, KEYS)["parent"] == {
            "key": "AGILE-119", "type": "initiative", "title": "An initiative"}

    def test_sprint_labels_are_the_dates_worked_in(self, tool):
        labels = {"nodes": [{"name": "type:story"}, {"name": "sprint:2026-10-12"},
                            {"name": "sprint:2026-09-28"}]}
        facts = tool.view_facts(node(labels=labels), 4, KEYS)
        assert facts["sprint_labels"] == ["2026-09-28", "2026-10-12"]


class TestRenderView:
    def render(self, tool, checks="1 item(s): no problems found", **overrides):
        return tool.render_view(tool.view_facts(node(**overrides), 4, KEYS), checks)

    def test_the_head_line(self, tool):
        assert self.render(tool).splitlines()[0] == "AGILE-200 · epic · open · In Progress"

    def test_an_epics_children_are_its_stories_with_the_rollup(self, tool):
        text = self.render(tool)
        assert "stories: 1/2 closed" in text
        assert "AGILE-201  story      Done" in text

    def test_the_checks_and_then_the_body(self, tool):
        text = self.render(tool)
        assert text.index("checks") < text.index("## Intent")
        assert "no problems found" in text

    def test_the_system_labels_are_not_repeated(self, tool):
        """`type:`, `key:` and `sprint:` are said elsewhere in the view."""
        text = self.render(tool)
        assert "labels     initiative:big" in text and "key:AGILE" not in text

    def test_not_planned_is_said(self, tool):
        text = self.render(tool, state="CLOSED", stateReason="NOT_PLANNED")
        assert "closed (not planned)" in text.splitlines()[0]

    def test_an_issue_off_the_board_says_how_to_put_it_there(self, tool):
        text = tool.render_view(tool.view_facts(node(), 5, KEYS), None)
        assert "gh agile sync" in text and "checks" not in text


@pytest.fixture
def view(monkeypatch, tool, capsys):
    """`cmd_view` against one fake issue."""
    calls = {"gh": []}

    def go(argv, issue=None, checks="no problems found"):
        monkeypatch.setattr(tool, "graphql",
                            lambda q, **v: {"data": {"repository": {"issue": issue or node()}}})
        monkeypatch.setattr(tool, "gh", lambda a, **k: calls["gh"].append(a) or "")
        monkeypatch.setattr(tool, "issue_checks", lambda args, facts: checks)
        args = tool.build_parser().parse_args(argv)
        args.owner, args.project, args.repo = "o", 4, "o/r"
        args._config = {"keys": [{"key": "AGILE", "repo": "o/r"}]}
        code = tool.cmd_view(args)
        return code, capsys.readouterr().out, calls
    return go


class TestCmdView:
    def test_a_level_views_itself(self, tool, view):
        code, out, _ = view(["epic", "view", "200"])
        assert code == 0 and out.startswith("AGILE-200 · epic")

    def test_issue_view_takes_any_level(self, tool, view):
        code, _, _ = view(["issue", "view", "200"])
        assert code == 0

    @pytest.mark.parametrize("asked", ["story", "initiative"])
    def test_another_level_is_refused_with_the_right_command(self, tool, view, asked):
        with pytest.raises(SystemExit) as exit_info:
            view([asked, "view", "200"])
        message = str(exit_info.value)
        assert "AGILE-200 is an epic" in message
        assert "gh agile epic view 200" in message

    def test_an_untyped_issue_is_sent_to_issue_view(self, tool, view):
        untyped = node(labels={"nodes": [{"name": "bug-ish"}]})
        with pytest.raises(SystemExit) as exit_info:
            view(["epic", "view", "200"], issue=untyped)
        assert "untyped" in str(exit_info.value)
        assert "gh agile issue view 200" in str(exit_info.value)

    def test_json(self, tool, view):
        _, out, _ = view(["issue", "view", "200", "--json", "key,checks"])
        data = json.loads(out)
        assert data["key"] == "AGILE-200" and data["checks"] == "no problems found"

    def test_web_opens_the_issue_and_reads_nothing(self, tool, view, monkeypatch):
        monkeypatch.setattr(tool, "graphql", lambda *a, **k: pytest.fail("read"))
        code, _, calls = view(["epic", "view", "200", "-w"])
        assert calls["gh"] == [["issue", "view", "200", "--repo", "o/r", "--web"]]


class TestCmdList:
    @pytest.fixture
    def listed(self, monkeypatch, tool):
        shown = {}

        def show_board(args, v, kind, typed, *, limit=None, announce_unfiltered=True,
                       keep=None):
            shown.update(view=v, kind=kind, typed=typed, limit=limit,
                         announce=announce_unfiltered)
            return 0

        monkeypatch.setattr(tool, "show_board", show_board)

        def go(argv):
            args = tool.build_parser().parse_args(argv)
            args.owner, args.project, args._config = "o", 4, {}
            tool.cmd_list(args)
            return shown
        return go

    @pytest.mark.parametrize("argv,expected", [
        (["epic", "list"], "label:type:epic is:open"),
        (["story", "list", "-s", "closed"], "label:type:story is:closed"),
        (["initiative", "list", "-s", "all"], "label:type:initiative"),
        (["bug", "list"], "label:type:bug is:open"),
        (["issue", "list"], "is:open"),
    ])
    def test_each_level_is_a_filter_the_board_understands(self, tool, listed, argv, expected):
        assert listed(argv)["view"]["filter"] == expected

    def test_the_filter_parses(self, tool):
        """Every term is in `FILTER_TERMS`, or `board show` would refuse it."""
        for kind in tool.TYPE_FILTERS:
            for state in tool.STATE_FILTERS:
                text = " ".join(f for f in (tool.TYPE_FILTERS[kind],
                                            tool.STATE_FILTERS[state]) if f)
                tool.parse_filter(text)

    def test_search_and_limit_go_through(self, tool, listed):
        shown = listed(["epic", "list", "-S", "sprint:@current", "-L", "5"])
        assert (shown["typed"], shown["limit"]) == ("sprint:@current", 5)

    def test_a_list_is_not_warned_about_as_an_unconfigured_view(self, tool, listed):
        """`issue list -s all` excludes nothing, and that is the request."""
        assert listed(["issue", "list", "-s", "all"])["announce"] is False

    def test_the_defaults_are_ghs(self, tool):
        args = tool.build_parser().parse_args(["epic", "list"])
        assert (args.state, args.limit) == ("open", 30)


class TestTaskList:
    def test_tasks_come_from_a_search_with_their_story(self, tool, monkeypatch, capsys):
        """A task is never on the board, so the board read would find none."""
        asked = []

        def graphql(query, **variables):
            asked.append(variables["q"])
            return {"data": {"search": {"nodes": [{
                "number": 31, "title": "Tidy", "state": "OPEN", "url": "u",
                "repository": {"nameWithOwner": "o/r"},
                "parent": {"number": 30, "repository": {"nameWithOwner": "o/r"}}}]}}}

        monkeypatch.setattr(tool, "graphql", graphql)
        args = tool.build_parser().parse_args(["task", "list"])
        args._config = {"keys": [{"key": "AGILE", "repo": "o/r"}]}
        tool.cmd_task_list(args)
        out = capsys.readouterr().out
        assert asked == ["repo:o/r is:issue label:type:task is:open"]
        assert "AGILE-31" in out and "AGILE-30" in out

    def test_it_needs_no_project(self, tool):
        args = tool.build_parser().parse_args(["task", "list"])
        assert args.projectless is True


class TestValidateIdMoved:
    def test_the_flag_is_gone(self, tool):
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args(["validate", "--id", "24"])

    def test_issue_checks_asks_validate_for_one_issue(self, tool, monkeypatch):
        seen = {}
        monkeypatch.setattr(tool, "cmd_validate",
                            lambda a: seen.update(id=a.id) or print("1 problem") or 1)
        args = argparse.Namespace(owner="o", project=4, _config={})
        facts = tool.view_facts(node(), 4, KEYS)
        assert "1 problem" in tool.issue_checks(args, facts)
        assert seen["id"] == "AGILE-200"
