"""`github_catalog.json` describes what the export actually writes.

**A catalog that has drifted is worse than none, because it is trusted.** The
same lesson as `make check-guide` for the guide and the interpreter matrix for the
floor: *a promise nothing verifies is a promise nothing keeps.*

This is not hypothetical. When `#90` added five columns to `github_issues`, the
catalog was updated **by hand** and parity checked **by hand** against a live
export. Nothing would have caught the omission, and the next person adding a
column has no reason to know the file exists.

Both directions, because the likelier one is a column added to a builder and not
to the catalog: adding a column is routine, and updating a schema file is the step
people forget.

Offline. The builders are called with fixtures, so nothing here needs GitHub --
which is what lets it run in `make test` on every change rather than in a live
target nobody runs before merging.
"""

from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Added by `cmd_export` to every row of the issue-shaped grains, not by the
#: builders themselves. Master rows carry it already, since they are stamped
#: where they are built.
STAMPED_BY_EXPORT = {"exported_at"}

KEYS = {"o/r": "AGILE"}


@pytest.fixture(scope="session")
def catalog():
    return {s["tap_stream_id"]: s
            for s in json.loads((ROOT / "github_catalog.json").read_text())["streams"]}


def field(name, value, typename="ProjectV2ItemFieldTextValue", key="text"):
    return {"__typename": typename, key: value, "field": {"name": name}}


def board_item():
    """One project item carrying every field `setup` creates, so the dynamic
    `field_*` columns the catalog declares are all produced."""
    return {
        "id": "PVTI_1", "isArchived": False, "updatedAt": "2026-09-16T00:00:00Z",
        "fieldValues": {"nodes": [
            field("Title", "a title"),
            field("Status", "Done", "ProjectV2ItemFieldSingleSelectValue", "name"),
            field("Sprint", "0004 W38-2026", "ProjectV2ItemFieldIterationValue", "title"),
            field("Story Points", 3.0, "ProjectV2ItemFieldNumberValue", "number"),
            field("Priority", "high", "ProjectV2ItemFieldSingleSelectValue", "name"),
            field("FR", "FR-7.18"),
        ]},
        "content": {
            "__typename": "Issue", "id": "I_1", "number": 7, "title": "a title",
            "url": "u", "state": "CLOSED", "stateReason": "COMPLETED",
            "createdAt": "2026-09-01T00:00:00Z", "updatedAt": "2026-09-16T00:00:00Z",
            "closedAt": "2026-09-16T00:00:00Z",
            "author": {"login": "dev"}, "repository": {"nameWithOwner": "o/r"},
            "labels": {"nodes": [{"name": "type:story"}, {"name": "key:AGILE"},
                                 {"name": "sprint:2026-09-14"},
                                 {"name": "initiative:big-thing"}]},
            "assignees": {"nodes": [{"login": "dev"}]},
            "milestone": {"title": "m"},
            "parent": {"number": 9, "title": "an epic",
                       "repository": {"nameWithOwner": "o/r"},
                       "labels": {"nodes": [{"name": "type:epic"}]}},
            "subIssuesSummary": {"total": 1, "completed": 1},
            "closedByPullRequestsReferences": {"nodes": [
                {"number": 3, "createdAt": "2026-09-10T00:00:00Z", "merged": True,
                 "author": {"login": "dev"}}]},
        },
    }


def pull():
    return {
        "id": "PR_1", "number": 3, "title": "a change", "url": "u", "state": "MERGED",
        "isDraft": False, "createdAt": "2026-09-10T00:00:00Z",
        "updatedAt": "2026-09-11T00:00:00Z", "closedAt": "2026-09-11T00:00:00Z",
        "mergedAt": "2026-09-11T00:00:00Z", "author": {"login": "dev"},
        "repository": {"nameWithOwner": "o/r"}, "baseRefName": "main",
        "headRefName": "f", "additions": 1, "deletions": 1, "changedFiles": 1,
        "commits": {"totalCount": 1}, "reviewDecision": "APPROVED",
        "mergedBy": {"login": "dev"},
        "closingIssuesReferences": {"nodes": []},
        "reviews": {"totalCount": 1, "nodes": [
            {"id": "RV_1", "state": "APPROVED", "submittedAt": "2026-09-11T00:00:00Z",
             "author": {"login": "bea"},
             "comments": {"nodes": [{"id": "RC_1", "createdAt": "2026-09-11T00:00:00Z",
                                     "author": {"login": "bea"}}]}}]},
    }


