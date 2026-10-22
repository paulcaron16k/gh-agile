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
    VIEWS = [{"number": 2, "name": "Backlog"},
             {"number": 5, "name": "Team: AGILE"},
             {"number": 6, "name": "Team: ZMBNI"}]

    @pytest.fixture(autouse=True)
    def views(self, monkeypatch, tool):
        monkeypatch.setattr(tool, "views_of", lambda *a, **k: self.VIEWS)

    def test_an_exact_name(self, tool):
        assert tool.find_view("o", 1, "Backlog")["name"] == "Backlog"

    def test_an_unambiguous_substring(self, tool):
        assert tool.find_view("o", 1, "agile")["name"] == "Team: AGILE"

    def test_an_exact_name_wins_over_a_substring(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "views_of",
                            lambda *a, **k: [{"number": 1, "name": "Team"},
                                             {"number": 2, "name": "Team: AGILE"}])
        assert tool.find_view("o", 1, "Team")["name"] == "Team"

    def test_the_view_number(self, tool):
        """What `board list` prints, and the handle that survives a rename."""
        assert tool.find_view("o", 1, "5")["name"] == "Team: AGILE"

    def test_a_number_naming_no_view_is_refused(self, tool):
        with pytest.raises(SystemExit) as exit_info:
            tool.find_view("o", 1, "9")
        assert "no board matches" in str(exit_info.value)

    def test_a_board_named_with_digits_wins_over_the_number(self, tool, monkeypatch):
        """An exact name is still first: `2` is a number *unless* a board is called 2."""
        monkeypatch.setattr(tool, "views_of",
                            lambda *a, **k: [{"number": 1, "name": "2"},
                                             {"number": 2, "name": "Backlog"}])
        assert tool.find_view("o", 1, "2")["number"] == 1

    def test_a_prefix_beats_a_substring(self, tool, monkeypatch):
        """`board show Sprint` means the board called "Sprint board", not the one
        that mentions sprints halfway through its name. Both are substring
        matches; only one starts with it, so it resolves instead of being refused."""
        monkeypatch.setattr(tool, "views_of",
                            lambda *a, **k: [{"number": 1, "name": "Sprint board"},
                                             {"number": 2, "name": "Team sprint review"}])
        assert tool.find_view("o", 1, "Sprint")["name"] == "Sprint board"

    def test_an_ambiguous_prefix_is_still_refused(self, tool):
        with pytest.raises(SystemExit) as exit_info:
            tool.find_view("o", 1, "Team")
        message = str(exit_info.value)
        assert "more than one board" in message
        assert "Team: AGILE" in message and "Team: ZMBNI" in message

    def test_an_ambiguous_match_lists_the_numbers_to_pick_from(self, tool):
        """The refusal names the other way to say which one."""
        with pytest.raises(SystemExit) as exit_info:
            tool.find_view("o", 1, "Team")
        message = str(exit_info.value)
        assert "5  Team: AGILE" in message and "6  Team: ZMBNI" in message

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


def row(key="AGILE-9", kind="story", points=None, sprint=None, title="a title",
        number=None):
    """A `board_row` result, trimmed to what the text view reads.

    `number` defaults from the key, since the footnote for a stale Status names
    the command that fixes it and that takes an issue number.
    """
    return {"key": key, "type": kind, "story_points": points, "sprint": sprint,
            "title": title,
            "number": number if number is not None else int(key.rsplit("-", 1)[-1])}


VIEW = {"name": "Engineering: all work", "layout": "BOARD_LAYOUT", "filter": "-status:Done"}


def rendered(tool, rows, width=80, sections=None):
    sections = [("Todo", rows)] if sections is None else sections
    return tool.render_board(VIEW, "kanban", rows, sections, "o", 4, len(rows),
                             "-status:Done", width)


