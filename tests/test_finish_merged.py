"""The post-merge prompt: what a merge closed and did not finish. AGILE-186.

**`Item closed -> Status = Done` stays off**, and this is what replaces it. The
workflow writes one field -- no Evidence, no closing `sprint:` label, no
completed-or-not-planned -- so an issue it touches reads Done while unfinished,
which is worse than one visibly left In Progress. The wrap-up is a person's, and
what a person needs is to be told at the moment they are already at the
terminal: `#123` sat closed and In Progress for twenty-two hours, `#138`
repeated it, `#174` was still in that state days later.

Offline. Every shell-out is stubbed, and the rule about what a finished issue
looks like is deliberately **not** restated here -- `validate --id` owns it and
this asserts only that its exit code is believed.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def hook():
    """`scripts/finish_merged.py`, imported rather than run."""
    spec = importlib.util.spec_from_file_location(
        "finish_merged", ROOT / "scripts" / "finish_merged.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["finish_merged"] = module
    spec.loader.exec_module(module)
    return module


MERGE = "Merge pull request #188 from paulcaron16k/story/agile-187_planner-types-a-duration"
SQUASH = "A planner types a duration, not an end date (#188)"


class TestFindingThePullRequests:
    def test_a_merge_commit(self, hook):
        assert hook.pull_requests([MERGE]) == [188]

    def test_a_squash_commit(self, hook):
        """The merge style is a repository setting somebody can change, and a
        parser that knows only today's silently stops reporting."""
        assert hook.pull_requests([SQUASH]) == [188]

    def test_both_spellings_in_one_range(self, hook):
        assert hook.pull_requests([MERGE, "Other (#185)"]) == [188, 185]

    def test_the_same_pull_request_twice_is_one(self, hook):
        assert hook.pull_requests([MERGE, SQUASH]) == [188]

    def test_order_is_the_order_merged(self, hook):
        assert hook.pull_requests(["A (#3)", "B (#1)", "C (#2)"]) == [3, 1, 2]

    def test_an_ordinary_commit_names_no_pull_request(self, hook):
        assert hook.pull_requests(["Every date was written as text (AGILE-182)"]) == []

    def test_an_issue_reference_mid_subject_is_not_a_pull_request(self, hook):
        """`(#188)` at the end is the squash marker; `#188` in prose is not."""
        assert hook.pull_requests(["Fix the thing #188 complained about"]) == []


class TestWhatItAsksGitHub:
    def test_the_closing_issues_come_from_github_not_from_the_message(
            self, hook, monkeypatch):
        """In this repository `Closes #n` lives in the pull request *body*; the
        merge commit says only which pull request it was."""
        asked = []
        monkeypatch.setattr(hook, "run", lambda cmd: asked.append(cmd) or
                            '{"closingIssuesReferences": [{"number": 187}]}')
        assert hook.closing_issues(188) == [187]
        assert "closingIssuesReferences" in " ".join(asked[0])

    def test_a_pull_request_that_closes_nothing(self, hook, monkeypatch):
        monkeypatch.setattr(hook, "run", lambda cmd: '{"closingIssuesReferences": []}')
        assert hook.closing_issues(188) == []

    def test_a_failed_call_reports_nothing_rather_than_raising(self, hook, monkeypatch):
        monkeypatch.setattr(hook, "run", lambda cmd: None)
        assert hook.closing_issues(188) == []


class TestTheRuleIsNotRestated:
    def test_it_believes_validates_exit_code(self, hook, monkeypatch):
        """A second copy of *what a finished issue looks like* is one that can
        disagree with `validate`."""
        monkeypatch.setattr(hook.shutil, "which", lambda name: "/usr/bin/gh")
        monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: Stub(1, "a problem"))
        assert hook.unfinished(187) == "a problem"

    def test_a_clean_issue_says_nothing(self, hook, monkeypatch):
        monkeypatch.setattr(hook.shutil, "which", lambda name: "/usr/bin/gh")
        monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: Stub(0, ""))
        assert hook.unfinished(187) is None

    def test_no_gh_says_nothing(self, hook, monkeypatch):
        monkeypatch.setattr(hook.shutil, "which", lambda name: None)
        assert hook.unfinished(187) is None

    def test_the_source_restates_no_status_rule(self, hook):
        source = (ROOT / "scripts" / "finish_merged.py").read_text()
        assert "In Progress" not in source.split('"""', 2)[2]


class Stub:
    def __init__(self, returncode, stdout):
        self.returncode, self.stdout, self.stderr = returncode, stdout, ""


class TestTheReport:
    def test_it_names_the_issue_and_the_command(self, hook):
        text = hook.report(187, "closed but status is not Done (1):")
        assert "#187" in text
        assert "gh agile move 187 --status Done --evidence" in text

    def test_it_says_not_to_close_again_and_why(self, hook):
        """Closing an already-closed issue exits 0 and changes nothing, which is
        how `--not-planned` lost its reason."""
        text = hook.report(187, "x")
        assert "no --close" in text
        assert "exits 0" in text

    def test_it_carries_what_validate_said(self, hook):
        assert "closed but status is not Done" in hook.report(187, "closed but status is not Done")


class TestItNeverFailsAPull:
    def drive(self, hook, monkeypatch, capsys, *, log, issues=(), problem=None, quiet=True):
        monkeypatch.setattr(sys, "argv",
                            ["finish_merged"] + (["--quiet"] if quiet else []))
        monkeypatch.setattr(hook, "run", lambda cmd: log)
        monkeypatch.setattr(hook, "closing_issues", lambda pr: list(issues))
        monkeypatch.setattr(hook, "unfinished", lambda issue: problem)
        code = hook.main()
        return code, capsys.readouterr()

    def test_no_orig_head_is_silence_and_success(self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=None)
        assert code == 0 and out.out == "" and out.err == ""

    def test_a_merge_that_closed_nothing_is_silent_when_quiet(
            self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=MERGE, issues=[])
        assert code == 0 and out.err == "" and out.out == ""

    def test_and_says_so_when_not_quiet(self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=MERGE, issues=[], quiet=False)
        assert code == 0 and "waiting to be finished" in out.out

    def test_a_finished_issue_is_not_reported(self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=MERGE,
                               issues=[187], problem=None)
        assert code == 0 and out.err == ""

    def test_an_unfinished_one_is_reported_on_stderr(self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=MERGE,
                               issues=[187], problem="closed but status is not Done")
        assert "#187" in out.err
        assert "gh agile move 187" in out.err

    def test_and_still_exits_zero(self, hook, monkeypatch, capsys):
        """A hook that can stop you pulling is a hook people delete."""
        code, _out = self.drive(hook, monkeypatch, capsys, log=MERGE,
                                issues=[187], problem="closed but status is not Done")
        assert code == 0


class TestTheHookInstallsIt:
    def test_the_template_calls_the_script(self):
        assert "finish_merged.py" in (ROOT / "templates" / "post-merge").read_text()

    def test_it_is_called_quietly(self):
        """Every pull would otherwise print a line, and a hook that always
        prints is one people stop reading."""
        text = (ROOT / "templates" / "post-merge").read_text()
        assert "finish_merged.py\" --quiet" in text

    def test_it_cannot_fail_the_pull(self):
        for line in (ROOT / "templates" / "post-merge").read_text().splitlines():
            if "finish_merged.py" in line and line.startswith("python3"):
                assert line.rstrip().endswith("|| true")

    def test_make_hooks_installs_the_template(self):
        assert "templates/post-merge" in (ROOT / "Makefile").read_text()
