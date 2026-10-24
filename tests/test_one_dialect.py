"""board, project, key, sprint, export and init speak one dialect. AGILE-203.

Everything that is not a work item, and the flag names that meant two things:
`board show` where `gh` says `view`, `key` reading or writing on whether `--key`
was given, three ways to stand a project up, `--format display`, `export
--state` for a file while `sync --state` meant open/closed/all, and `--grain
both` among four grains.

Offline: the parser is walked, and every read and write is stubbed.
"""

from __future__ import annotations

import argparse
import json

import pytest


def parse(tool, *argv):
    return tool.build_parser().parse_args(list(argv))


def every_parser(parser, path=()):
    yield path, parser
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, child in action.choices.items():
                yield from every_parser(child, (*path, name))


GROUPS = {"initiative", "epic", "story", "bug", "task", "issue", "board", "sprint", "project",
          "key"}


class TestTheTopLevel:
    def shown(self, tool):
        top = next(a for a in tool.build_parser()._actions
                   if isinstance(a, argparse._SubParsersAction))
        return {a.dest for a in top._choices_actions}

    def test_four_commands_besides_the_groups(self, tool):
        assert self.shown(tool) - GROUPS == {"init", "sync", "validate", "export"}

    @pytest.mark.parametrize("hidden", ["self-test", "unfinished"])
    def test_hidden_commands_still_run(self, tool, hidden):
        argv = [hidden] + (["-R", "o/r"] if hidden == "self-test" else [])
        assert parse(tool, *argv).command == hidden
        assert hidden not in self.shown(tool)

    def test_help_does_not_spell_out_the_hidden_ones(self, tool):
        text = tool.build_parser().format_help()
        assert "self-test" not in text and "unfinished" not in text

    @pytest.mark.parametrize("gone", [["setup"], ["hooks"], ["project", "create", "-t", "x"],
                                      ["project", "owner"], ["project", "sprint-template"],
                                      ["project", "title-prefix", "--mode", "key"],
                                      ["board", "show", "x"], ["key", "--key", "X"]])
    def test_each_retired_spelling_fails_at_parsing(self, tool, gone):
        with pytest.raises(SystemExit):
            parse(tool, *gone)


class TestOneMeaningPerFlag:
    def test_no_display_value_anywhere(self, tool):
        for path, parser in every_parser(tool.build_parser()):
            for action in parser._actions:
                assert "display" not in (action.choices or ()), path

    def test_state_means_open_closed_all_everywhere(self, tool):
        found = 0
        for path, parser in every_parser(tool.build_parser()):
            for action in parser._actions:
                if "--state" in action.option_strings:
                    found += 1
                    assert set(action.choices) == {"open", "closed", "all"}, path
        assert found > 3

    def test_format_is_only_ever_an_output_format(self, tool):
        for path, parser in every_parser(tool.build_parser()):
            for action in parser._actions:
                if "--format" in action.option_strings:
                    assert set(action.choices) <= {"json", "jsonl", "csv"}, path

    def test_sync_search_is_gh_issue_lists_name(self, tool):
        assert parse(tool, "sync", "-S", "label:type:story").search == "label:type:story"
        with pytest.raises(SystemExit):
            parse(tool, "sync", "--query", "x")


class TestExportFlags:
    def test_format_csv(self, tool):
        assert parse(tool, "export", "--format", "csv").format == "csv"
        with pytest.raises(SystemExit):
            parse(tool, "export", "--csv")

    def test_state_file_and_no_state(self, tool):
        assert parse(tool, "export", "--state-file", "w.json").state_file == "w.json"
        assert parse(tool, "export", "--no-state").state_file is None

    @pytest.mark.parametrize("text,want", [
        ("issues", {"issues"}), ("issues,events", {"issues", "events"}),
        ("events, prs", {"events", "prs"}), ("all", {"issues", "events", "prs", "master"}),
    ])
    def test_grains_are_a_comma_list(self, tool, text, want):
        assert parse(tool, "export", "--grain", text).grain == want

    @pytest.mark.parametrize("text", ["both", "issues,nonsense", ""])
    def test_an_unknown_grain_is_refused(self, tool, text):
        with pytest.raises(SystemExit):
            parse(tool, "export", "--grain", text)


