"""A level that spans sprints is never asked for a sprint. AGILE-121, under #114.

#115 made it deliberate that an epic or initiative carries no `Sprint` value and
no `sprint:` label. Nothing told the rest of the tool, so three places went on
demanding both and reported the tool's own correct behaviour as a failure. Live
on the board the moment #114 was started:

    In Progress but in no sprint (1):
      #114 AGILE-114 Initiative and epic visibility on the

`validate` exits 1 on that, so any board with a started epic fails validation
permanently -- and a check that fails forever is a check people stop running.

The three are not equally harmless. Two only talk. The third, `sprint backfill`,
*writes*, in bulk, with no `type:` filter -- and it is precisely what someone runs
because `validate` complained. Measured on this board before the fix: a single
`--dry-run` proposed `sprint:` labels for epic `gh-agile#114` and epic
`agile-reports#1`, which is #115 undone in one command. The closed-issue message
is what recommends it, which is the #72 shape exactly: a message recommending a
repair that writes a sprint the work was never in.

One predicate at all three sites, so the next level added is covered by editing
one list.

Offline: `rows`, `iterations` and every `gh` call are stubbed.
"""

from __future__ import annotations

import argparse

import pytest

SPRINTLESS = "In Progress but in no sprint"
NO_LABEL = "closed with no sprint: label"

LEVELS = ["epic", "initiative"]


def row(*, kind, number=9, state="OPEN", status="In Progress", labels_extra="",
        state_reason=""):
    """One board row at the given level, in no sprint and carrying no stamp."""
    return {
        "number": number, "title": f"an {kind}", "repository": "o/r", "state": state,
        "state_reason": state_reason or ("COMPLETED" if state == "CLOSED" else ""),
        "labels": f"type:{kind};key:AGILE" + labels_extra,
        "field_status": status, "field_sprint": "", "epic_number": None,
        "sub_issues_total": 2, "sub_issues_done": 0,
        "started_at": "2026-09-01T00:00:00Z", "done_at": "",
        # Assigned, so the assignee check stays out of tests that are
        # not about it -- an In Progress row with nobody on it is now a
        # finding of its own.
        "assignees": "dev",
    }


@pytest.fixture
def validate(monkeypatch, tool, capsys):
    def go(*rows):
        monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
        monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
            [{"title": "Sprint 2", "startDate": "2026-08-31", "duration": 14}], []))
        tool.cmd_validate(argparse.Namespace(owner="o", project=1, _config={}, id=None))
        return capsys.readouterr().out
    return go


class TestValidateStopsDemandingASprint:
    @pytest.mark.parametrize("kind", LEVELS)
    def test_a_started_one_is_not_reported_as_sprintless(self, tool, validate, kind):
        assert SPRINTLESS not in validate(row(kind=kind))

    @pytest.mark.parametrize("kind", LEVELS)
    def test_a_closed_one_is_not_asked_for_a_label(self, tool, validate, kind):
        """The message that matters: it recommends the backfill that would write
        the label #115 stopped writing."""
        assert NO_LABEL not in validate(
            row(kind=kind, state="CLOSED", status="Done"))

    @pytest.mark.parametrize("kind", LEVELS)
    def test_a_board_whose_only_finding_was_this_is_clean(self, tool, validate, kind):
        """It exited 1 for as long as any epic was in progress."""
        assert "no problems found" in validate(row(kind=kind))


class TestAStoryIsStillHeldToBoth:
    """The invariants exist for a reason and must keep working."""

    def test_a_started_story_in_no_sprint_is_still_reported(self, tool, validate):
        assert SPRINTLESS in validate(row(kind="story"))

    def test_a_closed_story_with_no_label_is_still_reported(self, tool, validate):
        assert NO_LABEL in validate(row(kind="story", state="CLOSED", status="Done"))

    def test_an_abandoned_story_is_still_exempt(self, tool, validate):
        """The #72 exemption beside this one, unchanged."""
        assert NO_LABEL not in validate(
            row(kind="story", state="CLOSED", status="Done", state_reason="NOT_PLANNED"))

    def test_an_untyped_issue_is_still_held(self, tool, validate):
        """A machine may not infer a type: no `type:` label is not an epic."""
        out = validate({**row(kind="story"), "labels": "key:AGILE"})
        assert SPRINTLESS in out


class TestBackfillSkipsThem:
    @pytest.fixture
    def backfill(self, monkeypatch, tool, capsys):
        def go(*rows, source="timeline", dry_run=True):
            edits = []
            monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
            monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
                [{"title": "Sprint 2", "startDate": "2026-08-31", "duration": 14}], []))
            monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
            monkeypatch.setattr(tool, "gh", lambda args, **k: edits.append(args) or "")
            args = argparse.Namespace(owner="o", project=1, _config={}, source=source,
                                      dry_run=dry_run)
            tool.backfill_sprint_labels(args)
            return capsys.readouterr().out, edits
        return go

    @pytest.mark.parametrize("kind", LEVELS)
    def test_it_is_not_stamped(self, tool, backfill, kind):
        """The bulk write. Before the fix one run undid #115 board-wide."""
        out, _ = backfill(row(kind=kind))
        assert "would stamp o/r#9" not in out
        assert "would stamp 0," in out
        assert "skipped" in out

    @pytest.mark.parametrize("kind", LEVELS)
    def test_nothing_is_written_even_for_real(self, tool, backfill, kind):
        _out, edits = backfill(row(kind=kind), dry_run=False)
        assert edits == []

    @pytest.mark.parametrize("kind", LEVELS)
    def test_the_skip_is_counted_out_loud(self, tool, backfill, kind):
        """A silent skip on a repair pass reads as a pass that found nothing."""
        out, _ = backfill(row(kind=kind))
        assert "1 epic(s)/initiative(s) skipped" in out

    def test_a_story_is_still_stamped(self, tool, backfill):
        out, _ = backfill(row(kind="story"))
        assert "would stamp o/r#9" in out
        assert "skipped" not in out

    def test_the_field_source_skips_them_too(self, tool, backfill):
        """Both sources, not just the one that derives from the timeline."""
        item = {**row(kind="epic"), "field_sprint": "Sprint 2"}
        out, _ = backfill(item, source="field")
        assert "would stamp o/r#9" not in out
        assert "1 epic(s)/initiative(s) skipped" in out


class TestOnePredicateAtEverySite:
    def test_validate_and_backfill_both_use_spans_sprints(self, tool):
        """Three separate label tests would drift; the next level added must be
        covered by editing one list."""
        import pathlib
        source = pathlib.Path(tool.__file__).read_text()
        assert source.count("spans_sprints(") >= 4   # helper + move + validate + backfill
        assert 'type:epic' not in source.split("SPANNING_TYPES")[2].split("def cmd_")[0]
