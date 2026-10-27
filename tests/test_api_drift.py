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
    USED = {"ProjectV2Iteration", "ProjectV2Iteration.title", "Mutation.updateProjectV2Field",
            "Mutation.updateProjectV2Field(input)", "Gist"}
    ROOTS = {"Query", "Mutation"}

    @pytest.mark.parametrize("change,path,ours", [
        ("added", "ProjectV2Iteration.id", True),          # on a type we use: adoptable
        ("removed", "ProjectV2Iteration.id", False),       # never sent, so not ours
        ("removed", "ProjectV2Iteration.title", True),
        ("added", "Mutation.updateProjectV2Field", True),
        ("added", "Mutation.updateProjectV2Field(dryRun)", True),
        ("removed", "Mutation.updateProjectV2Field(dryRun)", False),
        ("removed", "Mutation.updateProjectV2Field(input)", True),
        ("removed", "Mutation.updateProjectV2Field.input", True),   # GitHub's spelling
        ("added", "Mutation.addStar", False),              # a root field we do not call
        ("changed", "Mutation", False),
        ("removed", "Repository.project", False),
    ])
    def test_by_use(self, drift, change, path, ours):
        assert drift.touches_us({"change": change, "path": path}, self.USED, self.ROOTS) is ours

    def test_the_extensions_own_graphql_is_read(self, drift):
        spec = json.loads((ROOT / "GitHub_API_spec.json").read_text())
        used = drift.names_used((ROOT / "gh-agile").read_text(), spec)
        assert {"Mutation.updateProjectV2Field", "Mutation.addSubIssue", "Query.user",
                "Query.organization", "ProjectV2Iteration", "ProjectV2Iteration.id",
                "ProjectV2IterationFieldConfigurationInput.iterations",
                "ProjectV2Item.project", "AssignedEvent.assignee"} <= used
        # The words are all over the comments; the GraphQL never selects them.
        assert not {"Repository.project", "User.project", "Project", "Issue.timeline",
                    "AssignedEvent.user"} & used

    def test_the_entry_puts_ours_first(self, drift):
        changes = [{"change": "added", "path": "Gist.forks", "what": "field", "detail": ""},
                   {"change": "added", "path": "ProjectV2Iteration.id", "what": "input field",
                    "detail": "String"}]
        entry = drift.render(changes, "2026-10-27T17:00:00Z", self.USED - {"Gist"}, self.ROOTS)
        assert entry.startswith("## 2026-10-27T17:00:00Z")
        assert "2 change(s): 2 added, 0 removed, 0 changed. 1 touch what gh-agile uses." in entry
        ours = entry.index("### Touches what gh-agile uses")
        rest = entry.index("### Elsewhere in the schema")
        assert ours < entry.index("`ProjectV2Iteration.id`") < rest < entry.index("`Gist.forks`")


#: Fixture copies of GitHub's published files, in their real shapes.
PUBLISHED_LOG = [
    {"date": "2026-10-27", "previewChanges": [], "upcomingChanges": [], "schemaChanges": [
        {"title": "The GraphQL schema includes these changes:", "changes": [
            "<p>Field <code>forks</code> was added to object type <code>Gist</code></p>"]}]},
    {"date": "2026-10-01", "previewChanges": [], "upcomingChanges": [], "schemaChanges": [
        {"title": "The GraphQL schema includes these changes:", "changes": [
            "<p>Input field <code>id</code> of type <code>String</code> was added to input "
            "object type 'ProjectV2Iteration'</p>"]}]},
    {"date": "2026-06-23", "previewChanges": [], "schemaChanges": [], "upcomingChanges": [
        {"title": "The following changes will be made to the schema:", "changes": [
            "<p>On member <code>Gist.stars</code>: will be removed.</p>"]}]},
]
UPCOMING = {
    "2026-12-01": [{"location": "ProjectV2Iteration.title", "date": "2026-12-01",
                    "criticality": "breaking",
                    "description": "<p><code>title</code> will be removed.</p>"}],
    "2027-07-01": [{"location": "Mutation.updateProjectV2Field", "date": "2027-07-01",
                    "criticality": "breaking",
                    "description": "<p>Use <code>updateProjectV2IterationField</code>.</p>"},
                   {"location": "Gist.stars", "date": "2026-11-01",
                    "criticality": "breaking", "description": "<p>gone</p>"}],
}