class TestBoard:
    def test_view_is_the_verb(self, tool):
        args = parse(tool, "board", "view", "Backlog", "--format", "jsonl")
        assert (args.board_command, args.name, args.format) == ("view", "Backlog", "jsonl")

    def test_create_takes_its_name_positionally(self, tool):
        assert parse(tool, "board", "create", "Team X", "--type", "scrum").name == "Team X"

    def test_a_substring_does_not_converge_somebody_elses_board(self, tool, monkeypatch):
        """Only reads match loosely. `board view Eng` finding "Engineering" is a
        read; `board create Eng` converging it would rewrite that board's filter."""
        calls = []
        monkeypatch.setattr(tool, "views_of", lambda *a: [
            {"id": "V1", "number": 3, "name": "Engineering: all work"}])
        monkeypatch.setattr(tool, "project_id", lambda *a: "P")

        def fake_graphql(query, **variables):
            calls.append(query)
            if "createProjectV2View" in query:
                return {"data": {"createProjectV2View": {
                    "projectV2View": {"id": "V9", "number": 9}}}}
            return {}
        monkeypatch.setattr(tool, "graphql", fake_graphql)
        result = tool.make_board("o", 1, "Engineering", "kanban", None)
        assert result["action"] == "created"
        assert any("createProjectV2View" in q for q in calls)

    def test_web_opens_the_view(self, tool, monkeypatch, capsys):
        opened = []
        monkeypatch.setattr(tool, "find_view", lambda *a: {"number": 3, "name": "B"})
        monkeypatch.setattr("webbrowser.open", opened.append)
        args = parse(tool, "board", "view", "B", "-w")
        args.owner, args.project, args._config = "o", 4, {}
        tool.cmd_board(args)
        assert opened == ["https://github.com/users/o/projects/4/views/3"]


@pytest.fixture
def not_a_terminal(tool, monkeypatch):
    monkeypatch.setattr(tool, "stdout_is_terminal", lambda: False)


@pytest.fixture
def a_terminal(tool, monkeypatch):
    monkeypatch.setattr(tool, "stdout_is_terminal", lambda: True)


