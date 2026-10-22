"""`--for 6w` -- a planner types a duration, not an end date. AGILE-187.

**This is how a WBS has always worked.** A planner sizes a phase in weeks, the
chart places it after a start and draws the bar; nobody types the far end.
GitHub's roadmap layout is that chart and the two DATE fields are its bar, so
the missing piece was the input a planner actually gives.

The duration is **typed**, which is what keeps this on the right side of the
line #179 drew: the tool does arithmetic on what a person said, and reads no
estimate, no velocity and nothing beneath the item. A test below holds that.

Offline. The board is never touched; what is under test is the arithmetic and
the refusals.
"""

from __future__ import annotations

import pytest

FORTNIGHT = {"sprint": {"cadence_days": 14}}
TEN_DAY = {"sprint": {"cadence_days": 10}}
NO_SPRINT_BLOCK = {}

EPIC = ["type:epic", "key:AGILE"]
STORY = ["type:story", "key:AGILE"]


class TestDurationDays:
    @pytest.mark.parametrize("text,days", [
        ("1d", 1), ("10d", 10), ("10day", 10), ("10days", 10),
        ("1w", 7), ("6w", 42), ("6week", 42), ("6weeks", 42),
    ])
    def test_days_and_weeks(self, tool, text, days):
        assert tool.duration_days(text, NO_SPRINT_BLOCK) == days

    def test_a_profile_with_no_sprint_block_still_takes_weeks(self, tool):
        """Read the cadence only for the unit that needs it."""
        assert tool.duration_days("2w", NO_SPRINT_BLOCK) == 14

    @pytest.mark.parametrize("text", ["1sprint", "1sprints"])
    def test_a_sprint_is_the_profiles_cadence(self, tool, text):
        assert tool.duration_days(text, FORTNIGHT) == 14

    def test_and_follows_a_cadence_that_is_not_a_fortnight(self, tool):
        """The reason `sprints` is offered at all: exact, not approximate."""
        assert tool.duration_days("3sprints", TEN_DAY) == 30

    def test_case_and_spaces_do_not_matter(self, tool):
        assert tool.duration_days(" 6 W ", NO_SPRINT_BLOCK) == 42

    @pytest.mark.parametrize("text", ["1m", "3months", "2mo", "1y", "2years"])
    def test_a_month_or_a_year_is_refused_by_name(self, tool, text):
        with pytest.raises(SystemExit) as caught:
            tool.duration_days(text, FORTNIGHT)
        assert "not a fixed number of days" in str(caught.value)

    def test_the_refusal_says_what_to_say_instead(self, tool):
        with pytest.raises(SystemExit) as caught:
            tool.duration_days("3months", FORTNIGHT)
        assert "13w" in str(caught.value)

    @pytest.mark.parametrize("text", ["", "w", "soon", "6", "6x", "0w", "-2w"])
    def test_anything_else_is_refused(self, tool, text):
        with pytest.raises(SystemExit):
            tool.duration_days(text, FORTNIGHT)


class TestTargetFrom:
    def test_a_span_is_inclusive_of_its_first_day(self, tool):
        """`1d` starting today ends today."""
        assert tool.target_from("2026-10-01", "1d", NO_SPRINT_BLOCK) == "2026-10-01"

    def test_a_week_ends_on_the_seventh_day(self, tool):
        assert tool.target_from("2026-10-01", "1w", NO_SPRINT_BLOCK) == "2026-10-07"

    def test_a_sprint_span_matches_what_sprint_list_prints(self, tool):
        """The decisive case. `sprint list` shows 0005 W40-2026 as
        2026-09-28 .. 2026-10-11, and a convention that disagreed with the
        tool's own sprint windows by a day would never be believed again."""
        assert tool.target_from("2026-09-28", "1sprint", FORTNIGHT) == "2026-10-11"

    def test_six_weeks(self, tool):
        assert tool.target_from("2026-10-01", "6w", NO_SPRINT_BLOCK) == "2026-11-11"

    def test_a_span_crossing_a_year_boundary(self, tool):
        assert tool.target_from("2026-12-20", "3w", NO_SPRINT_BLOCK) == "2027-01-09"

    def test_a_span_crossing_a_leap_day(self, tool):
        """2028 is a leap year: 21 days from 2028-02-20 reaches 2028-03-11,
        not 2028-03-12."""
        assert tool.target_from("2028-02-20", "3w", NO_SPRINT_BLOCK) == "2028-03-11"

    def test_a_span_crossing_a_non_leap_february(self, tool):
        assert tool.target_from("2027-02-20", "3w", NO_SPRINT_BLOCK) == "2027-03-12"


class TestSpannedTarget:
    def test_no_span_leaves_the_typed_target_alone(self, tool):
        assert tool.spanned_target("2026-10-01", "2026-12-19", None, FORTNIGHT) \
            == "2026-12-19"

    def test_no_span_and_no_target_is_no_target(self, tool):
        assert tool.spanned_target("2026-10-01", None, None, FORTNIGHT) is None

    def test_a_span_computes_the_target(self, tool):
        assert tool.spanned_target("2026-10-01", None, "6w", FORTNIGHT) == "2026-11-11"

    def test_a_span_and_a_target_together_are_refused(self, tool):
        """Two answers to one question, and they can disagree."""
        with pytest.raises(SystemExit) as caught:
            tool.spanned_target("2026-10-01", "2026-12-19", "6w", FORTNIGHT)
        assert "--for and --target" in str(caught.value)

    def test_a_span_with_no_start_is_refused(self, tool):
        with pytest.raises(SystemExit) as caught:
            tool.spanned_target(None, None, "6w", FORTNIGHT)
        assert "no start date" in str(caught.value)


