"""Dates are UTC, everywhere, without exception.

A sprint window is a pair of plain dates that GitHub stores and compares in UTC,
and `@current` is decided the same way. A local `today` puts the tool and GitHub
a day out of step for anyone east or west of UTC around midnight.
"""

from __future__ import annotations

import datetime as dt
import os
import time


class TestTodayIsUtc:
    def test_matches_utc_not_local(self, tool, monkeypatch):
        """Pinned with a timezone far enough from UTC that the date differs for
        part of every day: Kiritimati is UTC+14."""
        monkeypatch.setenv("TZ", "Pacific/Kiritimati")
        time.tzset()
        try:
            assert tool.today_utc() == dt.datetime.now(dt.timezone.utc).date()
        finally:
            monkeypatch.delenv("TZ", raising=False)
            time.tzset()

    def test_disagrees_with_local_when_it_should(self, tool, monkeypatch):
        """Not a tautology: at UTC+14 the local date is genuinely ahead for ten
        hours a day, so this asserts the tool follows UTC rather than whichever
        happens to match."""
        monkeypatch.setenv("TZ", "Pacific/Kiritimati")
        time.tzset()
        try:
            utc_now = dt.datetime.now(dt.timezone.utc)
            local_ahead = utc_now.hour >= 10
            if local_ahead:
                # The one deliberate local-date call in the project: the
                # assertion is precisely that the tool disagrees with it.
                assert tool.today_utc() != dt.date.today()  # noqa: DTZ011
            assert tool.today_utc() == utc_now.date()
        finally:
            monkeypatch.delenv("TZ", raising=False)
            time.tzset()

    def test_returns_a_date_not_a_datetime(self, tool):
        assert isinstance(tool.today_utc(), dt.date)
        assert not isinstance(tool.today_utc(), dt.datetime)

    def test_no_local_date_call_remains(self, tool):
        """The helper is only useful if nothing bypasses it."""
        import inspect

        source = inspect.getsource(tool)
        assert "date.today()" not in source


class TestTimezoneIndependence:
    """Placement must not move when the machine does."""

    def _aligned(self, tool, tz: str):
        os.environ["TZ"] = tz
        time.tzset()
        try:
            return tool.aligned_start(dt.date(2026, 8, 19), "monday")
        finally:
            os.environ.pop("TZ", None)
            time.tzset()

    def test_alignment_is_the_same_in_every_timezone(self, tool):
        results = {
            tz: self._aligned(tool, tz)
            for tz in ("UTC", "Pacific/Kiritimati", "Pacific/Niue",
                       "Europe/London", "America/Los_Angeles")
        }
        assert len(set(results.values())) == 1, results