class TestAPipedListIsData:
    """As `gh issue list | cut -f1` works: tab-separated, no header."""

    VIEWS = [{"number": 3, "name": "Backlog", "layout": "TABLE_LAYOUT",
              "filter": "no:sprint -status:Done"}]

    def board_list(self, tool, monkeypatch, capsys):
        monkeypatch.setattr(tool, "views_of", lambda *a: self.VIEWS)
        args = parse(tool, "board", "list")
        args.owner, args.project, args._config = "o", 4, {}
        tool.cmd_board(args)
        return capsys.readouterr().out

    def test_piped_board_list_is_tab_separated_and_headerless(
            self, tool, monkeypatch, capsys, not_a_terminal):
        out = self.board_list(tool, monkeypatch, capsys)
        assert out.splitlines() == ["3\tBacklog\tbacklog\ttable\tno:sprint -status:Done"]

    def test_at_a_terminal_it_is_a_table(self, tool, monkeypatch, capsys, a_terminal):
        out = self.board_list(tool, monkeypatch, capsys)
        assert "name" in out.splitlines()[0] and "\t" not in out

    def test_json_whatever_the_destination(self, tool, monkeypatch, capsys,
                                           not_a_terminal):
        monkeypatch.setattr(tool, "views_of", lambda *a: self.VIEWS)
        args = parse(tool, "board", "list", "--json", "name")
        args.owner, args.project, args._config = "o", 4, {}
        tool.cmd_board(args)
        assert json.loads(capsys.readouterr().out)[0]["name"] == "Backlog"

    def test_key_list_too(self, tool, capsys, not_a_terminal):
        args = parse(tool, "key", "list")
        args._config = {"keys": [{"key": "AGILE", "repo": "o/r", "name": "A"}]}
        tool.cmd_key_list(args)
        assert capsys.readouterr().out == "AGILE\to/r\tA\n"

    def test_sprint_list_too(self, tool, monkeypatch, capsys, not_a_terminal):
        monkeypatch.setattr(tool, "iterations", lambda *a: (
            [{"title": "S2", "startDate": "2026-10-12", "duration": 14}],
            [{"title": "S1", "startDate": "2026-09-28", "duration": 14}]))
        args = parse(tool, "sprint", "list")
        args.owner, args.project = "o", 4
        tool.cmd_sprint(args)
        assert capsys.readouterr().out.splitlines() == [
            "S2\t2026-10-12\t2026-10-25\tcurrent", "S1\t2026-09-28\t2026-10-11\tcompleted"]

    def test_a_work_item_list_too(self, tool, monkeypatch, capsys, not_a_terminal):
        row = {"key": "AGILE-12", "number": 12, "status": "Todo", "type": "story", "title": "T",
               "sprint": None, "story_points": 3, "assignees": ["a", "b"]}
        monkeypatch.setattr(tool, "iterations", lambda *a: ([], []))
        monkeypatch.setattr(tool, "fetch_items", lambda *a: ("t", [
            {"content": {"__typename": "Issue"}}]))
        monkeypatch.setattr(tool, "item_matches", lambda *a, **k: True)
        monkeypatch.setattr(tool, "board_row", lambda *a: dict(row))
        monkeypatch.setattr(tool, "current_repo", lambda: None)
        args = parse(tool, "epic", "list")
        args.owner, args.project, args._config = "o", 4, {}
        tool.cmd_list(args)
        assert capsys.readouterr().out == "AGILE-12\tTodo\tstory\tT\t\t3\ta,b\n"


class TestSprintView:
    ACTIVE = [{"title": "0006 W42-2026", "startDate": "2026-10-12", "duration": 14},
              {"title": "0007 W44-2026", "startDate": "2026-10-26", "duration": 14}]
    DONE = [{"title": "Sprint 3", "startDate": "2026-09-28", "duration": 14}]

    @pytest.fixture
    def view(self, tool, monkeypatch):
        seen = {}
        monkeypatch.setattr(tool, "iterations", lambda *a: (self.ACTIVE, self.DONE))
        monkeypatch.setattr(tool, "show_board",
                            lambda args, view, kind, typed, **k: seen.update(view) or 0)

        def go(*argv):
            args = parse(tool, "sprint", "view", *argv)
            args.owner, args.project, args._config = "o", 4, {}
            tool.cmd_sprint(args)
            return seen
        return go

    def test_no_argument_is_the_current_sprint(self, view):
        seen = view()
        assert seen["name"].startswith("0006 W42-2026") and "(current)" in seen["name"]

    def test_the_current_sprint_reads_the_field(self, view):
        assert view()["filter"] == 'sprint:"0006 W42-2026"'

    def test_a_start_date_names_one(self, view):
        assert "(future)" in view("2026-10-26")["name"]

    def test_a_completed_sprint_reads_its_labels(self, view):
        """Field for the present, labels for the past."""
        assert view("2026-09-28")["filter"] == "label:sprint:2026-09-28"

    def test_a_title_names_one_without_case(self, view):
        assert view("sprint 3")["name"].startswith("Sprint 3")

    def test_an_unknown_one_is_refused_listing_them(self, view):
        with pytest.raises(SystemExit) as caught:
            view("2027-01-01")
        assert "2026-10-12" in str(caught.value)

    def test_the_title_filter_parses_as_one_term(self, tool):
        assert tool.parse_filter('sprint:"0006 W42-2026"') == [
            (False, "sprint", "0006 W42-2026")]