class TestNothingIsDerivedFromTheWork:
    """The guard on the proposal this story replaced.

    Deriving a target from story points and velocity was measured and rejected:
    points against cycle time is rho = -0.13 on this board, points per elapsed
    day spans 156x, and epic estimate coverage is 0%. If this code ever reads an
    estimate it has become that proposal.
    """

    def test_the_arithmetic_reads_only_what_was_typed(self, tool, monkeypatch):
        def forbidden(*a, **k):
            raise AssertionError("a duration consulted the board")
        monkeypatch.setattr(tool, "gh", forbidden)
        monkeypatch.setattr(tool, "graphql", forbidden)
        assert tool.target_from("2026-10-01", "6w", FORTNIGHT) == "2026-11-11"

    def test_the_arithmetic_references_no_estimate(self, tool):
        """Read from the compiled code, not the source text: the docstrings
        explain what is *not* read, and a grep over prose would match that."""
        names = set()
        for f in (tool.duration_days, tool.target_from, tool.spanned_target):
            names |= set(f.__code__.co_names)
        assert not {n for n in names if "point" in n.casefold()
                    or "velocity" in n.casefold() or "estimate" in n.casefold()}


@pytest.fixture
def plan(monkeypatch, tool, capsys, edit_args):
    """Drive `issue edit` with `--for`, capturing the writes."""
    def go(start=None, target=None, span=None, *, labels=EPIC, stored=None):
        written, cleared = [], []
        monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 7))
        monkeypatch.setattr(tool, "issue_labels", lambda *a, **k: labels)
        monkeypatch.setattr(tool, "board_item_for", lambda *a, **k: {"id": "PVTI_7"})
        monkeypatch.setattr(tool, "item_date", lambda *a, **k: stored)
        monkeypatch.setattr(tool, "set_field",
                            lambda login, project, item, name, v: written.append((name, v)))
        monkeypatch.setattr(tool, "clear_field",
                            lambda login, project, item, name: cleared.append(name))
        go.written, go.cleared = written, cleared
        argv = [*(["--start", start] if start else []),
                *(["--target", target] if target else []),
                *(["--for", span] if span else [])]
        tool.cmd_edit(edit_args("7", *argv, config=FORTNIGHT))
        return written, cleared, capsys.readouterr().out
    return go


class TestPlanWithASpan:
    def test_the_start_and_the_computed_target_are_both_written(self, plan):
        written, _c, _out = plan(start="2026-10-01", span="6w")
        assert written == [("Start date", "2026-10-01"), ("Target date", "2026-11-11")]

    def test_a_span_alone_measures_from_the_date_already_on_the_item(self, plan):
        """Re-sizing a phase is a thing a planner does without restating a start."""
        written, _c, _out = plan(span="8w", stored="2026-10-01")
        assert written == [("Target date", "2026-11-25")]

    def test_the_output_says_where_the_date_came_from(self, plan):
        """The field cannot hold provenance; a computed date looks typed."""
        _w, _c, out = plan(span="6w", stored="2026-10-01")
        assert "Target date = 2026-11-11 (6w from 2026-10-01)" in out

    def test_a_typed_start_beats_the_stored_one(self, plan):
        written, _c, _out = plan(start="2026-11-02", span="1w", stored="2026-01-01")
        assert ("Target date", "2026-11-08") in written

    def test_a_span_with_no_start_anywhere_is_refused(self, plan):
        with pytest.raises(SystemExit) as caught:
            plan(span="6w", stored=None)
        assert "no start date" in str(caught.value)

    def test_and_writes_nothing(self, plan):
        with pytest.raises(SystemExit):
            plan(span="6w", stored=None)
        assert plan.written == [] and plan.cleared == []

    def test_a_span_with_a_target_is_refused(self, plan):
        with pytest.raises(SystemExit) as caught:
            plan(start="2026-10-01", target="2026-12-19", span="6w")
        assert "--for and --target" in str(caught.value)

    def test_a_span_while_clearing_the_start_is_refused(self, plan):
        """`--start none --for 6w` measures from the date it is removing."""
        with pytest.raises(SystemExit) as caught:
            plan(start="none", span="6w")
        assert "takes it away" in str(caught.value)

    def test_that_refusal_writes_nothing(self, plan):
        with pytest.raises(SystemExit):
            plan(start="none", span="6w")
        assert plan.written == [] and plan.cleared == []

    def test_a_story_is_still_refused(self, plan):
        with pytest.raises(SystemExit) as caught:
            plan(start="2026-10-01", span="6w", labels=STORY)
        assert "not an epic or an initiative" in str(caught.value)

    def test_no_flags_at_all_names_for_as_well(self, plan):
        with pytest.raises(SystemExit) as caught:
            plan()
        assert "--for" in str(caught.value)

    def test_the_item_is_not_read_when_a_start_is_given(self, plan, monkeypatch, tool):
        """One GraphQL point, and only for the command that needs it."""
        monkeypatch.setattr(tool, "item_date", lambda *a, **k: pytest.fail(
            "item_date was called although --start was given"))
        assert plan(start="2026-10-01", span="6w")[0][-1] == ("Target date", "2026-11-11")

    def test_it_is_not_read_when_no_span_is_given(self, plan, monkeypatch, tool):
        monkeypatch.setattr(tool, "item_date", lambda *a, **k: pytest.fail(
            "item_date was called with no --for"))
        assert plan(start="2026-10-01")[0] == [("Start date", "2026-10-01")]
