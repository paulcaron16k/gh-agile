"""`Start date` and `Target date`, so the web roadmap can draw a bar. AGILE-175.

GitHub's roadmap layout places an item from a **date field or an iteration
field**, and an epic has neither: #115 made it a rule that a container carries
no Sprint, enforced at `move`, `validate` and `sprint backfill`. So every epic
landed in the web roadmap's undated bucket.

**`board show` is what hid it.** It reconstructs an axis from the `sprint:`
labels of an epic's *descendants* (#151) -- a reconstruction the web UI cannot
perform, having no notion of *the earliest sprint beneath this*. The text
roadmap looked right while the web roadmap, which is what a stakeholder opens,
drew nothing.

**A plan, not a measurement.** These say when somebody intended an epic to run;
the derived axis says when work actually began. Neither replaces the other, and
`board show` keeps deriving.

Nothing here writes an iteration configuration: they are `DATE` fields on the
project, so the `ProjectV2Iteration` hazard is untouched.
"""

from __future__ import annotations

import argparse
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestSetupCreatesThem:
    def test_both_are_in_the_default_spec(self, tool):
        names = [f["name"] for f in tool.DEFAULT_SPEC["fields"]]
        assert "Start date" in names and "Target date" in names

    def test_they_are_date_fields(self, tool):
        by_name = {f["name"]: f for f in tool.DEFAULT_SPEC["fields"]}
        assert by_name["Start date"]["type"] == "DATE"
        assert by_name["Target date"]["type"] == "DATE"

    def test_the_constant_and_the_spec_agree(self, tool):
        """One list, so a field added to the spec cannot be missed by the
        writer -- or the other way round."""
        names = [f["name"] for f in tool.DEFAULT_SPEC["fields"]]
        assert set(tool.DATE_FIELDS) <= set(names)

    def test_date_is_a_type_the_creator_accepts(self, tool):
        """`gh project field-create` takes TEXT, SINGLE_SELECT, DATE and NUMBER,
        which is why this needed no new machinery."""
        source = pathlib.Path(tool.__file__).read_text()
        assert '"TEXT", "SINGLE_SELECT", "DATE", "NUMBER"' in source

    def test_nothing_here_writes_an_iteration(self, tool):
        """The one hazard this must not go near."""
        by_name = {f["name"]: f for f in tool.DEFAULT_SPEC["fields"]}
        assert by_name["Start date"]["type"] != "ITERATION"
        assert by_name["Target date"]["type"] != "ITERATION"


class TestTheDateIsValidated:
    @pytest.mark.parametrize("value", ["2026-09-01", "2026-12-31", "2026-02-28"])
    def test_an_iso_date_passes_through(self, tool, value):
        assert tool.iso_date(value, "--start") == value

    def test_surrounding_space_is_forgiven(self, tool):
        assert tool.iso_date("  2026-09-01 ", "--start") == "2026-09-01"

    def test_absent_is_none_not_an_error(self, tool):
        """Both flags are optional everywhere."""
        assert tool.iso_date(None, "--start") is None

    @pytest.mark.parametrize("value", [
        "01/09/2026", "Sept 1", "2026-13-01", "2026-02-30", "tomorrow", ""])
    def test_anything_else_is_refused(self, tool, value):
        with pytest.raises(SystemExit) as exit_info:
            tool.iso_date(value, "--start")
        assert "not a date" in str(exit_info.value)

    def test_the_refusal_names_the_flag_and_the_form(self, tool):
        """GitHub would accept the string and render nothing, so refusing is
        the only way the mistake is ever seen."""
        with pytest.raises(SystemExit) as exit_info:
            tool.iso_date("01/09/2026", "--target")
        message = str(exit_info.value)
        assert "--target" in message and "YYYY-MM-DD" in message and "UTC" in message


