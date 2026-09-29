"""Initiatives belong on the roadmap, above their epics. AGILE-176, under #173.

The roadmap's filter was `label:type:epic`, which excludes `type:initiative` by
construction -- so the top of the hierarchy was missing from the one view that
exists to show the shape of the plan.

**`level:container` follows the `initiative:` precedent**, which is the pattern
this codebase already had for a shorthand: a term the tool understands, expanded
by `github_filter` into something GitHub's own view evaluates the same way, so
the web UI and `board show` cannot disagree about what a board shows.

**And a shorthand that expands must parse on the way home.** A board's filter
comes *back* from the view it was written to: `github_filter` writes
`label:type:initiative,type:epic`, and `board show` then reads that string. Found
by running it -- the roadmap it had just written matched **0 of 86 items** --
which is why a comma is now OR, exactly as GitHub means it.

**The tree is drawn per section**, and the usual objection does not apply: a
status-grouped board separates a parent from its children by construction, but
this one groups by when work began, and an initiative is dated by the earliest
start among its epics -- so a parent and the child that dated it land together.
"""

from __future__ import annotations

import argparse
import json

import pytest


def item(number, kind, *, sprint_stamps=(), parent=None, repo="o/r", state="OPEN"):
    labels = [{"name": f"type:{kind}"}, {"name": "key:AGILE"}]
    labels += [{"name": f"sprint:{d}"} for d in sprint_stamps]
    content = {
        "__typename": "Issue", "number": number, "title": f"issue {number}",
        "url": "u", "state": state, "repository": {"nameWithOwner": repo},
        "labels": {"nodes": labels}, "assignees": {"nodes": []},
        "subIssuesSummary": {"total": 0, "completed": 0},
    }
    if parent:
        content["parent"] = {
            "number": parent, "title": f"issue {parent}",
            "repository": {"nameWithOwner": repo},
            "labels": {"nodes": [{"name": "type:initiative"}]}}
    return {"id": f"PVTI_{number}", "isArchived": False,
            "fieldValues": {"nodes": []}, "content": content}


def matches(tool, it, text):
    return tool.item_matches(it, tool.parse_filter(text), current_sprint=None)


class TestTheLevelTerm:
    @pytest.mark.parametrize("kind,hit", [
        ("initiative", True), ("epic", True),
        ("story", False), ("bug", False), ("task", False)])
    def test_container_is_the_two_levels_that_hold_work(self, tool, kind, hit):
        assert matches(tool, item(1, kind), "level:container") is hit

    def test_it_reads_the_one_list(self, tool):
        """`CONTAINER_TYPES` again, so a level added there is admitted here."""
        for level in tool.CONTAINER_TYPES:
            assert matches(tool, item(1, level), "level:container")

    def test_a_named_level_matches_only_itself(self, tool):
        assert matches(tool, item(1, "epic"), "level:epic")
        assert not matches(tool, item(1, "initiative"), "level:epic")

    def test_it_negates(self, tool):
        assert not matches(tool, item(1, "epic"), "-level:container")
        assert matches(tool, item(1, "story"), "-level:container")

    def test_the_term_is_documented(self, tool):
        """`FILTER_TERMS` is where a term's meaning lives, and an undocumented
        one is refused rather than ignored."""
        assert "level" in tool.FILTER_TERMS
        assert "container" in tool.FILTER_TERMS["level"]


class TestItSurvivesTheRoundTrip:
    def test_it_expands_to_labels_github_evaluates(self, tool):
        """GitHub knows `label:` and does not know `level:`."""
        assert tool.github_filter("level:container") == \
            "label:type:initiative,type:epic"

    def test_a_named_level_expands_too(self, tool):
        assert tool.github_filter("level:epic") == "label:type:epic"

    def test_negation_survives_expansion(self, tool):
        assert tool.github_filter("-level:container").startswith("-label:")

    def test_the_expanded_form_matches_what_the_shorthand_did(self, tool):
        """**The defect this found.** The view stores the expanded string and
        `board show` reads it back -- without comma-OR the roadmap it had just
        written matched nothing."""
        expanded = tool.github_filter("level:container")
        for kind in ("initiative", "epic"):
            assert matches(tool, item(1, kind), expanded), kind
        assert not matches(tool, item(1, "story"), expanded)

    def test_a_comma_is_or_generally(self, tool):
        """GitHub's own meaning, so a filter typed in the web UI works here."""
        assert matches(tool, item(1, "bug"), "label:type:bug,type:story")

    def test_a_negated_comma_excludes_every_alternative(self, tool):
        assert not matches(tool, item(1, "bug"), "-label:type:bug,type:story")
        assert matches(tool, item(1, "epic"), "-label:type:bug,type:story")

    def test_a_space_still_separates_terms_not_alternatives(self, tool):
        """Comma is OR *within* a term; a space is a new term, in this language
        and in GitHub's. `label:a, b` is therefore two terms, and the second is
        refused like any unknown one -- comma-OR must not weaken that."""
        with pytest.raises(SystemExit) as exit_info:
            matches(tool, item(1, "epic"), "label:type:bug, type:epic")
        assert "type" in str(exit_info.value)

    def test_an_unknown_term_is_still_refused(self, tool):
        """Refused, never ignored: dropping a term renders another team's work
        under this team's name and looks entirely plausible."""
        with pytest.raises(SystemExit):
            matches(tool, item(1, "epic"), "nonsense:value")


