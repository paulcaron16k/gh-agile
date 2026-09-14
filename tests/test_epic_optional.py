"""`--epic none`: a story may stand alone, and saying so is required.

An epic was mandatory in three places -- `--epic` was `required=True`, `validate`
reported `story has no epic`, and **POLICY.md §2** said of a story *"One parent,
always. An orphan story is a validation failure, not a style choice."*

That last one made this a **policy change, not a flag**. A tool that contradicts
its own written convention is the failure found when POLICY §4 promised evidence
"filled in as work proceeds" while the tool discarded it on every status but Done;
whichever lands second is wrong for as long as the gap is open. So the text moved
with the code.

**Explicit opt-out, not silent permission.** Some teams file one-off and ad-hoc
work, and refusing it pushes that work outside the tool entirely, where it is
neither tracked nor exported -- not great project management, and not this tool's
decision to enforce. But an orphan story is far more often an accident than an
intention, so a bare omission still refuses.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def story(monkeypatch, tool, capsys):
    linked = []
    created = []
    monkeypatch.setattr(tool, "require_sprint_config", lambda *a, **k: None)
    monkeypatch.setattr(tool, "require_key_for_prefix", lambda *a, **k: None)
    monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
    monkeypatch.setattr(tool, "create_issue",
                        lambda *a, **k: created.append(a) or (7, "I_7"))
    monkeypatch.setattr(tool, "apply_title_prefix", lambda *a, **k: a[-1])
    monkeypatch.setattr(tool, "add_to_project", lambda *a, **k: "PVTI_7")
    monkeypatch.setattr(tool, "set_field", lambda *a, **k: None)
    monkeypatch.setattr(tool, "graphql", lambda q, **v: linked.append(v) or {"data": {}})
    monkeypatch.setattr(tool, "gh", lambda a, **k: json.dumps({"id": "I_parent"}))

    def go(epic):
        import argparse
        args = argparse.Namespace(title="a story", repo="o/r", key="A", epic=epic,
                                  points=None, priority=None, status="Todo",
                                  intent=None, acceptance=None, owner="o", project=1,
                                  _config={})
        tool.cmd_story(args)
        return linked, created, capsys.readouterr().out

    go.created = created
    return go


class TestEpicNone:
    def test_the_story_is_created(self, tool, story):
        _, created, _ = story("none")
        assert len(created) == 1

    def test_and_attached_to_nothing(self, tool, story):
        linked, _, _ = story("none")
        assert linked == []

    def test_the_output_says_so(self, tool, story):
        """Rather than printing `under epic #none`."""
        _, _, out = story("none")
        assert "standing alone" in out and "under epic" not in out

    @pytest.mark.parametrize("spelling", ["none", "NONE", "None", " none "])
    def test_however_it_is_spelled(self, tool, story, spelling):
        linked, _, _ = story(spelling)
        assert linked == []


class TestAnEpicStillAttaches:
    def test_a_number_makes_the_edge(self, tool, story):
        linked, _, _ = story("9")
        assert linked == [{"parent": "I_parent", "child": "I_7"}]

    def test_the_output_names_it(self, tool, story):
        _, _, out = story("9")
        assert "under epic #9" in out


class TestSayingItIsRequired:
    def test_nonsense_is_refused(self, tool, story):
        with pytest.raises(SystemExit) as exit_info:
            story("banana")
        message = str(exit_info.value)
        assert "neither an epic's issue number nor `none`" in message
        assert "--epic none" in message

    def test_nothing_is_created_when_it_is_refused(self, tool, story):
        """The check is before `create_issue`, so a typo costs no orphan issue --
        and issue numbers are never reused."""
        with pytest.raises(SystemExit):
            story("banana")
        assert story.created == []

    def test_the_flag_is_still_required_by_the_parser(self, tool, monkeypatch):
        """A bare omission refuses, because an orphan story is far more often an
        accident than an intention."""
        import sys as _sys
        monkeypatch.setattr(tool, "require_interpreter", lambda: None)
        monkeypatch.setattr(tool, "apply_defaults", lambda args: None)
        monkeypatch.setattr(_sys, "argv", ["gh-agile", "story", "a title"])
        with pytest.raises(SystemExit):
            tool.main()


class TestValidateNotesRatherThanFails:
    @pytest.fixture
    def validate(self, monkeypatch, tool, capsys):
        def go(*rows):
            import argparse
            monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
            monkeypatch.setattr(tool, "iterations", lambda *a, **k: ([], []))
            args = argparse.Namespace(owner="o", project=1, _config={}, id=None)
            code = tool.cmd_validate(args)
            return code, capsys.readouterr().out
        return go

    def row(self, **overrides):
        base = {"number": 7, "title": "a story", "repository": "o/r", "state": "OPEN",
                "state_reason": "", "labels": "type:story;key:A", "field_status": "Todo",
                "field_sprint": "", "epic_number": None, "sub_issues_total": 0,
                "sub_issues_done": 0, "started_at": "", "done_at": ""}
        base.update(overrides)
        return base

    def test_an_orphan_story_is_reported(self, tool, validate):
        """Still visible: the same state arrives by accident far more often than
        on purpose, and nothing marks which this is."""
        _, out = validate(self.row())
        assert "story has no epic" in out

    def test_but_it_does_not_fail_the_run(self, tool, validate):
        """A finding that is somebody's deliberate choice cannot be fatal without
        the validator arguing with the person using it -- and a check that fails
        forever is a check people stop running."""
        code, out = validate(self.row())
        assert code == 0
        assert "no problems found" in out

    def test_it_is_under_a_heading_that_says_so(self, tool, validate):
        _, out = validate(self.row())
        assert "notes -- reported, not failures" in out

    def test_the_count_is_carried_in_the_summary(self, tool, validate):
        _, out = validate(self.row(), self.row(number=8))
        assert "2 note(s)" in out

    def test_a_real_problem_still_fails(self, tool, validate):
        code, out = validate(self.row(state="CLOSED", field_status="Todo"))
        assert code == 1 and "problem(s) across" in out

    def test_problems_and_notes_are_both_shown(self, tool, validate):
        code, out = validate(self.row(state="CLOSED", field_status="Todo"))
        assert code == 1
        assert "story has no epic" in out and "closed but status is not Done" in out

    def test_a_story_with_an_epic_notes_nothing(self, tool, validate):
        _, out = validate(self.row(epic_number=9))
        assert "story has no epic" not in out
