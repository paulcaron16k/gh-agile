"""The roadmap groups by when work began. AGILE-151, under #148.

`ROADMAP_LAYOUT` grouped by sprint -- *"the nearest text analogue of a
timeline"*, chosen when an epic could carry one. **#115 made it guaranteed that a
container carries none**, so every epic landed in a single `(no sprint)` bucket:
measured on project #4, nine of ten. The board rendered correctly and conveyed
nothing. A regression we caused, found by review rather than by anyone hitting
it.

**A roadmap is a WBS report and its axis is when work started** -- normally the
planned order, and sometimes not, because plans get rearranged as work arrives.
So the order is derived from what happened rather than from what was intended,
and an epic planned third but started first appears first.

**First story started, read from the `sprint:` labels.** Those are the immutable
record of the sprint a piece of work was worked in, so the earliest label
anywhere beneath an epic is when that epic began. Read from labels rather than
the Status timeline because the labels are already in hand -- `fetch_items`
returns the whole board -- and the timeline would be one query per issue.
"""

from __future__ import annotations

import pytest

BY_START = {"2026-08-03": "Sprint 1", "2026-08-17": "Sprint 2",
            "2026-08-31": "Sprint 3"}


def item(number, kind, *, parent_key="", stamps=(), repo="o/r"):
    labels = [{"name": f"type:{kind}"}, {"name": "key:AGILE"}]
    labels += [{"name": f"sprint:{d}"} for d in stamps]
    content = {
        "__typename": "Issue", "number": number, "title": f"issue {number}",
        "url": "u", "state": "OPEN", "repository": {"nameWithOwner": repo},
        "labels": {"nodes": labels}, "assignees": {"nodes": []},
        "subIssuesSummary": {"total": 0, "completed": 0},
    }
    if parent_key:
        n = int(parent_key.split("-")[-1])
        content["parent"] = {"number": n, "title": f"issue {n}",
                             "repository": {"nameWithOwner": repo},
                             "labels": {"nodes": [{"name": "type:epic"}]}}
    return {"id": f"PVTI_{number}", "isArchived": False,
            "fieldValues": {"nodes": []}, "content": content}


def starts_for(tool, issues, shown_numbers):
    keys = {"o/r": "AGILE"}
    rows = [tool.board_row(i, keys) for i in issues
            if i["content"]["number"] in shown_numbers]
    tool.derive_starts(issues, rows, keys, BY_START)
    return {r["key"]: r["started_in"] for r in rows}


class TestWhenTheWorkBegan:
    def test_an_epic_starts_when_its_first_story_did(self, tool):
        issues = [item(1, "epic"), item(2, "story", parent_key="AGILE-1",
                                        stamps=["2026-08-17"])]
        assert starts_for(tool, issues, {1}) == {"AGILE-1": "Sprint 2"}

    def test_the_earliest_of_several_children_wins(self, tool):
        issues = [item(1, "epic"),
                  item(2, "story", parent_key="AGILE-1", stamps=["2026-08-31"]),
                  item(3, "story", parent_key="AGILE-1", stamps=["2026-08-03"])]
        assert starts_for(tool, issues, {1}) == {"AGILE-1": "Sprint 1"}

    def test_the_earliest_label_on_one_child_wins(self, tool):
        """A story carried across a boundary carries one label per sprint."""
        issues = [item(1, "epic"),
                  item(2, "story", parent_key="AGILE-1",
                       stamps=["2026-08-31", "2026-08-17"])]
        assert starts_for(tool, issues, {1}) == {"AGILE-1": "Sprint 2"}

    def test_it_reaches_descendants_not_just_children(self, tool):
        """An initiative begins when the first story under any of its epics
        does, and the level in between must not hide it."""
        issues = [item(1, "initiative"), item(2, "epic", parent_key="AGILE-1"),
                  item(3, "story", parent_key="AGILE-2", stamps=["2026-08-03"])]
        assert starts_for(tool, issues, {1})["AGILE-1"] == "Sprint 1"

    def test_an_items_own_label_counts(self, tool):
        issues = [item(1, "epic", stamps=["2026-08-17"])]
        assert starts_for(tool, issues, {1}) == {"AGILE-1": "Sprint 2"}

    def test_nothing_started_says_so(self, tool):
        issues = [item(1, "epic"), item(2, "story", parent_key="AGILE-1")]
        assert starts_for(tool, issues, {1}) == {"AGILE-1": tool.NOT_STARTED}

    def test_an_epic_with_no_children_at_all_is_not_started(self, tool):
        assert starts_for(tool, [item(1, "epic")], {1}) == {"AGILE-1": tool.NOT_STARTED}

    def test_its_own_sprint_field_is_not_consulted(self, tool):
        """The axis is work done, not a field left set before #115 existed --
        the live board's `REPORTS-1` was grouped under `Sprint 2` on exactly
        that, while having no stories at all."""
        issue = item(1, "epic")
        issue["fieldValues"]["nodes"].append(
            {"__typename": "ProjectV2ItemFieldIterationValue", "title": "Sprint 2",
             "field": {"name": "Sprint"}})
        assert starts_for(tool, [issue], {1}) == {"AGILE-1": tool.NOT_STARTED}

    def test_a_date_no_sprint_covers_is_shown_as_the_date(self, tool):
        """Never invent a sprint -- the rule `reconcile_sprints` follows when a
        label names one the configuration no longer has."""
        issues = [item(1, "epic"), item(2, "story", parent_key="AGILE-1",
                                        stamps=["2025-01-06"])]
        assert starts_for(tool, issues, {1}) == {"AGILE-1": "2025-01-06"}

    def test_a_cycle_does_not_hang(self, tool):
        a, b = item(1, "epic", parent_key="AGILE-2"), item(2, "epic", parent_key="AGILE-1")
        assert starts_for(tool, [a, b], {1, 2})