class TestTheRoadmapShowsBothLevels:
    def test_the_board_type_admits_containers(self, tool):
        assert "level:container" in tool.BOARD_TYPES["roadmap"]["filter"]

    def test_and_keeps_174_s_exclusions(self, tool):
        """A roadmap answers where we are going, so finished work stays off."""
        spec = tool.BOARD_TYPES["roadmap"]["filter"]
        assert "-status:Done" in spec and "is:open" in spec

    def test_the_two_stories_do_not_fight_over_the_string(self, tool):
        """Composed, not replaced: #174's terms survive #176's change."""
        written = tool.github_filter(tool.BOARD_TYPES["roadmap"]["filter"])
        assert written == "label:type:initiative,type:epic -status:Done is:open"


class TestTheTreeInsideASection:
    @staticmethod
    def row(tool, number, kind, *, parent="", on="2026-09-14", section="Sprint 3"):
        return {"key": f"A-{number}", "number": number, "repository": "o/r",
                "title": f"issue {number}", "type": kind, "status": "Todo",
                "sprint": None, "story_points": None, "assignees": [],
                "labels": [], "parent_key": parent, "parent_type": "",
                "state": "OPEN", "sub_issues_total": 0, "sub_issues_done": 0,
                "started_in": section, "started_on": on}

    def test_an_epic_is_indented_under_its_initiative(self, tool):
        rows = [self.row(tool, 2, "epic", parent="A-1"), self.row(tool, 1, "initiative")]
        _name, items = tool.board_sections(rows, "start", [], [])[0]
        assert [(r["depth"], r["key"]) for r in items] == [(0, "A-1"), (1, "A-2")]

    def test_an_epic_with_no_initiative_stays_at_the_top(self, tool):
        """An initiative is optional; a roadmap must not hide an epic for
        lacking one."""
        rows = [self.row(tool, 1, "epic")]
        _name, items = tool.board_sections(rows, "start", [], [])[0]
        assert items[0]["depth"] == 0

    def test_an_initiative_is_listed_once(self, tool):
        """An epic starting in a later section appears there under no repeated
        parent: the initiative is dated by when its work began, stated once."""
        early = [self.row(tool, 1, "initiative"),
                 self.row(tool, 2, "epic", parent="A-1")]
        late = [self.row(tool, 3, "epic", parent="A-1", on="2026-09-28",
                         section="0005 W40-2026")]
        sections = tool.board_sections(early + late, "start", [], [])
        keys = [[r["key"] for r in items] for _name, items in sections]
        assert keys == [["A-1", "A-2"], ["A-3"]]

    def test_and_that_later_epic_is_not_indented_under_nothing(self, tool):
        early = [self.row(tool, 1, "initiative")]
        late = [self.row(tool, 3, "epic", parent="A-1", on="2026-09-28",
                         section="0005 W40-2026")]
        sections = tool.board_sections(early + late, "start", [], [])
        _name, items = sections[1]
        assert items[0]["depth"] == 0

    def test_the_sections_still_run_in_date_order(self, tool):
        """#151's axis is untouched."""
        rows = [self.row(tool, 1, "epic", on="2026-09-28", section="later"),
                self.row(tool, 2, "epic", on="2026-09-14", section="earlier")]
        names = [name for name, _ in tool.board_sections(rows, "start", [], [])]
        assert names[0].startswith("earlier")


class TestTheShapeReachesAReader:
    def test_the_jsonl_carries_the_level_and_the_parent(self, tool):
        """So the indent is presentation, not the only place the shape exists."""
        rows = [tool.board_row(item(2, "epic", parent=1), {"o/r": "AGILE"})]
        out = tool.board_jsonl({"name": "R", "layout": "ROADMAP_LAYOUT", "filter": ""},
                               "roadmap", rows, [("s", tool.hierarchy_order(rows))],
                               argparse.Namespace(owner="o", project=4), "", 1,
                               "2026-09-29T00:00:00Z")
        row = json.loads(out.splitlines()[1])
        assert row["type"] == "epic"
        assert row["parent_key"] == "AGILE-1"
        assert row["parent_type"] == "initiative"
        assert row["depth"] == 0
