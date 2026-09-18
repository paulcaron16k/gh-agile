"""Clearing the `sprint:` labels left on epics, and stopping them coming back. #123.

#115 stopped giving an epic or initiative a `Sprint` value or a `sprint:` label;
#121 stopped `validate` and `backfill` demanding one. Labels written before all
that are still there -- five closed epics on this board -- and they are **not
inert**.

`reconcile_sprints` reads labels and writes the field, and `heal_sprint_fields`
runs it automatically after every destructive iteration write, which is the
routine fortnightly sprint append. Measured on the live board before this
change: a plain `sprint reconcile --dry-run` proposed Sprint 2 for all five
closed epics -- #115 undone with nobody aiming a command at anything.

So two halves, and the guard is the durable one. A cleanup alone leaves the door
open to a label added by hand, an older board adopted with `sync --adopt`, or any
epic stamped before the fix reaches a given checkout.

`unstamp` is the only place this tool *removes* a `sprint:` label. The label is
the immutable record, so removing one is the stated exception rather than a
convenience: stamped at close, it records the sprint the issue was **closed** in,
which for a story is the same fact as "worked in" and for an epic spanning four
sprints is not.

Offline: `fetch_items` and every `gh` call are stubbed.
"""

from __future__ import annotations

import argparse

import pytest

EPIC = ["type:epic", "key:AGILE"]
INITIATIVE = ["type:initiative", "key:AGILE"]
STORY = ["type:story", "key:AGILE"]


def item(number, *, labels, sprint=None, repo="o/r"):
    values = []
    if sprint is not None:
        values.append({"__typename": "ProjectV2ItemFieldIterationValue",
                       "title": sprint, "field": {"name": "Sprint"}})
    return {
        "id": f"PVTI_{number}",
        "isArchived": False,
        "updatedAt": "2026-09-01T00:00:00Z",
        "fieldValues": {"nodes": values},
        "content": {
            "__typename": "Issue", "number": number, "title": f"issue {number}",
            "repository": {"nameWithOwner": repo},
            "labels": {"nodes": [{"name": n} for n in labels]},
        },
    }


@pytest.fixture
def unstamp(monkeypatch, tool, capsys):
    def go(*items, dry_run=True):
        edits = []
        monkeypatch.setattr(tool, "fetch_items", lambda *a, **k: ("board", list(items)))
        monkeypatch.setattr(tool, "gh", lambda args, **k: edits.append(args) or "")
        args = argparse.Namespace(owner="o", project=1, _config={}, dry_run=dry_run)
        tool.unstamp_containers(args)
        return capsys.readouterr().out, edits
    return go


class TestItClearsTheStrays:
    @pytest.mark.parametrize("labels,level", [(EPIC, "epic"), (INITIATIVE, "initiative")])
    def test_a_stamped_level_is_cleared(self, tool, unstamp, labels, level):
        out, _ = unstamp(item(9, labels=labels + ["sprint:2026-08-31"]))
        assert "would clear o/r#9  -sprint:2026-08-31" in out
        assert level in out

    def test_every_label_on_one_issue_is_cleared(self, tool, unstamp):
        """An epic stamped across several sprints carries one per sprint."""
        out, _ = unstamp(item(9, labels=EPIC + ["sprint:2026-08-31", "sprint:2026-09-14"]))
        assert "-sprint:2026-08-31" in out and "-sprint:2026-09-14" in out
        assert "would clear 2 label(s)" in out

    def test_for_real_it_removes_rather_than_adds(self, tool, unstamp):
        _out, edits = unstamp(item(9, labels=EPIC + ["sprint:2026-08-31"]), dry_run=False)
        assert edits == [["issue", "edit", "9", "--repo", "o/r",
                          "--remove-label", "sprint:2026-08-31"]]

    def test_a_dry_run_writes_nothing(self, tool, unstamp):
        _out, edits = unstamp(item(9, labels=EPIC + ["sprint:2026-08-31"]))
        assert edits == []


