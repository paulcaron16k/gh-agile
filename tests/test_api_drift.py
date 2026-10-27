"""Detect GitHub API drift: a committed snapshot, a check, a changelog. AGILE-291.

`ProjectV2Iteration` gained `id` and nothing here noticed (#290); the design
rested on its absence. `scripts/api_drift.py` keeps an ordered snapshot of the
schema and says what changed. The fetch is live and stubbed here; everything
else is pure.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def drift():
    spec = importlib.util.spec_from_file_location("api_drift", ROOT / "scripts" / "api_drift.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def named(name, kind="OBJECT"):
    return {"kind": kind, "name": name, "ofType": None}


def non_null(ref):
    return {"kind": "NON_NULL", "name": None, "ofType": ref}


def listed(ref):
    return {"kind": "LIST", "name": None, "ofType": ref}


def value(name, ref, description=None):
    return {"name": name, "description": description, "type": ref, "defaultValue": None}


def introspection():
    """A small `__schema`, deliberately out of order, as a server might send it."""
    iteration = {"kind": "INPUT_OBJECT", "name": "ProjectV2Iteration",
                 "description": "Represents an iteration", "specifiedByURL": None,
                 "fields": None, "interfaces": None, "enumValues": None,
                 "possibleTypes": None, "inputFields": [
                     value("title", non_null(named("String", "SCALAR"))),
                     value("startDate", non_null(named("Date", "SCALAR")))]}
    mutation = {"kind": "OBJECT", "name": "Mutation", "description": None,
                "specifiedByURL": None, "inputFields": None, "enumValues": None,
                "possibleTypes": None, "interfaces": [], "fields": [
                    {"name": "updateProjectV2Field", "description": None,
                     "args": [value("input", non_null(named("X", "INPUT_OBJECT")))],
                     "type": named("UpdateProjectV2FieldPayload"),
                     "isDeprecated": False, "deprecationReason": None},
                    {"name": "addStar", "description": None, "args": [],
                     "type": named("AddStarPayload"), "isDeprecated": False,
                     "deprecationReason": None}]}
    starrable = {"kind": "OBJECT", "name": "Gist", "description": None,
                 "specifiedByURL": None, "inputFields": None, "enumValues": None,
                 "possibleTypes": None, "interfaces": [named("Starrable", "INTERFACE")],
                 "fields": [{"name": "stars", "description": None, "args": [],
                             "type": non_null(listed(non_null(named("User")))),
                             "isDeprecated": False, "deprecationReason": None}]}
    return {"queryType": {"name": "Query"}, "mutationType": {"name": "Mutation"},
            "subscriptionType": None, "types": [starrable, mutation, iteration],
            "directives": [{"name": "skip", "description": None,
                            "locations": ["INLINE_FRAGMENT", "FIELD"], "isRepeatable": False,
                            "args": [value("if", non_null(named("Boolean", "SCALAR")))]}]}


class TestTheSnapshot:
    def test_types_and_members_are_sorted(self, drift):
        spec = drift.normalize(introspection())
        assert [t["name"] for t in spec["types"]] == ["Gist", "Mutation", "ProjectV2Iteration"]
        iteration = spec["types"][2]
        assert [f["name"] for f in iteration["inputFields"]] == ["startDate", "title"]
        assert spec["directives"][0]["locations"] == ["FIELD", "INLINE_FRAGMENT"]

    def test_a_type_reference_is_written_as_the_schema_language_writes_it(self, drift):
        spec = drift.normalize(introspection())
        assert spec["types"][0]["fields"][0]["type"] == "[User!]!"
        assert spec["types"][2]["inputFields"][1]["type"] == "String!"

    def test_the_same_schema_in_another_order_dumps_identically(self, drift):
        shuffled = introspection()
        shuffled["types"].reverse()
        next(t for t in shuffled["types"]
             if t["name"] == "ProjectV2Iteration")["inputFields"].reverse()
        assert drift.dump(drift.normalize(shuffled)) == drift.dump(
            drift.normalize(introspection()))

    def test_keys_are_sorted(self, drift):
        text = drift.dump(drift.normalize(introspection()))
        first = json.loads(text)["types"][0]
        assert list(first) == sorted(first)


@pytest.fixture
def base(drift):
    return drift.normalize(introspection())


def changed(drift, base, edit):
    new = copy.deepcopy(base)
    edit(new)
    return drift.diff(base, new)


def find(spec, name):
    return next(t for t in spec["types"] if t["name"] == name)


class TestTheDiff:
    def test_no_change_is_no_drift(self, drift, base):
        assert drift.diff(base, copy.deepcopy(base)) == []

    def test_the_change_that_started_this(self, drift, base):
        """`ProjectV2Iteration` gains `id`, with its description."""
        def add_id(spec):
            find(spec, "ProjectV2Iteration")["inputFields"].insert(0, {
                "name": "id", "type": "String", "defaultValue": None,
                "description": "The ID of an existing iteration."})
        (change,) = changed(drift, base, add_id)
        assert change["change"] == "added" and change["what"] == "input field"
        assert change["path"] == "ProjectV2Iteration.id"
        assert "String" in change["detail"] and "existing iteration" in change["detail"]

    def test_a_removed_type(self, drift, base):
        (change,) = changed(drift, base, lambda s: s["types"].pop(0))
        assert change == {"change": "removed", "path": "Gist", "what": "object", "detail": ""}

    def test_a_type_change(self, drift, base):
        def loosen(spec):
            find(spec, "ProjectV2Iteration")["inputFields"][1]["type"] = "String"
        (change,) = changed(drift, base, loosen)
        assert change["path"] == "ProjectV2Iteration.title"
        assert change["detail"] == "type: 'String!' -> 'String'"

    def test_a_deprecation(self, drift, base):
        def deprecate(spec):
            field = find(spec, "Gist")["fields"][0]
            field.update(isDeprecated=True, deprecationReason="Use stargazers")
        paths = {(c["path"], c["detail"].split(":")[0]) for c in changed(drift, base, deprecate)}
        assert paths == {("Gist.stars", "isDeprecated"), ("Gist.stars", "deprecationReason")}

    def test_an_argument_added(self, drift, base):
        def add_arg(spec):
            find(spec, "Mutation")["fields"][1]["args"].append(
                {"name": "dryRun", "type": "Boolean", "description": None,
                 "defaultValue": None})
        (change,) = changed(drift, base, add_arg)
        assert change["path"] == "Mutation.updateProjectV2Field(dryRun)"
        assert change["what"] == "argument"

    def test_a_description_change_is_reported(self, drift, base):
        """The `id` field's behaviour was documented in its description."""
        def reword(spec):
            find(spec, "ProjectV2Iteration")["description"] = "Now identified"
        (change,) = changed(drift, base, reword)
        assert change["detail"] == 'description now: "Now identified"'


