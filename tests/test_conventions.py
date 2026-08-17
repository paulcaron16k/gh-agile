"""Status handling, issue bodies, and the profile's own invariants."""

from __future__ import annotations

import json

import pytest


class TestStatusComparison:
    def test_case_insensitive(self, tool):
        """A case-sensitive comparison made every cycle time null: the
        transitions were in the timeline and the match silently missed them."""
        assert tool.same_status("in progress", "In Progress")
        assert tool.same_status("DONE", "Done")

    def test_distinct_statuses_do_not_match(self, tool):
        assert not tool.same_status("Todo", "Done")

    def test_none_never_matches(self, tool):
        assert not tool.same_status(None, "Done")
        assert not tool.same_status("Done", None)

    def test_the_cycle_endpoints_are_real_statuses(self, tool):
        assert tool.CYCLE_START in tool.STATUSES
        assert tool.CYCLE_END in tool.STATUSES


class TestIssueBody:
    def test_the_template_carries_every_required_section(self, tool):
        body = tool.BODY_TEMPLATE.format(intent="i", acceptance="a")
        for heading, _about in tool.SECTIONS:
            assert f"## {heading}" in body

    def test_sections_round_trip(self, tool):
        body = tool.BODY_TEMPLATE.format(intent="why", acceptance="when")
        parsed = tool.parse_sections(body)
        assert parsed["Intent"].strip() == "why"
        assert parsed["Acceptance"].strip() == "when"

    def test_a_placeholder_section_is_not_filled_in(self, tool):
        body = tool.BODY_TEMPLATE.format(intent=tool.PLACEHOLDER, acceptance="a")
        parsed = tool.parse_sections(body)
        with pytest.raises(SystemExit):
            tool.require_sections(parsed, required=("Intent",))

    def test_a_filled_section_passes(self, tool):
        parsed = tool.parse_sections(tool.BODY_TEMPLATE.format(intent="real", acceptance="a"))
        tool.require_sections(parsed, required=("Intent",))


class TestConfigReading:
    def test_absent_config_is_an_empty_dict(self, tool, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert tool.read_config() == {}

    def test_unreadable_json_is_refused_rather_than_ignored(self, tool, tmp_path):
        bad = tmp_path / "agile.json"
        bad.write_text("{not json")
        with pytest.raises(SystemExit):
            tool.read_config(str(bad))

    def test_config_is_read_from_the_given_path(self, tool, tmp_path):
        path = tmp_path / "agile.json"
        path.write_text(json.dumps({"project": {"number": 7}}))
        assert tool.read_config(str(path))["project"]["number"] == 7


class TestState:
    def test_watermark_round_trips(self, tool, tmp_path):
        path = str(tmp_path / "state.json")
        tool.write_state(path, "owner/4", "2026-08-14T00:00:00Z", 25)
        assert tool.read_state(path)["owner/4"]["watermark"] == "2026-08-14T00:00:00Z"

    def test_other_keys_survive_a_write(self, tool, tmp_path):
        """The state file holds one entry per project; writing one must not
        drop another's watermark."""
        path = str(tmp_path / "state.json")
        tool.write_state(path, "owner/1", "2026-01-01T00:00:00Z", 1)
        tool.write_state(path, "owner/2", "2026-02-02T00:00:00Z", 2)
        state = tool.read_state(path)
        assert state["owner/1"]["watermark"] == "2026-01-01T00:00:00Z"
        assert state["owner/2"]["watermark"] == "2026-02-02T00:00:00Z"

    def test_missing_state_file_reads_empty(self, tool, tmp_path):
        assert tool.read_state(str(tmp_path / "nope.json")) == {}


class TestSprintConfigGate:
    def test_refuses_until_a_cadence_is_chosen(self, tool):
        """Defaults used to apply silently, so the first sprint was created
        with whatever the tool assumed and the cadence was discovered after
        sprints already followed it."""
        with pytest.raises(SystemExit) as exit_info:
            tool.require_sprint_config({}, "creating a story")
        assert "2-week" in str(exit_info.value), "the refusal must list the choices"

    def test_passes_once_configured(self, tool):
        tool.require_sprint_config({"sprint": {"cadence_days": 14}}, "creating a story")


class TestBudgetPreflight:
    def test_no_assignments_needs_no_budget(self, tool, monkeypatch):
        """Nothing to restore, so nothing to protect -- and no reason to spend
        a call asking."""
        monkeypatch.setattr(tool, "graphql_remaining",
                            lambda: (_ for _ in ()).throw(AssertionError("asked anyway")))
        tool.require_graphql_budget(0, "creating a sprint")

    def test_refuses_when_the_budget_cannot_cover_the_restore(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "graphql_remaining", lambda: 5)
        with pytest.raises(SystemExit) as exit_info:
            tool.require_graphql_budget(50, "creating a sprint")
        assert "refused" in str(exit_info.value)

    def test_proceeds_with_room_to_spare(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "graphql_remaining", lambda: 5000)
        tool.require_graphql_budget(50, "creating a sprint")

    def test_an_unknown_budget_does_not_block(self, tool, monkeypatch):
        """Not being able to ask is not a reason to stop someone working."""
        monkeypatch.setattr(tool, "graphql_remaining", lambda: None)
        tool.require_graphql_budget(50, "creating a sprint")

    def test_the_margin_is_counted(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "graphql_remaining", lambda: 50 + tool.BUDGET_MARGIN - 1)
        with pytest.raises(SystemExit):
            tool.require_graphql_budget(50, "creating a sprint")