class TestGitHubsPublishedRecord:
    USED = {"ProjectV2Iteration", "ProjectV2Iteration.title", "Mutation.updateProjectV2Field"}
    ROOTS = {"Query", "Mutation"}

    def test_html_becomes_markdown(self, drift):
        assert drift.as_markdown("<p>Field <code>a&amp;b</code> was <em>added</em></p>") == (
            "Field `a&b` was added")

    def test_items_since_our_last_entry_oldest_first(self, drift):
        items = drift.published_since(PUBLISHED_LOG, "2026-10-01")
        assert [d for d, _t in items] == ["2026-10-01", "2026-10-27"]
        assert "'ProjectV2Iteration'" in items[0][1]

    def test_no_previous_entry_means_no_window(self, drift):
        assert drift.published_since(PUBLISHED_LOG, None) == []

    def test_our_last_entry_date_is_read_from_the_changelog(self, drift, tmp_path):
        log = tmp_path / "log.md"
        log.write_text("# x\n\n## 2026-09-01T00:00:00Z\n\na\n\n## 2026-10-27T21:40:05Z\n\nb\n")
        assert drift.last_entry_date(log) == "2026-10-27"
        assert drift.last_entry_date(tmp_path / "absent.md") is None

    def test_upcoming_removals_touching_us_due_first(self, drift):
        import datetime as dt

        items = drift.upcoming_for_us(UPCOMING, self.USED, self.ROOTS, dt.date(2026, 10, 27))
        assert [(i["location"], i["due"]) for i in items] == [
            ("ProjectV2Iteration.title", True), ("Mutation.updateProjectV2Field", False)]

    def test_a_removal_of_a_member_we_do_not_use_is_not_ours(self, drift):
        import datetime as dt

        upcoming = {"2026-11-01": [{"location": "ProjectV2Iteration.weight",
                                    "date": "2026-11-01", "criticality": "breaking",
                                    "description": ""}]}
        assert drift.upcoming_for_us(upcoming, self.USED, self.ROOTS,
                                     dt.date(2026, 10, 27)) == []

    @pytest.mark.parametrize("path,said", [
        ("ProjectV2Iteration.id", True),      # the type is quoted, not in code
        ("Gist.forks", True),
        ("Gist.stars", True),                 # announced, in an upcomingChanges group
        ("Gist.watchers", False),
        ("ProjectV2Iteration.startDate", False),
    ])
    def test_whether_githubs_changelog_mentions_a_change(self, drift, path, said):
        items = drift.published_since(PUBLISHED_LOG, "2026-01-01")
        assert drift.mentioned({"path": path}, items) is said

    def test_the_entry_says_what_github_did_not_mention(self, drift):
        changes = [{"change": "added", "path": "ProjectV2Iteration.id", "what": "input field",
                    "detail": "String"},
                   {"change": "added", "path": "Gist.watchers", "what": "field", "detail": ""}]
        published = {"since": "2026-10-01", "error": None,
                     "items": drift.published_since(PUBLISHED_LOG, "2026-10-01"),
                     "upcoming": []}
        entry = drift.render(changes, "2026-10-27T17:00:00Z", self.USED, self.ROOTS, published)
        lines = {line.split("`")[1]: line for line in entry.splitlines() if line.startswith("- ")
                 and "`" in line and not line.startswith("- 2026")}
        assert "not in GitHub's changelog" not in lines["ProjectV2Iteration.id"]
        assert "not in GitHub's changelog" in lines["Gist.watchers"]
        assert "### GitHub's changelog since 2026-10-01" in entry

    def test_the_entry_lists_removals_touching_us(self, drift):
        import datetime as dt

        published = {"since": None, "error": None, "items": [],
                     "upcoming": drift.upcoming_for_us(UPCOMING, self.USED, self.ROOTS,
                                                       dt.date(2026, 10, 27))}
        entry = drift.render([], "2026-10-27T17:00:00Z", self.USED, self.ROOTS, published)
        removals = entry.split("### Announced removals touching gh-agile", 1)[1]
        assert removals.index("due 2026-12-01 `ProjectV2Iteration.title` (breaking)") \
            < removals.index("2027-07-01 `Mutation.updateProjectV2Field`")

    def test_a_published_record_that_cannot_be_read_is_said_not_fatal(self, drift):
        published = {"since": "2026-10-01", "error": "could not be read: 404",
                     "items": [], "upcoming": []}
        changes = [{"change": "added", "path": "Gist.x", "what": "field", "detail": ""}]
        entry = drift.render(changes, "t", self.USED, self.ROOTS, published)
        assert "could not be read: 404" in entry and "not in GitHub's changelog" not in entry

    def test_fetch_failure_is_reported_not_raised(self, drift, monkeypatch):
        def refuse(name):
            raise OSError("no network")
        monkeypatch.setattr(drift, "_get_json", refuse)
        assert drift.fetch_published() == (
            None, None, "GitHub's published changelog could not be read: no network")