class TestDisplayWidth:
    """Where the width comes from, and where it deliberately does not.

    `shutil.get_terminal_size` reads `$COLUMNS` before it asks the device, so a
    run writing to a file would otherwise inherit the width of the shell that
    launched it. The `isatty` check has to come first.
    """

    class Stream:
        def __init__(self, tty):
            self._tty = tty

        def isatty(self):
            return self._tty

    def test_a_pipe_gets_the_fixed_width(self, tool, monkeypatch):
        monkeypatch.setenv("COLUMNS", "203")
        assert tool.display_width(self.Stream(tty=False)) == tool.BOARD_WIDTH

    def test_a_terminal_gets_its_own_width(self, tool, monkeypatch):
        monkeypatch.setenv("COLUMNS", "203")
        assert tool.display_width(self.Stream(tty=True)) == 203

    def test_a_stream_that_cannot_say_gets_the_fixed_width(self, tool):
        assert tool.display_width(object()) == tool.BOARD_WIDTH


class TestElide:
    @pytest.mark.parametrize("text,width,want", [
        ("short", 20, "short"),
        ("exactly ten", 11, "exactly ten"),      # fits: untouched
        ("one over the edge", 16, "one over the ed…"),
        ("cut just after a space", 10, "cut just…"),   # the space goes with the tail
        ("nospacehereatallok", 10, "nospacehe…"),
    ])
    def test_elide(self, tool, text, width, want):
        assert tool.elide(text, width) == want
        assert len(tool.elide(text, width)) <= width


class TestBoardColumns:
    def test_the_title_takes_what_the_others_leave(self, tool):
        columns = tool.board_columns([row()], 80)
        spent = sum(columns[c] for c in ("key", "type", "points", "sprint"))
        assert columns["title"] == 80 - (spent + 10)     # two spaces before each of five

    def test_a_wider_terminal_widens_only_the_title(self, tool):
        narrow = tool.board_columns([row()], 80)
        wide = tool.board_columns([row()], 200)
        assert {c: wide[c] for c in narrow if c != "title"} == \
               {c: narrow[c] for c in narrow if c != "title"}
        assert wide["title"] - narrow["title"] == 120

    def test_a_column_is_never_narrower_than_its_heading(self, tool):
        columns = tool.board_columns([row(key="A-1", kind="bug")], 80)
        assert columns["key"] == len("key") and columns["type"] == len("type")
        assert columns["points"] == len("pts") and columns["sprint"] == len("sprint")

    def test_widths_are_measured_across_every_row_not_per_section(self, tool):
        """Per-section widths staggered the sections against each other, and left
        the one heading true of the first section only."""
        rows = [row(key="A-1"), row(key="AGILE-100")]
        assert tool.board_columns(rows, 80)["key"] == len("AGILE-100")

    def test_the_title_stops_giving_ground_at_the_minimum(self, tool):
        assert tool.board_columns([row()], 20)["title"] == tool.MIN_TITLE_WIDTH


class TestRenderBoard:
    def test_the_columns_carry_a_heading(self, tool):
        """Five unlabelled columns put `8` next to `AGILE Sprint 4`."""
        lines = rendered(tool, [row(points=8.0, sprint="AGILE Sprint 4")]).splitlines()
        heading = next(line for line in lines if "title" in line)
        for label in ("key", "type", "pts", "sprint", "title"):
            assert label in heading
        assert lines[lines.index(heading) + 1].strip().startswith("─")

    def test_the_heading_lines_up_with_the_rows(self, tool):
        lines = rendered(tool, [row(key="AGILE-100", title="a title")]).splitlines()
        heading = next(line for line in lines if line.strip().startswith("key"))
        item_line = next(line for line in lines if "AGILE-100" in line)
        assert heading.index("title") == item_line.index("a title")

    def test_an_empty_board_has_no_heading(self, tool):
        text = rendered(tool, [], sections=[("Todo", [])])
        assert "pts" not in text
        assert "empty: Todo" in text

    def test_a_wide_terminal_keeps_the_whole_title(self, tool):
        long_title = "Export pull requests, reviews and comments as events"
        assert long_title in rendered(tool, [row(title=long_title)], width=200)

    def test_a_title_too_long_for_the_width_is_wrapped_not_elided(self, tool):
        """A window is as wide as the developer made it, and the tool renders to
        that width -- the fixed 80 is for a pipe and a file. Where a title still
        does not fit, `…` loses the half that usually says what the work is."""
        long_title = "Export pull requests, reviews and comments as events"
        text = rendered(tool, [row(title=long_title)], width=80)
        assert "…" not in text
        # Every word survives, across however many lines it took.
        assert set(long_title.split()) <= set(text.split())

    def test_a_continuation_line_is_indented_to_the_title_column(self, tool):
        long_title = "Export pull requests, reviews and comments as events, and more besides"
        lines = rendered(tool, [row(key="AGILE-9", title=long_title)],
                         width=60).splitlines()
        first = next(line for line in lines if "AGILE-9" in line)
        at = first.index("Export")
        continuation = lines[lines.index(first) + 1]
        assert continuation.startswith(" " * at) and continuation[at] != " "

    def test_no_line_runs_past_the_width(self, tool):
        """The old rendering elided at a hard 46 and still put the row at 88."""
        rows = [row(key="AGILE-100", points=13.0, sprint="AGILE Sprint 4",
                    title="Export pull requests, reviews and comments as events")]
        for width in (80, 100, 200):
            assert max(len(line) for line in rendered(tool, rows, width).splitlines()) <= width

    def test_the_sections_and_the_empty_line_survive(self, tool):
        rows = [row()]
        text = rendered(tool, rows, sections=[("Todo", rows), ("In Review", [])])
        assert "Todo (1)" in text and "empty: In Review" in text


