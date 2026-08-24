"""Rendering a board as text: the filter evaluator, the sections, the naming.

**`ProjectV2View` has no `items` field.** Introspected 2026-08-24: a view exposes
`filter` as an opaque string plus `layout`, `verticalGroupByFields` and
`sortByFields`, and there is no way to ask GitHub what a view displays. So the
text board is *reconstructed* from the same inputs the web UI uses, and the
filter is evaluated here.

That puts the correctness of the whole feature in `parse_filter`, `item_matches`
and `status_excluded`. A term silently dropped would render a board that looks
entirely plausible and shows another team's work under this team's name, so an
unreadable term is refused instead. These tests are that guarantee.
"""

from __future__ import annotations

import pytest


def item(*, number=1, status=None, sprint=None, labels=(), state="OPEN",
         typename="Issue", title="a title", points=None, repo="o/r", archived=False):
    """A `fetch_items` node, trimmed to what the board path reads."""
    fields = []
    if status is not None:
        fields.append({"__typename": "ProjectV2ItemFieldSingleSelectValue",
                       "name": status, "field": {"name": "Status"}})
    if sprint is not None:
        fields.append({"__typename": "ProjectV2ItemFieldIterationValue",
                       "title": sprint, "field": {"name": "Sprint"}})
    if points is not None:
        fields.append({"__typename": "ProjectV2ItemFieldNumberValue",
                       "number": points, "field": {"name": "Story Points"}})
    return {
        "id": f"PVTI_{number}", "isArchived": archived,
        "fieldValues": {"nodes": fields},
        "content": {
            "__typename": typename, "number": number, "title": title, "url": "u",
            "state": state, "repository": {"nameWithOwner": repo},
            "labels": {"nodes": [{"name": n} for n in labels]},
            "assignees": {"nodes": []}, "parent": None,
        },
    }


def matches(tool, it, text, current=None):
    return tool.item_matches(it, tool.parse_filter(text), current_sprint=current)


class TestParseFilter:
    def test_a_plain_term(self, tool):
        assert tool.parse_filter("status:Done") == [(False, "status", "Done")]

    def test_negation(self, tool):
        assert tool.parse_filter("-status:Done") == [(True, "status", "Done")]

    def test_a_value_containing_a_colon_stays_whole(self, tool):
        """`label:key:AGILE` is one term whose value has a colon in it."""
        assert tool.parse_filter("label:key:AGILE") == [(False, "label", "key:AGILE")]

    def test_a_quoted_value_keeps_its_space(self, tool):
        """A view filter writes a multi-word status as status:"In Progress"."""
        assert tool.parse_filter('status:"In Progress"') == [(False, "status", "In Progress")]

    def test_several_terms(self, tool):
        assert tool.parse_filter("no:sprint -status:Done") == [
            (False, "no", "sprint"), (True, "status", "Done")]

    def test_an_empty_filter_is_no_terms(self, tool):
        assert tool.parse_filter("") == []
        assert tool.parse_filter(None) == []

    def test_an_unknown_term_is_refused_not_ignored(self, tool):
        """The whole point: a dropped term shows the wrong items convincingly."""
        with pytest.raises(SystemExit) as exit_info:
            tool.parse_filter("assignee:someone")
        message = str(exit_info.value)
        assert "'assignee' is not one this tool can evaluate" in message
        assert "refused rather than ignored" in message
        assert "status" in message and "sprint" in message   # it lists what works

    def test_a_term_with_no_value_is_refused(self, tool):
        with pytest.raises(SystemExit):
            tool.parse_filter("status")

    def test_the_key_is_case_insensitive(self, tool):
        assert tool.parse_filter("STATUS:Done") == [(False, "status", "Done")]


