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


REPO = "o/r"


def board(**states):
    """A board read, as `rows` returns it: `n<number>=<state>`."""
    return [{"number": int(key.lstrip("n")), "state": state, "repository": REPO}
            for key, state in states.items()]


def args_for(tool, quiet=True, span="ORIG_HEAD..HEAD"):
    return argparse.Namespace(owner="o", project=1, _config={},
                              quiet=quiet, **{"range": span})


class Stub:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


#: What `commits/{sha}/pulls` answers, after the `--jq` the tool sends: one
#: merged pull request per line, number and base repository. Keyed by commit,
#: and named for the merge style that produced it -- the API answers all four
#: the same way, which is the point of asking it.
MERGE_COMMIT, SQUASH, REBASED_1, REBASED_2, EDITED, STORY = (
    "aaaa1111", "bbbb2222", "cccc3333", "cccc4444", "dddd5555", "eeee6666")
PULLS = {
    MERGE_COMMIT: f"188\t{REPO}\n",
    SQUASH: f"189\t{REPO}\n",
    REBASED_1: f"190\t{REPO}\n",
    REBASED_2: f"190\t{REPO}\n",
    EDITED: f"191\t{REPO}\n",
    # Zamboni's 92a5bc7, "... retired spellings (#228)": the subject names an
    # issue, and GitHub says the commit belongs to pull request 229.
    STORY: f"229\t{REPO}\n",
}


def line(*shas):
    """A first-parent line as `first_parent_commits` returns it, no merges."""
    return [(sha, []) for sha in shas]


def github(pulls=PULLS, fail=(), unknown=()):
    """A stand-in for `gh api repos/{owner}/{repo}/commits/{sha}/pulls`."""
    asked = []

    def run(cmd, **_kwargs):
        asked.append(cmd)
        sha = cmd[2].split("/")[-2]
        if sha in fail:
            return Stub(1, "", "gh: Server Error (HTTP 502)")
        if sha in unknown:
            return Stub(1, "", f"gh: No commit found for SHA: {sha} (HTTP 422)")
        return Stub(0, pulls.get(sha, ""))
    run.asked = asked
    return run


class TestFindingThePullRequests:
    """GitHub says which pull request a commit belongs to; the subject is never
    read. AGILE-225: Zamboni's story commit `... (#228)` names an issue, the old
    parser took it for a pull request, and the merge's real one, #229, was never
    checked.
    """

    def test_a_merge_commit(self, hook, monkeypatch):
        monkeypatch.setattr(hook.subprocess, "run", github())
        assert hook.merged_pull_requests(line(MERGE_COMMIT), REPO) == ([188], [])

    def test_a_squash_merge(self, hook, monkeypatch):
        monkeypatch.setattr(hook.subprocess, "run", github())
        assert hook.merged_pull_requests(line(SQUASH), REPO) == ([189], [])

    def test_a_rebase_merge_is_one_pull_request(self, hook, monkeypatch):
        """A rebase keeps the original subjects and names no pull request at all;
        each commit still belongs to one, and it is asked about once."""
        monkeypatch.setattr(hook.subprocess, "run", github())
        assert hook.merged_pull_requests(line(REBASED_1, REBASED_2), REPO) == ([190], [])

    def test_a_merge_whose_title_was_edited(self, hook, monkeypatch):
        monkeypatch.setattr(hook.subprocess, "run", github())
        assert hook.merged_pull_requests(line(EDITED), REPO) == ([191], [])

    def test_an_issue_number_in_a_subject_has_no_effect(self, hook, monkeypatch):
        """The Zamboni merge: the merge commit and its story commit both belong
        to #229, and #228 -- the issue in the story's subject -- is nowhere."""
        monkeypatch.setattr(hook.subprocess, "run",
                            github({**PULLS, MERGE_COMMIT: f"229\t{REPO}\n"}))
        assert hook.merged_pull_requests(line(MERGE_COMMIT, STORY), REPO) == ([229], [])

    def test_the_subject_is_never_asked_for(self, hook, monkeypatch):
        run = github()
        monkeypatch.setattr(hook.subprocess, "run", run)
        hook.merged_pull_requests(line(MERGE_COMMIT), REPO)
        assert run.asked[0][:2] == ["gh", "api"]
        assert "commits/aaaa1111/pulls" in run.asked[0][2]
        assert "merged_at" in " ".join(run.asked[0])

    def test_order_is_the_order_merged(self, hook, monkeypatch):
        monkeypatch.setattr(hook.subprocess, "run", github())
        assert hook.merged_pull_requests(line(EDITED, MERGE_COMMIT, SQUASH), REPO)[0] == [
            191, 188, 189]

    def test_a_pull_request_based_elsewhere_is_not_this_merge(self, hook, monkeypatch):
        """A commit can belong to a fork's pull request too."""
        monkeypatch.setattr(hook.subprocess, "run",
                            github({MERGE_COMMIT: f"7\tfork/r\n188\t{REPO}\n"}))
        assert hook.merged_pull_requests(line(MERGE_COMMIT), REPO) == ([188], [])

    def test_a_commit_in_no_pull_request(self, hook, monkeypatch):
        monkeypatch.setattr(hook.subprocess, "run", github({}))
        assert hook.merged_pull_requests(line("ffff0000"), REPO) == ([], [])

    def test_a_commit_github_has_never_seen_is_not_a_failure(self, hook, monkeypatch):
        """A local `git merge` of an unpushed branch runs the hook too, and no
        pull request merged a commit GitHub does not have."""
        monkeypatch.setattr(hook.subprocess, "run", github(unknown={"ffff0000"}))
        assert hook.merged_pull_requests(line("ffff0000"), REPO) == ([], [])

    def test_a_failing_lookup_among_good_ones(self, hook, monkeypatch):
        """The failure is named, and every other commit is still asked."""
        monkeypatch.setattr(hook.subprocess, "run", github(fail={SQUASH}))
        found, failed = hook.merged_pull_requests(line(MERGE_COMMIT, SQUASH, EDITED), REPO)
        assert found == [188, 191]
        assert len(failed) == 1 and SQUASH[:8] in failed[0]