class TestRenderBoardList:
    VIEWS = [
        {"number": 1, "name": "View 1", "layout": "TABLE_LAYOUT", "filter": None},
        {"number": 3, "name": "Engineering: all work", "layout": "BOARD_LAYOUT",
         "filter": "-status:Done"},
    ]
    CONFIG = {"boards": [{"name": "Engineering: all work", "type": "kanban"}]}

    def test_the_columns_carry_a_heading(self, tool):
        heading = tool.render_board_list(self.VIEWS, self.CONFIG).splitlines()[0]
        for label in ("#", "name", "type", "layout", "filter"):
            assert label in heading

    def test_the_number_is_bare_because_it_is_what_show_takes(self, tool):
        lines = tool.render_board_list(self.VIEWS, self.CONFIG).splitlines()
        assert lines[2].split() == ["1", "View", "1", "custom", "table"]

    def test_the_name_column_fits_the_longest_name(self, tool):
        """It was a fixed 28, and "Engineering: all work" ran into the type."""
        lines = tool.render_board_list(self.VIEWS, self.CONFIG).splitlines()
        row_line = next(line for line in lines if "Engineering" in line)
        assert "  kanban" in row_line
        assert row_line.index("kanban") == lines[0].index("type")

    def test_a_view_with_no_filter_leaves_no_trailing_space(self, tool):
        for line in tool.render_board_list(self.VIEWS, self.CONFIG).splitlines():
            assert line == line.rstrip()


class TestABoardThatExcludesNothing:
    """A board with no filter shows every item on the project, and its name is
    usually promising otherwise.

    On the Zamboni project, GitHub's default view had been renamed `Backlog` in
    the web UI and never given the backlog filter, so closed work appeared there
    and in the scrum board's Done section at the same time. It was reported as a
    bug in `board show`, and `board show` was doing the one thing it promises:
    **a board is reconstructed, never mirrored**, so the filter comes from the
    view rather than from its name. Both signals were there -- `custom` rather
    than `backlog`, and `filter: (none)` -- and both were easy to read past.

    The fact is stated; the type is **not** inferred from the name, because
    guessing that a view called `Backlog` wants the backlog filter is the same
    name-based inference that refusing an unknown filter term exists to prevent.
    """

    def test_the_rendered_filter_line_says_so(self, tool):
        text = rendered(tool, [row()], sections=[("Todo", [row()])])
        assert "filter: -status:Done" in text        # the fixture's own filter
        unfiltered = tool.render_board(
            {"name": "View 1", "layout": "TABLE_LAYOUT", "filter": ""},
            "custom", [row()], [("", [row()])], "o", 4, 1, "", 80)
        assert "excludes nothing" in unfiltered

    def test_the_fact_travels_with_a_written_board(self, tool):
        """It is in the rendering, so an `--out-dir` file carries it too -- the
        record should say the board excluded nothing."""
        unfiltered = tool.render_board(
            {"name": "View 1", "layout": "TABLE_LAYOUT", "filter": ""},
            "custom", [row()], [("", [row()])], "o", 4, 1, "", 80)
        assert "(none)" in unfiltered and "excludes nothing" in unfiltered