class TestItIsNarrow:
    def test_a_story_is_never_touched(self, tool, unstamp):
        _out, edits = unstamp(item(9, labels=STORY + ["sprint:2026-08-31"]), dry_run=False)
        assert edits == []

    def test_only_sprint_labels_go(self, tool, unstamp):
        """`key:` and `initiative:` are not this pass's business."""
        _out, edits = unstamp(
            item(9, labels=EPIC + ["sprint:2026-08-31", "initiative:thing"]), dry_run=False)
        assert [e[-1] for e in edits] == ["sprint:2026-08-31"]

    def test_a_clean_epic_is_left_alone(self, tool, unstamp):
        out, edits = unstamp(item(9, labels=EPIC), dry_run=False)
        assert edits == []
        assert "no stray labels" in out

    def test_a_clean_board_says_so(self, tool, unstamp):
        """A repair pass that prints nothing reads as one that failed to look."""
        out, _ = unstamp(item(9, labels=STORY + ["sprint:2026-08-31"]))
        assert "no stray labels" in out

    def test_the_summary_counts_what_it_scanned(self, tool, unstamp):
        out, _ = unstamp(item(9, labels=EPIC + ["sprint:2026-08-31"]),
                         item(10, labels=INITIATIVE), item(11, labels=STORY))
        assert "1 label(s) across 2 epic(s)/initiative(s)" in out


class TestReconcileNoLongerFeedsTheField:
    @pytest.fixture
    def reconcile(self, monkeypatch, tool, capsys):
        def go(*items, dry_run=True):
            written = []
            monkeypatch.setattr(tool, "fetch_items", lambda *a, **k: ("board", list(items)))
            monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
                [{"title": "Sprint 2", "startDate": "2026-08-31", "duration": 14}], []))
            monkeypatch.setattr(tool, "set_field",
                                lambda *a: written.append(a[-1]))
            tool.reconcile_sprints("o", 1, dry_run=dry_run)
            return capsys.readouterr().out, written
        return go

    @pytest.mark.parametrize("labels", [EPIC, INITIATIVE])
    def test_a_stamped_level_gets_no_field(self, tool, reconcile, labels):
        """The one nobody runs on purpose: the automatic heal calls it."""
        out, written = reconcile(item(9, labels=labels + ["sprint:2026-08-31"]),
                                 dry_run=False)
        assert written == []
        assert "would set" not in out

    def test_the_skip_is_counted_and_points_at_the_repair(self, tool, reconcile):
        out, _ = reconcile(item(9, labels=EPIC + ["sprint:2026-08-31"]))
        assert "spanning 1" in out
        assert "sprint unstamp" in out

    def test_a_story_is_still_reconciled(self, tool, reconcile):
        """The repair this whole mechanism exists for must keep working."""
        out, written = reconcile(item(9, labels=STORY + ["sprint:2026-08-31"]),
                                 dry_run=False)
        assert written == ["Sprint 2"]


class TestFixReportsRatherThanRepairs:
    @pytest.fixture
    def fix(self, monkeypatch, tool, capsys):
        def go(labels, sprint=None):
            written = []
            monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 9))
            monkeypatch.setattr(tool, "issue_project_item",
                                lambda *a, **k: ("PVTI_9", list(labels), sprint))
            monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
                [{"title": "Sprint 2", "startDate": "2026-08-31", "duration": 14}], []))
            monkeypatch.setattr(tool, "set_field", lambda *a: written.append(a[-1]))
            args = argparse.Namespace(owner="o", project=1, _config={}, id="9",
                                      repo="o/r", overwrite=False, dry_run=False)
            tool.cmd_fix(args)
            return capsys.readouterr().out, written
        return go

    @pytest.mark.parametrize("labels,level", [(EPIC, "epic"), (INITIATIVE, "initiative")])
    def test_it_says_there_is_no_field_to_repair(self, tool, fix, labels, level):
        out, written = fix(labels + ["sprint:2026-08-31"])
        assert written == []
        assert f"is an {level}" in out

    def test_it_names_the_stray_label_and_the_repair(self, tool, fix):
        out, _ = fix(EPIC + ["sprint:2026-08-31"])
        assert "stray" in out and "sprint unstamp" in out

    def test_an_unstamped_epic_says_only_the_first_half(self, tool, fix):
        out, _ = fix(EPIC)
        assert "no Sprint field to repair" in out
        assert "stray" not in out

    def test_a_story_is_still_repaired(self, tool, fix):
        _out, written = fix(STORY + ["sprint:2026-08-31"])
        assert written == ["Sprint 2"]
