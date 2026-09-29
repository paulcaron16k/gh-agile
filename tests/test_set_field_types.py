"""Which `gh project item-edit` flag `set_field` chooses, per field type.

**Asserted on the argv, because a stub of `set_field` is what let #182 ship.**
Roughly thirty tests in this suite monkeypatch `set_field` away -- they are
about what the commands decide to write, and rightly do not care how it is
written -- so nothing had ever looked at the command it builds. `epic --start`
was released in #175 sending every date as `--text`, which `gh` accepts and the
API rejects, and no test failed.

The field records here are the shape `project_node` returns, not the shape
`project_fields` produces, so the mapping from `dataType` to the dict the
dispatch reads is under test too. The one thing an offline test cannot check is
that GitHub still answers `dataType` at all; `PROJECT_FIELDS_SELECTION` asking
for it is checked below, and the rest is what the live run in the pull request
is for.
"""

from __future__ import annotations

import pytest

#: One field per `dataType` this tool writes, carrying **both** answers the API
#: gives -- `__typename` as well, though nothing reads it any more.
#:
#: It is here so these tests fail against the defect for the defect's own
#: reason. With `dataType` alone they fail against the old code on a `KeyError`,
#: which proves only that the fix is installed; with both, the old dispatch runs
#: exactly as it shipped and sends the date as `--text`. Note what three of
#: these five share, and that TEXT, NUMBER and DATE are indistinguishable by it.
NODES = [
    {"__typename": "ProjectV2Field", "id": "F_text", "name": "FR", "dataType": "TEXT"},
    {"__typename": "ProjectV2Field", "id": "F_number", "name": "Story Points",
     "dataType": "NUMBER"},
    {"__typename": "ProjectV2Field", "id": "F_date", "name": "Target date",
     "dataType": "DATE"},
    {"__typename": "ProjectV2SingleSelectField", "id": "F_select", "name": "Status",
     "dataType": "SINGLE_SELECT", "options": [{"id": "O_todo", "name": "Todo"}]},
    {"__typename": "ProjectV2IterationField", "id": "F_iteration", "name": "Sprint",
     "dataType": "ITERATION"},
]


@pytest.fixture
def written(monkeypatch, tool):
    """Call `set_field` and hand back the argv it passed to `gh`."""
    monkeypatch.setattr(tool, "_FIELDS", {})
    monkeypatch.setattr(tool, "project_node", lambda *a, **k: {"fields": {"nodes": NODES}})
    monkeypatch.setattr(tool, "project_id", lambda *a, **k: "PVT_1")
    monkeypatch.setattr(tool, "resolve_iteration", lambda *a, **k: "ITER_9")
    calls = []
    monkeypatch.setattr(tool, "gh", lambda cmd, **k: calls.append(cmd))

    def call(field_name, value):
        tool.set_field("acme", 4, "ITEM_1", field_name, value)
        assert len(calls) == 1
        return calls[0]

    return call


def value_of(argv, flag):
    """The argument after `flag`, or None if the flag is not there."""
    return argv[argv.index(flag) + 1] if flag in argv else None


class TestTheFlagFollowsTheFieldNotTheValue:
    def test_a_date_field_is_written_as_a_date(self, written):
        assert value_of(written("Target date", "2026-09-01"), "--date") == "2026-09-01"

    def test_a_date_field_is_not_written_as_text(self, written):
        # The shipped defect, exactly: `--text 2026-09-01`.
        assert "--text" not in written("Target date", "2026-09-01")

    def test_a_text_field_is_written_as_text(self, written):
        assert value_of(written("FR", "FR-7.1"), "--text") == "FR-7.1"

    def test_a_number_field_is_written_as_a_number(self, written):
        assert value_of(written("Story Points", 5), "--number") == "5"

    def test_a_number_field_given_a_string_is_still_a_number(self, written):
        # `set --field "Story Points" --value 3` arrives as a string; the old
        # `isinstance(value, (int, float))` guess sent it as text.
        assert value_of(written("Story Points", "3"), "--number") == "3"

    def test_a_text_field_given_a_number_is_still_text(self, written):
        # And the guess was wrong in the other direction too.
        assert value_of(written("FR", 3), "--text") == "3"

    def test_a_single_select_is_written_as_an_option_id(self, written):
        argv = written("Status", "Todo")
        assert value_of(argv, "--single-select-option-id") == "O_todo"

    def test_an_iteration_is_written_as_an_iteration_id(self, written):
        assert value_of(written("Sprint", "@current"), "--iteration-id") == "ITER_9"

    def test_the_field_id_is_the_one_named(self, written):
        assert value_of(written("Target date", "2026-09-01"), "--field-id") == "F_date"


class TestRefusals:
    def test_an_unparseable_date_is_refused(self, written, tool):
        # `set` reaches any field on the board without meeting `--start`'s
        # parser, and GitHub would take the string and render nothing.
        with pytest.raises(SystemExit) as caught:
            written("Target date", "soon")
        assert "is not a date" in str(caught.value)

    def test_the_refusal_names_the_field(self, written):
        with pytest.raises(SystemExit) as caught:
            written("Target date", "soon")
        assert "Target date" in str(caught.value)

    def test_an_unknown_option_is_still_refused(self, written):
        with pytest.raises(SystemExit) as caught:
            written("Status", "Nowhere")
        assert "is not an option of" in str(caught.value)

    def test_an_absent_field_is_still_refused(self, written):
        with pytest.raises(SystemExit) as caught:
            written("Nonexistent", "x")
        assert "gh agile setup" in str(caught.value)


class TestTheRecordTheDispatchReads:
    def test_the_query_asks_for_dataType(self, tool):
        # Without this the dispatch has nothing to read, and the only symptom
        # is a write that GitHub rejects.
        assert "dataType" in tool.PROJECT_FIELDS_SELECTION

    def test_every_field_carries_a_data_type(self, monkeypatch, tool):
        monkeypatch.setattr(tool, "project_node", lambda *a, **k: {"fields": {"nodes": NODES}})
        got = tool.project_fields("acme", 4)
        assert [f["data_type"] for f in got] == [n["dataType"] for n in NODES]

    def test_the_typename_is_gone(self, monkeypatch, tool):
        # One answer to "what kind of field is this", not two that disagree.
        monkeypatch.setattr(tool, "project_node", lambda *a, **k: {"fields": {"nodes": NODES}})
        assert all("type" not in f for f in tool.project_fields("acme", 4))