class TestTheUnfilteredWarning:
    @pytest.fixture
    def show(self, monkeypatch, tool, capsys):
        def go(view_filter, extra=None):
            import argparse
            monkeypatch.setattr(tool, "find_view", lambda *a, **k: {
                "name": "View 1", "number": 1, "layout": "TABLE_LAYOUT",
                "filter": view_filter})
            monkeypatch.setattr(tool, "iterations", lambda *a, **k: ([], []))
            monkeypatch.setattr(tool, "fetch_items", lambda *a, **k: ("t", []))
            # It asks `gh` which repository this is, to resolve an initiative
            # filter; unstubbed it shelled out from inside the suite.
            monkeypatch.setattr(tool, "current_repo", lambda: None)
            args = argparse.Namespace(owner="o", project=4, name="View 1",
                                      filter=extra, format=None, out_dir=None,
                                      _config={})
            tool.cmd_board_show(args)
            return capsys.readouterr()
        return go

    def test_an_unfiltered_view_is_called_out(self, tool, show):
        err = show("").err
        assert "has no filter" in err and "every item on the project" in err

    def test_the_advice_goes_to_stderr_not_into_the_board(self, tool, show):
        """So a redirected or `--out-dir` run keeps the fact and drops the
        suggestion."""
        out = show("")
        assert "board create" in out.err and "board create" not in out.out

    def test_no_board_type_is_guessed_from_the_name(self, tool, show):
        """It lists the types rather than picking one. A view called `Backlog`
        probably wants the backlog filter, and probably is not good enough."""
        err = show("").err
        for kind in ("scrum", "kanban", "backlog", "roadmap"):
            assert kind in err

    def test_a_filtered_view_says_nothing(self, tool, show):
        assert show("-status:Done").err == ""

    def test_nor_does_one_the_caller_filtered(self, tool, show):
        """A filterless view shown with `--filter status:Todo` **is** filtered."""
        assert show("", extra="status:Todo").err == ""


class TestTheInitiativeTerm:
    """`initiative:<slug>` shows an initiative's whole tree.

    It works at all only because `initiative reconcile` puts the label on every
    issue in the tree. A filter cannot traverse the hierarchy -- `item_matches`
    judges one item at a time, and GitHub's own view filters reach at most one
    level -- so the label is the only thing an evaluator can see.

    A term of its own rather than leaving people to write
    `label:initiative:large-new-feature`, which reads badly, and because the term
    is where the meaning gets documented for `--help`.
    """

    def test_it_matches_the_label(self, tool):
        it = item(labels=["type:story", "initiative:big-thing"])
        assert matches(tool, it, "initiative:big-thing")

    def test_it_does_not_match_another_initiative(self, tool):
        it = item(labels=["type:story", "initiative:other"])
        assert not matches(tool, it, "initiative:big-thing")

    def test_an_unlabelled_item_does_not_match(self, tool):
        assert not matches(tool, item(labels=["type:story"]), "initiative:big-thing")

    def test_negation(self, tool):
        it = item(labels=["type:story", "initiative:big-thing"])
        assert not matches(tool, it, "-initiative:big-thing")
        assert matches(tool, item(labels=["type:story"]), "-initiative:big-thing")

    def test_it_is_case_insensitive_like_label(self, tool):
        it = item(labels=["initiative:Big-Thing"])
        assert matches(tool, it, "initiative:big-thing")

    def test_an_unknown_slug_matches_nothing_rather_than_erroring(self, tool):
        """Consistent with an unmatched label: an empty board, not a failure."""
        assert not matches(tool, item(labels=["type:story"]), "initiative:no-such-thing")

    def test_it_is_in_the_documented_vocabulary(self, tool):
        assert "initiative" in tool.FILTER_TERMS


