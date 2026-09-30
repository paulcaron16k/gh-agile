"""`gh agile unfinished` -- what a merge closed and nobody finished. AGILE-186/190/193.

**`Item closed -> Status = Done` stays off**, and this is what replaces it. The
workflow writes one field -- no Evidence, no closing `sprint:` label, no
completed-or-not-planned -- so an issue it touches reads Done while unfinished,
which is worse than one visibly left In Progress. The wrap-up is a person's, and
what a person needs is to be told at the moment they are already at the
terminal: `#123` sat closed and In Progress for twenty-two hours, `#138`
repeated it, `#174` is still in that state.

**A merge leaves an issue in one of two states** (#190) and they need different
commands. Measured across five consecutive pull requests: the closing link was
registered for every one and the close fired for only some, which is how `#186`'s
own merge left it open.

It lives in the tool rather than in `scripts/` (#193) because a git hook in
somebody else's repository cannot reach a file in this one. These tests moved
with it: they hold the behaviour, not the location.

Offline. Every shell-out is stubbed, and the rule about what a finished issue
looks like is deliberately **not** restated here -- `validate` owns it and this
asserts only that its verdict is believed.
"""

from __future__ import annotations

import argparse
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def hook(tool):
    """The tool itself: `unfinished` is one of its commands now, not a script."""
    return tool


MERGE = "Merge pull request #188 from paulcaron16k/story/agile-187_planner-types-a-duration"
SQUASH = "A planner types a duration, not an end date (#188)"


REPO = "o/r"


def board(**states):
    """A board read, as `rows` returns it: `n<number>=<state>`."""
    return [{"number": int(key.lstrip("n")), "state": state, "repository": REPO}
            for key, state in states.items()]


def args_for(tool, quiet=True, span="ORIG_HEAD..HEAD"):
    return argparse.Namespace(owner="o", project=1, _config={},
                              quiet=quiet, **{"range": span})


class TestFindingThePullRequests:
    def test_a_merge_commit(self, hook):
        assert hook.merged_pull_requests([MERGE]) == [188]

    def test_a_squash_commit(self, hook):
        """The merge style is a repository setting somebody can change, and a
        parser that knows only today's silently stops reporting."""
        assert hook.merged_pull_requests([SQUASH]) == [188]

    def test_both_spellings_in_one_range(self, hook):
        assert hook.merged_pull_requests([MERGE, "Other (#185)"]) == [188, 185]

    def test_the_same_pull_request_twice_is_one(self, hook):
        assert hook.merged_pull_requests([MERGE, SQUASH]) == [188]

    def test_order_is_the_order_merged(self, hook):
        assert hook.merged_pull_requests(["A (#3)", "B (#1)", "C (#2)"]) == [3, 1, 2]

    def test_an_ordinary_commit_names_no_pull_request(self, hook):
        assert hook.merged_pull_requests(["Every date was written as text (AGILE-182)"]) == []

    def test_an_issue_reference_mid_subject_is_not_a_pull_request(self, hook):
        """`(#188)` at the end is the squash marker; `#188` in prose is not."""
        assert hook.merged_pull_requests(["Fix the thing #188 complained about"]) == []

    def test_a_merge_of_something_that_is_not_a_number(self, hook):
        assert hook.merged_pull_requests(["Merge pull request #x from y"]) == []


CLOSING_JSON = ('{"closingIssuesReferences": [{"number": 187, "repository": '
                '{"name": "thing", "owner": {"login": "acme"}}}]}')


