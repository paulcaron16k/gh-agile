"""Following a `config_from` pointer, and saying why when it cannot be followed.

docs/review-2026-08.md S4. One message used to cover two very different
situations: "points at X, which has no profile". **GitHub answers an unauthorised
read with 404 rather than 403, deliberately, so a private repository's existence
is not leaked** -- so a contributor with no access to the main repository was told
with confidence that the profile was not there when it was, and sent off to write
a second one. A profile that disagrees with the main one is worse than none.

The review proposed inspecting the HTTP status. That does not work: measured
2026-08-23, a repository that does not exist and one this account cannot see both
return byte-identical `404 Not Found`. GitHub has already made them the same.

What can be distinguished is whether the *repository* is readable, which is the
actionable difference -- a readable repository with no profile is a configuration
mistake, an unreadable one is an access problem.
"""

from __future__ import annotations

import subprocess

import pytest

NOT_FOUND = "gh: Not Found (HTTP 404)"


@pytest.fixture
def probe(monkeypatch, tool):
    """Control the `gh api repos/<pointer>` readability probe."""
    def install(returncode: int, stderr: str = ""):
        calls = []

        def run(cmd, **_kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, returncode, stdout="o/main\n",
                                               stderr=stderr)

        monkeypatch.setattr(subprocess, "run", run)
        return calls
    return install


class TestConfigFromProblem:
    def test_a_readable_repository_with_no_profile_says_so(self, tool, probe):
        probe(0)
        message = tool.config_from_problem("here/agile.json", "o/main")
        assert "readable and carries no profile" in message
        assert "Add one there" in message

    def test_an_unreadable_repository_does_not_claim_the_profile_is_missing(self, tool, probe):
        """The S4 defect: this case used to produce "which has no profile"."""
        probe(1, NOT_FOUND)
        message = tool.config_from_problem("here/agile.json", "o/main")
        assert "cannot be read" in message
        assert "no profile at any of" not in message

    def test_it_refuses_to_guess_between_absent_and_forbidden(self, tool, probe):
        """Both are 404 by design, so the message must not pick one."""
        probe(1, NOT_FOUND)
        message = tool.config_from_problem("here/agile.json", "o/main")
        assert "does not exist or one this account cannot see" in message
        assert "404" in message

    def test_the_reason_from_gh_is_kept(self, tool, probe):
        probe(1, NOT_FOUND)
        assert NOT_FOUND in tool.config_from_problem("here/agile.json", "o/main")

    def test_it_says_not_to_write_a_second_profile(self, tool, probe):
        """The wrong recovery, and the one the old message actively invited."""
        probe(1, NOT_FOUND)
        message = tool.config_from_problem("here/agile.json", "o/main")
        assert "Do not write a second profile" in message

    def test_it_suggests_checking_the_account(self, tool, probe):
        probe(1, NOT_FOUND)
        assert "gh auth status" in tool.config_from_problem("here/agile.json", "o/main")

    def test_the_probe_asks_about_the_repository_itself(self, tool, probe):
        """Not about a path inside it -- the file's 404 is what we already have."""
        calls = probe(0)
        tool.config_from_problem("here/agile.json", "o/main")
        assert calls, "the repository was never probed"
        assert "repos/o/main" in calls[0]
        assert not any("contents" in part for part in calls[0])