class TestKey:
    @pytest.fixture
    def profile(self, tmp_path):
        path = tmp_path / "agile.json"
        config = {"keys": [{"key": "AGILE", "repo": "o/r"}, {"key": "OLD", "repo": "o/r"}]}
        path.write_text(json.dumps(config))
        return path, config

    def delete(self, tool, monkeypatch, profile, carrying):
        path, config = profile
        monkeypatch.setattr(tool, "key_issue_count", lambda repos, key: carrying)
        args = parse(tool, "key", "delete", "OLD")
        args._config, args.config = config, str(path)
        return tool.cmd_key_delete(args)

    def test_delete_refuses_while_issues_carry_the_key(self, tool, monkeypatch, profile):
        with pytest.raises(SystemExit) as caught:
            self.delete(tool, monkeypatch, profile, carrying=4)
        assert "4 issue(s) still carry key:OLD" in str(caught.value)
        assert "OLD" in profile[0].read_text()

    def test_delete_removes_an_unused_key(self, tool, monkeypatch, profile):
        self.delete(tool, monkeypatch, profile, carrying=0)
        keys = [e["key"] for e in json.loads(profile[0].read_text())["keys"]]
        assert keys == ["AGILE"]

    def test_an_unknown_key_is_refused(self, tool, monkeypatch, profile):
        path, config = profile
        args = parse(tool, "key", "delete", "NOPE")
        args._config, args.config = config, str(path)
        with pytest.raises(SystemExit):
            tool.cmd_key_delete(args)

    def test_the_count_is_one_search_of_issues_only(self, tool, monkeypatch):
        asked = []
        monkeypatch.setattr(tool, "graphql", lambda query, **v: asked.append(v["q"]) or {
            "data": {"search": {"issueCount": 2}}})
        assert tool.key_issue_count(["o/a", "o/b"], "OLD") == 2
        assert asked == ['repo:o/a repo:o/b is:issue label:"key:OLD"']

    def test_add_takes_the_key_positionally(self, tool):
        args = parse(tool, "key", "add", "WIDG", "-R", "o/z", "--name", "Z")
        assert (args.key, args.repo, args.name) == ("WIDG", "o/z", "Z")

    def test_list_never_writes(self, tool):
        assert parse(tool, "key", "list").func is tool.cmd_key_list


class TestProject:
    def test_edit_needs_something_to_change(self, tool):
        args = parse(tool, "project", "edit")
        args._config = {}
        with pytest.raises(SystemExit) as caught:
            tool.cmd_project_edit(args)
        assert "nothing to change" in str(caught.value)

    def test_edit_writes_the_cadence(self, tool, tmp_path):
        path = tmp_path / "agile.json"
        args = parse(tool, "project", "edit", "--sprint-template", "2-week")
        args._config, args.config = {}, str(path)
        tool.cmd_project_edit(args)
        assert json.loads(path.read_text())["sprint"]["template"] == "2-week"

    def test_backfill_goes_with_the_title_prefix(self, tool):
        args = parse(tool, "project", "edit", "--sprint-template", "2-week", "--backfill")
        args._config = {}
        with pytest.raises(SystemExit):
            tool.cmd_project_edit(args)

    def test_view_as_json(self, tool, capsys):
        args = parse(tool, "project", "view", "--json", "owner,number,issue_title_prefix,keys")
        args.owner, args.project = "o", 4
        args._config = {"project": {"name": "B", "issue_title_prefix": "key"},
                        "keys": [{"key": "AGILE", "repo": "o/r"}],
                        "sprint": {"template": "2-week", "cadence_days": 14}}
        tool.cmd_project_view(args)
        shown = json.loads(capsys.readouterr().out)
        assert (shown["owner"], shown["number"], shown["issue_title_prefix"]) == ("o", 4, "key")
        assert shown["keys"][0]["key"] == "AGILE"

    def test_view_needs_a_project_edit_does_not(self, tool):
        assert not parse(tool, "project", "view").__dict__.get("projectless")
        assert parse(tool, "project", "edit").projectless is True