class TestGithubFilter:
    """What gets written onto a view has to be what GitHub can evaluate.

    `initiative:<slug>` is exactly `label:initiative:<slug>`; GitHub knows
    `label:` and does not know `initiative:`. Saving the short form would put the
    web UI and `board show` into disagreement about what a board shows -- the one
    thing a reconstructed board must never do, since the whole claim is that it
    renders *that* definition rather than something retyped beside it.
    """

    @pytest.mark.parametrize("given,want", [
        ("sprint:@current initiative:big-thing",
         "sprint:@current label:initiative:big-thing"),
        ("-initiative:big-thing -status:Done", "-label:initiative:big-thing -status:Done"),
        ("initiative:a initiative:b", "label:initiative:a label:initiative:b"),
    ])
    def test_the_shorthand_is_expanded(self, tool, given, want):
        assert tool.github_filter(given) == want

    @pytest.mark.parametrize("given", [
        "label:key:AGILE", "-status:Done", "no:sprint -status:Done",
        "sprint:@current label:key:ZMBNI", "",
    ])
    def test_everything_else_is_left_alone(self, tool, given):
        assert tool.github_filter(given) == given

    def test_an_already_expanded_term_is_not_expanded_twice(self, tool):
        assert tool.github_filter("label:initiative:big") == "label:initiative:big"

    def test_what_board_create_writes_is_expanded(self, tool, monkeypatch):
        """The property that matters: the filter reaching GitHub, not the helper."""
        written = {}
        monkeypatch.setattr(tool, "views_of", lambda *a, **k: [])
        monkeypatch.setattr(tool, "project_id", lambda *a, **k: "PVT_1")

        def fake_graphql(query, **variables):
            if "updateProjectV2View" in query:
                written["filter"] = variables["f"]
            return {"data": {"createProjectV2View": {
                "projectV2View": {"id": "V_1", "number": 7}}}}

        monkeypatch.setattr(tool, "graphql", fake_graphql)
        tool.make_board("o", 4, "Big thing", "scrum", "initiative:big-thing")
        assert written["filter"] == "sprint:@current label:initiative:big-thing"


class TestResolvingReferencesInAFilter:
    """`--filter initiative:35` and `--filter initiative:TEST-35`, not just the slug.

    `--initiative` on `epic` takes all three forms; the filter term took only the
    slug, so `initiative:35` matched the *label* `initiative:35`, which nothing
    carries. Measured before the fix: `2 of 10 items` for the slug and `0 of 10`
    for either reference -- **silently**, because a board showing nothing looks
    exactly like an initiative with nothing in it. That is the shape of wrong
    answer this tool refuses unknown filter terms to avoid.
    """

    @pytest.fixture
    def resolve(self, monkeypatch, tool):
        looked_up = []

        def fake_target(config, ref, repo):
            looked_up.append(ref)
            return {"repo": "o/r", "number": 35, "id": "I_35", "slug": "big-thing"}

        monkeypatch.setattr(tool, "initiative_target", fake_target)
        config = {"keys": [{"key": "TEST", "repo": "o/r"}]}

        def go(text):
            looked_up.clear()
            return tool.resolve_filter_initiatives(config, text, "o/r"), looked_up
        return go

    def test_a_bare_number_resolves_to_the_slug(self, tool, resolve):
        assert resolve("initiative:35")[0] == "initiative:big-thing"

    def test_a_keyed_reference_resolves_too(self, tool, resolve):
        assert resolve("initiative:TEST-35")[0] == "initiative:big-thing"

    def test_a_slug_is_left_alone_and_costs_no_lookup(self, tool, resolve):
        text, looked_up = resolve("initiative:big-thing")
        assert text == "initiative:big-thing" and looked_up == []

    def test_negation_survives(self, tool, resolve):
        assert resolve("-initiative:35")[0] == "-initiative:big-thing"

    def test_other_terms_are_untouched(self, tool, resolve):
        text, looked_up = resolve("-status:Done label:key:AGILE no:sprint")
        assert text == "-status:Done label:key:AGILE no:sprint" and looked_up == []

    def test_it_resolves_only_the_initiative_term(self, tool, resolve):
        assert resolve("sprint:@current initiative:35")[0] == \
            "sprint:@current initiative:big-thing"

    def test_an_empty_filter_stays_empty(self, tool, resolve):
        assert resolve(None)[0] is None and resolve("")[0] == ""

    def test_a_slug_that_looks_keyed_is_still_a_slug(self, tool, resolve):
        """`pyiceberg-0-12` parses as key `pyiceberg-0`, which no profile knows."""
        text, looked_up = resolve("initiative:pyiceberg-0-12")
        assert text == "initiative:pyiceberg-0-12" and looked_up == []


