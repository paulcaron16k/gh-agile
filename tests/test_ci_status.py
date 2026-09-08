"""`scripts/ci_status.py`: does the default branch's last run say the build is broken?

CI already caught the failure this exists for. **Nobody was told.** Two pull
requests, each green on its own branch, left `main` red on the merge; the
`push: branches: [main]` run fired and failed at `ebd4b4d`, and `main` then sat
red while the next branch was cut from it, a pull request was opened, reviewed
and merged.

These tests are offline: `runs()` is stubbed, so nothing shells out to `gh`.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def ci():
    spec = importlib.util.spec_from_file_location("ci_status", ROOT / "scripts" / "ci_status.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(conclusion, status="completed", sha="abc1234def", title="a merge"):
    return {"conclusion": conclusion, "status": status, "headSha": sha,
            "displayTitle": title, "workflowName": "CI", "url": "https://example/run",
            "createdAt": "2026-09-07T00:00:00Z"}


class TestNewestDecided:
    def test_the_newest_run_with_a_verdict(self, ci):
        entries = [run("success", sha="newest"), run("failure", sha="older")]
        assert ci.newest_decided(entries)["headSha"] == "newest"

    def test_a_run_still_going_is_skipped(self, ci):
        """In flight says nothing about the branch yet."""
        entries = [run(None, status="in_progress", sha="running"), run("failure", sha="done")]
        assert ci.newest_decided(entries)["headSha"] == "done"

    def test_a_cancelled_run_is_skipped(self, ci):
        """It says only that somebody stopped it."""
        entries = [run("cancelled", sha="stopped"), run("success", sha="green")]
        assert ci.newest_decided(entries)["headSha"] == "green"

    @pytest.mark.parametrize("conclusion",
                             ["failure", "startup_failure", "timed_out", "action_required"])
    def test_every_kind_of_not_passing_counts(self, ci, conclusion):
        """A build that never started is as broken as one that failed."""
        assert ci.newest_decided([run(conclusion)])["conclusion"] == conclusion

    def test_nothing_decided_is_none(self, ci):
        assert ci.newest_decided([run(None, status="queued")]) is None

    def test_no_runs_at_all_is_none(self, ci):
        assert ci.newest_decided([]) is None


class TestTheVerdict:
    @pytest.fixture
    def verdict(self, ci, monkeypatch, capsys):
        def go(*entries, argv=()):
            monkeypatch.setattr(ci, "runs", lambda branch, limit: list(entries))
            monkeypatch.setattr(ci.sys, "argv", ["ci_status", *argv])
            code = ci.main()
            return code, capsys.readouterr()
        return go

    def test_green_exits_zero(self, ci, verdict):
        code, out = verdict(run("success"))
        assert code == 0 and "is green" in out.out

    def test_red_exits_one(self, ci, verdict):
        code, _ = verdict(run("failure"))
        assert code == 1

    def test_red_says_so_on_stderr(self, ci, verdict):
        """Loud, and not on stdout: the whole defect was a failure that scrolled
        past in a stream nobody reads to the end."""
        _, out = verdict(run("failure", sha="ebd4b4d0", title="Merge pull request #67"))
        assert "RED" in out.err
        assert "ebd4b4d" in out.err and "#67" in out.err
        assert "https://example/run" in out.err
        assert out.out == ""

    def test_quiet_says_nothing_when_green(self, ci, verdict):
        """For the git hook: a check that chatters on every pull gets ignored,
        and then so does the one message that mattered."""
        code, out = verdict(run("success"), argv=["--quiet"])
        assert code == 0 and out.out == "" and out.err == ""

    def test_quiet_still_shouts_when_red(self, ci, verdict):
        code, out = verdict(run("failure"), argv=["--quiet"])
        assert code == 1 and "RED" in out.err

    def test_no_finished_run_is_not_a_failure(self, ci, verdict):
        """A branch nothing has built yet is not a broken branch."""
        code, _ = verdict(run(None, status="queued"))
        assert code == 0
