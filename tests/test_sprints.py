"""Sprint placement, cadence and duration.

Every regression named here was a live incident, and each cost real data or real
confusion. They are pinned in the order they happened.
"""

from __future__ import annotations

import datetime as dt

import pytest


def span(start: str, days: int = 14) -> dict:
    return {"startDate": start, "duration": days, "title": f"S {start}"}


class TestAlignedStart:
    """A sprint created mid-week still begins on the configured weekday."""

    @pytest.mark.parametrize("today,expected", [
        ("2026-08-17", "2026-08-17"),   # a Monday: itself
        ("2026-08-19", "2026-08-17"),   # Wednesday snaps back
        ("2026-08-23", "2026-08-17"),   # Sunday snaps back to the same Monday
        ("2026-08-24", "2026-08-24"),   # the next Monday
    ])
    def test_snaps_back_to_monday(self, tool, today, expected):
        got = tool.aligned_start(dt.date.fromisoformat(today), "monday")
        assert got == dt.date.fromisoformat(expected)

    def test_snapping_back_never_moves_forward(self, tool):
        """Forward-snapping would leave today uncovered by the sprint it made."""
        for offset in range(28):
            today = dt.date(2026, 8, 1) + dt.timedelta(days=offset)
            assert tool.aligned_start(today, "monday") <= today

    @pytest.mark.parametrize("day", ["sunday", "monday", "wednesday", "saturday"])
    def test_every_weekday_lands_on_that_weekday(self, tool, day):
        """GitHub numbers startDay 1=Sunday, Python 0=Monday. One off-by-one,
        written down once, and asserted here for all seven."""
        target = (tool.WEEKDAYS[day] - 2) % 7
        for offset in range(14):
            today = dt.date(2026, 8, 1) + dt.timedelta(days=offset)
            assert tool.aligned_start(today, day).weekday() == target


class TestOverlap:
    """Intersection, not containment.

    Testing containment read a partial overlap as uncovered and put three
    overlapping sprints on a live board, which makes `@current` arbitrary.
    """

    def test_partial_overlap_is_an_overlap(self, tool):
        spans = tool.iteration_spans([span("2026-08-03")])
        clash = tool.overlapping(
            spans, dt.date(2026, 8, 10), dt.date(2026, 8, 23)
        )
        assert clash is not None, "a partial overlap must be detected"

    def test_containment_is_an_overlap(self, tool):
        spans = tool.iteration_spans([span("2026-08-03", 28)])
        assert tool.overlapping(spans, dt.date(2026, 8, 10), dt.date(2026, 8, 12))

    def test_abutting_is_not_an_overlap(self, tool):
        """The day after the last one ends is the intended default placement."""
        spans = tool.iteration_spans([span("2026-08-03")])   # 08-03 .. 08-16
        assert tool.overlapping(spans, dt.date(2026, 8, 17), dt.date(2026, 8, 30)) is None

    def test_single_day_touch_at_each_edge(self, tool):
        spans = tool.iteration_spans([span("2026-08-03")])   # inclusive 08-16
        assert tool.overlapping(spans, dt.date(2026, 8, 16), dt.date(2026, 8, 29))
        assert tool.overlapping(spans, dt.date(2026, 7, 21), dt.date(2026, 8, 3))

    def test_spans_are_inclusive_of_the_end_day(self, tool):
        (start, end), = tool.iteration_spans([span("2026-08-03", 14)])
        assert start == dt.date(2026, 8, 3)
        assert end == dt.date(2026, 8, 16), "14 days from the 3rd ends on the 16th"

    def test_empty_configuration_never_clashes(self, tool):
        assert tool.overlapping([], dt.date(2026, 8, 3), dt.date(2026, 8, 16)) is None


class TestSprintSettings:
    def test_week_sugar_becomes_days(self, tool):
        assert tool.sprint_settings({"sprint": {"cadence_days": "2-week"}})["cadence_days"] == 14
        assert tool.sprint_settings({"sprint": {"cadence_days": "3 weeks"}})["cadence_days"] == 21

    def test_bare_number_is_days(self, tool):
        assert tool.sprint_settings({"sprint": {"cadence_days": "10"}})["cadence_days"] == 10

    @pytest.mark.parametrize("bad", [0, 31, 365])
    def test_cadence_outside_one_to_thirty_is_refused(self, tool, bad):
        with pytest.raises(SystemExit):
            tool.sprint_settings({"sprint": {"cadence_days": bad}})

    def test_unknown_start_day_is_refused(self, tool):
        with pytest.raises(SystemExit):
            tool.sprint_settings({"sprint": {"start_day": "funday"}})

    def test_defaults_apply_when_absent(self, tool):
        s = tool.sprint_settings({})
        assert (s["cadence_days"], s["start_day"], s["ahead"]) == (14, "monday", 2)

    def test_record_label_defaults_on(self, tool):
        assert tool.sprint_settings({})["record_label"] is True

    def test_max_sprint_days_matches_the_validated_bound(self, tool):
        """`sprint create --weeks` and the profile must agree on the limit;
        they disagreed, so --weeks could create what no profile allowed."""
        assert tool.MAX_SPRINT_DAYS == 30
        tool.sprint_settings({"sprint": {"cadence_days": tool.MAX_SPRINT_DAYS}})
        with pytest.raises(SystemExit):
            tool.sprint_settings({"sprint": {"cadence_days": tool.MAX_SPRINT_DAYS + 1}})


class TestSprintTemplates:
    def test_every_template_is_a_legal_setting(self, tool):
        for name, spec in tool.SPRINT_TEMPLATES.items():
            merged = tool.sprint_settings({"sprint": spec})
            assert 1 <= merged["cadence_days"] <= tool.MAX_SPRINT_DAYS, name
            assert merged["start_day"] in tool.WEEKDAYS, name

    def test_none_means_no_sprints(self, tool):
        spec = tool.SPRINT_TEMPLATES["none"]
        assert spec["autocreate"] is False and spec["ahead"] == 0
