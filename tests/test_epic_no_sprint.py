"""An epic or initiative is never put in a sprint. AGILE-115, under #114.

`move` decided the sprint from the status alone -- `if same_status(args.status,
CYCLE_START)` with no type check -- so starting an epic assigned it the current
sprint, stamped a `sprint:YYYY-MM-DD` label and claimed it, exactly as for a
story.

Both writes are wrong for a level that spans sprints, and wrong in the way that
is hardest to catch. The `Sprint` field holds one value and is filled only when
empty, so the epic stays pinned to the iteration it happened to start in: on the
scrum board for that sprint, silently gone the next while the work continues --
correct-looking for a fortnight. And the `sprint:` label asserts *the sprint this
was worked in*, which one label cannot say for work spanning four.

What must not change: the epic still starts, and is still claimed. Only the
sprint half is skipped, and it is said out loud rather than skipped quietly --
an epic that starts with no sprint line otherwise looks like a failed write.

Offline: every `gh` call is captured, so nothing here reaches GitHub.
"""

from __future__ import annotations

import argparse
import json

import pytest

BODY_WITH_EVIDENCE = "## Intent\nwhy\n\n## Acceptance\nwhat\n\n## Evidence\nPR #1, merged.\n"


def argparse_namespace(tool, **overrides):
    args = argparse.Namespace(
        issue="7", repo="o/r", owner="o", project=1, close=False, not_planned=False,
        evidence=None, evidence_file=None, add_assignee=None, status="In Progress",
        _config={"sprint": {"cadence_days": 14}},
    )
    for name, value in overrides.items():
        setattr(args, name, value)
    return args


class Run:
    """What one `cmd_move` did: the fields it wrote and the labels it stamped."""

    def __init__(self):
        self.fields = []
        self.labels = []
        self.claims = []
        self.out = ""

    @property
    def sprint_writes(self):
        return [value for name, value in self.fields if name == "Sprint"]

    @property
    def status_writes(self):
        return [value for name, value in self.fields if name == "Status"]


@pytest.fixture
def move(monkeypatch, tool, capsys):
    """`cmd_move` with GitHub replaced, parameterised by the issue's labels."""
    def run(status="In Progress", *, labels=(), **overrides):
        record = Run()

        def fake_gh(args, **kwargs):
            if args[:2] == ["issue", "view"] and "--json" in args:
                if "labels" in args:
                    return json.dumps({"labels": [{"name": n} for n in labels]})
                if "body" in args:
                    # `Done` validates the body before anything is written, so a
                    # move to it needs an Evidence section already present.
                    return json.dumps({"body": BODY_WITH_EVIDENCE})
                return json.dumps({"assignees": []})
            return ""

        monkeypatch.setattr(tool, "gh", fake_gh)
        monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 7))
        monkeypatch.setattr(tool, "board_item_for", lambda *a, **k: {"id": "PVTI_7"})
        monkeypatch.setattr(tool, "set_field",
                            lambda login, project, item, name, value:
                                record.fields.append((name, value)))
        monkeypatch.setattr(tool, "sprint_assignments", lambda *a, **k: {})
        monkeypatch.setattr(tool, "iterations",
                            lambda *a, **k: ([{"title": "Sprint 3", "id": "I_3"}], []))
        monkeypatch.setattr(tool, "record_sprint_label",
                            lambda *a, **k: record.labels.append("sprint:2026-09-14")
                            or "sprint:2026-09-14")
        monkeypatch.setattr(tool, "claim_issue",
                            lambda repo, issue, wanted, *, explicit:
                                record.claims.append((wanted, explicit)) or "  claimed")
        monkeypatch.setattr(tool, "close_issue", lambda *a, **k: None)

        tool.cmd_move(argparse_namespace(tool, status=status, **overrides))
        record.out = capsys.readouterr().out
        return record
    return run


