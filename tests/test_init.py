"""`gh agile init`: install to a working board, in one path. AGILE-162, under #157.

The path existed and nobody was walked along it: write a profile, `setup`,
`board create` once per board, then two web-UI toggles that nothing mentions
until you read far enough into a 900-line README. The knowledge was all here --
this assembles it into the order the tool already knew.

**The hard part is honesty about the boundary.** Built-in workflows cannot be
created, enabled or configured through the API: the schema has
`deleteProjectV2Workflow` and nothing that writes one. A wizard that stopped
without saying so would leave a board that looks set up and silently loses
statuses. So `init` ends by naming what is left, with what each omission costs,
and reads back which are already on -- since `workflows(first: 20)` returns
`enabled` even though nothing can set it.

Offline: every write is captured.
"""

from __future__ import annotations

import argparse
import json

import pytest


def args_for(tool, tmp_path, **overrides):
    base = {"key": "AGILE", "title": "A board", "sprint_template": "2-week",
            "title_prefix": "off", "repo": "o/r", "owner": "o", "project": None,
            "config": str(tmp_path / "agile.json"), "_config": {}}
    base.update(overrides)
    return argparse.Namespace(**base)


@pytest.fixture
def run(monkeypatch, tool, tmp_path, capsys):
    """`cmd_init` with the project, setup and workflow reads stubbed."""
    def go(**overrides):
        # `Item closed` is ON here on purpose: #186 made it a `by-hand` verdict,
        # so a board with it enabled is one the table has to argue with.
        state = overrides.pop("_workflows", {"Item added to project": False,
                                             "Item closed": True,
                                             "Auto-add sub-issues to project": True})
        calls = {"project": [], "setup": [], "workflows": []}
        monkeypatch.setattr(tool, "cmd_project",
                            lambda a: calls["project"].append(a) or 0)
        monkeypatch.setattr(tool, "cmd_setup",
                            lambda a: calls["setup"].append(a) or 0)
        monkeypatch.setattr(tool, "project_workflows",
                            lambda login, number:
                            calls["workflows"].append(number) or state)
        # #141 widened the closing report into a verdict table, which states
        # the board's pull-request count as the evidence behind two of them.
        monkeypatch.setattr(tool, "pull_request_items", lambda *a: 0)
        monkeypatch.setattr(tool, "read_config",
                            lambda *a, **k: overrides.get("_config") or {})
        args = args_for(tool, tmp_path, **overrides)
        code = tool.cmd_init(args)
        return code, calls, capsys.readouterr().out, args
    return go


def written(tmp_path):
    path = tmp_path / "agile.json"
    return json.loads(path.read_text()) if path.exists() else None


class TestItRefusesBeforeItWrites:
    """An issue number is never reused and a project is awkward to delete, so a
    run that fails at step four must not have written steps one to three."""

    @pytest.mark.parametrize("missing,expected", [
        ({"title": None, "project": None}, "--title is required"),
        ({"key": None}, "--key is required"),
        ({"sprint_template": None}, "--sprint-template is required"),
        ({"key": "bad key"}, "--key 'bad key'"),
        ({"title_prefix": "nonsense"}, "issue_title_prefix"),
    ])
    def test_each_missing_decision_is_refused(self, tool, run, missing, expected):
        with pytest.raises(SystemExit) as exit_info:
            run(**missing)
        assert expected in str(exit_info.value)

    def test_the_refusal_names_the_flag(self, tool, run):
        """A refusal that does not say what to pass is half a message."""
        with pytest.raises(SystemExit) as exit_info:
            run(key=None)
        assert "gh agile init --key" in str(exit_info.value)

    def test_nothing_is_written_when_it_refuses(self, tool, run, tmp_path):
        with pytest.raises(SystemExit):
            run(sprint_template=None)
        assert written(tmp_path) is None

    def test_adopting_a_project_needs_no_title(self, tool, run):
        """`--project` answers the question `--title` is asked for. Refusing
        anyway suggested the flag that had just been given."""
        code, _calls, _out, _args = run(title=None, project=7)
        assert code == 0


class TestItWritesTheDecisionsDown:
    def test_the_key_lands_in_the_profile(self, tool, run, tmp_path):
        run(project=7)
        assert written(tmp_path)["keys"][0]["key"] == "AGILE"

    def test_and_the_cadence(self, tool, run, tmp_path):
        run(project=7)
        assert written(tmp_path)["sprint"]["cadence_days"] == 14

    def test_and_the_title_prefix(self, tool, run, tmp_path):
        run(project=7, title_prefix="key")
        assert written(tmp_path)["project"]["issue_title_prefix"] == "key"

    def test_and_the_starter_boards(self, tool, run, tmp_path):
        run(project=7)
        recorded = {b["name"] for b in written(tmp_path)["boards"]}
        assert recorded == {b["name"] for b in tool.STARTER_BOARDS}

    def test_a_roadmap_is_among_them(self, tool):
        """The one board type built for epics over time, and the one this
        project went a year without."""
        assert any(b["type"] == "roadmap" for b in tool.STARTER_BOARDS)