class TestItemMatches:
    def test_status(self, tool):
        assert matches(tool, item(status="Done"), "status:Done")
        assert not matches(tool, item(status="Todo"), "status:Done")

    def test_status_accepts_the_hyphen_alias(self, tool):
        """`same_status` is shared, so a board filter and `move` agree."""
        assert matches(tool, item(status="In Progress"), "status:In-Progress")

    def test_negated_status(self, tool):
        assert matches(tool, item(status="Todo"), "-status:Done")
        assert not matches(tool, item(status="Done"), "-status:Done")

    def test_an_item_with_no_status_survives_a_negated_status(self, tool):
        """`-status:Done` means "not Done", and an unset status is not Done."""
        assert matches(tool, item(status=None), "-status:Done")

    def test_sprint_current(self, tool):
        assert matches(tool, item(sprint="Sprint 1"), "sprint:@current", current="Sprint 1")
        assert not matches(tool, item(sprint="Sprint 2"), "sprint:@current", current="Sprint 1")

    def test_sprint_current_with_no_active_sprint_matches_nothing(self, tool):
        """Which is why `Team: AGILE` renders empty when @current has no items."""
        assert not matches(tool, item(sprint="Sprint 1"), "sprint:@current", current=None)

    def test_sprint_by_title(self, tool):
        assert matches(tool, item(sprint="AGILE Sprint 4"), 'sprint:"AGILE Sprint 4"')

    def test_no_sprint(self, tool):
        assert matches(tool, item(sprint=None), "no:sprint")
        assert not matches(tool, item(sprint="Sprint 1"), "no:sprint")

    def test_label(self, tool):
        assert matches(tool, item(labels=["type:epic"]), "label:type:epic")
        assert not matches(tool, item(labels=["type:story"]), "label:type:epic")

    def test_negated_label(self, tool):
        assert matches(tool, item(labels=["type:story"]), "-label:type:epic")

    def test_is_open_and_closed(self, tool):
        assert matches(tool, item(state="OPEN"), "is:open")
        assert not matches(tool, item(state="OPEN"), "is:closed")
        assert matches(tool, item(state="CLOSED"), "is:closed")

    def test_terms_are_anded(self, tool):
        it = item(status="Todo", sprint=None, labels=["key:AGILE"])
        assert matches(tool, it, "no:sprint -status:Done label:key:AGILE")
        assert not matches(tool, it, "no:sprint -status:Done label:key:ZMBNI")

    def test_the_real_backlog_filter(self, tool):
        """`no:sprint -status:Done` -- an item in a sprint is out even if not Done."""
        assert not matches(tool, item(status="Todo", sprint="AGILE Sprint 4"),
                           "no:sprint -status:Done")

    def test_an_unknown_no_target_is_refused(self, tool):
        with pytest.raises(SystemExit):
            matches(tool, item(), "no:assignee")


class TestStatusExcluded:
    def test_a_negated_status_excludes_that_section(self, tool):
        """Kanban's `-status:Done` leaves Done *out*, not empty."""
        terms = tool.parse_filter("-status:Done")
        assert tool.status_excluded("Done", terms)
        assert not tool.status_excluded("Todo", terms)

    def test_a_positive_status_excludes_every_other_section(self, tool):
        terms = tool.parse_filter("status:Done")
        assert not tool.status_excluded("Done", terms)
        assert tool.status_excluded("Todo", terms)

    def test_no_status_excludes_all_named_sections(self, tool):
        terms = tool.parse_filter("no:status")
        assert all(tool.status_excluded(s, terms) for s in tool.STATUSES)

    def test_an_unrelated_filter_excludes_nothing(self, tool):
        terms = tool.parse_filter("no:sprint label:type:epic")
        assert not any(tool.status_excluded(s, terms) for s in tool.STATUSES)


class TestSections:
    KEYS = {"o/r": "AGILE"}

    def rows(self, tool, items):
        return [tool.board_row(i, self.KEYS) for i in items]

    def test_status_grouping_follows_the_declared_order(self, tool):
        rows = self.rows(tool, [item(number=2, status="Done"), item(number=1, status="Todo")])
        got = tool.board_sections(rows, "status", [], [])
        assert [name for name, _ in got] == list(tool.STATUSES)

    def test_an_excluded_status_is_dropped_from_the_sections(self, tool):
        rows = self.rows(tool, [item(number=1, status="Todo")])
        terms = tool.parse_filter("-status:Done")
        got = tool.board_sections(rows, "status", [], terms)
        assert "Done" not in [name for name, _ in got]

    def test_an_allowed_but_empty_status_is_kept(self, tool):
        """"In Review is empty" is a fact a board exists to show."""
        rows = self.rows(tool, [item(number=1, status="Todo")])
        got = dict(tool.board_sections(rows, "status", [], []))
        assert got["In Review"] == []

    def test_an_unrecognised_status_gets_its_own_section(self, tool):
        rows = self.rows(tool, [item(number=1, status="Icebox")])
        got = dict(tool.board_sections(rows, "status", [], []))
        assert [r["number"] for r in got["Icebox"]] == [1]

    def test_a_table_layout_is_one_flat_section(self, tool):
        rows = self.rows(tool, [item(number=2), item(number=1)])
        got = tool.board_sections(rows, None, [], [])
        assert len(got) == 1
        assert [r["number"] for r in got[0][1]] == [1, 2]

    def test_sprint_grouping_follows_the_configuration_order(self, tool):
        rows = self.rows(tool, [item(number=1, sprint="Sprint 2"),
                                item(number=2, sprint="Sprint 1"),
                                item(number=3, sprint=None)])
        got = tool.board_sections(rows, "sprint", ["Sprint 1", "Sprint 2"], [])
        assert [name for name, _ in got] == ["Sprint 1", "Sprint 2", "(no sprint)"]


