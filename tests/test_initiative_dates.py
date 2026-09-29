"""An initiative carries dates too, or the web roadmap drops it. AGILE-179.

#175 gave an **epic** `Start date` and `Target date` because GitHub's roadmap
layout places an item from a date field or an iteration field, and a container
has neither -- #115 barred the Sprint. #176 then put initiatives on that
roadmap, which reproduced the defect exactly one level up: `board show` renders
them, and the web UI drops them into the undated bucket.

**Typed, never derived.** The tool could compute an initiative's dates from the
epics beneath it, and would then be authoring a plan nobody made. The derived
answer to *when did this start* already exists as the roadmap's own axis, from
the `sprint:` labels below. **A plan is not a measurement**, and the two are not
interchangeable -- the distinction #175 was careful to establish and this story
must not quietly undo.

Nothing here creates a field: `setup` already makes both.
"""

from __future__ import annotations

import argparse
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def make(monkeypatch, tool, capsys):
    """`cmd_initiative` with GitHub replaced."""
    def go(**overrides):
        fields = []
        monkeypatch.setattr(tool, "require_sprint_config", lambda *a, **k: None)
        monkeypatch.setattr(tool, "require_key_for_prefix", lambda *a, **k: None)
        monkeypatch.setattr(tool, "find_initiative", lambda *a, **k: None)
        monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
        monkeypatch.setattr(tool, "create_issue", lambda *a, **k: (9, "I_9"))
        monkeypatch.setattr(tool, "apply_title_prefix", lambda *a, **k: "AGILE-9 an init")
        monkeypatch.setattr(tool, "add_to_project", lambda *a, **k: "PVTI_9")
        monkeypatch.setattr(tool, "set_field",
                            lambda login, project, item, name, v: fields.append((name, v)))
        args = argparse.Namespace(title="an initiative", slug=None, repo="o/r",
                                  key="AGILE", intent=None, acceptance=None,
                                  owner="o", project=1, start=None, target=None,
                                  initiative_command="create", _config={})
        for name, value in overrides.items():
            setattr(args, name, value)
        go.fields = fields
        tool.cmd_initiative(args)
        return fields, capsys.readouterr().out
    return go


class TestItTakesTheSameTwoFlags:
    def test_both_dates_are_written(self, tool, make):
        fields, _out = make(start="2026-09-01", target="2026-12-31")
        assert ("Start date", "2026-09-01") in fields
        assert ("Target date", "2026-12-31") in fields

    def test_one_alone_is_fine(self, tool, make):
        fields, _out = make(start="2026-09-01")
        assert ("Start date", "2026-09-01") in fields
        assert not any(name == "Target date" for name, _v in fields)

    def test_neither_behaves_as_before(self, tool, make):
        """An initiative with no dates behaves exactly as it does today."""
        fields, _out = make()
        assert fields == [("Status", "Todo")]

    def test_the_write_is_reported(self, tool, make):
        _fields, out = make(target="2026-12-31")
        assert "Target date = 2026-12-31" in out

    def test_the_slug_and_label_are_unaffected(self, tool, make):
        _fields, out = make(start="2026-09-01")
        assert "initiative:an-initiative" in out


class TestItRefusesBeforeItCreates:
    @pytest.mark.parametrize("bad", ["01/09/2026", "Sept", "2026-13-01", ""])
    def test_a_bad_date_is_refused(self, tool, make, bad):
        with pytest.raises(SystemExit) as exit_info:
            make(start=bad)
        assert "not a date" in str(exit_info.value)

    def test_and_creates_nothing(self, tool, make, monkeypatch):
        """An issue number is never reused, so a refusal afterwards costs one."""
        created = []
        monkeypatch.setattr(tool, "create_issue",
                            lambda *a, **k: created.append(1) or (9, "I_9"))
        with pytest.raises(SystemExit):
            make(target="tomorrow")
        assert created == []

    def test_it_is_the_same_parser_epic_uses(self, tool):
        """A second parser is one that can disagree about what a date is.

        Read from `create_initiative`, not `cmd_initiative`: the latter only
        dispatches, so splitting on it finds an empty body and passes on
        nothing."""
        source = pathlib.Path(tool.__file__).read_text()
        body = source.split("def create_initiative(")[1].split("\ndef ")[0]
        assert "iso_date(" in body


class TestNothingIsDerived:
    def test_the_command_does_not_look_at_its_epics(self, tool):
        """**The line this story must not cross.** A plan is typed; the derived
        answer already exists as the roadmap's axis.

        Against `create_initiative`, which is where the work is -- this passed
        vacuously against the dispatcher first time out."""
        source = pathlib.Path(tool.__file__).read_text()
        body = source.split("def create_initiative(")[1].split("\ndef ")[0]
        for derived in ("derive_starts", "sub_issues", "SPRINT_LABEL"):
            assert derived not in body

    def test_the_roadmap_axis_still_comes_from_labels(self, tool):
        source = pathlib.Path(tool.__file__).read_text()
        body = source.split("def derive_starts(")[1].split("\ndef ")[0]
        assert "SPRINT_LABEL" in body
        assert "Start date" not in body

    def test_an_undated_initiative_still_has_a_roadmap_section(self, tool):
        """The axis needs no field: `derive_starts` walks descendants."""
        assert tool.LAYOUT_SECTIONS["ROADMAP_LAYOUT"] == "start"


class TestNoFieldIsCreatedHere:
    def test_setup_already_makes_both(self, tool):
        """If this story found itself editing the spec, something went wrong."""
        names = [f["name"] for f in tool.DEFAULT_SPEC["fields"]]
        assert set(tool.DATE_FIELDS) <= set(names)

    def test_the_export_needs_no_new_column(self, tool):
        """`field_start_date` and `field_target_date` carry any item's values,
        initiative included -- asserted rather than assumed."""
        import json
        doc = json.loads((ROOT / "github_catalog.json").read_text())
        stream = next(s for s in doc["streams"]
                      if s["tap_stream_id"] == "github_issues")
        props = stream["schema"]["properties"]
        for field_name in tool.DATE_FIELDS:
            assert "field_" + field_name.lower().replace(" ", "_") in props

    def test_the_two_commands_write_the_same_field_names(self, tool):
        """One constant, so a third date added to it reaches both or neither."""
        source = pathlib.Path(tool.__file__).read_text()
        for command in ("cmd_epic(", "create_initiative("):
            body = source.split(f"def {command}")[1].split("\ndef ")[0]
            assert "DATE_FIELDS" in body