class TestTheSequence:
    def test_setup_runs_after_the_profile_is_written(self, tool, run, tmp_path):
        """`setup` reads the profile for its boards, so a profile written
        afterwards would create none of them."""
        _code, calls, _out, _args = run(project=7)
        assert calls["setup"], "setup was not run"
        assert written(tmp_path)["boards"]

    def test_setup_is_given_the_project_it_just_recorded(self, tool, run):
        _code, calls, _out, _args = run(project=7)
        assert calls["setup"][0].project == 7

    def test_a_project_is_created_when_none_is_named(self, tool, run):
        _code, calls, _out, _args = run(project=None)
        assert calls["project"], "expected `project create`"
        assert calls["project"][0].project_command == "create"

    def test_and_not_created_when_one_is_adopted(self, tool, run):
        _code, calls, _out, _args = run(project=7)
        assert calls["project"] == []

    def test_nor_when_the_profile_already_names_one(self, tool, run):
        _code, calls, _out, out_text = run(
            _config={"project": {"number": 4, "owner": "o"},
                     "sprint": {"template": "2-week", "cadence_days": 14},
                     "keys": [{"key": "AGILE", "repo": "o/r"}]})
        assert calls["project"] == []


class TestItIsIdempotent:
    def test_a_second_run_reports_rather_than_duplicating(self, tool, run, tmp_path):
        existing = {"project": {"number": 4, "owner": "o"},
                    "sprint": {"template": "2-week", "cadence_days": 14},
                    "keys": [{"key": "AGILE", "name": "A", "repo": "o/r"}],
                    "boards": [dict(b) for b in tool.STARTER_BOARDS]}
        _code, calls, out, _args = run(_config=existing)
        assert "already in the profile" in out
        assert calls["project"] == []

    def test_it_does_not_duplicate_a_key_it_already_has(self, tool, run, tmp_path):
        existing = {"project": {"number": 4, "owner": "o"},
                    "sprint": {"template": "2-week", "cadence_days": 14},
                    "keys": [{"key": "AGILE", "name": "A", "repo": "o/r"}]}
        run(_config=existing)
        assert len(written(tmp_path)["keys"]) == 1

    def test_nor_a_board(self, tool, run, tmp_path):
        existing = {"project": {"number": 4, "owner": "o"},
                    "sprint": {"template": "2-week", "cadence_days": 14},
                    "keys": [{"key": "AGILE", "repo": "o/r"}],
                    "boards": [dict(b) for b in tool.STARTER_BOARDS]}
        run(_config=existing)
        assert len(written(tmp_path)["boards"]) == len(tool.STARTER_BOARDS)


class TestItEndsByNamingWhatItCannotDo:
    def test_the_manual_steps_are_printed(self, tool, run):
        _code, _calls, out, _args = run(project=7)
        assert "cannot write them" in out

    def test_each_unfinished_step_says_what_it_costs(self, tool, run):
        """A checklist without consequences is a checklist people skip."""
        _code, _calls, out, _args = run(project=7)
        assert "an item arriving by any other route has no Status" in out

    def test_it_reads_back_which_are_already_on(self, tool, run):
        """`workflows(first: 20)` returns `enabled` even though nothing can set
        it, so nobody should be told to go and check."""
        _code, _calls, out, _args = run(project=7)
        assert "[on]  by hand   Item closed" in out
        assert "[off] enable    Item added to project" in out

    def test_a_satisfied_step_does_not_repeat_its_cost(self, tool, run):
        """A `never`, a `by-hand` or a pull-request one still explains itself
        even when correct -- see #141 and #186 -- but a satisfied `enable` is
        simply working."""
        _code, _calls, out, _args = run(project=7)
        after = out.split("[on]  enable    Auto-add sub-issues to project")[1].split("[")[0]
        assert "every story created" not in after

    def test_a_by_hand_that_is_on_still_explains_itself(self, tool, run):
        """The one somebody is most likely to have turned on, because it was
        recommended until #186."""
        _code, _calls, out, _args = run(project=7)
        after = out.split("[on]  by hand   Item closed")[1].split("[")[0]
        assert "writes Status and nothing else" in after

    def test_an_unreadable_workflow_list_is_not_fatal(self, tool, run):
        """A checklist is more useful than an error at the end of a successful
        setup."""
        code, _calls, out, _args = run(project=7, _workflows={})
        assert code == 0
        assert "could not read which are enabled" in out

    def test_it_points_at_validate(self, tool, run):
        _code, _calls, out, _args = run(project=7)
        assert "gh agile validate" in out


class TestTheWorkflowRead:
    def test_it_returns_name_to_enabled(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "graphql", lambda q, **v: {"data": {"user": {
            "projectV2": {"workflows": {"nodes": [
                {"name": "Item closed", "enabled": True}]}}}}})
        assert tool.project_workflows("o", 4) == {"Item closed": True}

    def test_an_organisation_project_is_reached_too(self, tool, monkeypatch):
        def fake(query, **variables):
            if "user(login:" in query:
                raise SystemExit("Could not resolve to a User")
            return {"data": {"organization": {"projectV2": {"workflows": {
                "nodes": [{"name": "Item closed", "enabled": False}]}}}}}
        monkeypatch.setattr(tool, "graphql", fake)
        assert tool.project_workflows("acme", 4) == {"Item closed": False}

    def test_an_unreadable_project_is_empty_not_an_error(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "graphql",
                            lambda q, **v: (_ for _ in ()).throw(SystemExit("no")))
        assert tool.project_workflows("o", 4) == {}

    def test_every_workflow_has_a_verdict_and_a_reason(self, tool):
        """#141 widened three entries into a verdict for all six."""
        assert len(tool.WORKFLOW_ADVICE) == 6
        assert all(why and len(why) > 20
                   for _verdict, why in tool.WORKFLOW_ADVICE.values())
