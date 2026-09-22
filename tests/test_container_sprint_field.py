"""A container never keeps a Sprint field. AGILE-170.

`REPORTS-1` was an epic carrying `Sprint 2` and no `sprint:` label, so it showed
on the Roadmap and vanished from the Backlog -- whose filter is `no:sprint` --
the one board an unstarted epic belongs to. Found by a person asking why an epic
was on one board and not the other.

**The repair set had a hole and #123 was half of it.** `sprint unstamp` cleared
stray *labels*; nothing cleared a stray *field*. `reconcile_sprints` only ever
sets a field from labels, `heal_sprint_fields` fills empty ones, and
`restore_assignments` carries the value across every iteration write -- so the
routine fortnightly append actively preserved it. And `validate` was silent by
design: #121 exempted containers from the sprint invariants, correctly, because
demanding a sprint of one is the check-that-fails-forever failure.

What was missing is the **mirror**: not *a container with no sprint*, which is
right, but *a container with one*, which cannot be.

One instance on this board, and the count is not reassurance: the gh-agile
containers were clean because an earlier iteration write had wiped their fields
and left only labels, which #123 then cleaned. Different cause, same look.
"""

from __future__ import annotations

import argparse

import pytest


def item(number, kind, *, sprint=None, stamps=(), repo="o/r"):
    labels = [{"name": f"type:{kind}"}, {"name": "key:AGILE"}]
    labels += [{"name": f"sprint:{d}"} for d in stamps]
    values = []
    if sprint:
        values.append({"__typename": "ProjectV2ItemFieldIterationValue",
                       "title": sprint, "field": {"name": "Sprint"}})
    return {"id": f"PVTI_{number}", "isArchived": False,
            "fieldValues": {"nodes": values},
            "content": {"__typename": "Issue", "number": number,
                        "title": f"issue {number}", "url": "u", "state": "OPEN",
                        "repository": {"nameWithOwner": repo},
                        "labels": {"nodes": labels}, "assignees": {"nodes": []},
                        "subIssuesSummary": {"total": 0, "completed": 0}}}


@pytest.fixture
def unstamp(monkeypatch, tool, capsys):
    def go(*items, dry_run=True):
        cleared, edits = [], []
        monkeypatch.setattr(tool, "fetch_items", lambda *a, **k: ("b", list(items)))
        monkeypatch.setattr(tool, "gh", lambda a, **k: edits.append(a) or "")
        monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
        monkeypatch.setattr(tool, "clear_field",
                            lambda login, project, item_id, field:
                                cleared.append((item_id, field)))
        args = argparse.Namespace(owner="o", project=1, _config={}, dry_run=dry_run)
        tool.unstamp_containers(args)
        return capsys.readouterr().out, cleared, edits
    return go


class TestClearField:
    def test_it_calls_the_clear_mutation(self, tool, monkeypatch):
        """`gh project item-edit` has no flag for an absent value, so this is
        the one unset in the tool and it is written out."""
        sent = {}
        monkeypatch.setattr(tool, "fields_of", lambda *a, **k: {"Sprint": {"id": "F1"}})
        monkeypatch.setattr(tool, "project_id", lambda *a: "PVT_1")
        monkeypatch.setattr(tool, "graphql",
                            lambda q, **v: sent.update({"q": q, **v}) or {})
        tool.clear_field("o", 1, "PVTI_9", "Sprint")
        assert "clearProjectV2ItemFieldValue" in sent["q"]
        assert sent["i"] == "PVTI_9" and sent["f"] == "F1"

    def test_a_missing_field_is_refused(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "fields_of", lambda *a, **k: {})
        with pytest.raises(SystemExit) as exit_info:
            tool.clear_field("o", 1, "PVTI_9", "Sprint")
        assert "gh agile setup" in str(exit_info.value)


