"""Every spelling retired since AGILE-200 fails at parsing, and is never reinterpreted.

`gh agile epic list` filed an epic called "list" (WIDG-185), because `epic`
took its first word as a title. The work-item types became noun groups and a
title became `-t`, as `gh issue create -t` takes it (#202), and v0.4.0 and
v0.5.0 retired the old spellings with a hint naming each replacement.

**The hints are gone (#307)**, as both release notes said they would be: an old
spelling now fails like any other typo -- stage 3 of the README's deprecation
policy. What stays is the promise that mattered more: **nothing retired is
reinterpreted as something else.** Every old command line below is still run
through `main`, and must exit 2 before anything is parsed into a command.
"""

from __future__ import annotations

import pytest


def run(tool, monkeypatch, capsys, *argv):
    """`main` on a command line, with nothing reaching GitHub."""
    import sys as _sys

    monkeypatch.setattr(tool, "require_interpreter", lambda: None)
    monkeypatch.setattr(tool, "apply_defaults",
                        lambda args: (_ for _ in ()).throw(AssertionError("parsed")))
    monkeypatch.setattr(_sys, "argv", ["gh-agile", *argv])
    try:
        code = tool.main()
    except SystemExit as exc:
        code = exc.code
    return code, capsys.readouterr().err


#: Every command line the v0.4.0 and v0.5.0 hints answered, kept as data now
#: that the hints are gone: each must still fail at parsing.
REMOVED = [
    # The title as a positional (v0.4.0).
    ["epic", "Snapshot expiry", "--key", "AGILE"],
    ["story", "A story", "--epic", "3"],
    ["task", "Tidy", "--story", "9"],
    ["initiative", "create", "Big thing"],
    ["--project", "4", "epic", "Title", "--repo", "o/r"],
    ["story", "create", "-t", "S", "--epic", "none", "--status", "In Progress"],
    ["story", "S", "--epic", "none", "--status=Blocked"],
    # Commands that moved under `issue` (v0.4.0).
    ["move", "WIDG-34", "--status", "Done", "--evidence-file", "notes.md", "--close"],
    ["move", "185", "--status", "Done", "--not-planned", "--close"],
    ["move", "12", "--status=In Progress"],
    ["move", "--evidence", "some text", "12", "--status", "Done"],
    ["set", "--issue", "WIDG-34", "--field", "Sprint", "--value", "@current"],
    ["--project", "4", "fix", "--id", "26", "--dry-run"],
    ["set", "--issue", "12", "--field", "Story Points", "--number", "3"],
    ["issue", "edit", "12", "--field", "Story Points", "--number", "3"],
    ["plan", "AGILE-12", "--start", "2026-11-02", "--for", "6w"],
    ["validate", "--id", "AGILE-24"],
    ["validate", "--id=AGILE-24"],
    ["issue", "move", "7", "In Progress", "--add-assignee"],
    # Everything that is not a work item, in `gh`'s words (v0.4.0, #203).
    ["board", "show", "Backlog", "--format", "jsonl"],
    ["board", "create", "--name", "Team X", "--type", "scrum", "--save"],
    ["setup"],
    ["setup", "--spec", "f.json"],
    ["hooks"],
    ["project", "create", "--title", "B", "--key", "K"],
    ["project", "owner"],
    ["--owner", "org", "project", "owner"],
    ["project", "sprint-template", "--template", "2-week"],
    ["project", "title-prefix", "--mode", "key", "--backfill", "--dry-run"],
    ["key", "--key", "WIDG", "--name", "Z"],
    ["key"],
    ["export", "--csv", "--out-dir", "x"],
    ["export", "--state", "w.json"],
    ["export", "--state=w.json"],
    ["export", "--grain", "both"],
    ["sync", "--query", "label:x"],
    # `--format json` became `--json` (v0.5.0, #219).
    ["issue", "view", "12", "--format", "json"],
    ["story", "list", "--format", "json"],
    ["issue", "status", "--format=json"],
]