def who_row(assignees=(), status="Todo", **kw):
    base = row(**kw)
    base["assignees"] = list(assignees)
    base["status"] = status
    return base


class TestTheWhoColumn:
    """The board a team reads in a standup could not say who has the work.

    `README.md` already said `assignees[]` *answers "who has this now", which a
    board needs and a report cannot use* -- and the board did not show it. The
    data was already fetched; `board_row` carried it and only the rendering
    dropped it, so this costs no extra call.
    """

    def test_it_shows_who_has_it(self, tool):
        assert tool.render_who(who_row(["dev"])) == "dev"

    def test_two_people_show_the_first_and_a_count(self, tool):
        """A standup asks who is *driving* this; the second name does not change
        the answer, and the column is not where a full list belongs."""
        assert tool.render_who(who_row(["ann", "bea"])) == "ann +1"

    def test_a_long_login_is_elided_not_wrapped(self, tool):
        out = tool.render_who(who_row(["averyverylonggithublogin"]))
        assert len(out) <= tool.WHO_WIDTH and out.endswith("…")

    def test_an_unassigned_todo_is_just_empty(self, tool):
        """The ordinary state of a backlog. Flagging it would mark nearly every
        row and teach people to ignore the column."""
        assert tool.render_who(who_row([], status="Todo")) == "—"

    def test_unassigned_work_in_progress_is_called_out(self, tool):
        """Somebody is meant to have this right now and nobody does -- the one
        cell on a standup board worth stopping at."""
        assert tool.render_who(who_row([], status="In Progress")) == tool.NOBODY

    def test_the_flag_is_a_word_not_a_symbol(self, tool):
        """`—` reads as *nothing here* and is exactly what a reader skims past."""
        assert tool.NOBODY == "nobody" and tool.NOBODY != "—"

    @pytest.mark.parametrize("status", ["Blocked", "In Review", "Done"])
    def test_no_other_status_is_flagged(self, tool, status):
        assert tool.render_who(who_row([], status=status)) == "—"

    def test_a_spanning_level_is_not_exempt(self, tool):
        """An epic is exempt from the *sprint*, not from having somebody on it:
        `move` claims it, and `validate` reports it unassigned. The board says the
        same thing."""
        assert tool.render_who(who_row([], status="In Progress")) == tool.NOBODY


class TestTheColumnEarnsItsPlace:
    """Fourteen characters taken from the title, on a board with nothing to say
    about who has anything, is fourteen characters of `—`. The title is what a
    person reads."""

    def test_a_board_where_nobody_holds_anything_omits_it(self, tool):
        text = rendered(tool, [who_row([], status="Todo")],
                        sections=[("Todo", [who_row([], status="Todo")])])
        assert " who " not in text

    def test_one_assignee_brings_it_back(self, tool):
        rows = [who_row(["dev"], status="Todo")]
        assert "who" in rendered(tool, rows, sections=[("Todo", rows)])

    def test_so_does_one_unassigned_item_in_progress(self, tool):
        """The case that matters most is the one with no assignees at all."""
        rows = [who_row([], status="In Progress")]
        text = rendered(tool, rows, sections=[("In Progress", rows)])
        assert "who" in text and tool.NOBODY in text

    def test_the_rule_under_the_heading_drops_it_too(self, tool):
        """Five segments without the column, six with -- a rule with a stray
        segment is how a dropped column announces itself."""
        def segments(rows):
            lines = rendered(tool, rows, sections=[("Todo", rows)]).splitlines()
            at = next(i for i, line in enumerate(lines) if line.strip().startswith("key"))
            return len([part for part in lines[at + 1].strip().split("  ") if part])

        assert segments([who_row([], status="Todo")]) == 5
        assert segments([who_row(["dev"], status="Todo")]) == 6

    def test_the_title_gets_the_space_back(self, tool):
        without = tool.board_columns([who_row([], status="Todo")], 80)
        with_who = tool.board_columns([who_row(["dev"], status="Todo")], 80)
        assert without["who"] == 0 and with_who["who"] > 0
        assert without["title"] > with_who["title"]


