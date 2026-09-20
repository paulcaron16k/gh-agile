"""A list view ordered by the hierarchy, indented by level. AGILE-150, under #148.

The list was flat. Every board ordered rows by issue number inside its sections,
so an initiative, its epics and their stories interleaved with unrelated work and
the reader rebuilt the tree. Measured the honest way: across the whole of #114 I
ran `board show --filter initiative:...` perhaps twenty times and reconstructed
the shape mentally every time.

**The value is the ordering; the indent only makes it visible.** Indentation
alone would duplicate the `type` column, which already says what level a row is.
What `type` cannot say is *which parent*.

**It belongs where a tree is shown together, and not everywhere.** A
status-grouped board separates a parent from its children by construction, so
indenting inside a section would show children under a parent that is not there.
`TABLE_LAYOUT` is one flat table -- Backlog and View 1 -- and is also how an
`initiative:` filter is read.

Depends on #149: a row could not name its parent unambiguously until `board_row`
carried `parent_key`.
"""

from __future__ import annotations

import argparse
import json

import pytest

VIEW = {"name": "b", "layout": "TABLE_LAYOUT", "filter": ""}


def row(key, number, *, parent=None, kind="story", repo="o/r", title=None):
    return {"key": key, "number": number, "repository": repo,
            "title": title or f"issue {number}", "type": kind,
            "parent_key": parent or "", "parent_type": "", "status": "Todo",
            "story_points": None, "sprint": None, "assignees": [], "labels": [],
            "state": "OPEN", "sub_issues_total": 0, "sub_issues_done": 0}


def shape(rows):
    """`[(depth, key)]` -- the order and the indent, which is the whole subject."""
    return [(r["depth"], r["key"]) for r in rows]


class TestTheForest:
    def test_a_child_follows_its_parent(self, tool):
        got = tool.hierarchy_order([row("A-2", 2, parent="A-1"), row("A-1", 1)])
        assert shape(got) == [(0, "A-1"), (1, "A-2")]

    def test_three_levels_nest(self, tool):
        got = tool.hierarchy_order([
            row("A-3", 3, parent="A-2"), row("A-1", 1), row("A-2", 2, parent="A-1")])
        assert shape(got) == [(0, "A-1"), (1, "A-2"), (2, "A-3")]

    def test_siblings_are_ordered_by_number(self, tool):
        got = tool.hierarchy_order([
            row("A-9", 9, parent="A-1"), row("A-1", 1), row("A-4", 4, parent="A-1")])
        assert shape(got) == [(0, "A-1"), (1, "A-4"), (1, "A-9")]

    def test_a_whole_subtree_comes_before_the_next_sibling(self, tool):
        """Depth-first: a second epic does not interrupt the first one's stories."""
        got = tool.hierarchy_order([
            row("A-1", 1), row("A-2", 2, parent="A-1"), row("A-3", 3, parent="A-1"),
            row("A-4", 4), row("A-5", 5, parent="A-4")])
        assert shape(got) == [(0, "A-1"), (1, "A-2"), (1, "A-3"),
                              (0, "A-4"), (1, "A-5")]

    def test_siblings_across_repositories_are_deterministic(self, tool):
        """A board may span repositories and two `#12` is ordinary."""
        got = tool.hierarchy_order([
            row("A-1", 1), row("B-12", 12, parent="A-1", repo="o/other"),
            row("A-12", 12, parent="A-1")])
        assert shape(got) == [(0, "A-1"), (1, "B-12"), (1, "A-12")]


class TestRootsAndTheRest:
    def test_a_child_whose_parent_is_filtered_out_is_a_root(self, tool):
        """The tree shown is the tree present, not the tree that exists."""
        got = tool.hierarchy_order([row("A-2", 2, parent="A-1")])
        assert shape(got) == [(0, "A-2")]

    def test_work_in_no_tree_comes_after_the_trees(self, tool):
        """Even when its number would have put it first."""
        got = tool.hierarchy_order([
            row("A-1", 1, kind="bug"), row("A-8", 8), row("A-9", 9, parent="A-8")])
        assert shape(got) == [(0, "A-8"), (1, "A-9"), (0, "A-1")]

    def test_several_loose_items_keep_number_order(self, tool):
        got = tool.hierarchy_order([row("A-9", 9), row("A-2", 2), row("A-5", 5)])
        assert shape(got) == [(0, "A-2"), (0, "A-5"), (0, "A-9")]

    def test_a_parent_with_no_children_shown_is_loose_not_a_tree(self, tool):
        got = tool.hierarchy_order([row("A-1", 1, kind="epic"), row("A-2", 2)])
        assert shape(got) == [(0, "A-1"), (0, "A-2")]