class TestCheck:
    @pytest.fixture
    def files(self, drift, tmp_path, base, monkeypatch):
        spec, log = tmp_path / "spec.json", tmp_path / "changelog.md"
        spec.write_text(drift.dump(base))
        monkeypatch.setattr(drift, "now_utc", lambda: "2026-10-27T17:00:00Z")
        monkeypatch.setattr(drift, "fetch_published", lambda: (PUBLISHED_LOG, UPCOMING, None))
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

    def test_summary_is_the_entry_alone(self, drift, files, base, monkeypatch, tmp_path):
        """The scheduled workflow's pull request body (#298)."""
        spec, log = files
        new = copy.deepcopy(base)
        new["types"].pop(0)
        monkeypatch.setattr(drift, "fetch", lambda: new)
        summary = tmp_path / "entry.md"
        drift.cmd_check(spec, log, summary=summary)
        text = summary.read_text()
        assert text.startswith("## 2026-10-27T17:00:00Z") and "`Gist`" in text
        assert "# GitHub API changelog" not in text

    def test_no_drift_writes_no_summary(self, drift, files, base, monkeypatch, tmp_path):
        spec, log = files
        monkeypatch.setattr(drift, "fetch", lambda: copy.deepcopy(base))
        summary = tmp_path / "entry.md"
        drift.cmd_check(spec, log, summary=summary)
        assert not summary.exists()

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


def test_no_drift_still_warns_of_a_removal_that_is_due(drift, tmp_path, base, monkeypatch,
                                                      capsys):
    """A removal is announced months before the schema changes, and the warning
    is worth nothing after it lands."""
    spec = tmp_path / "spec.json"
    spec.write_text(drift.dump(base))
    monkeypatch.setattr(drift, "now_utc", lambda: "2026-10-27T17:00:00Z")
    monkeypatch.setattr(drift, "fetch", lambda: copy.deepcopy(base))
    monkeypatch.setattr(drift, "fetch_published", lambda: (PUBLISHED_LOG, UPCOMING, None))
    monkeypatch.setattr(drift, "names_used", lambda source, spec: {
        "ProjectV2Iteration", "ProjectV2Iteration.title", "Mutation.updateProjectV2Field"})
    assert drift.cmd_check(spec, tmp_path / "log.md") == 0
    out = capsys.readouterr().out
    assert "no drift" in out and "`ProjectV2Iteration.title`" in out
    assert "updateProjectV2Field" not in out    # announced, but not due within 90 days


#: A schema small enough to read, shaped like the parts gh-agile touches.
def kind(name, kind_="OBJECT", fields=(), inputs=None):
    return {"name": name, "kind": kind_, "fields": [
        {"name": f, "type": t, "args": [{"name": a, "type": at} for a, at in args]}
        for f, t, args in fields] if kind_ != "INPUT_OBJECT" else None,
        "inputFields": [{"name": f, "type": t} for f, t in inputs] if inputs else None}