@pytest.fixture
def produced(monkeypatch, tool):
    """The column set each stream's builders actually emit, from fixtures only."""
    config = {"keys": [{"key": "AGILE", "repo": "o/r"}],
              "project": {"key": "AGILE", "number": 4, "name": "p"},
              "sprint": {"cadence_days": 14, "start_day": "monday"},
              "boards": [{"name": "Sprint board", "type": "scrum"}]}
    monkeypatch.setattr(tool, "read_config", lambda *a, **k: config)
    monkeypatch.setattr(tool, "fetch_items", lambda *a, **k: ("t", [board_item()]))
    monkeypatch.setattr(tool, "history", lambda issue_id: {
        "added_to_board_at": "2026-09-01T00:00:00Z",
        "started_at": "2026-09-02T00:00:00Z", "done_at": "2026-09-16T00:00:00Z",
        "_events": [{"__typename": "ClosedEvent", "createdAt": "2026-09-16T00:00:00Z",
                     "actor": {"login": "dev"}, "stateReason": "COMPLETED"}]})
    monkeypatch.setattr(tool, "views_of", lambda *a, **k: [
        {"id": "V_1", "number": 1, "name": "Sprint board", "layout": "BOARD_LAYOUT",
         "filter": "sprint:@current"}])
    monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
        [{"title": "0004 W38-2026", "startDate": "2026-09-14", "duration": 14}], []))

    def columns(rows):
        out = []
        for row in rows:
            out.extend(k for k in row if k not in out)
        return set(out)

    events: list[dict] = []
    issues = tool.rows("o", 4, with_history=True, events=events)
    events.extend(tool.pr_event_rows(pull(), "AGILE", KEYS))
    master = tool.master_rows("o", 4, config, "2026-09-16T00:00:00Z")
    return {
        "github_issues": columns(issues) | STAMPED_BY_EXPORT,
        "github_events": columns(events) | STAMPED_BY_EXPORT,
        "github_prs": columns([tool.pr_row(pull(), KEYS)]) | STAMPED_BY_EXPORT,
        **{f"github_{name}": columns(rows) for name, rows in master.items()},
    }


class TestEveryStreamIsDescribed:
    def test_the_catalog_has_exactly_the_streams_the_export_writes(self, catalog, produced):
        assert set(catalog) == set(produced)

    def test_each_one_declares_a_key(self, catalog):
        """A loader needs to know what a row is identified by, and two
        repositories on one board both have a `#12`."""
        for name, stream in catalog.items():
            assert stream["key_properties"], f"{name} declares no key_properties"

    def test_each_one_declares_how_it_replicates(self, catalog):
        for name, stream in catalog.items():
            meta = stream["metadata"][0]["metadata"]
            assert meta["replication-method"] in ("INCREMENTAL", "FULL_TABLE"), name


class TestNoColumnDriftsEitherWay:
    def test_nothing_is_exported_that_the_catalog_does_not_describe(
            self, catalog, produced):
        """The likelier direction. Adding a column is routine; updating a schema
        file is the step people forget, and a loader's DDL is wrong from then on."""
        for name, columns in sorted(produced.items()):
            declared = set(catalog[name]["schema"]["properties"])
            extra = sorted(columns - declared)
            # `field_<name>` columns are the project's own fields and the schema
            # is open for them by design; anything else is drift.
            open_schema = catalog[name]["schema"].get("additionalProperties")
            extra = [c for c in extra if not (open_schema and c.startswith("field_"))]
            assert not extra, (
                f"{name} exports {extra} which github_catalog.json does not "
                f"describe. Add them there, with a type and nullability.")

    def test_nothing_is_described_that_the_export_no_longer_produces(
            self, catalog, produced):
        for name, columns in sorted(produced.items()):
            declared = set(catalog[name]["schema"]["properties"])
            stale = sorted(declared - columns)
            assert not stale, (
                f"github_catalog.json describes {stale} on {name}, which the "
                f"export no longer produces. Remove them, or the DDL has columns "
                f"nothing fills.")

    def test_the_key_properties_are_columns_that_exist(self, catalog, produced):
        for name, stream in catalog.items():
            missing = [k for k in stream["key_properties"] if k not in produced[name]]
            assert not missing, f"{name} is keyed on {missing}, which it does not export"

    def test_a_replication_key_is_a_column_that_exists(self, catalog, produced):
        for name, stream in catalog.items():
            key = stream["metadata"][0]["metadata"].get("replication-key")
            assert key is None or key in produced[name], \
                f"{name} replicates on {key!r}, which it does not export"


class TestTheConventionsHold:
    """A type alone cannot say these, so the catalog is where they are checked."""

    def test_every_column_declares_a_type(self, catalog):
        for name, stream in catalog.items():
            for column, spec in stream["schema"]["properties"].items():
                assert "type" in spec, f"{name}.{column} declares no type"

    def test_no_column_name_carries_a_unit_suffix(self, catalog):
        """Every duration is an integer count of seconds and no name says so.
        Days reported 0.0 for work taking twenty minutes and for work taking six
        hours."""
        for name, stream in catalog.items():
            for column in stream["schema"]["properties"]:
                assert not column.endswith(("_days", "_hours", "_minutes")), \
                    f"{name}.{column} carries a unit suffix"

    @pytest.mark.parametrize("column", [
        "cycle_time", "lead_time", "time_to_first_review", "review_latency",
        "time_to_merge",
    ])
    def test_durations_are_nullable_integers(self, catalog, column):
        """Null means an endpoint is missing -- an unreviewed pull request has no
        time to first review -- and is emphatically not zero."""
        for stream in catalog.values():
            spec = stream["schema"]["properties"].get(column)
            if spec:
                assert spec["type"] == ["null", "integer"], column

    def test_no_column_mixes_a_scalar_with_a_string(self, catalog):
        """`epic_number` was `int` or `""`, which is a union no loader can turn
        into a DDL type. Fixed in #93; this is what stops it coming back."""
        for name, stream in catalog.items():
            for column, spec in stream["schema"]["properties"].items():
                types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
                real = [t for t in types if t != "null"]
                assert len(real) == 1, f"{name}.{column} declares {types}"
