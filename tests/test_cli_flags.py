"""#201: the flags a `gh` user already types, and one grammar for naming an issue.

The non-breaking half of AGILE-200, which reshapes the command surface to read
like `gh`. Four things, each measured against `gh` 2.86's own help rather than
remembered:

- `--owner`, `--project` and `--config` parse after the subcommand as well as
  before it. `gh agile board list --project 19` was `unrecognized arguments`.
- Short flags only where `gh` has the same one meaning the same thing. `-a` is
  not among them: in `gh` it is `--assignee`, and `--add-assignee` has none.
- An issue is a number, a `KEY-NUMBER` reference or a URL, everywhere -- the
  parent flags included. `story --epic` took digits only.
- `sprint create --dry-run`, on the one write that clears every Sprint value.
"""

from __future__ import annotations

import argparse
import json

import pytest

CONFIG = {"keys": [{"key": "AGILE", "repo": "o/agile"}, {"key": "ZMBNI", "repo": "o/zamboni"}]}


def subparsers(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            yield from action.choices.items()


def every_parser(parser, path=()):
    yield path, parser
    for name, child in subparsers(parser):
        yield from every_parser(child, (*path, name))


class TestGlobalFlagsEitherSide:
    @pytest.mark.parametrize("argv", [
        ["--project", "19", "board", "list"],
        ["board", "list", "--project", "19"],
        ["board", "--project", "19", "list"],
    ])
    def test_project_is_read_wherever_it_is_typed(self, tool, argv):
        assert tool.build_parser().parse_args(argv).project == 19

    @pytest.mark.parametrize("flag,value", [("--owner", "someone"),
                                            ("--config", "elsewhere.json")])
    def test_owner_and_config_too(self, tool, flag, value):
        args = tool.build_parser().parse_args(["sprint", "create", flag, value])
        assert getattr(args, flag[2:]) == value

    def test_a_flag_typed_before_survives_the_subcommand(self, tool):
        """The reason every copy below the top is `SUPPRESS`: an ordinary default
        in the subparser would write `None` over the value typed first."""
        args = tool.build_parser().parse_args(["--project", "4", "--owner", "o",
                                               "issue", "move", "7", "Done"])
        assert (args.project, args.owner) == (4, "o")

    def test_untyped_is_still_none(self, tool):
        """`apply_defaults` and `resolve_owner` read `None` as "not given"."""
        args = tool.build_parser().parse_args(["board", "list"])
        assert (args.owner, args.project, args.config) == (None, None, None)

    def test_every_command_accepts_them(self, tool):
        for path, parser in every_parser(tool.build_parser()):
            options = {o for a in parser._actions for o in a.option_strings}
            assert {"--owner", "--project", "--config"} <= options, path


#: Every short flag, and the long flags it may stand for. Each one is `gh`'s
#: own, meaning the same thing there. `-t` is two, as in `gh`: `--title` where an
#: issue is written, `--template` where output is formatted.
GH_SHORT_FLAGS = {"-h": {"--help"}, "-R": {"--repo"}, "-L": {"--limit"},
                  "-s": {"--state"}, "-t": {"--title", "--template"}, "-r": {"--reason"},
                  "-c": {"--comment"}, "-S": {"--search"}, "-w": {"--web"},
                  "-b": {"--body"}, "-F": {"--body-file"}, "-a": {"--assignee"},
                  "-l": {"--label"}, "-m": {"--milestone"}, "-e": {"--editor"},
                  "-A": {"--author"}, "-q": {"--jq"}}


class TestShortFlagsAreGhs:
    def test_no_short_flag_means_something_gh_does_not(self, tool):
        for path, parser in every_parser(tool.build_parser()):
            for action in parser._actions:
                shorts = [o for o in action.option_strings if len(o) == 2]
                longs = [o for o in action.option_strings if o.startswith("--")]
                for short in shorts:
                    assert GH_SHORT_FLAGS.get(short, set()) & set(longs), (path, short, longs)

    def test_repo_has_its_short_form_everywhere(self, tool):
        """`-R` is inherited by every `gh issue` and `gh pr` subcommand."""
        for path, parser in every_parser(tool.build_parser()):
            for action in parser._actions:
                if "--repo" in action.option_strings:
                    assert "-R" in action.option_strings, path

    def test_add_assignee_has_none(self, tool):
        issue = dict(subparsers(tool.build_parser()))["issue"]
        move = dict(subparsers(issue))["move"]
        flag = next(a for a in move._actions if "--add-assignee" in a.option_strings)
        assert flag.option_strings == ["--add-assignee"]

    def test_export_state_is_not_s(self, tool):
        """`export`'s watermark file is `--state-file` (#203): `--state` is
        open/closed/all everywhere else, as in `gh`."""
        export = dict(subparsers(tool.build_parser()))["export"]
        flag = next(a for a in export._actions if "--state-file" in a.option_strings)
        assert flag.option_strings == ["--state-file"]
        assert not any("--state" in a.option_strings for a in export._actions)


class TestOneIssueGrammar:
    @pytest.mark.parametrize("text,want", [
        ("34", ("o/here", 34)),
        ("ZMBNI-34", ("o/zamboni", 34)),
        ("https://github.com/o/zamboni/issues/34", ("o/zamboni", 34)),
        ("https://github.com/o/zamboni/issues/34#issuecomment-1", ("o/zamboni", 34)),
        ("https://ghe.example.com/team/repo/issues/9", ("team/repo", 9)),
        (" https://github.com/o/my-repo/issues/5 ", ("o/my-repo", 5)),
    ])
    def test_a_number_a_key_or_a_url(self, tool, text, want):
        assert tool.parse_issue_ref(text, CONFIG, "o/here") == want

    @pytest.mark.parametrize("text", [
        "https://github.com/o/r/pull/34",
        "https://github.com/o/r/issues",
        "https://github.com/o/r/issues/abc",
        "ftp://github.com/o/r/issues/3",
    ])
    def test_not_an_issue_address(self, tool, text):
        with pytest.raises(SystemExit):
            tool.parse_issue_ref(text, CONFIG, "o/here")

    def test_a_url_is_a_reference_and_not_a_slug(self, tool):
        """`initiative` tells a reference from a slug with this, so a URL given
        to `--initiative` must not be looked up as a slug."""
        assert tool.looks_like_issue_ref("https://github.com/o/r/issues/3", CONFIG)


@pytest.fixture
def story(monkeypatch, tool, capsys):
    """`cmd_story` against a fake GitHub that knows a few epics."""
    record = {"viewed": [], "created": [], "linked": []}
    known = {("o/agile", 9): "epic", ("o/zamboni", 40): "epic", ("o/agile", 12): "story"}

    def fake_gh(argv, **kwargs):
        if argv[:2] == ["issue", "view"]:
            where = (argv[argv.index("--repo") + 1], int(argv[2]))
            record["viewed"].append(where)
            if where not in known:
                raise SystemExit("could not resolve to an issue")
            return json.dumps({"id": f"I_{where[1]}",
                               "labels": [{"name": f"type:{known[where]}"}]})
        raise AssertionError(argv)

    monkeypatch.setattr(tool, "gh", fake_gh)
    monkeypatch.setattr(tool, "require_sprint_config", lambda *a, **k: None)
    monkeypatch.setattr(tool, "require_key_for_prefix", lambda *a, **k: None)
    monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
    monkeypatch.setattr(tool, "create_issue",
                        lambda *a, **k: record["created"].append(a) or (7, "I_7"))
    monkeypatch.setattr(tool, "apply_title_prefix", lambda *a, **k: a[-1])
    monkeypatch.setattr(tool, "add_to_project", lambda *a, **k: "PVTI_7")
    monkeypatch.setattr(tool, "set_field", lambda *a, **k: None)
    monkeypatch.setattr(tool, "graphql",
                        lambda q, **v: record["linked"].append(v) or {"data": {}})

    def go(epic):
        args = argparse.Namespace(title="a story", repo="o/agile", key="AGILE", epic=epic,
                                  points=None, priority=None, status="Todo",
                                  intent=None, acceptance=None, owner="o", project=1,
                                  _config=CONFIG)
        tool.cmd_story(args)
        record["out"] = capsys.readouterr().out
        return record

    go.record = record
    return go


class TestStoryEpic:
    @pytest.mark.parametrize("epic", ["9", "AGILE-9", "https://github.com/o/agile/issues/9"])
    def test_every_spelling_reaches_the_same_epic(self, story, epic):
        record = story(epic)
        assert record["viewed"] == [("o/agile", 9)]
        assert record["linked"] == [{"parent": "I_9", "child": "I_7"}]

    def test_an_epic_in_another_repository(self, story):
        """Refused before #201 while `task --story ZMBNI-40` worked."""
        record = story("ZMBNI-40")
        assert record["viewed"] == [("o/zamboni", 40)]
        assert "under epic o/zamboni#40" in record["out"]

    def test_same_repository_reads_as_before(self, story):
        assert "under epic #9" in story("9")["out"]

    def test_an_epic_that_does_not_exist_creates_nothing(self, story):
        """It used to create the story and then fail on the epic, leaving an
        orphan behind its own error -- and an issue number is never reused."""
        with pytest.raises(SystemExit) as exit_info:
            story("9999")
        assert "Nothing was created" in str(exit_info.value)
        assert story.record["created"] == []

    def test_a_story_is_not_an_epic(self, story):
        with pytest.raises(SystemExit) as exit_info:
            story("12")
        assert "is a story, and a story belongs to an epic" in str(exit_info.value)
        assert story.record["created"] == []


class TestSprintCreateDryRun:
    @pytest.fixture
    def create(self, monkeypatch, tool, capsys):
        writes = []
        monkeypatch.setattr(tool, "sprint_field",
                            lambda *a: {"id": "F", "configuration": {"duration": 14}})
        monkeypatch.setattr(tool, "iterations", lambda *a: (
            [{"title": "Sprint 2", "startDate": "2026-10-12", "duration": 14}],
            [{"title": "Sprint 1", "startDate": "2026-09-28", "duration": 14}]))
        monkeypatch.setattr(tool, "sprint_assignments", lambda *a: {"PVTI_1": "x",
                                                                    "PVTI_2": "y"})
        monkeypatch.setattr(tool, "require_graphql_budget", lambda *a: None)
        monkeypatch.setattr(tool, "graphql", lambda *a, **k: writes.append(a))
        monkeypatch.setattr(tool, "restore_assignments", lambda *a: writes.append(a))
        monkeypatch.setattr(tool, "heal_sprint_fields", lambda *a: writes.append(a))

        def go(**overrides):
            args = argparse.Namespace(sprint_command="create", owner="o", project=1,
                                      start=None, weeks=None, title=None, dry_run=True,
                                      _config={"sprint": {"name_template": "Sprint {n}"}})
            for name, value in overrides.items():
                setattr(args, name, value)
            tool.cmd_sprint(args)
            return writes, capsys.readouterr().out

        return go

    def test_it_writes_nothing(self, create):
        writes, _ = create()
        assert writes == []

    def test_it_says_what_it_would_append_and_what_it_would_clear(self, create):
        _, out = create()
        assert "would append Sprint 3: 2026-10-26, 14 day(s)" in out
        assert "2 assignment(s) would be re-applied" in out

    def test_the_default_start_follows_the_latest_sprint(self, tool, monkeypatch, create):
        """Not the last list entry, which is a completed sprint whenever there is
        one: the default then landed inside a live sprint and was refused."""
        monkeypatch.setattr(tool, "iterations", lambda *a: (
            [{"title": "Sprint 3", "startDate": "2026-10-12", "duration": 14},
             {"title": "Sprint 4", "startDate": "2026-10-26", "duration": 14}],
            [{"title": "Sprint 1", "startDate": "2026-09-14", "duration": 14},
             {"title": "Sprint 2", "startDate": "2026-09-28", "duration": 14}]))
        _, out = create()
        assert "would append Sprint 5: 2026-11-09" in out

    def test_it_still_refuses_what_the_real_run_would(self, create):
        """A dry run that passes must be one the real run would not refuse."""
        with pytest.raises(SystemExit) as exit_info:
            create(start="2026-10-13")
        assert "would overlap" in str(exit_info.value)

    def test_the_parser_has_it(self, tool):
        args = tool.build_parser().parse_args(["sprint", "create", "--dry-run"])
        assert args.dry_run is True
