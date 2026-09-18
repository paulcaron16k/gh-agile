"""`closed/total` where the points em dash is. AGILE-116, under #114.

An epic renders an em dash in the points column, because points belong to
stories. That is dead space on exactly the rows most needing a progress figure,
and its emptiness is what made a half-finished epic read as untouched -- #85 sat
at `epic  —  —` on the backlog with six of six stories closed.

The data was already in hand: `FULL_ITEM_SELECTION` fetches `subIssuesSummary`
and `board_row` simply did not carry it through, so this costs no extra call.

**The cell, not the type.** The condition is *has children and no estimate*,
which is exactly when the column would otherwise print an em dash. Nothing
consults `type:`, so there is no second list to drift out of step with
`CONTAINER_TYPES`, and an estimate somebody actually set always beats a derived
number.

**`closed`, never `done`.** `subIssuesSummary.completed` counts *closed*
children, `NOT_PLANNED` included -- measured on `#9`, six of seven with one
abandoned. Abandoned is not completed. And per level, not transitively: an
initiative tallies its epics, an epic tallies its stories.
"""

from __future__ import annotations

import json

import pytest

VIEW = {"name": "Engineering: all work", "layout": "BOARD_LAYOUT", "filter": "-status:Done"}


def row(key="AGILE-9", kind="story", points=None, total=0, done=0, title="a title",
        sprint=None, status=None):
    return {"key": key, "type": kind, "story_points": points, "sprint": sprint,
            "title": title, "status": status, "assignees": [],
            "sub_issues_total": total, "sub_issues_done": done}


def rendered(tool, rows, width=80):
    return tool.render_board(VIEW, "kanban", rows, [("Todo", rows)], "o", 4,
                             len(rows), "-status:Done", width)


class TestRenderProgress:
    def test_an_epic_with_children_shows_the_tally(self, tool):
        assert tool.render_progress(row(kind="epic", total=6, done=3)) == "3/6"

    def test_none_closed_is_a_tally_not_an_em_dash(self, tool):
        """`0/6` is a fact; an em dash is the absence this story removes."""
        assert tool.render_progress(row(kind="epic", total=6, done=0)) == "0/6"

    def test_an_epic_with_no_children_is_unchanged(self, tool):
        """`0/0` would assert a denominator that does not exist."""
        assert tool.render_progress(row(kind="epic", total=0)) == "—"

    def test_a_story_still_shows_its_points(self, tool):
        assert tool.render_progress(row(points=8.0)) == "8"

    def test_a_fractional_estimate_survives(self, tool):
        assert tool.render_progress(row(points=0.5)) == "0.5"

    def test_a_parent_with_children_tallies_whatever_else_is_set(self, tool):
        """The legend promises a tally for these two levels, so it is a tally.
        Nothing in this tool gives an epic points; `story --points` is the only
        writer, and `set` would be somebody doing it deliberately."""
        assert tool.render_progress(row(kind="epic", points=13.0, total=6, done=3)) == "3/6"

    def test_a_closed_child_counts_whatever_it_was_closed_for(self, tool):
        """`completed` is GitHub's name for *closed*, NOT_PLANNED included."""
        assert tool.render_progress(row(kind="epic", total=7, done=6)) == "6/7"

    def test_a_storys_task_list_is_not_tallied(self, tool):
        """Sub-issues nest anywhere, but this tool has never used story tasks:
        `story` creates none, nothing counts them, and the Gold model has no
        grain for them. A figure here would contradict the legend."""
        assert tool.render_progress(row(kind="story", total=4, done=1)) == "—"
        assert tool.render_progress(row(kind="story", points=8.0, total=4)) == "8"

    def test_the_tally_is_per_level(self, tool):
        """An initiative counts its epics, not the stories under them."""
        assert tool.render_progress(row(kind="initiative", total=1, done=0)) == "0/1"


class TestShowsProgress:
    @pytest.mark.parametrize("kw,want", [
        ({"kind": "epic", "total": 6}, True),
        ({"kind": "epic", "total": 0}, False),
        ({"kind": "epic", "total": 6, "points": 3.0}, True),
        ({"kind": "story"}, False),
        ({"kind": "story", "total": 2}, False),     # a task list is not a tally
        ({"kind": "initiative", "total": 1}, True),
        ({"kind": None, "total": 2}, False),        # a machine may not infer a type
    ])
    def test_only_the_levels_above_a_story_tally(self, tool, kw, want):
        assert tool.shows_progress(row(**kw)) is want

    def test_it_reads_the_one_list_that_names_those_levels(self, tool):
        """A second list with the same contents would drift out of step with the
        sprint rule that reads this one."""
        assert set(tool.CONTAINER_TYPES) == {"epic", "initiative"}