class TestEpicWritesThem:
    @pytest.fixture
    def make(self, monkeypatch, tool, capsys):
        def go(**overrides):
            fields = []
            monkeypatch.setattr(tool, "require_sprint_config", lambda *a, **k: None)
            monkeypatch.setattr(tool, "require_key_for_prefix", lambda *a, **k: None)
            monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
            monkeypatch.setattr(tool, "create_issue", lambda *a, **k: (9, "I_9"))
            monkeypatch.setattr(tool, "apply_title_prefix",
                                lambda *a, **k: "AGILE-9 an epic")
            monkeypatch.setattr(tool, "add_to_project", lambda *a, **k: "PVTI_9")
            monkeypatch.setattr(tool, "set_field",
                                lambda login, project, item, name, v: fields.append((name, v)))
            args = argparse.Namespace(title="an epic", repo="o/r", key="AGILE",
                                      initiative=None, intent=None, acceptance=None,
                                      owner="o", project=1, start=None, target=None,
                                      _config={})
            for name, value in overrides.items():
                setattr(args, name, value)
            tool.cmd_epic(args)
            return fields, capsys.readouterr().out
        return go

    def test_both_dates_are_written(self, tool, make):
        fields, _out = make(start="2026-09-01", target="2026-10-31")
        assert ("Start date", "2026-09-01") in fields
        assert ("Target date", "2026-10-31") in fields

    def test_one_alone_is_fine(self, tool, make):
        fields, _out = make(target="2026-10-31")
        assert ("Target date", "2026-10-31") in fields
        assert not any(name == "Start date" for name, _v in fields)

    def test_neither_writes_nothing_extra(self, tool, make):
        """An epic with no dates behaves exactly as it did before they existed."""
        fields, _out = make()
        assert fields == [("Status", "Todo")]

    def test_the_write_is_reported(self, tool, make):
        _fields, out = make(start="2026-09-01")
        assert "Start date = 2026-09-01" in out

    def test_a_bad_date_creates_nothing(self, tool, make):
        """Refused before the issue exists: an issue number is never reused."""
        with pytest.raises(SystemExit):
            make(start="01/09/2026")

    def test_the_initiative_target_is_not_confused_with_a_date(self, tool, make,
                                                               monkeypatch):
        """`target` in `cmd_epic` was already the initiative being attached to,
        which is why the dates are named `starts_on` and `targets_on`."""
        attached = []
        monkeypatch.setattr(tool, "initiative_target",
                            lambda *a, **k: {"id": "I_i", "slug": "s",
                                             "repo": "o/r", "number": 5})
        monkeypatch.setattr(tool, "attach_to_initiative",
                            lambda t, repo, number, node: attached.append(number))
        fields, _out = make(initiative="s", target="2026-10-31")
        assert attached == [9]
        assert ("Target date", "2026-10-31") in fields


class TestTheExportAndCatalogMoveTogether:
    @staticmethod
    def catalog_props():
        doc = json.loads((ROOT / "github_catalog.json").read_text())
        stream = next(s for s in doc["streams"]
                      if s["tap_stream_id"] == "github_issues")
        return stream["schema"]["properties"]

    def test_both_columns_are_declared(self):
        props = self.catalog_props()
        assert "field_start_date" in props and "field_target_date" in props

    def test_they_are_nullable_dates(self):
        """Null on anything nobody dated, which is most rows."""
        for name in ("field_start_date", "field_target_date"):
            declared = self.catalog_props()[name]
            assert "null" in declared["type"]
            assert declared.get("format") == "date"

    def test_the_description_says_a_plan_is_not_a_measurement(self):
        described = self.catalog_props()["field_start_date"]["description"]
        assert "not interchangeable" in described

    def test_the_column_name_follows_the_field_name(self, tool):
        """`field_{name}` with spaces to underscores -- the rule the row builder
        applies, so a renamed field renames its column."""
        for field_name in tool.DATE_FIELDS:
            column = "field_" + field_name.lower().replace(" ", "_")
            assert column in self.catalog_props()


class TestTheDerivedAxisIsUnchanged:
    def test_the_roadmap_still_groups_by_started_in(self, tool):
        """A target date is a plan; `when did this start` stays derived from the
        `sprint:` labels beneath an item."""
        assert tool.LAYOUT_SECTIONS["ROADMAP_LAYOUT"] == "start"

    def test_derive_starts_reads_labels_not_fields(self, tool):
        source = pathlib.Path(tool.__file__).read_text()
        body = source.split("def derive_starts(")[1].split("\ndef ")[0]
        assert "SPRINT_LABEL" in body
        assert "Start date" not in body
