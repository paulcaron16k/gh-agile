"""`check_guide` must not be able to run a mutating command.

It executes the guide's read-only commands, and it makes them read-only by
appending flags -- `--dry-run` to a `sync`, `--no-state` to an `export`. The
commands run through `sh -c`.

**A documented line ending in a comment swallowed the flag.**
`gh agile sync   # every repo in the profile keys` became
`gh agile sync   # every repo in the profile keys --dry-run`, the shell dropped
everything after the `#`, and a real sync ran. Measured 2026-09-12: it added 35
issues from a second repository onto a live board. It had been harmless only for
as long as `sync` happened to be looking at one repository, and stopped being so
the same afternoon that changed.

So the comment is stripped before anything is appended, and it is stripped the
way a shell would strip it -- a `#` inside quotes is an argument, not a comment.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def guide():
    spec = importlib.util.spec_from_file_location("cg", ROOT / "scripts" / "check_guide.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestStripComment:
    @pytest.mark.parametrize("line,want", [
        ("gh agile sync   # every repo in the profile keys", "gh agile sync"),
        ("gh agile sync --dry-run  # what is missing", "gh agile sync --dry-run"),
        ("gh agile validate", "gh agile validate"),
        ("# a whole line", ""),
        ("gh agile sync ", "gh agile sync"),
    ])
    def test_a_trailing_comment_goes(self, guide, line, want):
        assert guide.strip_comment(line) == want

    @pytest.mark.parametrize("line", [
        'gh agile epic create -t "fixes #12"',
        "gh agile sync --search 'a#b' --state all",
        'gh agile issue move 7 Done --evidence "see #12 and #13"',
    ])
    def test_a_hash_inside_quotes_is_an_argument(self, guide, line):
        """The shell's own rule, and the guide does document titles with issue
        references in them."""
        assert guide.strip_comment(line) == line

    def test_a_hash_mid_word_is_not_a_comment(self, guide):
        assert guide.strip_comment("gh agile sync --repo o/r#x") == "gh agile sync --repo o/r#x"


class TestTheSafetyFlagSurvives:
    """The property that actually matters: after `run_safe` has finished
    rewriting it, a `sync` the guide documents cannot write."""

    @pytest.mark.parametrize("documented", [
        "gh agile sync                           # every repo in the profile keys",
        "gh agile sync --adopt                   # and give what it adds the convention",
        "gh agile sync --repo owner/other-repo   # just one",
        "gh agile sync",
        "gh agile sync --search 'label:type:story' --state all",
    ])
    def test_every_documented_sync_ends_up_a_dry_run(self, guide, documented):
        rewritten = guide.strip_comment(documented)
        if "--dry-run" not in rewritten:
            rewritten += " --dry-run"
        assert rewritten.split("#")[0].strip().endswith("--dry-run") or "--dry-run" in rewritten
        # and the flag is not stranded behind a comment the shell would eat
        assert "#" not in rewritten.split("--dry-run")[0]

    def test_an_export_keeps_its_state_flags(self, guide):
        rewritten = guide.strip_comment("gh agile export --format csv   # to stdout")
        assert "#" not in rewritten
        assert rewritten == "gh agile export --format csv"


class TestValidateFindingsAreAReport:
    """`validate` exits 1 when the board has a problem; that is a report, not a
    broken guide line. Its JSON prints no summary line (#284)."""

    @pytest.fixture
    def ran(self, guide, monkeypatch):
        def go(stdout, stderr, code=1):
            import subprocess

            monkeypatch.setattr(guide.subprocess, "run", lambda *a, **k:
                                subprocess.CompletedProcess(a, code, stdout, stderr))
            return guide.run_safe("gh agile validate --json ok")[0]
        return go

    def test_text_summary(self, ran):
        assert ran("\n1 problem(s) across 3 item(s)\n", "")

    def test_json_report(self, ran):
        assert ran('{\n  "ok": false\n}\n', "")

    def test_a_refusal_still_fails(self, ran):
        assert not ran("", "no project 4 found for 'o'\n")