class TestAStoryIsUnchanged:
    """The case that must not regress: this is the ordinary path."""

    def test_starting_a_story_still_assigns_the_current_sprint(self, tool, move):
        assert move(labels=["type:story"]).sprint_writes == ["@current"]

    def test_starting_a_story_still_stamps_the_label(self, tool, move):
        assert move(labels=["type:story"]).labels == ["sprint:2026-09-14"]

    def test_finishing_a_story_still_stamps_the_label(self, tool, move):
        assert move("Done", labels=["type:story"]).labels == ["sprint:2026-09-14"]

    def test_an_untyped_issue_is_treated_as_a_story(self, tool, move):
        """A machine may not infer a type, so an issue with no `type:` label is
        not assumed to span sprints -- the conservative direction."""
        assert move(labels=[]).sprint_writes == ["@current"]


@pytest.mark.parametrize("level", ["epic", "initiative"])
class TestTheSpanningLevels:
    def test_starting_one_writes_no_sprint(self, tool, move, level):
        assert move(labels=[f"type:{level}"]).sprint_writes == []

    def test_starting_one_stamps_no_label(self, tool, move, level):
        assert move(labels=[f"type:{level}"]).labels == []

    def test_finishing_one_stamps_no_label(self, tool, move, level):
        """Both call sites, not just the one that starts work."""
        assert move("Done", labels=[f"type:{level}"]).labels == []

    def test_the_status_is_still_written(self, tool, move, level):
        """It still starts. Only the sprint half is skipped."""
        assert move(labels=[f"type:{level}"]).status_writes == ["In Progress"]

    def test_it_is_still_claimed(self, tool, move, level):
        assert move(labels=[f"type:{level}"]).claims == [("", False)]

    def test_the_skip_is_said_out_loud(self, tool, move, level):
        """Silence here reads as a failed write."""
        out = move(labels=[f"type:{level}"]).out
        assert "spans sprints" in out
        assert level in out

    def test_an_explicit_assignee_still_works(self, tool, move, level):
        assert move("Blocked", labels=[f"type:{level}"],
                    add_assignee="dev").claims == [("dev", True)]


class TestSpansSprints:
    @pytest.mark.parametrize("labels,want", [
        (["type:epic"], "epic"),
        (["type:initiative"], "initiative"),
        (["type:story"], None),
        ([], None),
        (["key:AGILE", "type:epic", "sprint:2026-09-14"], "epic"),
        # Both labels is a mislabelled issue either way; the higher level wins,
        # and the name is only used to say why the sprint was skipped.
        (["type:epic", "type:initiative"], "initiative"),
    ])
    def test_the_level_is_named(self, tool, labels, want):
        assert tool.spans_sprints(labels) == want

    def test_a_type_that_merely_contains_the_word_is_not_a_match(self, tool):
        assert tool.spans_sprints(["type:epical", "initiative:some-slug"]) is None


class TestItCostsNothingOnOtherTransitions:
    @pytest.mark.parametrize("status", ["Blocked", "In Review", "Todo"])
    def test_no_label_read_on_a_status_that_touches_no_sprint(
        self, tool, monkeypatch, move, status,
    ):
        """The lookup is its own call, so it is made only where it is needed."""
        asked = []
        monkeypatch.setattr(tool, "issue_labels",
                            lambda repo, issue: asked.append(issue) or [])
        move(status, labels=["type:epic"])
        assert asked == []

    @pytest.mark.parametrize("status", ["In Progress", "Done"])
    def test_it_is_read_once_on_the_two_that_do(self, tool, monkeypatch, move, status):
        asked = []
        monkeypatch.setattr(tool, "issue_labels",
                            lambda repo, issue: asked.append(issue) or ["type:epic"])
        move(status, labels=["type:epic"])
        assert asked == [7]


class TestIssueLabels:
    def test_it_reads_the_names(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "gh", lambda *a, **k: json.dumps(
            {"labels": [{"name": "type:epic"}, {"name": "key:AGILE"}]}))
        assert tool.issue_labels("o/r", 7) == ["type:epic", "key:AGILE"]

    def test_an_issue_with_no_labels_is_an_empty_list(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "gh", lambda *a, **k: json.dumps({"labels": []}))
        assert tool.issue_labels("o/r", 7) == []
