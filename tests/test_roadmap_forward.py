"""The roadmap carries work that is ahead, not work that is done. AGILE-174, under #173.

`BOARD_TYPES["roadmap"]` was `label:type:epic` and nothing else -- the only
non-scrum type that kept finished work, where `kanban` is `-status:Done` and
`backlog` is `no:sprint -status:Done`. Measured on project #4 the day this was
filed:

    $ gh agile board show Roadmap
    roadmap - 12 of 81 items   filter: label:type:epic
      AGILE-9  7/7   AGILE-10  9/9   AGILE-12  3/3   AGILE-26  6/6  ...
      (not started) (1)  REPORTS-1

    $ gh agile board show Roadmap --filter=-status:Done
    roadmap - 1 of 81 items

**Twelve of twelve epics complete.** And the sections ascend by start, so those
twelve printed *above* the one thing actually ahead: a reader scrolled backwards
through history to reach the future.

The usual defence of history on a roadmap -- that watching Q1's epic land in Q2
is what makes next quarter's plan readable -- needs a baseline, and there is
none. The sections come from when work *began*, derived from the descendants'
`sprint:` labels; nothing records what was planned. So a finished epic here says
a thing happened, not that it slipped. `#175` adds a target date, and the
question is worth reopening then.

**Two terms, because `-status:Done` alone is not the same question.** An epic
closed as *not planned* need not carry Status `Done` -- the state-vs-Status gap
`#138` exists for -- and abandoned work left on a roadmap is worse than finished
work, because it is not coming.

Offline: `item_matches` against the real base filter, no project.
"""

from __future__ import annotations

import pytest


def item(*, number=1, status=None, state="OPEN", labels=("type:epic",)):
    fields = []
    if status is not None:
        fields.append({"__typename": "ProjectV2ItemFieldSingleSelectValue",
                       "name": status, "field": {"name": "Status"}})
    return {
        "id": f"PVTI_{number}", "isArchived": False,
        "fieldValues": {"nodes": fields},
        "content": {
            "__typename": "Issue", "number": number, "title": "an epic", "url": "u",
            "state": state, "repository": {"nameWithOwner": "o/r"},
            "labels": {"nodes": [{"name": n} for n in labels]},
            "assignees": {"nodes": []}, "parent": None,
        },
    }


@pytest.fixture
def on_roadmap(tool):
    """Whether the roadmap's own base filter admits this item."""
    terms = tool.parse_filter(tool.BOARD_TYPES["roadmap"]["filter"])

    def go(it):
        return tool.item_matches(it, terms, current_sprint=None)
    return go


class TestWhatTheRoadmapShows:
    def test_an_epic_in_flight_is_on_it(self, on_roadmap):
        assert on_roadmap(item(status="In Progress"))

    def test_an_epic_not_started_is_on_it(self, on_roadmap):
        """`(not started)` is the remainder section, and is the point of the view."""
        assert on_roadmap(item(status="Todo"))

    def test_an_epic_with_no_status_is_on_it(self, on_roadmap):
        """Unplaced is not finished. A roadmap must not hide work for being untidy."""
        assert on_roadmap(item(status=None))

    def test_a_finished_epic_is_not(self, on_roadmap):
        assert not on_roadmap(item(status="Done", state="CLOSED"))

    def test_an_abandoned_epic_is_not(self, on_roadmap):
        """**The case `-status:Done` alone would miss.** Closed as not planned, so
        the Status field was never moved to Done -- and it is not coming back."""
        assert not on_roadmap(item(status="In Progress", state="CLOSED"))

    def test_a_closed_epic_whose_status_never_caught_up_is_not(self, on_roadmap):
        """The `#138` shape: `Closes #n` sets the state and nothing else. Finished
        work showing as live is exactly what the roadmap must not do."""
        assert not on_roadmap(item(status="Todo", state="CLOSED"))

    def test_a_story_is_not_on_it_however_open(self, on_roadmap):
        """The level filter still decides; the new terms only subtract."""
        assert not on_roadmap(item(status="In Progress", labels=("type:story",)))


class TestTheTypesAgree:
    def test_roadmap_is_no_longer_the_one_that_keeps_finished_work(self, tool):
        """The reason this was a defect rather than a preference: every other
        non-scrum type already excluded it, so roadmap was the odd one out."""
        for kind in ("kanban", "backlog", "roadmap"):
            assert "-status:Done" in tool.BOARD_TYPES[kind]["filter"]

    def test_scrum_still_does_not_exclude_it(self, tool):
        """A sprint board shows the sprint's Done column -- that is the burndown."""
        assert "-status:Done" not in tool.BOARD_TYPES["scrum"]["filter"]

    def test_every_term_is_one_the_evaluator_knows(self, tool):
        """A term outside `FILTER_TERMS` is refused, so a base filter carrying one
        would make its own board unrenderable."""
        for kind, spec in tool.BOARD_TYPES.items():
            for _neg, key, _value in tool.parse_filter(spec["filter"]):
                assert key in tool.FILTER_TERMS, f"{kind} uses {key}"


class TestABoardIsStillRecognised:
    """Changing a base filter breaks the substring match that names a view's type.

    `board_kind` asks whether the type's base filter appears in the view's, which
    holds while a board is in step with this tool and fails the moment the spec
    changes underneath it. A roadmap created before this story carries
    `label:type:epic`, which no longer contains the spec -- so `board list` would
    have called project #4's view #9 `custom` until someone re-ran `setup`.
    """

    def test_a_converged_roadmap_is_a_roadmap(self, tool):
        view = {"name": "Roadmap", "layout": "ROADMAP_LAYOUT",
                "filter": tool.BOARD_TYPES["roadmap"]["filter"]}
        assert tool.board_kind(view, {}) == "roadmap"

    def test_one_created_before_this_story_is_still_a_roadmap(self, tool):
        """The regression this guards. The layout is what the web UI draws, and
        only the roadmap type uses it."""
        view = {"name": "Roadmap", "layout": "ROADMAP_LAYOUT",
                "filter": "label:type:epic"}
        assert tool.board_kind(view, {}) == "roadmap"

    def test_an_extra_filter_does_not_hide_the_type(self, tool):
        """`make_board` appends the caller's `--filter` to the base."""
        view = {"name": "Team roadmap", "layout": "ROADMAP_LAYOUT",
                "filter": tool.BOARD_TYPES["roadmap"]["filter"] + " label:key:AGILE"}
        assert tool.board_kind(view, {}) == "roadmap"

    def test_the_profile_still_wins(self, tool):
        """A declared type is the author's statement and outranks both signals."""
        view = {"name": "Roadmap", "layout": "ROADMAP_LAYOUT", "filter": ""}
        config = {"boards": [{"name": "Roadmap", "type": "kanban"}]}
        assert tool.board_kind(view, config) == "kanban"

    def test_a_table_view_is_still_custom(self, tool):
        """`TABLE_LAYOUT` is shared by backlog and custom, so it decides nothing
        and must not be guessed at."""
        view = {"name": "View 1", "layout": "TABLE_LAYOUT", "filter": ""}
        assert tool.board_kind(view, {}) == "custom"

    def test_a_board_layout_view_is_still_custom(self, tool):
        """Shared by scrum and kanban, for the same reason."""
        view = {"name": "Mine", "layout": "BOARD_LAYOUT", "filter": "label:mine"}
        assert tool.board_kind(view, {}) == "custom"