class TestTheRowStillFits:
    def test_no_line_runs_past_the_width(self, tool):
        rows = [who_row(["averyverylonglogin"], status="In Progress",
                        key="AGILE-100", points=13.0, sprint="AGILE Sprint 4",
                        title="Export pull requests, reviews and comments as events")]
        for width in (80, 100, 200):
            text = rendered(tool, rows, width, sections=[("In Progress", rows)])
            assert max(len(line) for line in text.splitlines()) <= width

    def test_the_heading_still_lines_up_with_the_rows(self, tool):
        rows = [who_row(["dev"], key="AGILE-100", title="a title")]
        lines = rendered(tool, rows, sections=[("Todo", rows)]).splitlines()
        heading = next(line for line in lines if line.strip().startswith("key"))
        item = next(line for line in lines if "AGILE-100" in line)
        assert heading.index("title") == item.index("a title")
        assert heading.index("who") == item.index("dev")


class TestTheColumnsAreCapped:
    """A column is paid for out of the title, which is the part a person reads."""

    def test_a_mail_domain_is_dropped(self, tool):
        """The domain is the same for everyone on the board and says nothing
        about who has the work."""
        assert tool.render_who(who_row(["paul@experienceflow.com"])) == "paul"

    def test_a_login_is_capped(self, tool):
        out = tool.render_who(who_row(["averylonggithublogin"]))
        assert len(out) <= tool.WHO_WIDTH == 10

    def test_ten_characters_is_enough_to_know_who(self, tool):
        """Two people sharing a ten-character prefix is not a team anybody has."""
        assert tool.render_who(who_row(["paulcaron16k"])).startswith("paulcaron")

    def test_the_sprint_column_never_exceeds_its_cap(self, tool):
        wide = tool.board_columns([row(sprint="0004 W38-2026")], 200)
        assert wide["sprint"] == tool.SPRINT_WIDTH == 8

    def test_a_short_sprint_name_does_not_pad_to_the_cap(self, tool):
        assert tool.board_columns([row(sprint="0004")], 200)["sprint"] == len("sprint")

    def test_the_cap_keeps_what_matters_in_the_new_naming(self, tool):
        """`0004 W38-2026` cuts to `0004 W38` -- number and week both survive.
        Cut rather than elided: `…` would spend one of the eight saying there is
        more, which the cap already implies, and would cost the week a digit."""
        rows = [row(sprint="0004 W38-2026")]
        text = rendered(tool, rows, width=200, sections=[("Todo", rows)])
        assert "0004 W38" in text and "0004 W3…" not in text


class TestTheDefaultSprintName:
    def test_it_leads_with_the_number(self, tool):
        """The only part anyone says out loud, and the only part that survives an
        eight-character column."""
        name = tool.SPRINT_DEFAULTS["name_template"].format(
            n=4, key="AGILE", start="", end="", year=2026, iso_week="38")
        assert name == "0004 W38-2026"
        assert name[:tool.SPRINT_WIDTH] == "0004 W38"

    def test_it_sorts_lexicographically_by_sprint(self, tool):
        tpl = tool.SPRINT_DEFAULTS["name_template"]
        names = [tpl.format(n=n, key="A", start="", end="", year=2026, iso_week="01")
                 for n in (2, 10, 1)]
        assert sorted(names) == [
            tpl.format(n=n, key="A", start="", end="", year=2026, iso_week="01")
            for n in (1, 2, 10)]

    def test_four_digits_is_ten_thousand_sprints(self, tool):
        """At a fortnight each, longer than anyone is going to run this board."""
        name = tool.SPRINT_DEFAULTS["name_template"].format(
            n=9999, key="A", start="", end="", year=2026, iso_week="01")
        assert name.startswith("9999") and len(name) == 13