class Stub:
    def __init__(self, returncode=0, stdout=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, ""


class TestWhatItAsksGitHub:
    def test_the_closing_issues_come_from_github_not_from_the_message(
            self, hook, monkeypatch):
        """In this repository `Closes #n` lives in the pull request *body*; the
        merge commit says only which pull request it was."""
        asked = []
        monkeypatch.setattr(hook.subprocess, "run", lambda cmd, **k: asked.append(cmd)
                            or Stub(0, CLOSING_JSON))
        assert hook.closing_issues(188) == [("acme/thing", 187)]
        assert "closingIssuesReferences" in " ".join(asked[0])

    def test_a_pull_request_that_closes_nothing(self, hook, monkeypatch):
        monkeypatch.setattr(hook.subprocess, "run",
                            lambda cmd, **k: Stub(0, '{"closingIssuesReferences": []}'))
        assert hook.closing_issues(188) == []

    def test_a_failed_call_reports_nothing_rather_than_raising(self, hook, monkeypatch):
        monkeypatch.setattr(hook.subprocess, "run", lambda cmd, **k: Stub(1, ""))
        assert hook.closing_issues(188) == []


class TestTheTwoStatesAMergeLeaves:
    """GitHub closes the issue, or it does not, and they need different
    commands. Measured across five consecutive pull requests: the closing link
    was registered for every one and the close fired for only some, which is how
    #186's own merge left it open. AGILE-190.
    """

    def test_closed_and_not_done_reports_the_no_close_command(self, hook, monkeypatch):
        monkeypatch.setattr(hook, "cmd_validate",
                            lambda a: print("closed but status is not Done") or 1)
        text = hook.outstanding(args_for(hook), board(n174="CLOSED"), REPO, 174)
        assert "gh agile move 174 --status Done --evidence" in text
        assert "--close" not in text.split("finish it:")[1].splitlines()[0]

    def test_and_says_why_not(self, hook, monkeypatch):
        """Closing an already-closed issue exits 0 and changes nothing, which is
        how `--not-planned` lost its reason."""
        monkeypatch.setattr(hook, "cmd_validate", lambda a: print("x") or 1)
        text = hook.outstanding(args_for(hook), board(n174="CLOSED"), REPO, 174)
        assert "no --close" in text and "exits 0" in text

    def test_it_carries_what_validate_said(self, hook, monkeypatch):
        monkeypatch.setattr(hook, "cmd_validate",
                            lambda a: print("closed but status is not Done") or 1)
        text = hook.outstanding(args_for(hook), board(n174="CLOSED"), REPO, 174)
        assert "closed but status is not Done" in text

    def test_closed_and_done_reports_nothing(self, hook, monkeypatch):
        monkeypatch.setattr(hook, "cmd_validate", lambda a: 0)
        assert hook.outstanding(args_for(hook), board(n187="CLOSED"), REPO, 187) is None

    def test_still_open_is_reported(self, hook, monkeypatch):
        """The gap #186 shipped with: GitHub left the issue open, `validate`
        found nothing wrong with it, and the terminal said nothing."""
        text = hook.outstanding(args_for(hook), board(n186="OPEN"), REPO, 186)
        assert "is still open" in text

    def test_and_reports_the_close_command(self, hook):
        text = hook.outstanding(args_for(hook), board(n186="OPEN"), REPO, 186)
        assert "gh agile move 186 --status Done --close --evidence" in text

    def test_and_says_why_the_reason_matters(self, hook):
        text = hook.outstanding(args_for(hook), board(n186="OPEN"), REPO, 186)
        assert "not-planned" in text

    def test_validate_is_never_asked_about_an_open_issue(self, hook, monkeypatch):
        """An open issue whose pull request merged is not a convention
        violation -- the board cannot see pull requests, and a story left open
        after a partial merge is ordinary. AGILE-190 keeps that knowledge in the
        hook rather than making it a rule the validator cannot fairly hold."""
        monkeypatch.setattr(hook, "cmd_validate", lambda a: pytest.fail(
            "validate was asked about an open issue"))
        assert hook.outstanding(args_for(hook), board(n186="OPEN"), REPO, 186) is not None

    def test_an_issue_that_is_not_on_the_board_reports_nothing(self, hook):
        assert hook.outstanding(args_for(hook), board(n1="CLOSED"), REPO, 186) is None

    def test_two_issues_are_each_in_their_own_state(self, hook, monkeypatch):
        """One pull request can close several, and they need not agree."""
        monkeypatch.setattr(hook, "cmd_validate", lambda a: print("stale") or 1)
        shared = board(n186="OPEN", n174="CLOSED")
        assert "--close" in hook.outstanding(
            args_for(hook), shared, REPO, 186).split("finish it:")[1].splitlines()[0]
        assert "--close" not in hook.outstanding(
            args_for(hook), shared, REPO, 174).split("finish it:")[1].splitlines()[0]


class TestTheBoardIsReadOnce:
    def test_validate_is_handed_the_board_rather_than_reading_its_own(
            self, hook, monkeypatch):
        """`--id` narrows the report and not the read, so asking about three
        issues used to cost three full board reads."""
        seen = []
        monkeypatch.setattr(hook, "cmd_validate",
                            lambda a: seen.append(getattr(a, "_board", None)) or 0)
        shared = board(n174="CLOSED")
        hook.outstanding(args_for(hook), shared, REPO, 174)
        assert seen == [shared]


class TestItNeverFailsAPull:
    def drive(self, hook, monkeypatch, capsys, *, log, issues=(), text=None, quiet=True):
        monkeypatch.setattr(hook.subprocess, "run", lambda cmd, **k: Stub(
            0 if log is not None else 128, log or ""))
        monkeypatch.setattr(hook, "closing_issues",
                            lambda pr: [(REPO, n) for n in issues])
        monkeypatch.setattr(hook, "rows", lambda *a, **k: [])
        monkeypatch.setattr(hook, "outstanding", lambda a, b, repo, issue: text)
        code = hook.cmd_unfinished(args_for(hook, quiet=quiet))
        return code, capsys.readouterr()

    def test_no_orig_head_is_silence_and_success(self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=None)
        assert code == 0 and out.out == "" and out.err == ""

    def test_a_merge_that_closed_nothing_is_silent_when_quiet(
            self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=MERGE, issues=[])
        assert code == 0 and out.err == "" and out.out == ""

    def test_and_says_so_when_not_quiet(self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=MERGE, issues=[],
                               quiet=False)
        assert code == 0 and "waiting to be finished" in out.out

    def test_a_finished_issue_is_not_reported(self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=MERGE,
                               issues=[187], text=None)
        assert code == 0 and out.err == ""

    def test_an_unfinished_one_is_reported_on_stderr(self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=MERGE, issues=[187],
                               text="  #187 needs finishing")
        assert "#187" in out.err

    def test_and_still_exits_zero(self, hook, monkeypatch, capsys):
        """A hook that can stop you pulling is a hook people delete."""
        code, _out = self.drive(hook, monkeypatch, capsys, log=MERGE, issues=[187],
                                text="  #187 needs finishing")
        assert code == 0

    def test_the_board_is_not_read_when_nothing_was_closed(
            self, hook, monkeypatch, capsys):
        """A pull that closed no issue should cost no GraphQL at all."""
        monkeypatch.setattr(hook.subprocess, "run", lambda cmd, **k: Stub(0, MERGE))
        monkeypatch.setattr(hook, "closing_issues", lambda pr: [])
        monkeypatch.setattr(hook, "rows", lambda *a, **k: pytest.fail(
            "the board was read although the merge closed nothing"))
        assert hook.cmd_unfinished(args_for(hook)) == 0


class TestInstallingTheHook:
    """A hook is per clone, which is git's decision: hooks are executable code,
    so cloning never brings them. What #193 removes is that the one act was
    undocumented, specific to this repository, and silently ineffective
    elsewhere.
    """

    @pytest.fixture
    def repo(self, hook, tmp_path, monkeypatch):
        (tmp_path / ".git" / "hooks").mkdir(parents=True)
        monkeypatch.setattr(hook.subprocess, "run",
                            lambda cmd, **k: Stub(0, str(tmp_path / ".git")))
        return tmp_path / ".git" / "hooks" / "post-merge"

    def test_it_writes_the_hook(self, hook, repo, capsys):
        assert hook.cmd_hooks(argparse.Namespace()) == 0
        assert repo.exists()

    def test_the_hook_is_executable(self, hook, repo):
        hook.cmd_hooks(argparse.Namespace())
        assert repo.stat().st_mode & 0o111

    def test_the_hook_reaches_no_path_inside_the_extension(self, hook, repo):
        """The defect this story exists for: `$root/scripts/...` resolves
        against the *consumer's* repository, where nothing of the sort is."""
        hook.cmd_hooks(argparse.Namespace())
        text = repo.read_text()
        assert "scripts/" not in text and "python3" not in text

    def test_it_calls_the_command(self, hook, repo):
        hook.cmd_hooks(argparse.Namespace())
        assert "gh agile unfinished --quiet" in repo.read_text()

    def test_it_cannot_fail_a_pull(self, hook, repo):
        hook.cmd_hooks(argparse.Namespace())
        text = repo.read_text()
        assert "|| true" in text and text.rstrip().endswith("exit 0")

    def test_its_own_hook_is_replaced(self, hook, repo, capsys):
        """Somebody who installed one last month gets this by running it again,
        not by reading a changelog."""
        repo.write_text(f"#!/bin/sh\n{hook.HOOK_MARKER} -- older\n")
        assert hook.cmd_hooks(argparse.Namespace()) == 0
        assert "gh agile unfinished" in repo.read_text()
        assert "replaced" in capsys.readouterr().out

    def test_somebody_elses_hook_is_not(self, hook, repo):
        """Overwriting a hook because the filename matched would be the worst
        kind of helpfulness."""
        repo.write_text("#!/bin/sh\necho mine\n")
        with pytest.raises(SystemExit) as caught:
            hook.cmd_hooks(argparse.Namespace())
        assert "not mine to replace" in str(caught.value)
        assert repo.read_text() == "#!/bin/sh\necho mine\n"

    def test_and_says_what_to_add_instead(self, hook, repo):
        repo.write_text("#!/bin/sh\necho mine\n")
        with pytest.raises(SystemExit) as caught:
            hook.cmd_hooks(argparse.Namespace())
        assert "gh agile unfinished --quiet" in str(caught.value)

    def test_outside_a_repository_it_refuses(self, hook, monkeypatch):
        monkeypatch.setattr(hook.subprocess, "run", lambda cmd, **k: Stub(128, ""))
        with pytest.raises(SystemExit) as caught:
            hook.cmd_hooks(argparse.Namespace())
        assert "not inside a git repository" in str(caught.value)


class TestThisRepositorysOwnHookAgrees:
    """Two hook bodies exist: the one the tool writes for everybody, and this
    repository's `templates/post-merge`, which adds a CI check of its own. They
    can drift, so the line they share is compared.
    """

    def template(self):
        return (ROOT / "templates" / "post-merge").read_text()

    def test_the_template_calls_the_same_command(self, hook):
        assert "gh agile unfinished --quiet" in self.template()

    def test_the_template_no_longer_reaches_for_the_deleted_script(self):
        assert "finish_merged" not in self.template()

    def test_the_script_is_gone(self):
        """A rule implemented twice is two rules that will disagree."""
        assert not (ROOT / "scripts" / "finish_merged.py").exists()

    def test_make_hooks_still_installs_the_template(self):
        assert "templates/post-merge" in (ROOT / "Makefile").read_text()