class TestWhatTouchesUs:
    USED = {"ProjectV2Iteration", "updateProjectV2Field"}
    ROOTS = {"Query", "Mutation"}

    @pytest.mark.parametrize("path,ours", [
        ("ProjectV2Iteration.id", True),
        ("Mutation.updateProjectV2Field", True),
        ("Mutation.updateProjectV2Field(dryRun)", True),
        ("Mutation.addStar", False),
        ("Mutation", False),
        ("Gist.stars", False),
    ])
    def test_by_name(self, drift, path, ours):
        assert drift.touches_us({"path": path}, self.USED, self.ROOTS) is ours

    def test_the_extensions_own_names_are_read(self, drift):
        used = drift.names_used((ROOT / "gh-agile").read_text())
        assert {"updateProjectV2Field", "addSubIssue", "ProjectV2Iteration"} <= used

    def test_the_entry_puts_ours_first(self, drift):
        changes = [{"change": "added", "path": "Gist.forks", "what": "field", "detail": ""},
                   {"change": "added", "path": "ProjectV2Iteration.id", "what": "input field",
                    "detail": "String"}]
        entry = drift.render(changes, "2026-10-27T17:00:00Z", self.USED, self.ROOTS)
        assert entry.startswith("## 2026-10-27T17:00:00Z")
        assert "2 change(s): 2 added, 0 removed, 0 changed. 1 touch what gh-agile uses." in entry
        ours = entry.index("### Touches what gh-agile uses")
        rest = entry.index("### Elsewhere in the schema")
        assert ours < entry.index("`ProjectV2Iteration.id`") < rest < entry.index("`Gist.forks`")


class TestCheck:
    @pytest.fixture
    def files(self, drift, tmp_path, base, monkeypatch):
        spec, log = tmp_path / "spec.json", tmp_path / "changelog.md"
        spec.write_text(drift.dump(base))
        monkeypatch.setattr(drift, "now_utc", lambda: "2026-10-27T17:00:00Z")
        return spec, log

    def test_no_drift_writes_nothing_and_exits_zero(self, drift, files, base, monkeypatch):
        spec, log = files
        monkeypatch.setattr(drift, "fetch", lambda: copy.deepcopy(base))
        assert drift.cmd_check(spec, log) == 0
        assert not log.exists()

    def test_drift_appends_an_entry_updates_the_snapshot_and_exits_one(
            self, drift, files, base, monkeypatch):
        spec, log = files
        new = copy.deepcopy(base)
        find(new, "ProjectV2Iteration")["inputFields"].insert(
            0, {"name": "id", "type": "String", "description": None, "defaultValue": None})
        monkeypatch.setattr(drift, "fetch", lambda: new)
        assert drift.cmd_check(spec, log) == 1
        text = log.read_text()
        assert text.startswith("# GitHub API changelog")
        assert "## 2026-10-27T17:00:00Z" in text and "`ProjectV2Iteration.id`" in text
        assert json.loads(spec.read_text()) == json.loads(drift.dump(new))

    def test_a_second_entry_is_appended_after_the_first(self, drift, files, base, monkeypatch):
        spec, log = files
        log.write_text(drift.CHANGELOG_HEADER + "## earlier\n\nBaseline.\n")
        new = copy.deepcopy(base)
        new["types"].pop(0)
        monkeypatch.setattr(drift, "fetch", lambda: new)
        drift.cmd_check(spec, log)
        text = log.read_text()
        assert text.index("## earlier") < text.index("## 2026-10-27T17:00:00Z")

    def test_no_write_reports_only(self, drift, files, base, monkeypatch):
        spec, log = files
        before = spec.read_text()
        new = copy.deepcopy(base)
        new["types"].pop(0)
        monkeypatch.setattr(drift, "fetch", lambda: new)
        assert drift.cmd_check(spec, log, write=False) == 1
        assert spec.read_text() == before and not log.exists()

    def test_no_snapshot_exits_two(self, drift, tmp_path):
        assert drift.cmd_check(tmp_path / "absent.json", tmp_path / "log.md") == 2


def test_the_committed_snapshot_is_in_order(drift):
    """Written by `dump`, so re-dumping it changes nothing: a diff against it
    is only ever real change."""
    path = ROOT / "GitHub_API_spec.json"
    text = path.read_text()
    assert drift.dump(json.loads(text)) == text


def test_the_committed_snapshot_has_the_field_that_started_this(drift):
    spec = json.loads((ROOT / "GitHub_API_spec.json").read_text())
    iteration = find(spec, "ProjectV2Iteration")
    assert "id" in {f["name"] for f in iteration["inputFields"]}
