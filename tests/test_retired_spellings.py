"""AGILE-200: every retired spelling fails loudly, and names its replacement.

`gh agile epic list` filed an epic called "list" (ZMBNI-185), because `epic`
took its first word as a title. The work-item types are now noun groups, and a
title is `-t`, as `gh issue create -t` takes it (#202).

Two promises, and each has its own failure. **Nothing retired is reinterpreted
as something else** -- an old spelling exits non-zero rather than doing a
different thing. And **the error names the new spelling**, rebuilt from what
was typed, because `main` is the release and the break reaches every install at
its next upgrade. The second must never undo the first: a `gh` verb is not a
title, so `epic list` is never answered with `epic create -t list`.

#206 finishes the table and, a release later, removes it.
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


class TestTheOldTitleSpelling:
    @pytest.mark.parametrize("argv,suggested", [
        (["epic", "Snapshot expiry", "--key", "AGILE"],
         "gh agile epic create -t 'Snapshot expiry' --key AGILE"),
        (["story", "A story", "--epic", "3"],
         "gh agile story create -t 'A story' --epic 3"),
        (["task", "Tidy", "--story", "9"],
         "gh agile task create -t Tidy --story 9"),
        (["initiative", "create", "Big thing"],
         "gh agile initiative create -t 'Big thing'"),
    ])
    def test_it_names_the_new_spelling(self, tool, monkeypatch, capsys, argv, suggested):
        code, err = run(tool, monkeypatch, capsys, *argv)
        assert code == 2
        assert suggested in err

    def test_global_flags_before_the_command_are_kept(self, tool, monkeypatch, capsys):
        _code, err = run(tool, monkeypatch, capsys,
                         "--project", "4", "epic", "Title", "--repo", "o/r")
        assert "gh agile --project 4 epic create -t Title --repo o/r" in err

    def test_the_suggestion_says_what_was_typed(self, tool, monkeypatch, capsys):
        _code, err = run(tool, monkeypatch, capsys, "initiative", "create", "X")
        assert "`initiative create TITLE` is now" in err

    def test_nothing_is_parsed_or_created(self, tool, monkeypatch, capsys):
        """`apply_defaults` raises in `run`, so reaching it fails the test."""
        code, _err = run(tool, monkeypatch, capsys, "epic", "Title")
        assert code == 2


class TestAVerbIsNeverATitle:
    """The hint must not be ZMBNI-185 offered as advice."""

    @pytest.mark.parametrize("verb", ["edit", "close", "status", "delete"])
    def test_no_create_is_suggested(self, tool, monkeypatch, capsys, verb):
        code, err = run(tool, monkeypatch, capsys, "epic", verb)
        assert code == 2
        assert "create -t" not in err

    def test_every_gh_issue_verb_is_covered(self, tool):
        """`gh issue`'s own verbs, read from its help on 2.86."""
        gh_issue = {"create", "list", "status", "close", "comment", "delete",
                    "develop", "edit", "lock", "pin", "reopen", "transfer",
                    "unlock", "unpin", "view"}
        assert gh_issue <= tool.GH_VERBS


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

    @pytest.mark.parametrize("argv,suggested", [
        (["move", "ZMBNI-34", "--status", "Done", "--evidence-file", "notes.md", "--close"],
         "gh agile issue close ZMBNI-34 --evidence-file notes.md"),
        (["move", "12", "--status=In Progress"],
         "gh agile issue move 12 'In Progress'"),
        (["move", "--evidence", "some text", "12", "--status", "Done"],
         "gh agile issue move 12 Done --evidence 'some text'"),
        (["set", "--issue", "ZMBNI-34", "--field", "Sprint", "--value", "@current"],
         "gh agile issue edit ZMBNI-34 --field Sprint --value @current"),
        (["--project", "4", "fix", "--id", "26", "--dry-run"],
         "gh agile --project 4 issue reconcile 26 --dry-run"),
        (["set", "--issue", "12", "--field", "Story Points", "--number", "3"],
         "gh agile issue edit 12 --field 'Story Points' --value 3"),
        (["issue", "edit", "12", "--field", "Story Points", "--number", "3"],
         "gh agile issue edit 12 --field 'Story Points' --value 3"),
        (["plan", "AGILE-12", "--start", "2026-11-02", "--for", "6w"],
         "gh agile issue edit AGILE-12 --start 2026-11-02 --for 6w"),
    ])
    def test_it_names_the_new_spelling(self, tool, monkeypatch, capsys, argv, suggested):
        code, err = run(tool, monkeypatch, capsys, *argv)
        assert code == 2
        assert suggested in err

    def test_an_evidence_value_is_not_taken_for_the_issue(self, tool, monkeypatch, capsys):
        """The issue is found by skipping every flag's value."""
        _code, err = run(tool, monkeypatch, capsys,
                         "move", "--evidence", "AGILE-9", "12", "--status", "Done")
        assert "issue move 12 Done --evidence AGILE-9" in err

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