SMALL = {"queryType": "Query", "mutationType": "Mutation", "subscriptionType": None, "types": [
    kind("Query", fields=[("user", "User", [("login", "String!")]),
                          ("organization", "Organization", [("login", "String!")]),
                          ("repository", "Repository", [("owner", "String!"),
                                                        ("name", "String!")])]),
    kind("Mutation", fields=[("updateField", "Payload", [("input", "UpdateInput!")]),
                             ("addStar", "Payload", [("input", "StarInput!")])]),
    kind("User", fields=[("projectV2", "ProjectV2", [("number", "Int!")]),
                         ("project", "Project", [("number", "Int!")])]),
    kind("Organization", fields=[("projectV2", "ProjectV2", [("number", "Int!")])]),
    kind("Repository", fields=[("project", "Project", []), ("issue", "Issue", [])]),
    kind("ProjectV2", fields=[("items", "ItemConnection!", [("first", "Int")]),
                              ("title", "String!", [])]),
    kind("ItemConnection", fields=[("nodes", "[Item]", [])]),
    kind("Item", fields=[("id", "ID!", []), ("project", "ProjectV2!", []),
                         ("content", "Content", [])]),
    kind("Content", "UNION"),
    kind("Issue", fields=[("number", "Int!", []), ("title", "String!", [])]),
    kind("Project", fields=[("name", "String!", [])]),
    kind("Payload", fields=[("ok", "Boolean", [])]),
    kind("UpdateInput", "INPUT_OBJECT", inputs=[("fieldId", "ID!"), ("config", "ConfigInput")]),
    kind("ConfigInput", "INPUT_OBJECT", inputs=[("duration", "Int"),
                                                ("iterations", "[EntryInput!]")]),
    kind("EntryInput", "INPUT_OBJECT", inputs=[("id", "String"), ("title", "String!")]),
    kind("StarInput", "INPUT_OBJECT", inputs=[("starrableId", "ID!")]),
]}

SOURCE = '''
"""A docstring that talks about Repository.project and addStar."""
# A comment: the user's project and addStar.

ITEMS_QUERY_SHELL = """
query($login: String!, $number: Int!) {
  %(root)s(login: $login) { projectV2(number: $number) {
    title
    items(first: 100) { nodes { %(nodes)s } } } }
}"""

ITEM_SELECTION = """
id
proj: project { title }
content { ... on Issue { number title } }
"""


def read(root):
    for root in ("user", "organization"):
        graphql(ITEMS_QUERY_SHELL % {"root": root, "nodes": ITEM_SELECTION})


def write(entries):
    graphql(
        "mutation($f: ID!) { updateField(input: {fieldId: $f, config: {duration: 14, "
        "iterations: [%s]}}) { ok } }" % ", ".join(entries))
'''


class TestTheReader:
    @pytest.fixture
    def used(self, drift):
        return drift.names_used(SOURCE, SMALL)

    def test_only_graphql_is_read(self, drift):
        texts, _words = drift.graphql_texts(SOURCE)
        assert texts and not any("docstring" in t or "comment" in t for t in texts)

    def test_an_interpolated_root_is_each_one_word_constant_that_fits(self, used):
        assert {"Query.user", "Query.organization", "Query.user(login)"} <= used
        assert "Query.repository" not in used

    def test_a_name_is_looked_up_on_the_type_it_is_selected_on(self, used):
        """`project` is selected on an item: not `User.project`, nor
        `Repository.project`, nor the classic `Project` type."""
        assert {"User.projectV2", "ProjectV2.items", "Item.project", "Item.id"} <= used
        assert not {"User.project", "Repository.project", "Project"} & used

    def test_an_alias_is_the_field_it_names(self, used):
        assert "Item.project" in used and "Item.proj" not in used

    def test_a_bare_selection_is_read_where_it_is_inserted(self, used):
        assert {"Item.content", "Content", "Issue", "Issue.number"} <= used

    def test_an_input_object_is_walked_through_its_fields(self, used):
        assert {"Mutation.updateField", "Mutation.updateField(input)", "UpdateInput",
                "UpdateInput.fieldId", "UpdateInput.config", "ConfigInput.duration",
                "ConfigInput.iterations", "EntryInput"} <= used

    def test_entries_built_elsewhere_count_every_input_field(self, used):
        """`iterations: [%s]`: `iteration_entry` builds each one whole."""
        assert {"EntryInput.id", "EntryInput.title"} <= used

    def test_a_root_field_never_called_is_not_used(self, used):
        assert "Mutation.addStar" not in used and "StarInput" not in used
