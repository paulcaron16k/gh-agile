"""A supporting repository's `config_from` pointer survives every profile write. #324.

`read_config` follows `{"config_from": "owner/main"}` and hands every command
the main repository's profile. Every command that writes the profile then
saved that resolved profile to the file it found -- the pointer -- so `init`,
`key add`, `key delete`, `board create --save` and `project edit`, run in a
supporting repository, replaced the pointer with a copy. A copy drifts from the
profile it was copied from, which is what the pointer exists to prevent.

Now each of them refuses there, before it does anything, naming the main
repository; `save_profile` refuses too, as the backstop. A bare `init` still
runs, because it is what a fresh clone needs: it installs the hook and
converges the project, and leaves the pointer byte-identical.
"""

from __future__ import annotations

import argparse
import json
import pathlib

import pytest

MAIN = "acme/widgets"
POINTER = json.dumps({"config_from": MAIN}) + "\n"


@pytest.fixture
def pointer(tmp_path):
    path = tmp_path / "agile.json"
    path.write_text(POINTER)
    return path


def main_profile(tool, tmp_path, monkeypatch) -> dict:
    """A complete main profile: what `init` writes in the main repository."""
    target = tmp_path / "main.json"
    monkeypatch.setattr(tool, "create_project", lambda a, config, target: 0)
    monkeypatch.setattr(tool, "converge_project", lambda a: 0)
    monkeypatch.setattr(tool, "report_manual_steps", lambda *a: None)
    tool.cmd_init(argparse.Namespace(
        key="WIDG", title="Widgets", sprint_template="2-week", title_prefix=None,
        repo=MAIN, owner="acme", project=7, config=str(target),
        _config={"project": {"number": 7, "owner": "acme"}},
        spec=None, no_hooks=True))
    return json.loads(target.read_text())


def init_args(path, config, **flags):
    base = {"key": None, "title": None, "sprint_template": None, "title_prefix": None,
            "repo": "acme/widget-parts", "owner": "acme", "project": 7,
            "config": str(path), "_config": config, "spec": None, "no_hooks": False}
    base.update(flags)
    return argparse.Namespace(**base)


class TestBareInitInASupportingClone:
    @pytest.fixture
    def run(self, tool, tmp_path, monkeypatch, pointer, capsys):
        resolved = main_profile(tool, tmp_path, monkeypatch)
        capsys.readouterr()
        calls = {"setup": [], "hook": []}
        monkeypatch.setattr(tool, "converge_project", calls["setup"].append)
        monkeypatch.setattr(tool, "install_hook", lambda: calls["hook"].append(1) or "installed")

        def go(config=resolved):
            code = tool.cmd_init(init_args(pointer, config))
            return code, calls, capsys.readouterr().out
        return go

    def test_the_pointer_is_left_byte_identical(self, run, pointer):
        code, _, out = run()
        assert code == 0
        assert pointer.read_text() == POINTER
        assert f"left pointing at {MAIN}" in out

    def test_it_still_installs_the_hook_and_converges_the_project(self, run):
        _, calls, _ = run()
        assert calls["hook"] and len(calls["setup"]) == 1
        assert calls["setup"][0].project == 7

    def test_defaults_missing_from_the_main_profile_are_named_not_written(
            self, run, pointer):
        code, _, out = run(config={"project": {"number": 7, "owner": "acme"},
                                   "keys": [{"key": "WIDG", "repo": MAIN}],
                                   "sprint": {"template": "2-week"}})
        assert code == 0
        assert pointer.read_text() == POINTER
        assert "run `gh agile init` there" in out


class TestRefusedInASupportingRepository:
    """Each refuses before it acts, names the main repository, and leaves the
    pointer as it was."""

    @pytest.fixture(autouse=True)
    def nothing_reaches_github(self, tool, monkeypatch):
        def refuse(*a, **k):
            raise AssertionError("acted before refusing")
        for name in ("create_project", "converge_project", "install_hook",
                     "make_board", "key_issue_count"):
            monkeypatch.setattr(tool, name, refuse)

    @pytest.mark.parametrize("flags", [
        {"key": "PARTS"}, {"title": "Parts"}, {"sprint_template": "1-week"},
        {"title_prefix": "key"},
    ])
    def test_init_with_a_flag_that_changes_the_profile(self, tool, pointer, flags):
        with pytest.raises(SystemExit) as stop:
            tool.cmd_init(init_args(pointer, {"project": {"number": 7}}, **flags))
        assert MAIN in str(stop.value) and next(iter(flags)).replace("_", "-") in str(stop.value)
        assert pointer.read_text() == POINTER

    def test_init_when_the_main_profile_names_no_project(self, tool, pointer):
        with pytest.raises(SystemExit) as stop:
            tool.cmd_init(init_args(pointer, {}, project=None))
        assert "names no project" in str(stop.value)
        assert pointer.read_text() == POINTER

    def test_key_add(self, tool, pointer):
        args = argparse.Namespace(key="PARTS", name=None, repo="acme/widget-parts",
                                  config=str(pointer), _config={"keys": []})
        with pytest.raises(SystemExit) as stop:
            tool.cmd_key_add(args)
        assert MAIN in str(stop.value)
        assert pointer.read_text() == POINTER

    def test_key_delete(self, tool, pointer):
        args = argparse.Namespace(key="WIDG", config=str(pointer),
                                  _config={"keys": [{"key": "WIDG", "repo": MAIN}]})
        with pytest.raises(SystemExit) as stop:
            tool.cmd_key_delete(args)
        assert MAIN in str(stop.value)
        assert pointer.read_text() == POINTER

    def test_project_edit(self, tool, pointer):
        args = argparse.Namespace(sprint_template="1-week", title_prefix=None,
                                  backfill=False, dry_run=False, config=str(pointer),
                                  _config={})
        with pytest.raises(SystemExit) as stop:
            tool.cmd_project_edit(args)
        assert MAIN in str(stop.value)
        assert pointer.read_text() == POINTER

    def test_board_create_save_refuses_before_the_board_is_made(self, tool, pointer):
        args = argparse.Namespace(board_command="create", name="Parts", type="kanban",
                                  filter=None, save=True, owner="acme", project=7,
                                  config=str(pointer), _config={})
        with pytest.raises(SystemExit) as stop:
            tool.cmd_board(args)
        assert MAIN in str(stop.value)
        assert pointer.read_text() == POINTER


class TestTheBackstop:
    def test_save_profile_refuses_a_pointer(self, tool, pointer):
        with pytest.raises(SystemExit):
            tool.save_profile({"keys": []}, pointer)
        assert pointer.read_text() == POINTER

    def test_save_profile_writes_an_ordinary_profile(self, tool, tmp_path):
        path = tmp_path / "agile.json"
        path.write_text(json.dumps({"keys": []}))
        tool.save_profile({"keys": [{"key": "WIDG"}]}, path)
        assert json.loads(path.read_text()) == {"keys": [{"key": "WIDG"}]}

    def test_no_profile_is_written_any_other_way(self, tool):
        """`save_profile` is the one writer, so the backstop covers them all."""
        text = pathlib.Path(tool.__file__).read_text()
        assert text.count("json.dumps(config,") == 1
