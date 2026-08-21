"""Permission failures must not be reported as success. docs/review-2026-08.md S1, S2.

Two grants, not one: creating an issue needs repository access, putting it on the
board needs project access, and creating a label needs *push* to the repository,
which project write does not include. An external contributor has the first and
not the others, so these are the ordinary paths for them rather than edge cases.

Both defects reported success for a failure:

  S1  `state = "created" if returncode == 0 else "already exists"` turned a 403
      into convergence, so `setup` printed a clean run having created nothing.
  S2  `epic` and `story` printed the issue number *after* the board write, so a
      refused board write exited without ever naming the issue that now existed.
"""

from __future__ import annotations

import subprocess

import pytest

EXISTS_STDERR = (
    'label with name "type:epic" already exists; '
    "use `--force` to update its color and description"
)
FORBIDDEN_STDERR = "HTTP 403: Resource not accessible by integration"


def fake_run(returncode: int, stderr: str = ""):
    """A `subprocess.run` that reports one fixed outcome."""
    def run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], returncode, stdout="", stderr=stderr)
    return run


@pytest.fixture(autouse=True)
def clean_label_cache(tool):
    """The confirmed-labels set is module state; each test starts empty."""
    tool._LABELS_PRESENT.clear()
    yield
    tool._LABELS_PRESENT.clear()


class TestCreateLabel:
    def test_a_new_label_reports_created(self, tool, monkeypatch):
        monkeypatch.setattr(subprocess, "run", fake_run(0))
        assert tool.create_label("o/r", "type:epic") == "created"

    def test_an_existing_label_reports_exists(self, tool, monkeypatch):
        monkeypatch.setattr(subprocess, "run", fake_run(1, EXISTS_STDERR))
        assert tool.create_label("o/r", "type:epic") == "exists"

    def test_a_permission_failure_is_not_reported_as_exists(self, tool, monkeypatch):
        """The S1 defect: this used to return "already exists" and print success."""
        monkeypatch.setattr(subprocess, "run", fake_run(1, FORBIDDEN_STDERR))
        with pytest.raises(SystemExit) as exit_info:
            tool.create_label("o/r", "type:epic")
        message = str(exit_info.value)
        assert "could not create label" in message
        assert "403" in message                    # the reason is kept, not swallowed
        assert "push access" in message            # and named
        assert "viewerPermission" in message       # with a way to check

    def test_a_rate_limit_is_not_reported_as_a_permission_problem(self, tool, monkeypatch):
        """Both wear a 403, and the first version of this message guessed wrong.

        Met for real on 2026-08-21: three self-test runs exhausted the REST
        budget, and the message confidently blamed push access.
        """
        limit = ("HTTP 403: API rate limit exceeded for user ID 1. "
                 "(https://api.github.com/repos/o/r/labels)")
        monkeypatch.setattr(subprocess, "run", fake_run(1, limit))
        with pytest.raises(SystemExit) as exit_info:
            tool.create_label("o/r", "type:epic")
        message = str(exit_info.value)
        assert "rate limit is exhausted" in message
        assert "gh api rate_limit" in message
        assert "push access" not in message    # the wrong cause must not be asserted

    def test_ensure_labels_propagates_the_failure(self, tool, monkeypatch):
        """It used to discard the result entirely and check nothing."""
        monkeypatch.setattr(subprocess, "run", fake_run(1, FORBIDDEN_STDERR))
        with pytest.raises(SystemExit):
            tool.ensure_labels("o/r", ["key:AGILE"])

    def test_a_confirmed_label_is_not_re_attempted(self, tool, monkeypatch):
        """`sync --adopt` applies one key: label per issue; the call is made once."""
        calls = []

        def counting(*args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess([], 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", counting)
        for _ in range(5):
            tool.ensure_labels("o/r", ["key:AGILE"])
        assert len(calls) == 1

    def test_a_failed_label_is_not_cached_as_present(self, tool, monkeypatch):
        """Caching a label we could not create would hide the failure on the retry."""
        monkeypatch.setattr(subprocess, "run", fake_run(1, FORBIDDEN_STDERR))
        with pytest.raises(SystemExit):
            tool.create_label("o/r", "type:epic")
        assert ("o/r", "type:epic") not in tool._LABELS_PRESENT

    def test_labels_are_cached_per_repository(self, tool, monkeypatch):
        calls = []

        def counting(*args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess([], 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", counting)
        tool.ensure_labels("o/a", ["key:X"])
        tool.ensure_labels("o/b", ["key:X"])
        assert len(calls) == 2


class TestBoardWriteReported:
    def test_a_refused_board_write_names_the_issue_that_exists(self, tool):
        """The S2 defect: the number and URL were printed after this point, so never."""
        with (pytest.raises(SystemExit) as exit_info,
              tool.board_write_reported(41, "https://github.com/o/r/issues/41", 4)):
            raise SystemExit("gh project item-add failed: HTTP 403")
        message = str(exit_info.value)
        assert "#41 was created" in message
        assert "https://github.com/o/r/issues/41" in message
        assert "project #4" in message
        assert "403" in message                  # the underlying reason survives
        assert "sync --adopt" in message          # and the recovery is named

    def test_success_passes_through_silently(self, tool):
        with tool.board_write_reported(41, "u", 4):
            pass

    def test_it_does_not_swallow_other_exceptions(self, tool):
        """Only SystemExit means "a gh call failed"; a bug should still surface."""
        with pytest.raises(KeyError), tool.board_write_reported(41, "u", 4):
            raise KeyError("a real bug")
