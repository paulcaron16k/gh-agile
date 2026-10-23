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
            "config": str(tmp_path / "agile.json"), "_config": {},
            # The hook is stubbed where it is tested; a real one would land in
            # this checkout's own `.git/hooks`.
            "spec": None, "no_hooks": True}
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
        monkeypatch.setattr(tool, "create_project",
                            lambda a, config, target: calls["project"].append(a) or 0)
        monkeypatch.setattr(tool, "converge_project",
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
        assert calls["project"], "expected the project to be created"
        assert calls["project"][0].title == "A board"

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
        """#141 widened three entries into a verdict for all six; #237 added
        the seventh a user-owned project now has."""
        assert len(tool.WORKFLOW_ADVICE) == 7
        assert all(why and len(why) > 20
                   for _verdict, why in tool.WORKFLOW_ADVICE.values())


class TestAFreshCloneIsNotRefused:
    """#210: `init --sprint-template 2-week` on a clone with no profile was
    refused, and told the person to write the profile by hand.

    Step 1 created the project through `cmd_project` with `sprint_template=None`,
    and `project create` refuses without a template unless the profile already
    has one. `init` recorded its own only in step 2. Every test above stubs
    the creation, which is how it shipped -- so this one runs the real
    `create_project` (which replaced `project create` in #203) and stubs only `gh`.
    """

    @pytest.fixture
    def fresh(self, monkeypatch, tool, tmp_path, capsys):
        calls = {"gh": [], "setup": []}

        def fake_gh(argv, **kwargs):
            calls["gh"].append(argv)
            if argv[:2] == ["project", "create"]:
                return json.dumps({"number": 12, "url": "https://github.com/users/o/projects/12"})
            raise AssertionError(f"unexpected gh call: {argv}")

        monkeypatch.setattr(tool, "gh", fake_gh)
        monkeypatch.setattr(tool, "converge_project",
                            lambda a: calls["setup"].append(a) or 0)
        monkeypatch.setattr(tool, "project_workflows", lambda *a: {})
        monkeypatch.setattr(tool, "pull_request_items", lambda *a: 0)

        def go(**overrides):
            args = args_for(tool, tmp_path, **overrides)
            code = tool.cmd_init(args)
            return code, calls, capsys.readouterr().out
        return go

    def test_it_creates_the_project(self, tool, fresh, tmp_path):
        code, calls, _out = fresh()
        assert code == 0
        assert [c[:2] for c in calls["gh"]] == [["project", "create"]]
        assert written(tmp_path)["project"]["number"] == 12

    def test_and_records_the_cadence_it_was_given(self, tool, fresh, tmp_path):
        fresh(sprint_template="1-week")
        assert written(tmp_path)["sprint"]["template"] == "1-week"

    def test_and_setup_runs(self, tool, fresh):
        _code, calls, _out = fresh()
        assert len(calls["setup"]) == 1

    def test_without_a_cadence_it_still_refuses_before_creating(self, tool, fresh, tmp_path):
        with pytest.raises(SystemExit) as exit_info:
            fresh(sprint_template=None)
        assert "--sprint-template is required" in str(exit_info.value)
        assert written(tmp_path) is None


class TestTheCrossTeamBoard:
    """#211: Engineering: all work is the view across teams, so a one-key
    project does not get it. Reported by the first adopter outside this repo."""

    def names(self, tmp_path):
        return {b["name"] for b in written(tmp_path)["boards"]}

    def test_one_key_gets_three_boards(self, tool, run, tmp_path):
        run(project=7)
        assert self.names(tmp_path) == {"Sprint board", "Backlog", "Roadmap"}

    def test_several_keys_get_it(self, tool, run, tmp_path):
        run(project=7, _config={"keys": [{"key": "ZMBNI", "repo": "o/zamboni"}]})
        assert tool.CROSS_TEAM_BOARD["name"] in self.names(tmp_path)
        assert len(self.names(tmp_path)) == 4

    def test_one_already_there_is_kept(self, tool, run, tmp_path):
        """`init` adds boards and never removes one."""
        run(project=7, _config={"boards": [dict(tool.CROSS_TEAM_BOARD)]})
        assert tool.CROSS_TEAM_BOARD["name"] in self.names(tmp_path)

    def test_the_count_printed_is_the_count_recorded(self, tool, run):
        _code, _calls, out, _args = run(project=7)
        assert "3 board(s) recorded" in out


class TestASecondKeySaysSo:
    """Recording a second key is the moment the cross-team board makes sense.
    Said, with the command, and not done: nobody asked for a board."""

    @pytest.fixture
    def record(self, tool, tmp_path, capsys):
        def go(config):
            args = argparse.Namespace(key="ZMBNI", repo="o/zamboni", name=None,
                                      project=None, owner="o", _config=config,
                                      config=str(tmp_path / "agile.json"))
            tool.cmd_key_add(args)
            return capsys.readouterr().out
        return go

    def test_the_second_key_names_the_board(self, tool, record):
        out = record({"keys": [{"key": "AGILE", "repo": "o/agile"}]})
        assert 'board create "Engineering: all work" --type kanban --save' in out

    def test_the_first_key_does_not(self, tool, record):
        assert "board create" not in record({})

    def test_nor_when_a_kanban_board_is_already_there(self, tool, record):
        out = record({"keys": [{"key": "AGILE", "repo": "o/agile"}],
                      "boards": [{"name": "Flow", "type": "kanban"}]})
        assert "board create" not in out


class TestTheHook:
    """`init` installs the post-merge hook, which `gh agile hooks` used to (#203).

    `init` is what a person runs in a fresh clone, it is idempotent, and the
    hook is per-clone setup like everything else it converges.
    """

    def test_it_is_installed_by_default(self, tool, run, monkeypatch):
        monkeypatch.setattr(tool, "install_hook", lambda: "installed .git/hooks/post-merge")
        _code, _calls, out, _args = run(project=7, no_hooks=False)
        assert "post-merge hook: installed" in out

    def test_no_hooks_leaves_it_alone(self, tool, run, monkeypatch):
        monkeypatch.setattr(tool, "install_hook",
                            lambda: pytest.fail("installed despite --no-hooks"))
        _code, _calls, out, _args = run(project=7, no_hooks=True)
        assert "not installed (--no-hooks)" in out

    def test_hooks_is_no_longer_a_command(self, tool):
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args(["hooks"])

    @pytest.fixture
    def git_dir(self, tool, tmp_path, monkeypatch):
        monkeypatch.setattr(tool, "hooks_dir", lambda: (tmp_path / "hooks", False))
        return tmp_path / "hooks" / "post-merge"

    def test_a_first_run_installs(self, tool, git_dir):
        assert tool.install_hook().startswith("installed")
        assert git_dir.read_text() == tool.POST_MERGE_HOOK

    def test_a_second_run_reports_it_present(self, tool, git_dir):
        tool.install_hook()
        assert tool.install_hook().startswith("present")

    def test_a_stale_one_is_replaced_and_says_so(self, tool, git_dir):
        git_dir.parent.mkdir(parents=True)
        git_dir.write_text(f"#!/bin/sh\n{tool.HOOK_MARKER} -- an older one\n")
        assert tool.install_hook().startswith("replaced a stale")
        assert git_dir.read_text() == tool.POST_MERGE_HOOK

    def test_somebody_elses_is_named_and_kept(self, tool, git_dir):
        git_dir.parent.mkdir(parents=True)
        git_dir.write_text("#!/bin/sh\necho mine\n")
        said = tool.install_hook()
        assert "not mine to replace" in said and "unfinished --quiet" in said
        assert git_dir.read_text() == "#!/bin/sh\necho mine\n"


class TestASecondRunKeepsTheTitlePrefix:
    """A bare re-run reset `key+type` to `off` on the sandbox: the flag
    defaulted to `off` and was written every time. Now that running `init`
    again *is* the converge, that was a silent rename of every new issue."""

    PROFILE = {"project": {"number": 4, "owner": "o", "issue_title_prefix": "key+type"},
               "keys": [{"key": "AGILE", "repo": "o/r"}], "sprint": {"template": "2-week"}}

    def test_absent_leaves_the_profiles(self, tool, run, tmp_path):
        run(project=None, title_prefix=None, _config=json.loads(json.dumps(self.PROFILE)))
        assert written(tmp_path)["project"]["issue_title_prefix"] == "key+type"

    def test_given_replaces_it(self, tool, run, tmp_path):
        run(project=None, title_prefix="key", _config=json.loads(json.dumps(self.PROFILE)))
        assert written(tmp_path)["project"]["issue_title_prefix"] == "key"

    def test_a_new_profile_gets_off(self, tool, run, tmp_path):
        run(project=7, title_prefix=None)
        assert written(tmp_path)["project"]["issue_title_prefix"] == "off"

    def test_the_flag_has_no_default(self, tool):
        assert tool.build_parser().parse_args(["init"]).title_prefix is None


class TestTheOwnerIsRecorded:
    """`project owner` went in #203; `init` records the owner a profile lacks."""

    def test_an_older_profile_gets_its_owner(self, tool, run, tmp_path):
        run(project=None, _config={"project": {"number": 4}, "keys": [
            {"key": "AGILE", "repo": "o/r"}], "sprint": {"template": "2-week"}})
        assert written(tmp_path)["project"]["owner"] == "o"

    def test_a_recorded_owner_is_left_alone(self, tool, run, tmp_path):
        run(project=None, _config={"project": {"number": 4, "owner": "team"}, "keys": [
            {"key": "AGILE", "repo": "o/r"}], "sprint": {"template": "2-week"}})
        assert written(tmp_path)["project"]["owner"] == "team"

    @pytest.mark.parametrize("old", [["setup"], ["project", "create", "-t", "x"],
                                     ["project", "owner"]])
    def test_the_other_doors_are_gone(self, tool, old):
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args(old)

    def test_spec_moved_onto_init(self, tool):
        assert tool.build_parser().parse_args(["init", "--spec", "f.json"]).spec == "f.json"
