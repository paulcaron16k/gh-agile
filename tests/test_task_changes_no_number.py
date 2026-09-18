"""A task changes no number. AGILE-135, under #132.

**A task is not work the board tracks, it is how one person is organising their
own story**, and every exclusion here is that sentence applied somewhere.

The failure this prevents is the one a team hits today when they silence
`validate` with `type:story`: the task carries points, lands in velocity, and
inflates the story count with private breakdown. A type that is *counted* would
reproduce that with a nicer label on it.

Four places a number could leak in: the `Sprint` field and its label, story
points, a board row, and a parent's tally.

Offline: every `gh` call is captured.
"""

from __future__ import annotations

import argparse
import json

import pytest

TASK = ["type:task", "key:AGILE"]
STORY = ["type:story", "key:AGILE"]


class TestSprintExempt:
    """One predicate, two reasons, and the message says which."""

    def test_a_task_is_exempt(self, tool):
        assert "task" in tool.sprint_exempt(TASK)

    def test_and_says_the_board_does_not_track_it(self, tool):
        assert "does not track" in tool.sprint_exempt(TASK)

    @pytest.mark.parametrize("level", ["epic", "initiative"])
    def test_a_container_is_exempt_for_a_different_reason(self, tool, level):
        reason = tool.sprint_exempt([f"type:{level}"])
        assert "spans sprints" in reason
        assert "does not track" not in reason

    def test_a_story_belongs_in_a_sprint(self, tool):
        assert tool.sprint_exempt(STORY) is None

    def test_an_untyped_issue_belongs_in_a_sprint(self, tool):
        """A machine may not infer a type; the conservative direction."""
        assert tool.sprint_exempt(["key:AGILE"]) is None


class TestMoveGivesATaskNoSprint:
    @pytest.fixture
    def move(self, monkeypatch, tool, capsys):
        def go(status="In Progress", *, labels=TASK):
            fields, stamped = [], []
            monkeypatch.setattr(tool, "gh", lambda a, **k: json.dumps(
                {"labels": [{"name": n} for n in labels]}
                if "--json" in a and "labels" in a else
                {"body": "## Evidence\nPR #1.\n"} if "body" in a else {"assignees": []}))
            monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 7))
            monkeypatch.setattr(tool, "board_item_for", lambda *a, **k: {"id": "PVTI_7"})
            monkeypatch.setattr(tool, "set_field",
                                lambda login, project, item, name, v: fields.append((name, v)))
            monkeypatch.setattr(tool, "sprint_assignments", lambda *a, **k: {})
            monkeypatch.setattr(tool, "iterations",
                                lambda *a, **k: ([{"title": "S3", "id": "I"}], []))
            monkeypatch.setattr(tool, "record_sprint_label",
                                lambda *a, **k: stamped.append(1) or "sprint:x")
            monkeypatch.setattr(tool, "claim_issue", lambda *a, **k: "  claimed")
            monkeypatch.setattr(tool, "close_issue", lambda *a, **k: None)
            monkeypatch.setattr(tool, "promote_parents", lambda *a, **k: None)
            args = argparse.Namespace(issue="7", repo="o/r", owner="o", project=1,
                                      close=False, not_planned=False, evidence=None,
                                      evidence_file=None, add_assignee=None,
                                      status=status, _config={"sprint": {"cadence_days": 14}})
            tool.cmd_move(args)
            return fields, stamped, capsys.readouterr().out
        return go

    def test_no_sprint_field_is_written(self, tool, move):
        fields, _stamped, _out = move()
        assert [name for name, _v in fields] == ["Status"]

    def test_no_label_is_stamped_at_either_end(self, tool, move):
        assert move("In Progress")[1] == []
        assert move("Done")[1] == []

    def test_the_reason_is_reported_and_names_the_task(self, tool, move):
        _f, _s, out = move()
        assert "task" in out and "does not track" in out

    def test_a_story_is_unaffected(self, tool, move):
        fields, stamped, _out = move(labels=STORY)
        assert ("Sprint", "@current") in fields
        assert stamped == [1]