class TestTheColumnStillLinesUp:
    def test_the_width_is_measured_from_what_is_printed(self, tool):
        """`3/6` is wider than `8`; a cell rendered outside the measurement
        pushes every row past the width the layout was chosen to fit."""
        columns = tool.board_columns([row(kind="epic", total=6, done=3),
                                      row(points=8.0)], 80)
        assert columns["points"] == 3

    def test_no_row_is_wider_than_the_board(self, tool):
        rows = [row(kind="epic", total=6, done=3, title="a" * 200), row(points=8.0)]
        assert max(len(line) for line in rendered(tool, rows).splitlines()) <= 80

    def test_the_heading_is_true_of_every_section(self, tool):
        """Widths come from all rows, not per section, so sections cannot stagger."""
        epics = [row(key="AGILE-1", kind="epic", total=6, done=3)]
        stories = [row(key="AGILE-2", points=8.0)]
        out = tool.render_board(VIEW, "kanban", epics + stories,
                                [("Todo", epics), ("In Progress", stories)],
                                "o", 4, 2, "-status:Done", 80)
        # The column is right-aligned, so the cells share an *end* offset: `3/6`
        # and `8` finish in the same place and begin in different ones.
        ends = {line.index("3/6") + 3 for line in out.splitlines() if "3/6" in line}
        ends |= {line.index("8") + 1 for line in out.splitlines()
                 if line.strip().startswith("AGILE-2")}
        assert len(ends) == 1, f"the two cells do not right-align: {ends}"

    def test_a_wrapped_title_still_indents_to_the_title_column(self, tool):
        """#126's wrapping is not disturbed by what the points column holds."""
        out = rendered(tool, [row(kind="epic", total=6, done=3,
                                  title="a very long title " * 6)], 60)
        lines = [line for line in out.splitlines() if line.startswith(" ")]
        continuation = [line for line in lines if "AGILE-9" not in line and line.strip()
                        and "pts" not in line and "─" not in line]
        assert continuation, "expected the title to wrap"
        assert len({len(line) - len(line.lstrip()) for line in continuation}) == 1


class TestTheLegend:
    def test_it_appears_when_the_column_holds_two_kinds_of_value(self, tool):
        out = rendered(tool, [row(kind="epic", total=6, done=3), row(points=8.0)])
        assert "pts: story points, or closed/total sub-issues for epics and initiatives" in out

    def test_it_says_closed_and_never_done(self, tool):
        """A child closed as NOT_PLANNED counts, and abandoned is not completed."""
        out = rendered(tool, [row(kind="epic", total=6, done=3)])
        legend = next(line for line in out.splitlines() if line.startswith("pts:"))
        assert "closed" in legend
        assert "done" not in legend and "completed" not in legend

    def test_it_is_absent_on_a_board_of_stories(self, tool):
        """Said only where it is true, or it is noise on every backlog."""
        assert "pts: story points" not in rendered(tool, [row(points=8.0)])

    def test_it_is_absent_when_an_epic_has_no_children(self, tool):
        assert "pts: story points" not in rendered(tool, [row(kind="epic", total=0)])

    def test_it_is_absent_on_a_board_of_stories_with_task_lists(self, tool):
        """The legend and the behaviour say the same thing or neither is trusted."""
        assert "pts: story points" not in rendered(tool, [row(total=4, done=1)])

    def test_it_names_the_two_levels_it_applies_to(self, tool):
        out = rendered(tool, [row(kind="epic", total=6, done=3)])
        legend = next(line for line in out.splitlines() if line.startswith("pts:"))
        assert "epics and initiatives" in legend


class TestBoardRowCarriesTheCounts:
    @staticmethod
    def item(total, done):
        return {
            "id": "PVTI_1", "isArchived": False, "fieldValues": {"nodes": []},
            "content": {
                "__typename": "Issue", "number": 9, "title": "t", "url": "u",
                "state": "OPEN", "repository": {"nameWithOwner": "o/r"},
                "labels": {"nodes": [{"name": "type:epic"}]},
                "assignees": {"nodes": []},
                "subIssuesSummary": {"total": total, "completed": done},
            },
        }

    def test_the_counts_are_carried_through(self, tool):
        got = tool.board_row(self.item(6, 3), {})
        assert (got["sub_issues_total"], got["sub_issues_done"]) == (6, 3)

    def test_an_absent_summary_is_zero_not_none(self, tool):
        item = self.item(0, 0)
        del item["content"]["subIssuesSummary"]
        got = tool.board_row(item, {})
        assert (got["sub_issues_total"], got["sub_issues_done"]) == (0, 0)

    def test_the_jsonl_carries_numbers_not_a_rendered_string(self, tool):
        """So a reader does not have to parse "3/6"."""
        import argparse
        rows = [tool.board_row(self.item(6, 3), {})]
        args = argparse.Namespace(owner="o", project=4)
        out = tool.board_jsonl(VIEW, "kanban", rows, [("Todo", rows)], args,
                               "-status:Done", 1, "2026-09-16T00:00:00Z")
        item = json.loads(out.splitlines()[1])
        assert item["sub_issues_total"] == 6 and item["sub_issues_done"] == 3