CLOSING_JSON = ('{"closingIssuesReferences": [{"number": 187, "repository": '
                '{"name": "thing", "owner": {"login": "acme"}}}]}')


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

    def test_a_failed_call_is_none_and_not_an_empty_list(self, hook, monkeypatch):
        """A call that failed and a pull request that closes nothing are
        different answers. Collapsing them reported a clean merge to somebody
        whose token had just expired -- AGILE-192."""
        monkeypatch.setattr(hook.subprocess, "run", lambda cmd, **k: Stub(1, ""))
        assert hook.closing_issues(188) is None


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
        assert "gh agile issue move 174 Done --evidence" in text
        assert "--close" not in text.split("finish it:")[1].splitlines()[0]

    def test_and_says_why_not(self, hook, monkeypatch):
        """Closing an already-closed issue exits 0 and changes nothing, which is
        how `--not-planned` lost its reason."""
        monkeypatch.setattr(hook, "cmd_validate", lambda a: print("x") or 1)
        text = hook.outstanding(args_for(hook), board(n174="CLOSED"), REPO, 174)
        assert "not `issue close`" in text and "exits 0" in text

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
        assert "gh agile issue close 186 --evidence" in text

    def test_and_says_why_the_reason_matters(self, hook):
        text = hook.outstanding(args_for(hook), board(n186="OPEN"), REPO, 186)
        assert '-r "not planned"' in text

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
        assert "issue close" in hook.outstanding(
            args_for(hook), shared, REPO, 186).split("finish it:")[1].splitlines()[0]
        assert "issue close" not in hook.outstanding(
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


def pulled(hook, monkeypatch, shas=(MERGE_COMMIT,), found=(188,), failed=()):
    """A pull that brought in `shas`, which GitHub says merged `found`."""
    monkeypatch.setattr(hook.subprocess, "run",
                        lambda cmd, **k: Stub(0, "".join(f"{sha}\n" for sha in shas)))
    monkeypatch.setattr(hook, "current_repo", lambda: REPO)
    monkeypatch.setattr(hook, "merged_pull_requests",
                        lambda *a: (list(found), list(failed)))


class TestItNeverFailsAPull:
    def drive(self, hook, monkeypatch, capsys, *, log, issues=(), text=None, quiet=True):
        if log is None:
            monkeypatch.setattr(hook.subprocess, "run", lambda cmd, **k: Stub(128, ""))
        else:
            pulled(hook, monkeypatch)
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
        code, out = self.drive(hook, monkeypatch, capsys, log=True, issues=[])
        assert code == 0 and out.err == "" and out.out == ""

    def test_and_says_so_when_not_quiet(self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=True, issues=[],
                               quiet=False)
        assert code == 0 and "waiting to be finished" in out.out

    def test_a_finished_issue_is_not_reported(self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=True,
                               issues=[187], text=None)
        assert code == 0 and out.err == ""

    def test_an_unfinished_one_is_reported_on_stderr(self, hook, monkeypatch, capsys):
        code, out = self.drive(hook, monkeypatch, capsys, log=True, issues=[187],
                               text="  #187 needs finishing")
        assert "#187" in out.err

    def test_and_still_exits_zero(self, hook, monkeypatch, capsys):
        """A hook that can stop you pulling is a hook people delete."""
        code, _out = self.drive(hook, monkeypatch, capsys, log=True, issues=[187],
                                text="  #187 needs finishing")
        assert code == 0

    def test_the_board_is_not_read_when_nothing_was_closed(
            self, hook, monkeypatch, capsys):
        """A pull that closed no issue should cost no GraphQL at all."""
        pulled(hook, monkeypatch)
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
        monkeypatch.setattr(hook, "hooks_dir", lambda: (tmp_path / ".git" / "hooks", False))
        return tmp_path / ".git" / "hooks" / "post-merge"

    def test_it_writes_the_hook(self, hook, repo, capsys):
        assert hook.install_hook().startswith("installed")
        assert repo.exists()

    def test_the_hook_is_executable(self, hook, repo):
        hook.install_hook()
        assert repo.stat().st_mode & 0o111

    def test_the_hook_reaches_no_path_inside_the_extension(self, hook, repo):
        """The defect this story exists for: `$root/scripts/...` resolves
        against the *consumer's* repository, where nothing of the sort is."""
        hook.install_hook()
        text = repo.read_text()
        assert "scripts/" not in text and "python3" not in text

    def test_it_calls_the_command(self, hook, repo):
        hook.install_hook()
        assert "gh agile unfinished --quiet" in repo.read_text()

    def test_it_cannot_fail_a_pull(self, hook, repo):
        """Every `exit` in it, not merely the last one: the failure branch
        added by #192 is a second way out of the script."""
        hook.install_hook()
        text = repo.read_text()
        exits = [line.strip() for line in text.splitlines()
                 if line.strip().startswith("exit ")]
        assert exits and all(line == "exit 0" for line in exits)
        assert text.rstrip().endswith("exit 0")

    def test_its_own_hook_is_replaced(self, hook, repo, capsys):
        """Somebody who installed one last month gets this by running it again,
        not by reading a changelog."""
        repo.write_text(f"#!/bin/sh\n{hook.HOOK_MARKER} -- older\n")
        said = hook.install_hook()
        assert "gh agile unfinished" in repo.read_text()
        assert "replaced" in said

    def test_somebody_elses_hook_is_not(self, hook, repo):
        """Overwriting a hook because the filename matched would be the worst
        kind of helpfulness."""
        repo.write_text("#!/bin/sh\necho mine\n")
        assert "not mine to replace" in hook.install_hook()
        assert repo.read_text() == "#!/bin/sh\necho mine\n"

    def test_and_says_what_to_add_instead(self, hook, repo):
        repo.write_text("#!/bin/sh\necho mine\n")
        assert "gh agile unfinished --quiet" in hook.install_hook()

    def test_and_does_not_claim_the_whole_tool_never_wrote_it(self, hook, repo):
        """`make hooks` is this tool's repository too; what did not write it is
        `init`. AGILE-234."""
        repo.write_text("#!/bin/sh\necho mine\n")
        said = hook.install_hook()
        assert "not written by `gh agile init`" in said and "this tool" not in said

    def test_a_hook_that_already_calls_it_is_not_told_to_add_it(self, hook, repo):
        """This repository's own hook, from `make hooks`, carries no marker and
        already runs the check; so does anybody's who took the advice once.
        AGILE-234."""
        mine = "#!/bin/sh\necho mine\ngh agile unfinished --quiet || true\n"
        repo.write_text(mine)
        said = hook.install_hook()
        assert "already calls `gh agile unfinished`" in said
        assert "Add this line" not in said
        assert repo.read_text() == mine

    def test_this_repositorys_template_is_left_alone(self, hook, repo):
        """Replacing it would drop the red-`main` check only it has; it belongs
        to `make hooks`, and two installers for one file would drift."""
        template = (ROOT / "templates" / "post-merge").read_text()
        repo.write_text(template)
        assert "already calls" in hook.install_hook()
        assert repo.read_text() == template

    def test_outside_a_repository_it_says_so(self, hook, monkeypatch):
        """Said, not fatal: `init` has done its real work by the time it gets
        here, and a clone-less run is not a failed one."""
        monkeypatch.setattr(hook.subprocess, "run", lambda cmd, **k: Stub(128, ""))
        assert "not inside a git repository" in hook.install_hook()


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


class TestSayingWhatDidNotHappen:
    """A check that cannot run says so, in the hook's words. AGILE-192.

    Filed as *silent*, which was wrong and is recorded on the issue: `|| true`
    swallowed the exit code and never the output, so a stray `can't open file`
    or `invalid choice` did reach the terminal. What was missing is that neither
    says a post-merge check did not happen, nor what to do about it -- and both
    repeated on every pull unchanged.
    """

    def test_a_finding_is_not_a_failure(self, hook, monkeypatch, capsys):
        """The contract the hook reads: non-zero means not everything was
        checked, never that something was found."""
        pulled(hook, monkeypatch)
        monkeypatch.setattr(hook, "closing_issues", lambda pr: [(REPO, 174)])
        monkeypatch.setattr(hook, "rows", lambda *a, **k: [])
        monkeypatch.setattr(hook, "outstanding",
                            lambda a, b, repo, issue: "  #174 needs finishing")
        assert hook.cmd_unfinished(args_for(hook)) == 0

    def test_a_failed_closing_lookup_is_not_a_clean_merge(self, hook, monkeypatch,
                                                          capsys):
        """`closing_issues` returning None rather than []: a token that expired
        would otherwise report *nothing waiting*, which looks exactly right."""
        pulled(hook, monkeypatch)
        monkeypatch.setattr(hook, "closing_issues", lambda pr: None)
        assert hook.cmd_unfinished(args_for(hook)) == 1
        assert "could not ask GitHub" in capsys.readouterr().err

    def test_a_board_it_cannot_read_is_not_a_clean_merge(self, hook, monkeypatch,
                                                         capsys):
        pulled(hook, monkeypatch)
        monkeypatch.setattr(hook, "closing_issues", lambda pr: [(REPO, 174)])
        def unreadable(*a, **k):
            raise SystemExit("no project 4 found")
        monkeypatch.setattr(hook, "rows", unreadable)
        assert hook.cmd_unfinished(args_for(hook)) == 1
        assert "could not read project" in capsys.readouterr().err

    def test_a_missing_scope_is_reported_rather_than_raised(self, hook, monkeypatch,
                                                            capsys):
        """`MissingScope` travels uncaught to `main` by design; a hook is where
        that would become a traceback on somebody's pull."""
        pulled(hook, monkeypatch)
        monkeypatch.setattr(hook, "closing_issues", lambda pr: [(REPO, 174)])
        def unscoped(*a, **k):
            raise hook.MissingScope("read:project is missing")
        monkeypatch.setattr(hook, "rows", unscoped)
        assert hook.cmd_unfinished(args_for(hook)) == 1

    def test_an_unresolvable_range_is_still_not_a_failure(self, hook, monkeypatch):
        """A first clone has no ORIG_HEAD and a pull that merged nothing has
        nothing to say. Neither is a broken check."""
        monkeypatch.setattr(hook.subprocess, "run", lambda cmd, **k: Stub(128, ""))
        assert hook.cmd_unfinished(args_for(hook)) == 0


class TestOneFailureDoesNotStopTheRest:
    """AGILE-225: the first failed lookup ended the check, so the pull request
    that mattered was never asked about and the hook printed only the failure.
    """

    def test_findings_are_reported_beside_the_failure(self, hook, monkeypatch, capsys):
        pulled(hook, monkeypatch, shas=(MERGE_COMMIT, SQUASH), found=(229,),
               failed=("could not ask GitHub which pull request merged bbbb2222",))
        monkeypatch.setattr(hook, "closing_issues", lambda pr: [(REPO, 227), (REPO, 228)])
        monkeypatch.setattr(hook, "rows", lambda *a, **k: [])
        monkeypatch.setattr(hook, "outstanding",
                            lambda a, b, repo, issue: f"  #{issue} needs finishing")
        code = hook.cmd_unfinished(args_for(hook))
        err = capsys.readouterr().err
        assert "#227 needs finishing" in err and "#228 needs finishing" in err
        assert "bbbb2222" in err
        assert code == 1

    def test_a_failed_closing_lookup_does_not_stop_the_next(self, hook, monkeypatch,
                                                            capsys):
        pulled(hook, monkeypatch, found=(228, 229))
        monkeypatch.setattr(hook, "closing_issues",
                            lambda pr: None if pr == 228 else [(REPO, 227)])
        monkeypatch.setattr(hook, "rows", lambda *a, **k: [])
        monkeypatch.setattr(hook, "outstanding",
                            lambda a, b, repo, issue: f"  #{issue} needs finishing")
        code = hook.cmd_unfinished(args_for(hook))
        err = capsys.readouterr().err
        assert "#227 needs finishing" in err
        assert "pull request #228" in err
        assert code == 1

    def test_only_failures_still_say_so(self, hook, monkeypatch, capsys):
        pulled(hook, monkeypatch, found=(),
               failed=("could not ask GitHub which pull request merged aaaa1111",))
        monkeypatch.setattr(hook, "rows", lambda *a, **k: pytest.fail(
            "the board was read although no issue was found"))
        assert hook.cmd_unfinished(args_for(hook, quiet=False)) == 1
        out = capsys.readouterr()
        assert "aaaa1111" in out.err and "waiting to be finished" not in out.out


class TestTheCostIsBounded:
    """One REST call per commit looked up. A pull bringing in more than the
    cap is refused whole: checking the first fifty would report the rest clean.
    """

    def test_the_log_is_first_parent_and_capped(self, hook, monkeypatch):
        asked = []
        monkeypatch.setattr(hook.subprocess, "run",
                            lambda cmd, **k: asked.append(cmd) or Stub(0, ""))
        hook.cmd_unfinished(args_for(hook))
        assert "--first-parent" in asked[0]
        assert f"--max-count={hook.UNFINISHED_COMMIT_CAP + 1}" in asked[0]

    def test_too_many_commits_checks_none_and_says_how(self, hook, monkeypatch, capsys):
        shas = [f"{n:08x}" for n in range(hook.UNFINISHED_COMMIT_CAP + 1)]
        monkeypatch.setattr(hook.subprocess, "run",
                            lambda cmd, **k: Stub(0, "".join(f"{sha}\n" for sha in shas)))
        monkeypatch.setattr(hook, "current_repo", lambda: REPO)
        monkeypatch.setattr(hook, "commit_pull_requests", lambda sha: pytest.fail(
            "GitHub was asked about part of a range too large to check"))
        assert hook.cmd_unfinished(args_for(hook)) == 1
        err = capsys.readouterr().err
        assert "none was checked" in err and "gh agile unfinished --range" in err

    def test_at_the_cap_it_checks(self, hook, monkeypatch):
        shas = [f"{n:08x}" for n in range(hook.UNFINISHED_COMMIT_CAP)]
        pulled(hook, monkeypatch, shas=shas, found=())
        assert hook.cmd_unfinished(args_for(hook)) == 0

    def test_a_repository_it_cannot_name_is_not_a_clean_merge(self, hook, monkeypatch,
                                                              capsys):
        pulled(hook, monkeypatch)
        monkeypatch.setattr(hook, "current_repo", lambda: None)
        assert hook.cmd_unfinished(args_for(hook)) == 1
        assert "which repository" in capsys.readouterr().err


LOCAL_MERGE, ORIG, UPSTREAM_MERGE, UPSTREAM_SQUASH, LOCAL_ONLY = (
    "1111aaaa", "2222bbbb", "3333cccc", "4444dddd", "5555eeee")


class TestALocalMergeCommit:
    """AGILE-233: a `git pull` that cannot fast-forward makes a merge commit
    GitHub has never seen, and the first-parent line of `ORIG_HEAD..HEAD` is
    that commit alone. The upstream pull requests are on its second parent.
    """

    @pytest.fixture
    def walk(self, hook, monkeypatch):
        """GitHub's answers by commit, and git's first-parent lines by start."""
        answers = {LOCAL_MERGE: hook.NOT_ON_GITHUB, LOCAL_ONLY: hook.NOT_ON_GITHUB,
                   UPSTREAM_MERGE: [(188, REPO)], UPSTREAM_SQUASH: [(189, REPO)]}
        lines = {UPSTREAM_MERGE: [(UPSTREAM_MERGE, ["9999", "8888"]),
                                  (UPSTREAM_SQUASH, ["9999"])],
                 LOCAL_ONLY: [(LOCAL_ONLY, [ORIG])]}
        followed, asked = [], []
        monkeypatch.setattr(hook, "commit_pull_requests",
                            lambda sha: asked.append(sha) or answers.get(sha, []))
        monkeypatch.setattr(hook, "first_parent_commits",
                            lambda *revs: followed.append(revs) or lines.get(revs[0]))
        return answers, lines, followed, asked

    def test_the_upstream_pull_requests_are_found(self, hook, walk):
        found, failed = hook.merged_pull_requests(
            [(LOCAL_MERGE, [ORIG, UPSTREAM_MERGE])], REPO, ["^" + ORIG])
        assert found == [188, 189] and failed == []

    def test_the_walk_stops_at_the_range_s_end(self, hook, walk):
        _answers, _lines, followed, _asked = walk
        hook.merged_pull_requests([(LOCAL_MERGE, [ORIG, UPSTREAM_MERGE])], REPO, ["^" + ORIG])
        assert followed == [(UPSTREAM_MERGE, "^" + ORIG)]

    def test_a_merge_github_knows_is_not_followed(self, hook, walk):
        """Its second parent is the pull request's own branch: nothing new."""
        _answers, _lines, followed, _asked = walk
        found, _failed = hook.merged_pull_requests(
            [(UPSTREAM_MERGE, ["9999", "8888"])], REPO, ["^" + ORIG])
        assert found == [188] and followed == []

    def test_a_merge_of_an_unpushed_branch_finds_nothing(self, hook, walk):
        found, failed = hook.merged_pull_requests(
            [(LOCAL_MERGE, [ORIG, LOCAL_ONLY])], REPO, ["^" + ORIG])
        assert (found, failed) == ([], [])

    def test_and_the_check_exits_zero(self, hook, walk, monkeypatch, capsys):
        monkeypatch.setattr(hook, "first_parent_commits", lambda *revs: (
            [(LOCAL_MERGE, [ORIG, LOCAL_ONLY])] if revs == ("ORIG_HEAD..HEAD",)
            else [(LOCAL_ONLY, [ORIG])]))
        monkeypatch.setattr(hook, "current_repo", lambda: REPO)
        monkeypatch.setattr(hook, "range_ends", lambda span: ["^" + ORIG])
        monkeypatch.setattr(hook, "rows", lambda *a, **k: pytest.fail(
            "the board was read although nothing was merged upstream"))
        assert hook.cmd_unfinished(args_for(hook)) == 0
        assert capsys.readouterr().err == ""

    def test_each_commit_is_looked_up_once(self, hook, walk):
        _answers, _lines, _followed, asked = walk
        hook.merged_pull_requests([(LOCAL_MERGE, [ORIG, UPSTREAM_MERGE]),
                                   (UPSTREAM_SQUASH, [])], REPO, ["^" + ORIG])
        assert sorted(asked) == sorted({LOCAL_MERGE, UPSTREAM_MERGE, UPSTREAM_SQUASH})

    def test_a_parent_it_cannot_follow_is_named_and_the_rest_go_on(self, hook, walk,
                                                                  monkeypatch):
        monkeypatch.setattr(hook, "first_parent_commits", lambda *revs: None)
        found, failed = hook.merged_pull_requests(
            [(LOCAL_MERGE, [ORIG, UPSTREAM_MERGE]), (UPSTREAM_SQUASH, [])], REPO)
        assert found == [189]
        assert len(failed) == 1 and LOCAL_MERGE[:8] in failed[0]

    def test_the_cap_counts_the_commits_it_walks_into(self, hook, walk, monkeypatch):
        many = [(f"{n:08x}", []) for n in range(hook.UNFINISHED_COMMIT_CAP)]
        monkeypatch.setattr(hook, "first_parent_commits", lambda *revs: many)
        with pytest.raises(hook.RangeTooLarge):
            hook.merged_pull_requests([(LOCAL_MERGE, [ORIG, UPSTREAM_MERGE])], REPO)


class TestAgainstRealGit:
    """The walk's two git questions, asked of a real repository holding the
    shape #233 is about: a pull that could not fast-forward."""

    @pytest.fixture
    def pulled_with_a_merge(self, tmp_path, monkeypatch):
        import subprocess

        def git(*args):
            return subprocess.run(["git", *args], cwd=tmp_path, check=True,
                                  capture_output=True, text=True).stdout.strip()
        git("init", "-q", "-b", "main")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        for name in ("base", "upstream-1", "upstream-2", "local"):
            if name == "upstream-1":
                git("checkout", "-q", "-b", "upstream", "main~0")
            if name == "local":
                git("checkout", "-q", "main")
            (tmp_path / name).write_text(name)
            git("add", name)
            git("commit", "-q", "-m", name)
        orig = git("rev-parse", "HEAD")
        git("merge", "-q", "--no-edit", "upstream")
        monkeypatch.chdir(tmp_path)
        return git, orig

    def test_the_first_parent_line_is_the_local_merge_alone(self, hook,
                                                             pulled_with_a_merge):
        git, orig = pulled_with_a_merge
        commits = hook.first_parent_commits(f"{orig}..HEAD")
        assert [sha for sha, _p in commits] == [git("rev-parse", "HEAD")]
        assert commits[0][1] == [orig, git("rev-parse", "upstream")]

    def test_its_second_parent_walks_to_the_upstream_commits_only(
            self, hook, pulled_with_a_merge):
        git, orig = pulled_with_a_merge
        ends = hook.range_ends(f"{orig}..HEAD")
        assert ends == ["^" + orig]
        line = hook.first_parent_commits(git("rev-parse", "upstream"), *ends)
        assert [sha for sha, _p in line] == [git("rev-parse", "upstream"),
                                             git("rev-parse", "upstream~1")]


class TestTheRangesEnds:
    def test_a_two_dot_range_excludes_its_start(self, hook, monkeypatch):
        monkeypatch.setattr(hook.subprocess, "run",
                            lambda cmd, **k: Stub(0, "bbbb\n^aaaa\n"))
        assert hook.range_ends("ORIG_HEAD..HEAD") == ["^aaaa"]

    def test_a_range_git_cannot_parse_has_none(self, hook, monkeypatch):
        monkeypatch.setattr(hook.subprocess, "run", lambda cmd, **k: Stub(128, ""))
        assert hook.range_ends("nope..HEAD") == []


class TestTheHookScriptItself:
    """The shell, which is where this bug lived and where no test looked."""

    def script(self, hook):
        return hook.POST_MERGE_HOOK

    def test_it_is_valid_shell(self, hook, tmp_path):
        import subprocess
        path = tmp_path / "post-merge"
        path.write_text(self.script(hook))
        assert subprocess.run(["sh", "-n", str(path)]).returncode == 0

    def test_it_says_the_check_did_not_happen(self, hook):
        assert "the post-merge check did not finish" in self.script(hook)

    def test_it_names_the_fix(self, hook):
        assert "gh extension upgrade agile" in self.script(hook)

    def test_it_says_how_to_stop(self, hook):
        """A message with no way out is one people silence by deleting the
        hook, which takes the working half with it."""
        assert "delete $0" in self.script(hook)

    def test_it_passes_the_underlying_message_through(self, hook):
        """The tool's own words are still worth showing; they are just not
        enough on their own."""
        assert '"$said"' in self.script(hook)

    def test_every_path_exits_zero(self, hook):
        lines = [line.strip() for line in self.script(hook).splitlines()
                 if line.strip().startswith("exit ")]
        assert lines and all(line == "exit 0" for line in lines)

    def test_the_escapes_survived_the_f_string(self, hook):
        r"""An ordinary f-string turns `\n` into a newline and `\` at a line end
        into nothing, which reflowed this script into one line the first time it
        was written. It is raw for that reason."""
        assert "printf '%s\\n'" in self.script(hook)
        assert self.script(hook).count("\\\n") >= 5

    def test_this_repositorys_template_says_the_same(self):
        """Two hook bodies exist and can drift; the sentence they share is the
        one a reader acts on."""
        template = (ROOT / "templates" / "post-merge").read_text()
        assert "the post-merge check did not finish" in template
        assert "gh extension upgrade agile" in template