class TestTheSections:
    @staticmethod
    def row(key, number, started_in, on):
        return {"key": key, "number": number, "repository": "o/r",
                "title": key, "type": "epic", "status": "Todo", "sprint": None,
                "story_points": None, "assignees": [], "labels": [],
                "parent_key": "", "state": "OPEN", "sub_issues_total": 0,
                "sub_issues_done": 0, "started_in": started_in, "started_on": on}

    def test_sections_run_in_date_order(self, tool):
        rows = [self.row("A-2", 2, "Sprint 3", "2026-08-31"),
                self.row("A-1", 1, "Sprint 1", "2026-08-03")]
        names = [name for name, _ in tool.board_sections(rows, "start", [], [])]
        assert names == ["Sprint 1 · from 2026-08-03", "Sprint 3 · from 2026-08-31"]

    def test_the_order_is_the_date_not_the_name(self, tool):
        """`0004 W38-2026` beside `AGILE Sprint 4` sorts alphabetically into
        nonsense. The live board has exactly that pair."""
        rows = [self.row("A-1", 1, "AGILE Sprint 4", "2026-07-06"),
                self.row("A-2", 2, "0004 W38-2026", "2026-09-14")]
        names = [name for name, _ in tool.board_sections(rows, "start", [], [])]
        assert names == ["AGILE Sprint 4 · from 2026-07-06",
                         "0004 W38-2026 · from 2026-09-14"]

    def test_not_started_comes_last(self, tool):
        rows = [self.row("A-1", 1, tool.NOT_STARTED, ""),
                self.row("A-2", 2, "Sprint 3", "2026-08-31")]
        names = [name for name, _ in tool.board_sections(rows, "start", [], [])]
        assert names == ["Sprint 3 · from 2026-08-31", tool.NOT_STARTED]

    def test_rows_within_a_section_are_ordered_by_date_then_number(self, tool):
        rows = [self.row("A-9", 9, "Sprint 1", "2026-08-05"),
                self.row("A-2", 2, "Sprint 1", "2026-08-03")]
        _name, items = tool.board_sections(rows, "start", [], [])[0]
        assert [r["key"] for r in items] == ["A-2", "A-9"]

    def test_the_heading_carries_the_date_it_sorts_on(self, tool):
        """A reader seeing `AGILE Sprint 4` above `Sprint 2` and concluding the
        sort is broken is reading the only thing the heading gave them -- and
        `AGILE Sprint 4` really did run first, two weeks before `Sprint 1`."""
        rows = [self.row("A-1", 1, "AGILE Sprint 4", "2026-08-03")]
        name, _items = tool.board_sections(rows, "start", [], [])[0]
        assert name == "AGILE Sprint 4 · from 2026-08-03"

    def test_a_bare_date_is_not_repeated(self, tool):
        """When no sprint covers the date, the name *is* the date."""
        rows = [self.row("A-1", 1, "2025-01-06", "2025-01-06")]
        name, _items = tool.board_sections(rows, "start", [], [])[0]
        assert name == "2025-01-06"

    def test_not_started_carries_no_date(self, tool):
        rows = [self.row("A-1", 1, tool.NOT_STARTED, "")]
        assert tool.board_sections(rows, "start", [], [])[0][0] == tool.NOT_STARTED

    def test_the_date_reaches_a_jsonl_reader_without_parsing_a_heading(self, tool):
        import argparse
        import json
        rows = [self.row("A-1", 1, "Sprint 1", "2026-08-03")]
        sections = tool.board_sections(rows, "start", [], [])
        out = tool.board_jsonl({"name": "R", "layout": "ROADMAP_LAYOUT", "filter": ""},
                               "roadmap", rows, sections,
                               argparse.Namespace(owner="o", project=4), "", 1,
                               "2026-09-20T00:00:00Z")
        item = json.loads(out.splitlines()[1])
        assert item["started_on"] == "2026-08-03" and item["started_in"] == "Sprint 1"

    def test_nothing_is_indented(self, tool):
        rows = [self.row("A-1", 1, "Sprint 1", "2026-08-03")]
        _name, items = tool.board_sections(rows, "start", [], [])[0]
        assert items[0]["depth"] == 0


class TestTheLayoutAndTheOtherBoards:
    def test_the_roadmap_no_longer_groups_by_sprint(self, tool):
        assert tool.LAYOUT_SECTIONS["ROADMAP_LAYOUT"] == "start"

    @pytest.mark.parametrize("layout,grouping", [
        ("BOARD_LAYOUT", "status"), ("TABLE_LAYOUT", None)])
    def test_the_others_are_untouched(self, tool, layout, grouping):
        assert tool.LAYOUT_SECTIONS[layout] == grouping

    def test_the_grouping_is_named_in_the_output(self, tool):
        """A section heading that reads like a sprint would otherwise be taken
        for the Sprint field, which these rows do not have."""
        rows = [TestTheSections.row("A-1", 1, "Sprint 1", "2026-08-03")]
        out = tool.render_board({"name": "R", "layout": "ROADMAP_LAYOUT", "filter": ""},
                                "roadmap", rows, tool.board_sections(rows, "start", [], []),
                                "o", 4, 1, "", 80)
        assert "when the work under each item began" in out

    def test_a_board_without_starts_says_nothing_about_them(self, tool):
        rows = [{k: v for k, v in TestTheSections.row("A-1", 1, "x", "y").items()
                 if k not in ("started_in", "_started_on")}]
        out = tool.render_board({"name": "B", "layout": "TABLE_LAYOUT", "filter": ""},
                                "backlog", rows, [("", rows)], "o", 4, 1, "", 80)
        assert "when the work under each item began" not in out
