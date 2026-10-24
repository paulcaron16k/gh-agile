"""`gh agile bug create | list | view` -- the type no command filed. AGILE-252.

POLICY.md defines a Bug as "an issue labelled `type:bug`; may or may not have an
epic", and `ISSUE_TYPES` named it, but nothing filed one. Bugs went in as stories
relabelled by hand (#209, #234), or as plain `gh issue create` that `sync
--adopt` boards and never types, leaving `validate` to report them.

The command is `story create` with the one difference the policy states: a bug's
epic is optional, so leaving it out is not an accident to refuse.
"""

from __future__ import annotations

import argparse
import json

import pytest


@pytest.fixture
def bug(monkeypatch, tool, capsys):
    """`cmd_bug` against a stubbed GitHub; returns what it created and wrote."""
    record = {"linked": [], "created": [], "fields": [], "labels": [], "titled": []}
    parents = {"9": "epic", "12": "story"}
    monkeypatch.setattr(tool, "require_sprint_config", lambda *a, **k: None)
    monkeypatch.setattr(tool, "require_key_for_prefix", lambda *a, **k: None)
    monkeypatch.setattr(tool, "ensure_labels", lambda repo, labels: record["labels"].extend(labels))
    monkeypatch.setattr(tool, "create_issue",
                        lambda *a, **k: record["created"].append(a) or (7, "I_7"))
    monkeypatch.setattr(tool, "apply_title_prefix",
                        lambda *a, **k: record["titled"].append(a) or a[-1])
    monkeypatch.setattr(tool, "add_to_project", lambda *a, **k: "PVTI_7")
    monkeypatch.setattr(tool, "set_field",
                        lambda o, p, item, name, value: record["fields"].append((name, value)))
    monkeypatch.setattr(tool, "graphql", lambda q, **v: record["linked"].append(v) or {"data": {}})
    monkeypatch.setattr(tool, "gh", lambda a, **k: json.dumps(
        {"id": "I_parent", "labels": [{"name": f"type:{parents[a[2]]}"}]}))

    def go(epic=None, **overrides):
        args = argparse.Namespace(**{
            "title": "Export drops closed bugs", "repo": "o/r", "key": "A", "epic": epic,
            "points": None, "priority": None, "intent": None, "acceptance": None,
            "owner": "o", "project": 1, "_config": {}, **overrides})
        code = tool.cmd_bug(args)
        record["out"] = capsys.readouterr().out
        record["code"] = code
        return record
    return go


class TestFilingABug:
    def test_it_is_typed_a_bug(self, bug):
        created = bug()["created"][0]
        assert "type:bug" in created[3] and "type:story" not in created[3]

    def test_and_keyed(self, bug):
        assert "key:A" in bug()["created"][0][3]

    def test_it_goes_on_the_board_in_todo(self, bug):
        assert ("Status", "Todo") in bug()["fields"]

    def test_its_title_prefix_names_the_type(self, bug):
        """`key+type` titles read `A-7 Bug: ...`, as they read `Story:`."""
        assert bug()["titled"][0][4] == "bug"

    def test_the_output_names_it_a_bug(self, bug):
        assert bug()["out"].startswith("  bug #7")

    def test_points_and_priority_are_set(self, bug):
        fields = bug(points=2.0, priority="high")["fields"]
        assert ("Story Points", 2.0) in fields and ("Priority", "high") in fields


class TestTheEpicIsOptional:
    def test_no_epic_stands_alone(self, bug):
        """The policy's own words: a bug may or may not have an epic."""
        record = bug()
        assert record["linked"] == [] and "standing alone" in record["out"]

    def test_and_is_not_refused(self, bug):
        """Where `story create` without `--epic` is a parse error."""
        assert bug()["code"] == 0

    def test_none_is_still_accepted(self, bug):
        assert bug("none")["linked"] == []

    def test_an_epic_makes_the_edge(self, bug):
        record = bug("9")
        assert record["linked"] == [{"parent": "I_parent", "child": "I_7"}]
        assert "under epic #9" in record["out"]

    def test_a_parent_that_is_not_an_epic_is_refused_before_anything_exists(self, bug):
        with pytest.raises(SystemExit, match="is a story, and a bug belongs to an epic"):
            bug("12")