class TestUnstampClearsTheField:
    @pytest.mark.parametrize("kind", ["epic", "initiative"])
    def test_a_stray_field_is_cleared(self, tool, unstamp, kind):
        _out, cleared, _edits = unstamp(item(9, kind, sprint="Sprint 2"),
                                        dry_run=False)
        assert cleared == [("PVTI_9", "Sprint")]

    def test_a_dry_run_clears_nothing(self, tool, unstamp):
        out, cleared, _edits = unstamp(item(9, "epic", sprint="Sprint 2"))
        assert cleared == []
        assert "would clear o/r#9  Sprint field" in out

    def test_both_a_field_and_a_label_go(self, tool, unstamp):
        _out, cleared, edits = unstamp(
            item(9, "epic", sprint="Sprint 2", stamps=["2026-08-31"]), dry_run=False)
        assert cleared == [("PVTI_9", "Sprint")]
        assert any("--remove-label" in e for e in edits)

    def test_a_label_alone_still_goes(self, tool, unstamp):
        """#123's half, unchanged."""
        _out, cleared, edits = unstamp(item(9, "epic", stamps=["2026-08-31"]),
                                       dry_run=False)
        assert cleared == []
        assert any("--remove-label" in e for e in edits)

    def test_a_clean_container_is_untouched(self, tool, unstamp):
        out, cleared, edits = unstamp(item(9, "epic"), dry_run=False)
        assert cleared == [] and edits == []
        assert "nothing stray" in out

    def test_a_story_with_a_sprint_is_never_touched(self, tool, unstamp):
        """A story belongs in a sprint. This pass is narrow or it is dangerous."""
        _out, cleared, edits = unstamp(item(9, "story", sprint="Sprint 2",
                                            stamps=["2026-08-31"]), dry_run=False)
        assert cleared == [] and edits == []

    def test_the_summary_counts_values_not_labels(self, tool, unstamp):
        out, _cleared, _edits = unstamp(
            item(9, "epic", sprint="Sprint 2", stamps=["2026-08-31"]))
        assert "would clear 2 stray value(s)" in out


class TestValidateReportsTheMirror:
    @pytest.fixture
    def validate(self, monkeypatch, tool, capsys):
        def go(*rows):
            monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
            monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
                [{"title": "Sprint 2", "startDate": "2026-08-31", "duration": 14}], []))
            code = tool.cmd_validate(argparse.Namespace(owner="o", project=1,
                                                        _config={}, id=None))
            return code, capsys.readouterr().out
        return go

    @staticmethod
    def row(kind, sprint):
        return {"number": 9, "issue_key": "A-9", "title": "an issue",
                "repository": "o/r", "state": "OPEN", "state_reason": "",
                "labels": f"type:{kind};key:AGILE;sprint:2026-08-31",
                "field_status": "Todo", "field_sprint": sprint,
                "epic_number": None, "parent_key": "", "parent_type": "",
                "assignees": "dev", "sub_issues_total": 1, "sub_issues_done": 0,
                "started_at": "", "done_at": ""}

    @pytest.mark.parametrize("kind", ["epic", "initiative"])
    def test_a_container_in_a_sprint_is_reported(self, tool, validate, kind):
        _code, out = validate(self.row(kind, "Sprint 2"))
        assert "is in a sprint" in out
        assert "Sprint 2" in out

    def test_the_finding_points_at_the_repair(self, tool, validate):
        _code, out = validate(self.row("epic", "Sprint 2"))
        assert "sprint unstamp" in out

    def test_it_is_a_problem_not_a_note(self, tool, validate):
        """Nobody chose this state and one command clears it."""
        code, _out = validate(self.row("epic", "Sprint 2"))
        assert code == 1

    def test_a_container_with_no_sprint_is_still_silent(self, tool, validate):
        """#121's exemption is right and must not be reintroduced: demanding a
        sprint of a container is the check-that-fails-forever failure."""
        _code, out = validate(self.row("epic", ""))
        assert "in a sprint" not in out
        assert "in no sprint" not in out

    def test_a_story_in_a_sprint_is_not_reported(self, tool, validate):
        _code, out = validate(self.row("story", "Sprint 2"))
        assert "is in a sprint" not in out


class TestTheSaveRestorePairStaysSymmetric:
    """Recorded rather than changed, as the story's acceptance asked.

    Dropping containers here would work -- the next iteration write would clear
    the stray value and nothing would put it back. It is still the wrong place:
    a save-and-restore has one job, it runs either side of the most destructive
    operation in this tool with no transaction, and a pair that restores less
    than it saved cannot be reasoned about when a run dies half way. It would
    also repair by side effect, with `sprint create` quietly removing a field
    and nothing saying so.
    """

    def test_it_still_saves_a_container_s_assignment(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "fetch_items", lambda *a, **k: (
            "b", [item(9, "epic", sprint="Sprint 2")]))
        assert tool.sprint_assignments("o", 1) == {"PVTI_9": "Sprint 2"}

    def test_and_the_reasoning_is_written_down(self, tool):
        import pathlib
        source = pathlib.Path(tool.__file__).read_text()
        after = source.split("def sprint_assignments")[1][:3000]
        assert "Why this does not skip containers" in after