class TestBoardRow:
    def test_the_key_comes_from_the_key_label(self, tool):
        row = tool.board_row(item(number=24, labels=["key:AGILE"]), {})
        assert row["key"] == "AGILE-24"

    def test_the_type_comes_from_the_type_label(self, tool):
        assert tool.board_row(item(labels=["type:epic"]), {})["type"] == "epic"

    def test_points_keep_the_type_github_gave_them(self, tool):
        """The row feeds JSONL as well as the display, so it must not retype the field.

        This assertion used to be `== 8`, which passes for 8.0 as well and so
        caught nothing. Normalising here put `8` and `0.5` in one JSONL column,
        and a loader inferring the type from early rows would call it an integer
        and truncate the first half-point.
        """
        assert tool.board_row(item(points=8.0), {})["story_points"] == pytest.approx(8.0)
        assert isinstance(tool.board_row(item(points=8.0), {})["story_points"], float)

    def test_fractional_points_survive(self, tool):
        """Half-points for trivial work are a real convention; the field is a NUMBER."""
        assert tool.board_row(item(points=0.5), {})["story_points"] == pytest.approx(0.5)
        assert tool.board_row(item(points=1.5), {})["story_points"] == pytest.approx(1.5)

    def test_absent_fields_are_none_rather_than_missing(self, tool):
        row = tool.board_row(item(), {})
        assert row["status"] is None and row["sprint"] is None
        assert row["story_points"] is None


class TestSlug:
    @pytest.mark.parametrize("name,want", [
        ("Team: AGILE", "team-agile"),
        ("Engineering: all work", "engineering-all-work"),
        ("Backlog", "backlog"),
        ("  spaces  ", "spaces"),
        (":::", "board"),
    ])
    def test_slug(self, tool, name, want):
        assert tool.slug(name) == want


class TestFindView:
    VIEWS = [{"name": "Backlog"}, {"name": "Team: AGILE"}, {"name": "Team: ZMBNI"}]

    @pytest.fixture(autouse=True)
    def views(self, monkeypatch, tool):
        monkeypatch.setattr(tool, "views_of", lambda *a, **k: self.VIEWS)

    def test_an_exact_name(self, tool):
        assert tool.find_view("o", 1, "Backlog")["name"] == "Backlog"

    def test_an_unambiguous_substring(self, tool):
        assert tool.find_view("o", 1, "agile")["name"] == "Team: AGILE"

    def test_an_exact_name_wins_over_a_substring(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "views_of",
                            lambda *a, **k: [{"name": "Team"}, {"name": "Team: AGILE"}])
        assert tool.find_view("o", 1, "Team")["name"] == "Team"

    def test_an_ambiguous_substring_is_refused_and_lists_the_candidates(self, tool):
        with pytest.raises(SystemExit) as exit_info:
            tool.find_view("o", 1, "Team")
        message = str(exit_info.value)
        assert "more than one board" in message
        assert "Team: AGILE" in message and "Team: ZMBNI" in message

    def test_no_match_lists_what_there_is(self, tool):
        with pytest.raises(SystemExit) as exit_info:
            tool.find_view("o", 1, "nope")
        assert "Backlog" in str(exit_info.value)


class TestRenderPoints:
    """Whole numbers lose the `.0` for humans; fractions are left alone."""

    @pytest.mark.parametrize("points,want", [
        (8.0, "8"), (13.0, "13"), (1.0, "1"), (0.0, "0"),
        (0.5, "0.5"), (1.5, "1.5"), (2.25, "2.25"),
        (None, "—"), ("", "—"),
        (8, "8"),                      # already an int, e.g. a hand-built row
    ])
    def test_render_points(self, tool, points, want):
        assert tool.render_points(points) == want

    def test_the_display_normalises_and_the_row_does_not(self, tool):
        """Two different jobs: one is for reading, one is for loading."""
        row = tool.board_row(item(points=8.0), {})
        assert isinstance(row["story_points"], float)      # for a typed consumer
        assert tool.render_points(row["story_points"]) == "8"   # for a person