@pytest.mark.parametrize("argv", REMOVED, ids=" ".join)
def test_each_fails_at_parsing_and_nothing_runs(tool, monkeypatch, capsys, argv):
    """`apply_defaults` raises in `run`, so a command line that parsed into a
    command fails this test rather than exiting 2."""
    code, err = run(tool, monkeypatch, capsys, *argv)
    assert code == 2
    assert "is now" not in err             # the hint, gone with #307


def test_the_hint_code_is_gone(tool):
    for name in ("retired_spelling", "RETIRED_TABLE", "RETIRED_NEXT", "GH_VERBS",
                 "MOVED_UNDER_ISSUE"):
        assert not hasattr(tool, name), name


@pytest.mark.parametrize("verb", ["edit", "close", "status", "delete"])
def test_a_verb_a_group_lacks_is_never_a_title(tool, monkeypatch, capsys, verb):
    """WIDG-185: `epic close` must be a usage error, not an epic called "close"."""
    code, _err = run(tool, monkeypatch, capsys, "epic", verb)
    assert code == 2


@pytest.mark.parametrize("argv", [
    ["key", "list"], ["key", "add", "Z"], ["export"], ["export", "--format", "csv"],
    ["export", "--format", "json"], ["story", "list", "--format", "jsonl"],
    ["sync", "--state", "all"], ["board", "view", "x"],
    ["board", "create", "X", "--type", "scrum"],
])
def test_the_current_spelling_parses(tool, argv):
    tool.build_parser().parse_args(argv)


class TestTheNewShape:
    @pytest.mark.parametrize("group", ["initiative", "epic", "story", "task"])
    def test_a_group_needs_its_verb(self, tool, group):
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args([group])

    @pytest.mark.parametrize("argv", [
        ["epic", "create", "Title"],
        ["story", "create", "Title", "--epic", "none"],
    ])
    def test_a_positional_title_is_refused_as_gh_refuses_it(self, tool, argv):
        """`gh issue create "x"` is `unknown argument "x"`."""
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args(argv)

    @pytest.mark.parametrize("argv", [
        ["initiative", "create", "-t", "T"],
        ["epic", "create", "-t", "T"],
        ["story", "create", "--title", "T", "--epic", "none"],
        ["task", "create", "-t", "T", "--story", "9"],
    ])
    def test_the_title_flag_parses(self, tool, argv):
        assert tool.build_parser().parse_args(argv).title == "T"

    def test_create_still_reaches_its_command(self, tool):
        args = tool.build_parser().parse_args(["epic", "create", "-t", "T"])
        assert args.func is tool.cmd_epic and args.needs_repo is True


class TestTheCommandsThatMovedUnderIssue:
    """`move`, `set` and `fix` act on any work item, so they live where `gh`
    keeps such verbs: under `issue`, the issue first."""

    @pytest.mark.parametrize("argv,func,dest", [
        (["issue", "move", "12", "in-progress"], "cmd_move", "status"),
        (["issue", "edit", "12", "--field", "FR", "--value", "x"], "cmd_edit", "field"),
        (["issue", "reconcile", "12", "--dry-run"], "cmd_fix", "dry_run"),
    ])
    def test_each_reaches_its_command(self, tool, argv, func, dest):
        args = tool.build_parser().parse_args(argv)
        assert args.func is getattr(tool, func)
        # `issue edit` takes several, as `gh issue edit` does.
        assert args.issue in ("12", ["12"]) and getattr(args, dest)
        assert args.needs_repo is True

    def test_the_status_is_the_second_positional(self, tool):
        """As `gh issue transfer <issue> <repo>` takes a required second value."""
        args = tool.build_parser().parse_args(["issue", "move", "AGILE-3", "In Progress"])
        assert (args.issue, args.status) == ("AGILE-3", "In Progress")

    @pytest.mark.parametrize("old", ["move", "set", "fix", "plan"])
    def test_the_old_top_level_command_is_gone(self, tool, old):
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args([old, "1"])