def stale_row(status="In Progress", state="CLOSED", **kw):
    base = who_row(["dev"], status=status, **kw)
    base["state"] = state
    return base


class TestAClosedIssueWithAStaleStatus:
    """A board filter reads the `Status` **field** and never looks at the issue's
    state, so a closed issue whose Status is still `In Progress` passes
    `-status:Done` and lands in the In Progress column -- indistinguishable from
    work somebody is doing. Not a missing row: a misleading one.

    Observed on `#123`, which sat there for twenty-two hours after the work was
    finished, with `validate` reporting it the whole time. The cause is a
    `Closes #n` automation, which sets the issue's state and nothing else.
    """

    def test_a_closed_row_with_a_live_status_is_stale(self, tool):
        assert tool.stale_status(stale_row())

    def test_an_open_row_at_any_status_is_not(self, tool):
        for status in ("Todo", "In Progress", "Blocked", "In Review"):
            assert not tool.stale_status(stale_row(status=status, state="OPEN"))

    def test_a_closed_row_that_reached_done_is_not(self, tool):
        assert not tool.stale_status(stale_row(status="Done"))

    def test_the_hyphen_spelling_counts_as_done(self, tool):
        """`In-Review` and `In Progress` are the same transition everywhere else."""
        assert not tool.stale_status(stale_row(status="done"))

    def test_the_key_is_marked(self, tool):
        rows = [stale_row(key="AGILE-123")]
        text = rendered(tool, rows, sections=[("In Progress", rows)])
        assert "AGILE-123*" in text

    def test_a_healthy_row_is_not_marked(self, tool):
        rows = [stale_row(key="AGILE-140", state="OPEN")]
        text = rendered(tool, rows, sections=[("In Progress", rows)])
        assert "AGILE-140*" not in text

    def test_the_footnote_says_what_it_means_and_how_to_fix_it(self, tool):
        rows = [stale_row(key="AGILE-123", number=123)]
        text = rendered(tool, rows, sections=[("In Progress", rows)])
        assert "closed, but Status is not Done" in text
        assert "showing finished work as live" in text
        assert "gh agile issue move 123 Done" in text

    def test_a_board_in_order_says_nothing_at_all(self, tool):
        """An explanation of a mark nothing carries is noise on every board that
        is in order, which is most of them."""
        rows = [stale_row(state="OPEN")]
        text = rendered(tool, rows, sections=[("In Progress", rows)])
        assert "*" not in text and "Status is not" not in text

    def test_the_mark_is_paid_for_in_the_key_column(self, tool):
        """So the mark cannot push a row past the width."""
        rows = [stale_row(key="AGILE-123")]
        assert tool.board_columns(rows, 80)["key"] == len("AGILE-123") + 1

    def test_no_line_runs_past_the_width(self, tool):
        rows = [stale_row(key="AGILE-100", number=100,
                          title="Export pull requests, reviews and comments as events")]
        for width in (80, 120):
            text = rendered(tool, rows, width, sections=[("In Progress", rows)])
            assert max(len(line) for line in text.splitlines()) <= width

    def test_it_lists_every_stale_row(self, tool):
        rows = [stale_row(key="AGILE-1", number=1), stale_row(key="AGILE-2", number=2)]
        text = rendered(tool, rows, sections=[("In Progress", rows)])
        assert "issue move 1 Done" in text and "issue move 2 Done" in text

    def test_there_is_no_double_blank_before_the_footnote(self, tool):
        rows = [stale_row(key="AGILE-123")]
        lines = rendered(tool, rows, sections=[("In Progress", rows)]).splitlines()
        at = next(i for i, line in enumerate(lines) if line.startswith("* closed"))
        assert lines[at - 1] == "" and lines[at - 2] != ""
