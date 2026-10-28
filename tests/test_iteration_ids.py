"""Every iteration write sends each sprint's id, so no assignment is lost. AGILE-290.

`ProjectV2Iteration` carried `startDate`, `duration` and `title` and no id, so any
write to the iteration configuration re-minted every iteration and cleared every
item's Sprint board-wide. It gained `id`: "Include this to preserve the
iteration's identity during replacement updates". Measured on the sandbox
2026-10-27: an append, and a rename of the current and a completed sprint, each
kept every id and all 13 assignments with no restore.

The save-and-restore stays as the fallback: if an id is replaced anyway, the
assignments are put back and the field healed from the labels.
"""

from __future__ import annotations

import pytest

OLD = [
    {"id": "a1", "title": "S1", "startDate": "2026-10-12", "duration": 14},
    {"id": "b2", "title": "S2", "startDate": "2026-10-26", "duration": 14},
]
NEW = {"title": "S3", "startDate": "2026-11-09", "duration": 14}


def test_an_existing_iteration_carries_its_id(tool):
    assert tool.iteration_entry(OLD[0]) == (
        '{id: "a1", startDate: "2026-10-12", duration: 14, title: "S1"}')


def test_a_new_iteration_has_none(tool):
    assert tool.iteration_entry(NEW) == '{startDate: "2026-11-09", duration: 14, title: "S3"}'


@pytest.fixture
def write(monkeypatch, tool, capsys):
    def go(after_ids):
        calls = go.calls = {"queries": [], "restored": [], "healed": 0}
        monkeypatch.setattr(tool, "sprint_assignments", lambda *a: {"PVTI_1": "S1"})
        monkeypatch.setattr(tool, "graphql",
                            lambda query, **v: calls["queries"].append(query) or {})
        monkeypatch.setattr(tool, "sprint_field", lambda *a: {"configuration": {
            "iterations": [{"id": i} for i in after_ids], "completedIterations": []}})
        monkeypatch.setattr(tool, "restore_assignments",
                            lambda login, project, saved: calls["restored"].append(saved)
                            or len(saved))
        monkeypatch.setattr(tool, "heal_sprint_fields",
                            lambda *a: calls.__setitem__("healed", calls["healed"] + 1))
        restored = tool.write_iterations("o", 1, "F", "2026-10-12", 14, [*OLD, NEW],
                                         doing="creating a sprint")
        calls["err"] = capsys.readouterr().err
        return restored, calls
    return go


class TestTheWrite:
    def test_it_sends_every_id(self, write):
        _restored, calls = write(["a1", "b2", "c3"])
        query = calls["queries"][0]
        assert 'id: "a1"' in query and 'id: "b2"' in query
        assert 'title: "S3"' in query

    def test_ids_kept_means_no_restore(self, write):
        restored, calls = write(["a1", "b2", "c3"])
        assert restored == 0 and calls["restored"] == [] and calls["healed"] == 0
        assert calls["err"] == ""

    def test_an_id_replaced_anyway_restores_and_heals(self, write):
        """A GitHub regression costs a restore and a warning, not data."""
        restored, calls = write(["zz", "b2", "c3"])
        assert restored == 1 and calls["restored"] == [{"PVTI_1": "S1"}]
        assert calls["healed"] == 1
        assert "replaced 1 sprint id(s)" in calls["err"]


def test_a_rename_is_an_ordinary_write(tool):
    """A sprint's title travels with its id; renaming one keeps its items."""
    renamed = {**OLD[1], "title": "S2 renamed"}
    assert tool.iteration_entry(renamed).startswith('{id: "b2"')


@pytest.fixture
def rename(monkeypatch, tool, capsys):
    def go(*argv):
        go.written = []
        field = {"id": "F", "configuration": {"duration": 14, "iterations": [OLD[1]],
                                              "completedIterations": [OLD[0]]}}
        monkeypatch.setattr(tool, "sprint_field", lambda *a: field)
        monkeypatch.setattr(tool, "iterations", lambda *a: ([OLD[1]], [OLD[0]]))
        monkeypatch.setattr(tool, "write_iterations",
                            lambda login, project, fid, start, duration, its, *, doing:
                            go.written.append((start, duration, its)) or 0)
        args = tool.build_parser().parse_args(["sprint", "edit", *argv])
        args.owner, args.project, args._config = "o", 1, {}
        code = tool.cmd_sprint(args)
        return code, capsys.readouterr().out
    return go


class TestSprintEdit:
    def test_renames_one_and_resends_all_with_ids(self, rename):
        _code, out = rename("2026-10-12", "--title", "0001 W42-2026")
        (start, duration, sent), = rename.written
        assert start == "2026-10-12" and duration == 14
        assert sent == [{**OLD[0], "title": "0001 W42-2026"}, OLD[1]]
        assert "S1 (2026-10-12) -> 0001 W42-2026" in out

    def test_with_no_sprint_it_is_the_current_one(self, rename):
        rename("--title", "Now")
        assert rename.written[0][2][1]["title"] == "Now"

    def test_a_title_naming_another_sprint_is_refused(self, rename):
        with pytest.raises(SystemExit) as refused:
            rename("S1", "--title", "s2")
        assert "already names" in str(refused.value) and rename.written == []

    def test_the_same_title_changes_nothing(self, rename):
        _code, out = rename("S1", "--title", "S1")
        assert rename.written == [] and "already called" in out

    def test_dry_run(self, rename):
        _code, out = rename("S1", "--title", "New", "--dry-run")
        assert rename.written == [] and "would rename S1 (2026-10-12) to New" in out
