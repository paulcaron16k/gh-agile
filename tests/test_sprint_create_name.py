"""`sprint create` names a sprint from `name_template`, as `ensure` does. AGILE-209.

`create` called a new sprint `Sprint <n>` and ignored the profile's template,
which `ensure` honoured -- so one board got two naming schemes depending on
which command added the sprint. A sprint is never renamed (any write to the
iteration configuration clears every Sprint value), so a wrongly named one
stays wrongly named.
"""

from __future__ import annotations

import argparse
import datetime as dt

import pytest

DEFAULT = {"sprint": {"template": "2-week"}}     # name_template from SPRINT_DEFAULTS

#: Project 4 as #209 found it: seven sprints, the last ending 2026-11-08.
SEVEN = [{"title": f"S{i}", "startDate": (dt.date(2026, 8, 3) + dt.timedelta(days=14 * i))
          .isoformat(), "duration": 14} for i in range(7)]


@pytest.fixture
def create(monkeypatch, tool, capsys):
    def go(config=DEFAULT, title=None, start=None):
        monkeypatch.setattr(tool, "sprint_field",
                            lambda *a: {"id": "F", "configuration": {"duration": 14}})
        monkeypatch.setattr(tool, "iterations", lambda *a: (SEVEN[-2:], SEVEN[:-2]))
        monkeypatch.setattr(tool, "sprint_assignments", lambda *a: {})
        monkeypatch.setattr(tool, "require_graphql_budget", lambda *a: None)
        args = argparse.Namespace(sprint_command="create", owner="o", project=4,
                                  start=start, weeks=None, title=title, dry_run=True,
                                  _config=config)
        tool.cmd_sprint(args)
        return capsys.readouterr().out
    return go


class TestTheDefaultIsTheTemplate:
    def test_the_case_209_found(self, create):
        assert "would append 0008 W46-2026: 2026-11-09, 14 day(s)" in create()

    def test_a_custom_template_with_the_key(self, create):
        out = create({"project": {"key": "AGILE"},
                      "sprint": {"name_template": "{key} {n} ({start})"}})
        assert "would append AGILE 8 (2026-11-09)" in out

    def test_title_still_overrides(self, create):
        assert "would append Hand named: 2026-11-09" in create(title="Hand named")

    def test_the_template_is_formatted_from_the_sprints_own_start(self, create):
        assert "would append 0008 W53-2026: 2026-12-28" in create(start="2026-12-28")


class TestCreateAndEnsureAgree:
    def test_both_name_the_same_sprint_identically(self, tool, monkeypatch):
        """One helper, so ensure's next sprint and create's are spelled alike."""
        made = {}
        monkeypatch.setattr(tool, "today_utc", lambda: dt.date(2026, 11, 2))
        monkeypatch.setattr(tool, "sprint_field", lambda *a: {"id": "F", "configuration": {
            "completedIterations": SEVEN[:-2], "iterations": SEVEN[-2:], "duration": 14}})
        monkeypatch.setattr(tool, "sprint_assignments", lambda *a: {})
        monkeypatch.setattr(tool, "require_graphql_budget", lambda *a: None)
        monkeypatch.setattr(tool, "graphql",
                            lambda query, **v: made.setdefault("query", query))
        monkeypatch.setattr(tool, "restore_assignments", lambda *a: 0)
        monkeypatch.setattr(tool, "heal_sprint_fields", lambda *a, **k: None)
        tool.ensure_sprints("o", 4, {**DEFAULT, "sprint": {"template": "2-week",
                                                          "start_day": "monday"}}, ahead=1)
        assert '"0008 W46-2026"' in made["query"]

    def test_one_helper(self, tool):
        start, end = dt.date(2026, 11, 9), dt.date(2026, 11, 22)
        assert tool.sprint_title(DEFAULT, 8, start, end) == "0008 W46-2026"


def test_the_help_states_the_template_as_the_default(tool):
    parser = tool.build_parser()
    for word in ("sprint", "create"):
        parser = {n: p for n, _t, p in parser.subcommands()}[word]
    assert "name_template" in parser.format_help()
    assert "Sprint <n>" not in parser.format_help()
