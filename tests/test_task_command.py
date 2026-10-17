"""`gh agile task`: create one under a story. AGILE-134, under #132.

The fourth creation command, and the one that makes the type real rather than
something a person hand-labels.

**`--story` is required and there is no `none`.** An epic may stand under no
initiative, and #91 gave a story the same, because the work is real either way.
A task is not: the whole definition is *how one person is organising their own
story*, so a parentless task is not a thin task -- it is an issue with the wrong
label on it.

**It does not touch the board.** A board listing tasks is the ceremony POLICY.md
§2 warns about: on a kanban board of fifty items, one story broken into five
turns one card into six. And there is no `--points`, `--priority` or `--status`,
so the flags that would let a task carry a number it must not carry simply do not
exist.

The parent is resolved before the issue is created, the ordering `epic
--initiative` uses: issue numbers are never reused, so a typo caught afterwards
leaves a permanent hole in the sequence.

Offline: every `gh` call and mutation is captured.
"""

from __future__ import annotations

import argparse
import json

import pytest

STORY = {"id": "I_story", "labels": [{"name": "type:story"}], "title": "a story"}


@pytest.fixture
def run(monkeypatch, tool, capsys):
    def go(parent=STORY, *, story="9", read_fails=False, **overrides):
        calls = {"gh": [], "graphql": [], "fields": [], "project": []}

        def fake_gh(argv, **kwargs):
            calls["gh"].append(argv)
            if argv[:2] == ["issue", "view"]:
                if argv[2] == "40":
                    # `create_issue` reads the node id of the issue it just made.
                    return json.dumps({"id": "I_task"})
                if read_fails:
                    raise SystemExit("gh issue view failed: not found")
                return json.dumps(parent)
            if argv[:2] == ["issue", "create"]:
                return "https://github.com/o/r/issues/40\n"
            return ""

        monkeypatch.setattr(tool, "gh", fake_gh)
        monkeypatch.setattr(tool, "graphql",
                            lambda q, **v: calls["graphql"].append(v) or {"data": {}})
        monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
        monkeypatch.setattr(tool, "parse_issue_ref", lambda ref, cfg, repo: ("o/r", int(ref)))
        monkeypatch.setattr(tool, "add_to_project",
                            lambda *a, **k: calls["project"].append(a) or "PVTI_x")
        monkeypatch.setattr(tool, "set_field",
                            lambda *a, **k: calls["fields"].append(a))
        go.calls = calls          # survives a SystemExit, so refusals can assert
        args = argparse.Namespace(title="a task", story=story, repo="o/r", key="AGILE",
                                  intent=None, acceptance=None, owner="o", project=1,
                                  _config={"project": {"issue_title_prefix": "off"}})
        for name, value in overrides.items():
            setattr(args, name, value)
        code = tool.cmd_task(args)
        return code, calls, capsys.readouterr()
    return go


class TestItCreatesAndAttaches:
    def test_the_issue_carries_the_task_label(self, tool, run):
        _code, calls, _out = run()
        create = next(c for c in calls["gh"] if c[:2] == ["issue", "create"])
        assert "type:task" in create

    def test_and_the_key_label(self, tool, run):
        _code, calls, _out = run()
        create = next(c for c in calls["gh"] if c[:2] == ["issue", "create"])
        assert "key:AGILE" in create

    def test_the_sub_issue_edge_is_made(self, tool, run):
        _code, calls, _out = run()
        assert calls["graphql"] == [{"parent": "I_story", "child": "I_task"}]

    def test_it_names_the_issue_before_the_edge(self, tool, run):
        """What follows can be refused on its own; an issue nobody named is an
        issue nobody can find."""
        _code, _calls, out = run()
        assert "task #40 under story #9" in out.out
        assert "https://github.com/o/r/issues/40" in out.out


class TestItTouchesNoNumber:
    def test_the_board_is_not_written_to(self, tool, run):
        _code, calls, _out = run()
        assert calls["project"] == []
        assert calls["fields"] == []

    def test_and_it_says_so(self, tool, run):
        """A task absent from the board looks like a failed write unless the
        command says it was never going to be there."""
        _code, _calls, out = run()
        assert "not added to the board" in out.out

    @pytest.mark.parametrize("flag", ["points", "priority", "status"])
    def test_the_number_carrying_flags_do_not_exist(self, tool, flag, monkeypatch):
        """Through the real parser: absence is the guarantee, not a check."""
        import sys as _sys
        monkeypatch.setattr(tool, "require_interpreter", lambda: None)
        monkeypatch.setattr(tool, "apply_defaults", lambda args: None)
        monkeypatch.setattr(tool, "cmd_task", lambda args: 0)
        monkeypatch.setattr(_sys, "argv",
                            ["gh-agile", "task", "create", "-t", "t", "--story", "9",
                             f"--{flag}", "1"])
        with pytest.raises(SystemExit) as exit_info:
            tool.main()
        assert exit_info.value.code != 0


class TestItRefusesBeforeItCosts:
    """Issue numbers are never reused, so a typo caught after creation leaves a
    permanent hole in the sequence."""

    def test_an_unreadable_story_creates_nothing(self, tool, run):
        with pytest.raises(SystemExit) as exit_info:
            run(read_fails=True)
        assert "Nothing was created" in str(exit_info.value)

    def test_a_parent_that_is_not_a_story_is_refused(self, tool, run):
        epic = {"id": "I_epic", "labels": [{"name": "type:epic"}], "title": "an epic"}
        with pytest.raises(SystemExit) as exit_info:
            run(epic)
        assert "a task belongs to a story" in str(exit_info.value)

    @pytest.mark.parametrize("bad", [
        {"id": "I_epic", "labels": [{"name": "type:epic"}], "title": "an epic"},
        {"id": "I_i", "labels": [{"name": "type:initiative"}], "title": "an initiative"},
    ])
    def test_the_refusal_happens_before_the_issue_exists(self, tool, run, bad):
        """The whole reason the parent is resolved first: a refusal after
        creation leaves a permanent hole in the issue numbering."""
        with pytest.raises(SystemExit):
            run(bad)
        created = [c for c in run.calls["gh"] if c[:2] == ["issue", "create"]]
        assert created == []

    def test_an_unlabelled_parent_is_allowed(self, tool, run):
        """A machine may not infer a type. An unlabelled issue is not refused as
        the wrong level; `validate` reports the missing label instead."""
        bare = {"id": "I_x", "labels": [], "title": "untyped"}
        code, _calls, _out = run(bare)
        assert code == 0


class TestTheStoryFlag:
    def test_it_is_required(self, tool, monkeypatch):
        import sys as _sys
        monkeypatch.setattr(tool, "require_interpreter", lambda: None)
        monkeypatch.setattr(tool, "apply_defaults", lambda args: None)
        monkeypatch.setattr(tool, "cmd_task", lambda args: 0)
        monkeypatch.setattr(_sys, "argv", ["gh-agile", "task", "create", "-t", "a task"])
        with pytest.raises(SystemExit) as exit_info:
            tool.main()
        assert exit_info.value.code != 0

    def test_there_is_no_none_escape(self, tool):
        """`--epic none` exists because a story standing alone is real work. A
        task standing alone is a mislabelled issue, so no such escape exists."""
        import pathlib as _p
        source = _p.Path(tool.__file__).read_text()
        body = source.split("def cmd_task(")[1].split("\ndef ")[0]
        assert '"none"' not in body
