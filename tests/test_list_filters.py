"""`issue list` and the level lists filter as `gh issue list` does. AGILE-220.

`gh issue list -a @me`, `-l bug` and `-A login` are habit, and `gh agile story
list -a @me` failed with "unrecognized arguments". The only filter was `-S`,
in project-filter syntax. These run the real `show_board` path over a fake
board, so the flags are tested against the same evaluator a list uses.
"""

from __future__ import annotations

import pytest


def item(number, *, assignees=(), author="ann", labels=("type:story",), milestone=None,
         status="Todo"):
    return {
        "isArchived": False,
        "fieldValues": {"nodes": [{"name": status, "field": {"name": "Status"}}]},
        "content": {
            "__typename": "Issue", "number": number, "state": "OPEN",
            "title": f"work {number}", "url": f"https://github.com/o/r/issues/{number}",
            "repository": {"nameWithOwner": "o/r"},
            "labels": {"nodes": [{"name": n} for n in labels]},
            "assignees": {"nodes": [{"login": a} for a in assignees]},
            "author": {"login": author},
            "milestone": {"title": milestone} if milestone else None,
        },
    }


BOARD = [
    item(1, assignees=["me"], labels=("type:story", "bug")),
    item(2, assignees=["bob"], author="me", milestone="v1"),
    item(3, labels=("type:story", "bug", "urgent"), milestone="v1", status="Blocked"),
    item(4, assignees=["Me"], author="bob", labels=("type:epic",)),
]


@pytest.fixture
def listed(tool, monkeypatch, capsys):
    def go(*argv, level="issue"):
        asked = []
        monkeypatch.setattr(tool, "iterations", lambda *a: ([], []))
        monkeypatch.setattr(tool, "fetch_items", lambda *a: ("t", BOARD))
        monkeypatch.setattr(tool, "current_repo", lambda: None)
        monkeypatch.setattr(tool, "stdout_is_terminal", lambda: False)
        monkeypatch.setattr(tool, "caller_login", lambda: asked.append(1) or "me")
        args = tool.build_parser().parse_args([level, "list", *argv])
        args.owner, args.project, args._config = "o", 4, {}
        go.asked = asked
        tool.cmd_list(args)
        return [int(line.split("\t")[0].rsplit("#", 1)[-1].rsplit("-", 1)[-1])
                for line in capsys.readouterr().out.splitlines()]
    return go


class TestEachFlagAlone:
    def test_assignee_me(self, listed):
        assert listed("-a", "@me") == [1, 4]

    def test_assignee_by_login(self, listed):
        assert listed("--assignee", "bob") == [2]

    def test_author(self, listed):
        assert listed("-A", "@me") == [2]

    def test_label(self, listed):
        assert listed("-l", "bug") == [1, 3]

    def test_labels_are_anded(self, listed):
        assert listed("-l", "bug", "-l", "urgent") == [3]

    def test_milestone(self, listed):
        assert listed("-m", "v1") == [2, 3]

    def test_no_flag_lists_everything(self, listed):
        assert listed() == [1, 2, 3, 4]


class TestCombined:
    def test_with_search(self, listed):
        assert listed("-l", "bug", "-S", "status:Blocked") == [3]

    def test_with_each_other(self, listed):
        assert listed("-m", "v1", "-A", "@me") == [2]

    def test_with_the_levels_own_filter(self, listed):
        """`story list` already filters on `label:type:story`; -a narrows it."""
        assert listed("-a", "@me", level="story") == [1]

    def test_with_state_and_limit(self, listed):
        assert listed("-l", "bug", "-s", "open", "-L", "1") == [1]


class TestMe:
    def test_me_is_asked_of_gh_once(self, listed):
        listed("-a", "@me", "-A", "@me")
        assert len(listed.asked) == 1

    def test_and_not_at_all_when_not_typed(self, listed):
        listed("-a", "bob")
        assert listed.asked == []


class TestTaskList:
    def test_the_flags_become_search_qualifiers(self, tool):
        args = tool.build_parser().parse_args(
            ["task", "list", "-a", "@me", "-A", "bob", "-l", "needs design", "-m", "v1"])
        assert tool.task_search_terms(args) == [
            "assignee:@me", "author:bob", 'label:"needs design"', 'milestone:"v1"']


@pytest.mark.parametrize("level", ["issue", "epic", "story", "initiative", "task"])
def test_every_list_takes_them(tool, level):
    args = tool.build_parser().parse_args(
        [level, "list", "-a", "x", "-A", "y", "-l", "z", "-m", "w", "-s", "all", "-L", "5",
         "-S", "status:Todo"])
    assert (args.assignee, args.author, args.label, args.milestone) == ("x", "y", ["z"], "w")
