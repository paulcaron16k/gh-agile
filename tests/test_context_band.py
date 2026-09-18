"""The derived context band above the scrum board. AGILE-118, under #114.

A scrum board filters on `sprint:@current`. A container is deliberately in no
sprint (#115), so the board looked at every day is the one place the larger work
cannot appear among the rows -- and the only way onto it used to be pinning the
epic to a sprint, which is the defect #115 removed.

So the band is *rendered* rather than filtered: above the status columns, naming
the initiatives and epics the displayed work belongs to, each with the
`closed/total` tally from #116.

**Membership is derived from the sprint's own contents**, not from the
containers' status: the parents of the items the filter selected, walked upward.
It cannot go stale and needs no epic status maintained to be correct. Keying it
off `In Progress` would list containers with nothing in this sprint and miss one
whose status nobody updated.

**It shows items the filter excludes**, which is a departure. A board here is
reconstructed from its filter and an unknown filter term is refused rather than
ignored, precisely so a board cannot quietly show the wrong set. The band is the
deliberate exception, so it is labelled as derived and kept out of the table.

Offline: items are built by hand; nothing here reaches GitHub.
"""

from __future__ import annotations

import argparse
import json

VIEW = {"name": "Sprint board", "layout": "BOARD_LAYOUT", "filter": "sprint:@current"}


def item(number, kind, *, title=None, repo="o/r", parent=None, total=0, done=0,
         status="In Progress", sprint="S3"):
    """A project item as `fetch_items` returns one."""
    content = {
        "__typename": "Issue", "number": number, "title": title or f"issue {number}",
        "url": "u", "state": "OPEN", "repository": {"nameWithOwner": repo},
        "labels": {"nodes": [{"name": f"type:{kind}"}]},
        "assignees": {"nodes": []},
        "subIssuesSummary": {"total": total, "completed": done},
    }
    if parent is not None:
        content["parent"] = parent
    values = []
    if sprint:
        values.append({"__typename": "ProjectV2ItemFieldIterationValue",
                       "title": sprint, "field": {"name": "Sprint"}})
    if status:
        values.append({"__typename": "ProjectV2ItemFieldSingleSelectValue",
                       "name": status, "field": {"name": "Status"}})
    return {"id": f"PVTI_{number}", "isArchived": False,
            "fieldValues": {"nodes": values}, "content": content}


def parent_of(number, kind, *, title=None, repo="o/r"):
    """The `parent` snippet the selection carries on a child."""
    return {"number": number, "title": title or f"issue {number}",
            "repository": {"nameWithOwner": repo},
            "labels": {"nodes": [{"name": f"type:{kind}"}]}}


class TestMembership:
    def test_the_parent_of_a_shown_item_is_listed(self, tool):
        story = item(10, "story", parent=parent_of(9, "epic"))
        epic = item(9, "epic", total=6, done=3, sprint=None)
        got = tool.board_containers([story, epic], [story], {})
        # `o/r#9` rather than `9`: with no profile keys the fallback form is
        # what `issue_key` produces, and it is unambiguous across repositories.
        assert [(c["key"], c["type"], c["progress"]) for c in got] == [
            ("o/r#9", "epic", "3/6")]

    def test_the_whole_chain_is_walked(self, tool):
        """An initiative is as invisible on a scrum board as the epic was."""
        story = item(10, "story", parent=parent_of(9, "epic"))
        epic = item(9, "epic", total=6, done=3, sprint=None,
                    parent=parent_of(5, "initiative"))
        initiative = item(5, "initiative", total=1, done=0, sprint=None)
        got = tool.board_containers([story, epic, initiative], [story], {})
        assert [c["type"] for c in got] == ["initiative", "epic"]

    def test_initiatives_come_first(self, tool):
        """The band reads down the hierarchy."""
        story = item(10, "story", parent=parent_of(9, "epic"))
        epic = item(9, "epic", sprint=None, parent=parent_of(5, "initiative"))
        initiative = item(5, "initiative", sprint=None)
        got = tool.board_containers([story, epic, initiative], [story], {})
        assert got[0]["type"] == "initiative"

    def test_a_container_with_nothing_in_the_sprint_is_absent(self, tool):
        """Derived from the sprint's contents, not from the containers' status."""
        story = item(10, "story", parent=parent_of(9, "epic"))
        other = item(11, "epic", total=2, sprint=None)
        got = tool.board_containers([story, item(9, "epic", sprint=None), other],
                                    [story], {})
        assert [c["key"] for c in got] == ["o/r#9"]

    def test_one_entry_however_many_children_are_shown(self, tool):
        shown = [item(n, "story", parent=parent_of(9, "epic")) for n in (10, 11, 12)]
        got = tool.board_containers([*shown, item(9, "epic", sprint=None)], shown, {})
        assert len(got) == 1

    def test_a_story_parent_is_not_a_container(self, tool):
        """Once tasks exist, a task's story parent does not belong in the band."""
        task = item(10, "task", parent=parent_of(9, "story"))
        got = tool.board_containers([task, item(9, "story")], [task], {})
        assert got == []

    def test_an_item_with_no_parent_contributes_nothing(self, tool):
        story = item(10, "story")
        assert tool.board_containers([story], [story], {}) == []