class TestTheBoardsDialect:
    """#203: everything that is not a work item, renamed to `gh`'s words."""

    @pytest.mark.parametrize("argv,suggested", [
        (["board", "show", "Backlog", "--format", "jsonl"],
         "gh agile board view Backlog --format jsonl"),
        (["board", "create", "--name", "Team X", "--type", "scrum", "--save"],
         "gh agile board create 'Team X' --type scrum --save"),
        (["setup"], "gh agile init"),
        (["setup", "--spec", "f.json"], "gh agile init --spec f.json"),
        (["hooks"], "gh agile init"),
        (["project", "create", "--title", "B", "--key", "K"], "gh agile init -t B --key K"),
        (["project", "owner"], "gh agile init"),
        (["--owner", "org", "project", "owner"], "gh agile --owner org init"),
        (["project", "sprint-template", "--template", "2-week"],
         "gh agile project edit --sprint-template 2-week"),
        (["project", "title-prefix", "--mode", "key", "--backfill", "--dry-run"],
         "gh agile project edit --title-prefix key --backfill --dry-run"),
        (["key", "--key", "ZMBNI", "--name", "Z"], "gh agile key add ZMBNI --name Z"),
        (["key"], "gh agile key list"),
        (["export", "--csv", "--out-dir", "x"], "gh agile export --format csv --out-dir x"),
        (["export", "--state", "w.json"], "gh agile export --state-file w.json"),
        (["export", "--state=w.json"], "gh agile export --state-file=w.json"),
        (["export", "--grain", "both"], "gh agile export --grain issues,events"),
        (["sync", "--query", "label:x"], "gh agile sync --search label:x"),
    ])
    def test_it_names_the_new_spelling(self, tool, monkeypatch, capsys, argv, suggested):
        code, err = run(tool, monkeypatch, capsys, *argv)
        assert code == 2
        assert suggested in err

    @pytest.mark.parametrize("argv", [
        ["key", "list"], ["key", "add", "Z"], ["key", "--help"], ["export"],
        ["export", "--format", "csv"], ["sync", "--state", "all"], ["board", "view", "x"],
        ["board", "create", "X", "--type", "scrum"],
    ])
    def test_the_current_spelling_is_left_alone(self, tool, argv):
        assert tool.retired_spelling(argv) is None


class TestEveryRowOfTheTable:
    """#206: the table is the record of what was retired, and the release
    note's table is this one. Each row is run through `main`, so a row cannot
    be listed without a hint that names its replacement."""

    @pytest.mark.parametrize("row", __import__("conftest")._load().RETIRED_TABLE,
                             ids=lambda row: row[0])
    def test_the_row_fails_and_names_the_new_spelling(self, tool, monkeypatch, capsys, row):
        _was, _is, argv, suggested = row
        code, err = run(tool, monkeypatch, capsys, *argv)
        assert code == 2
        assert suggested in err

    def test_the_old_spelling_also_fails_without_the_hint(self, tool):
        """Underneath the kindness, nothing retired is reinterpreted: with the
        hint gone, every row is still a parse error."""
        for _was, _is, argv, _suggested in tool.RETIRED_TABLE:
            with pytest.raises(SystemExit):
                tool.build_parser().parse_args(argv)

    def test_the_release_note_carries_the_same_table(self, tool):
        """The note sent to consumers and the table the hints are tested against
        are one table; a row added to one and not the other is caught here."""
        import pathlib
        note = (pathlib.Path(__file__).resolve().parent.parent
                / "docs" / "release-v0.4.0.md").read_text()
        rows = [line for line in note.splitlines()
                if line.startswith("| ") and not line.startswith("| Was ")]
        assert rows == [f"| {was} | {now} |" for was, now, _a, _e in tool.RETIRED_TABLE]


class TestTheNextReleasesRows:
    """Spellings retired after v0.4.0, recorded for the next note (#219)."""

    @pytest.mark.parametrize("row", __import__("conftest")._load().RETIRED_NEXT,
                             ids=lambda row: row[0])
    def test_the_row_fails_and_names_the_new_spelling(self, tool, monkeypatch, capsys, row):
        _was, _is, argv, suggested = row
        code, err = run(tool, monkeypatch, capsys, *argv)
        assert code == 2 and suggested in err

    def test_the_next_note_carries_the_same_table(self, tool):
        import pathlib
        note = (pathlib.Path(__file__).resolve().parent.parent
                / "docs" / "release-next.md").read_text()
        rows = [line for line in note.splitlines()
                if line.startswith("| ") and not line.startswith("| Was ")]
        assert rows == [f"| {was} | {now} |" for was, now, _a, _e in tool.RETIRED_NEXT]
