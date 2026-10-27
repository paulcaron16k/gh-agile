"""`check-guide` checks the CLI against the guide, not only the guide. AGILE-158.

`scripts/check_guide.py` verified **guide to tool** -- every documented
invocation exists, and the read-only ones run -- and never **tool to guide**. So
a command documented nowhere passed everything: `gh agile task` shipped in #134,
`make check-guide` reported *no problems found*, CI stayed green, and the
omission was found months later by a person asking whether the docs were
current.

The same shape as #151, where a grouping collapsed to a single bucket: the check
ran, passed, and conveyed nothing. **A guard that looks one way reports the
absence of what it cannot see.**

Writing it found a second one immediately -- `gh agile sprint unstamp`, shipped
in #123 and documented nowhere -- which is the argument for the direction.

Offline: the parser's help and a guide fixture are both local, so nothing here
reaches the board.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def guard():
    """`scripts/check_guide.py`, imported rather than run."""
    spec = importlib.util.spec_from_file_location(
        "check_guide", ROOT / "scripts" / "check_guide.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_guide"] = module
    spec.loader.exec_module(module)
    return module


class TestItReadsTheRealParser:
    def test_it_finds_the_top_level_commands(self, guard):
        leaves = guard.parser_leaves()
        assert ("validate",) in leaves and ("sync",) in leaves

    def test_it_finds_leaves_not_just_parents(self, guard):
        """A guide showing `board list` and never `board view` has not
        documented `board view`."""
        leaves = guard.parser_leaves()
        assert ("board", "view") in leaves
        assert ("board",) not in leaves

    def test_an_option_s_choices_are_not_mistaken_for_subcommands(self, guard):
        """argparse prints `--state {open,closed,all}` exactly as it prints a
        subparser group. Matching `{...}` anywhere reported `sync all`,
        `sync open` and `sync closed` as undocumented commands."""
        leaves = guard.parser_leaves()
        assert ("sync",) in leaves
        for bogus in ("all", "open", "closed"):
            assert ("sync", bogus) not in leaves

    def test_and_format_choices_are_not_either(self, guard):
        assert ("board", "jsonl") not in guard.parser_leaves()


class TestItCannotPassByFindingNothing:
    def test_a_parser_with_nothing_found_is_fatal(self, guard):
        """An extraction that stopped matching would otherwise make every
        command exempt and the check green -- which is what happened once,
        spotted only by a summary line reading `-2 command(s) require
        documenting`."""
        import argparse
        with pytest.raises(SystemExit) as exit_info:
            guard.parser_leaves(argparse.ArgumentParser())
        assert "stopped matching" in str(exit_info.value)


class TestWhatCountsAsDocumented:
    def test_an_invocation_counts(self, guard):
        seen = guard.documented_leaves([(1, "gh agile board view 3")])
        assert ("board", "view") in seen

    def test_the_parent_counts_too(self, guard):
        """`gh agile board view` documents `board`, whose own help is a menu."""
        seen = guard.documented_leaves([(1, "gh agile board view 3")])
        assert ("board",) in seen

    def test_a_flag_does_not_become_a_subcommand(self, guard):
        seen = guard.documented_leaves([(1, "gh agile sync --dry-run --state all")])
        assert seen == {("sync",)}

    def test_a_global_flag_before_the_subcommand_is_skipped(self, guard):
        seen = guard.documented_leaves([(1, "gh agile --owner acme board list")])
        assert ("board", "list") in seen

    def test_the_gh_agile_hyphen_form_is_read_too(self, guard):
        """The cron examples invoke the extension directly."""
        seen = guard.documented_leaves([(1, "gh-agile sync")])
        assert ("sync",) in seen


class TestTheReport:
    def test_an_undocumented_command_is_a_problem(self, guard, monkeypatch):
        monkeypatch.setattr(guard, "parser_leaves",
                            lambda: {("validate",), ("never", "mentioned")})
        problems = guard.coverage_problems([(1, "gh agile validate")])
        assert len(problems) == 1
        assert "never mentioned" in problems[0]

    def test_it_says_what_to_do_about_it(self, guard, monkeypatch):
        """A failure that only says a count did not match is a failure nobody
        can act on."""
        monkeypatch.setattr(guard, "parser_leaves", lambda: {("never", "mentioned")})
        problem = guard.coverage_problems([])[0]
        assert "USER_GUIDE.md" in problem and "UNDOCUMENTED_OK" in problem

    def test_a_documented_command_is_not(self, guard, monkeypatch):
        monkeypatch.setattr(guard, "parser_leaves", lambda: {("validate",)})
        assert guard.coverage_problems([(1, "gh agile validate")]) == []

    def test_an_exempt_command_is_not(self, guard, monkeypatch):
        monkeypatch.setattr(guard, "parser_leaves", lambda: {("task", "create")})
        assert guard.coverage_problems([]) == []


class TestTheExemptions:
    def test_every_exemption_carries_a_reason(self, guard):
        """An exemption with no justification is indistinguishable from an
        oversight, which is the failure this check exists to catch."""
        assert all(isinstance(why, str) and len(why) > 40
                   for why in guard.UNDOCUMENTED_OK.values())

    def test_every_exempt_command_actually_exists(self, guard):
        """An exemption for a command that has been renamed hides its
        successor."""
        leaves = guard.parser_leaves()
        assert set(guard.UNDOCUMENTED_OK) <= leaves

    def test_a_hidden_command_is_owed_no_documentation(self, guard):
        """Hidden from `--help` (#203), so not part of what a reader is shown:
        `self-test` is a maintainer target."""
        assert ("self-test",) not in guard.parser_leaves()

    def test_unfinished_is_owed_documentation(self, guard):
        """Shown in `--help` since #268, so the guide must invoke it."""
        assert ("unfinished",) in guard.parser_leaves()

    def test_task_is_exempt_deliberately_not_accidentally(self, guard):
        """Filing tasks as issues is not promoted: POLICY.md §2 still
        recommends a checklist, and documenting the command in the guide would
        read as a recommendation."""
        why = guard.UNDOCUMENTED_OK[("task", "create")]
        assert "checklist" in why and "POLICY" in why


class TestTheGuideIsActuallyCovered:
    def test_no_command_is_undocumented_and_unexempted(self, guard):
        """The end-to-end assertion, and the one that fails when somebody adds
        a command and forgets the guide."""
        assert guard.coverage_problems(guard.documented_commands()) == []

    def test_sprint_unstamp_is_documented(self, guard):
        """Found undocumented by this check the first time it ran."""
        assert ("sprint", "unstamp") in guard.documented_leaves(
            guard.documented_commands())