class TestAParentOffTheBoard:
    """Naming it understates nothing; dropping it would. *Empty is not excluded*
    is the rule this board already follows."""

    def test_it_is_still_named(self, tool):
        story = item(10, "story", parent=parent_of(9, "epic", title="an epic"))
        got = tool.board_containers([story], [story], {})
        assert [(c["key"], c["title"]) for c in got] == [("o/r#9", "an epic")]

    def test_it_carries_no_tally_it_cannot_know(self, tool):
        story = item(10, "story", parent=parent_of(9, "epic"))
        assert tool.board_containers([story], [story], {})[0]["progress"] == "—"


class TestRendering:
    @staticmethod
    def rendered(tool, rows, containers, width=80):
        return tool.render_board(VIEW, "scrum", rows, [("Done", rows)], "o", 4,
                                 len(rows), "sprint:@current", width, containers)

    @staticmethod
    def row(tool, it):
        return tool.board_row(it, {})

    def test_it_is_labelled_as_derived(self, tool):
        rows = [self.row(tool, item(10, "story"))]
        out = self.rendered(tool, rows, [{"key": "A-9", "type": "epic",
                                          "progress": "3/6", "title": "an epic"}])
        assert "derived" in out
        assert "not selected by the filter" in out

    def test_it_sits_above_the_column_heading(self, tool):
        rows = [self.row(tool, item(10, "story"))]
        out = self.rendered(tool, rows, [{"key": "A-9", "type": "epic",
                                          "progress": "3/6", "title": "an epic"}])
        assert out.index("an epic") < out.index("  key ")

    def test_it_lines_up_with_the_table(self, tool):
        """A band naming an `initiative` against rows that are all `story` used
        to overflow the type cell and push every band line out of alignment."""
        rows = [self.row(tool, item(10, "story"))]
        out = self.rendered(tool, rows, [{"key": "AGILE-119", "type": "initiative",
                                          "progress": "0/1", "title": "an initiative"}])
        band = next(line for line in out.splitlines() if "an initiative" in line)
        heading = next(line for line in out.splitlines() if line.startswith("  key "))
        assert band.index("initiative") == heading.index("type")

    def test_nothing_is_wider_than_the_board(self, tool):
        rows = [self.row(tool, item(10, "story"))]
        out = self.rendered(tool, rows, [{"key": "A-9", "type": "epic", "progress": "3/6",
                                          "title": "a very long name " * 8}])
        assert max(len(line) for line in out.splitlines()) <= 80

    def test_a_long_name_wraps_rather_than_eliding(self, tool):
        rows = [self.row(tool, item(10, "story"))]
        out = self.rendered(tool, rows, [{"key": "A-9", "type": "epic", "progress": "3/6",
                                          "title": "a very long name " * 8}])
        assert "…" not in out
        assert out.count("a very long name") > 1, "expected it to wrap"

    def test_no_containers_prints_no_band(self, tool):
        """The `who` column's rule: present only when it has something to say."""
        rows = [self.row(tool, item(10, "story"))]
        assert "derived" not in self.rendered(tool, rows, [])

    def test_the_band_is_not_a_status_section(self, tool):
        """The item counts and the `empty:` line are what they were."""
        rows = [self.row(tool, item(10, "story"))]
        with_band = self.rendered(tool, rows, [{"key": "A-9", "type": "epic",
                                                "progress": "3/6", "title": "an epic"}])
        assert "1 of 1 items" in with_band
        assert "Done (1)" in with_band


class TestTheRowsAreUnchanged:
    def test_the_table_is_byte_identical_apart_from_column_width(self, tool):
        """The band may widen a shared column; it must not alter a row otherwise."""
        rows = [tool.board_row(item(10, "story", title="a story"), {})]
        containers = [{"key": "A-9", "type": "epic", "progress": "3/6", "title": "e"}]
        without = tool.render_board(VIEW, "scrum", rows, [("Done", rows)], "o", 4, 1,
                                    "sprint:@current", 80, [])
        with_band = tool.render_board(VIEW, "scrum", rows, [("Done", rows)], "o", 4, 1,
                                      "sprint:@current", 80, containers)
        table = [line for line in with_band.splitlines() if "a story" in line]
        assert [line for line in without.splitlines() if "a story" in line] == table


class TestJsonl:
    def test_a_container_is_its_own_record_kind(self, tool):
        rows = [tool.board_row(item(10, "story"), {})]
        out = tool.board_jsonl(VIEW, "scrum", rows, [("Done", rows)],
                               argparse.Namespace(owner="o", project=4),
                               "sprint:@current", 1, "2026-09-18T00:00:00Z",
                               [{"key": "A-9", "type": "epic", "progress": "3/6",
                                 "title": "an epic"}])
        kinds = [json.loads(line)["kind"] for line in out.splitlines()]
        assert kinds == ["board", "container", "item"]

    def test_no_containers_adds_no_records(self, tool):
        rows = [tool.board_row(item(10, "story"), {})]
        out = tool.board_jsonl(VIEW, "scrum", rows, [("Done", rows)],
                               argparse.Namespace(owner="o", project=4),
                               "sprint:@current", 1, "2026-09-18T00:00:00Z", [])
        assert [json.loads(line)["kind"] for line in out.splitlines()] == ["board", "item"]