class TestTheCommandLine:
    def test_create_parses_without_an_epic(self, tool):
        args = tool.build_parser().parse_args(["bug", "create", "-t", "x"])
        assert args.epic is None and args.func is tool.cmd_bug

    def test_story_still_requires_one(self, tool, capsys):
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args(["story", "create", "-t", "x"])

    @pytest.mark.parametrize("verb", ["list", "view"])
    def test_it_lists_and_views_like_the_other_levels(self, tool, verb):
        argv = ["bug", verb] + (["7"] if verb == "view" else [])
        assert tool.build_parser().parse_args(argv).bug_command == verb

    def test_it_is_a_work_item_command(self, tool):
        groups = dict(tool.HELP_GROUPS) if hasattr(tool, "HELP_GROUPS") else None
        text = tool.build_parser().format_help()
        work = text.split("WORK ITEM COMMANDS")[1].split("BOARD COMMANDS")[0]
        assert "bug:" in work, groups


class TestValidateAcceptsABugAlone:
    """POLICY.md: a bug "may or may not have an epic". So `validate` says nothing
    about one standing alone -- not even the note an orphan story earns."""

    @pytest.fixture
    def validate(self, monkeypatch, tool, capsys):
        def go(labels):
            monkeypatch.setattr(tool, "rows", lambda *a, **k: [{
                "number": 7, "title": "a bug", "repository": "o/r", "state": "OPEN",
                "state_reason": "", "labels": labels, "field_status": "Todo",
                "field_sprint": "", "epic_number": None, "sub_issues_total": 0,
                "sub_issues_done": 0, "started_at": "", "done_at": ""}])
            monkeypatch.setattr(tool, "iterations", lambda *a, **k: ([], []))
            code = tool.cmd_validate(argparse.Namespace(owner="o", project=1, _config={}, id=None))
            return code, capsys.readouterr().out
        return go

    def test_a_bug_without_an_epic_is_clean(self, validate):
        code, out = validate("type:bug;key:A")
        assert code == 0 and "no epic" not in out and "note(s)" not in out

    def test_where_the_same_story_is_noted(self, validate):
        """The contrast that makes the first test mean something."""
        _code, out = validate("type:story;key:A")
        assert "story has no epic" in out


#: The types a command files and lists. Each per-type table must know every one:
#: `bug` reached the parser and was missing from four of them, which only a live
#: run in the sandbox found -- `bug list` crashed on `LIST_NAMES['bug']`, and
#: `bug create` found no key because `apply_defaults` names its commands.
FILED = ("initiative", "epic", "story", "bug")


class TestEveryTableKnowsEveryType:
    @pytest.mark.parametrize("kind", FILED)
    def test_list_has_a_filter_and_a_heading(self, tool, kind):
        assert tool.TYPE_FILTERS[kind] == f"label:type:{kind}"
        assert tool.LIST_NAMES[kind]

    @pytest.mark.parametrize("kind", FILED)
    def test_view_can_name_it(self, tool, kind):
        assert kind in tool.VIEWABLE

    @pytest.mark.parametrize("kind", FILED)
    def test_create_gets_the_default_key(self, tool, kind, monkeypatch):
        """The first key for the repository, as the profile orders them."""
        profile = {"project": {"number": 4, "owner": "o"},
                   "keys": [{"key": "TEST", "repo": "o/r"}]}
        # The profile and the clone stubbed, as `test_sync_repos.defaults` does:
        # `apply_defaults` reads both for itself.
        monkeypatch.setattr(tool, "read_config", lambda *a, **k: profile)
        monkeypatch.setattr(tool, "current_repo", lambda: "o/r")
        monkeypatch.setattr(tool, "resolve_owner", lambda args, cfg: None)
        argv = [kind, "create", "-t", "x"] + (["--epic", "none"] if kind == "story" else [])
        args = tool.build_parser().parse_args(argv)
        args.project, args.owner = 4, "o"
        tool.apply_defaults(args)
        assert args.key == "TEST"

    def test_bug_list_runs(self, tool, monkeypatch):
        """Parsed is not run: the `KeyError` was in the command, not the parser."""
        shown = {}
        monkeypatch.setattr(tool, "show_board",
                            lambda args, view, kind, typed, **k: shown.update(view=view) or 0)
        args = tool.build_parser().parse_args(["bug", "list"])
        args.owner, args.project, args._config = "o", 4, {}
        assert tool.cmd_list(args) == 0
        assert shown["view"]["name"] == "Bugs"