class TestItCannotLoseOrHangOnARow:
    def test_a_cycle_terminates(self, tool):
        """Impossible through GitHub's own sub-issue edges; a read must still
        not hang on a board that has one somehow."""
        got = tool.hierarchy_order([
            row("A-1", 1, parent="A-2"), row("A-2", 2, parent="A-1")])
        assert len(got) == 2

    def test_a_cycle_keeps_both_rows(self, tool):
        """A row the ordering cannot place must still be shown -- dropping it
        is a board quietly narrower than its filter."""
        got = tool.hierarchy_order([
            row("A-1", 1, parent="A-2"), row("A-2", 2, parent="A-1")])
        assert {r["key"] for r in got} == {"A-1", "A-2"}

    def test_a_row_that_is_its_own_parent_is_a_root(self, tool):
        got = tool.hierarchy_order([row("A-1", 1, parent="A-1")])
        assert shape(got) == [(0, "A-1")]

    def test_every_row_survives(self, tool):
        rows = [row("A-1", 1), row("A-2", 2, parent="A-1"), row("A-3", 3),
                row("A-4", 4, parent="A-missing")]
        assert len(tool.hierarchy_order(rows)) == 4

    def test_every_row_gets_a_depth(self, tool):
        rows = [row("A-1", 1), row("A-2", 2, parent="A-1")]
        assert all("depth" in r for r in tool.hierarchy_order(rows))


class TestWhereItApplies:
    def test_an_ungrouped_layout_is_ordered_as_a_forest(self, tool):
        rows = [row("A-2", 2, parent="A-1"), row("A-1", 1)]
        sections = tool.board_sections(rows, None, [], [])
        assert shape(sections[0][1]) == [(0, "A-1"), (1, "A-2")]

    def test_a_status_grouped_board_keeps_number_order(self, tool):
        """A parent and its children are separated by construction there."""
        rows = [row("A-2", 2, parent="A-1"), row("A-1", 1)]
        sections = tool.board_sections(rows, "status", [], [])
        todo = next(items for name, items in sections if name == "Todo")
        assert [r["key"] for r in todo] == ["A-1", "A-2"]

    def test_and_indents_nothing(self, tool):
        rows = [row("A-2", 2, parent="A-1"), row("A-1", 1)]
        sections = tool.board_sections(rows, "status", [], [])
        todo = next(items for name, items in sections if name == "Todo")
        assert all(r["depth"] == 0 for r in todo)

    def test_a_sprint_grouped_board_indents_nothing_either(self, tool):
        rows = [row("A-2", 2, parent="A-1"), row("A-1", 1)]
        sections = tool.board_sections(rows, "sprint", [], [])
        assert all(r["depth"] == 0 for _name, items in sections for r in items)


class TestTheIndentIsMeasuredWhereItIsPrinted:
    def test_the_key_cell_carries_the_indent(self, tool):
        assert tool.key_cell({**row("A-1", 1), "depth": 2}) == "  A-1"

    def test_and_still_carries_the_stale_mark(self, tool):
        stale = {**row("A-1", 1), "depth": 1, "state": "CLOSED", "status": "Todo"}
        assert tool.key_cell(stale) == " A-1" + tool.STALE_MARK

    def test_the_column_is_wide_enough_for_the_deepest_row(self, tool):
        rows = [{**row("A-1", 1), "depth": 0}, {**row("A-2", 2), "depth": 3}]
        assert tool.board_columns(rows, 80)["key"] >= len("   A-2")

    def test_nothing_is_pushed_past_the_board_width(self, tool):
        rows = tool.hierarchy_order([
            row("A-1", 1), row("A-2", 2, parent="A-1"),
            row("A-3", 3, parent="A-2", title="a very long title " * 6)])
        out = tool.render_board(VIEW, "backlog", rows, [("", rows)], "o", 4,
                                len(rows), "", 80)
        assert max(len(line) for line in out.splitlines()) <= 80

    def test_the_tree_is_visible_in_the_output(self, tool):
        rows = tool.hierarchy_order([row("A-1", 1), row("A-2", 2, parent="A-1")])
        out = tool.render_board(VIEW, "backlog", rows, [("", rows)], "o", 4, 2, "", 80)
        parent_line = next(ln for ln in out.splitlines() if "A-1" in ln and "key" not in ln)
        child_line = next(ln for ln in out.splitlines() if "A-2" in ln)
        assert child_line.index("A-2") == parent_line.index("A-1") + 1


class TestTheStructureSurvivesTheRendering:
    def test_the_jsonl_carries_depth(self, tool):
        """So a reader does not recover it by counting spaces."""
        rows = tool.hierarchy_order([row("A-1", 1), row("A-2", 2, parent="A-1")])
        out = tool.board_jsonl(VIEW, "backlog", rows, [("", rows)],
                               argparse.Namespace(owner="o", project=4), "", 2,
                               "2026-09-20T00:00:00Z")
        items = [json.loads(line) for line in out.splitlines()[1:]]
        assert [(i["key"], i["depth"]) for i in items] == [("A-1", 0), ("A-2", 1)]

    @pytest.mark.parametrize("grouping", ["status", "sprint"])
    def test_depth_is_always_present_and_an_integer(self, tool, grouping):
        rows = [row("A-1", 1)]
        sections = tool.board_sections(rows, grouping, [], [])
        assert all(isinstance(r["depth"], int)
                   for _name, items in sections for r in items)