class TestATaskCarriesNoEstimate:
    @pytest.fixture
    def set_field_on(self, monkeypatch, tool):
        def go(labels, field="Story Points", number=5):
            written = []
            monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 7))
            monkeypatch.setattr(tool, "board_item_for", lambda *a, **k: {"id": "PVTI_7"})
            monkeypatch.setattr(tool, "issue_labels", lambda *a, **k: labels)
            monkeypatch.setattr(tool, "set_field",
                                lambda login, project, item, name, v: written.append((name, v)))
            go.written = written      # survives a SystemExit, so refusals can assert
            args = argparse.Namespace(issue="7", repo="o/r", owner="o", project=1,
                                      field=field, value=None, number=number, _config={})
            tool.cmd_set(args)
            return written
        return go

    def test_points_on_a_task_are_refused(self, tool, set_field_on):
        with pytest.raises(SystemExit) as exit_info:
            set_field_on(TASK)
        assert "carries no estimate" in str(exit_info.value)

    def test_the_refusal_names_the_alternative(self, tool, set_field_on):
        """A refusal that does not say what to do instead is half a message."""
        with pytest.raises(SystemExit) as exit_info:
            set_field_on(TASK)
        assert "Estimate the story instead" in str(exit_info.value)

    def test_nothing_is_written(self, tool, set_field_on):
        """Refused, not accepted and then ignored somewhere downstream."""
        with pytest.raises(SystemExit):
            set_field_on(TASK)
        assert set_field_on.written == []

    def test_a_story_may_still_be_estimated(self, tool, set_field_on):
        assert set_field_on(STORY) == [("Story Points", 5)]

    def test_another_field_on_a_task_is_untouched(self, tool, set_field_on):
        """Only the number-carrying field is refused, not the whole issue."""
        assert set_field_on(TASK, field="FR", number=None) == [("FR", None)]


class TestSyncLeavesTasksOffTheBoard:
    @pytest.fixture
    def sync(self, monkeypatch, tool, capsys):
        def go(issues, *, query=None):
            monkeypatch.setattr(tool, "board_items", lambda *a, **k: [])
            monkeypatch.setattr(tool, "profile_keys",
                                lambda cfg: [{"key": "AGILE", "repo": "o/r"}])
            monkeypatch.setattr(tool, "gh", lambda a, **k: json.dumps(issues))
            args = argparse.Namespace(owner="o", project=1, repo=None, key=None,
                                      state="open", limit=200, query=query,
                                      dry_run=True, adopt=False, yes=False,
                                      _config={"keys": [{"key": "AGILE", "repo": "o/r"}]})
            tool.cmd_sync(args)
            return capsys.readouterr().out
        return go

    @staticmethod
    def issue(number, labels):
        return {"number": number, "title": f"issue {number}", "url": "u",
                "state": "OPEN", "labels": [{"name": n} for n in labels]}

    def test_a_task_is_not_a_candidate(self, tool, sync):
        out = sync([self.issue(1, TASK), self.issue(2, STORY)])
        assert "would add o/r#2" in out
        assert "would add o/r#1" not in out

    def test_the_skip_is_counted_and_says_how_to_override(self, tool, sync):
        """Silence is indistinguishable from a repository with no tasks in it."""
        out = sync([self.issue(1, TASK)])
        assert "1 task(s) left off the board" in out
        assert "label:type:task" in out

    def test_an_explicit_query_still_reaches_them(self, tool, sync):
        """Excluded by default, not excluded outright."""
        out = sync([self.issue(1, TASK)], query="label:type:task")
        assert "would add o/r#1" in out

    def test_a_board_with_no_tasks_says_nothing_about_them(self, tool, sync):
        assert "left off the board" not in sync([self.issue(2, STORY)])


class TestNoTallyCountsATask:
    def test_a_story_with_tasks_shows_no_tally(self, tool):
        """#116 already holds this; asserted here rather than assumed."""
        row = {"type": "story", "story_points": None, "sub_issues_total": 4,
               "sub_issues_done": 1}
        assert tool.render_progress(row) == "—"

    def test_an_epic_tallies_its_stories_not_their_tasks(self, tool):
        """`subIssuesSummary` counts direct children, so this is per level."""
        row = {"type": "epic", "story_points": None, "sub_issues_total": 6,
               "sub_issues_done": 3}
        assert tool.render_progress(row) == "3/6"

    def test_a_task_is_not_a_container(self, tool):
        assert tool.container_level(TASK) is None
