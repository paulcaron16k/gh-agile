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

    @pytest.mark.parametrize("verb", ["list", "view", "edit", "close", "status"])
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
        (["issue", "edit", "12", "--field", "FR", "--value", "x"], "cmd_set", "field"),
        (["issue", "reconcile", "12", "--dry-run"], "cmd_fix", "dry_run"),
    ])
    def test_each_reaches_its_command(self, tool, argv, func, dest):
        args = tool.build_parser().parse_args(argv)
        assert args.func is getattr(tool, func)
        assert args.issue == "12" and getattr(args, dest)
        assert args.needs_repo is True

    def test_the_status_is_the_second_positional(self, tool):
        """As `gh issue transfer <issue> <repo>` takes a required second value."""
        args = tool.build_parser().parse_args(["issue", "move", "AGILE-3", "In Progress"])
        assert (args.issue, args.status) == ("AGILE-3", "In Progress")

    @pytest.mark.parametrize("old", ["move", "set", "fix"])
    def test_the_old_top_level_command_is_gone(self, tool, old):
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args([old, "1"])
