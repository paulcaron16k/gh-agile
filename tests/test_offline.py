"""The offline suite refuses the network by default. AGILE-242.

`make test` was documented as offline and nothing enforced it: a `no_network`
fixture existed and no test used it. When #231 changed `board_item_for`, four
tests that stubbed only the board read ran real `gh api graphql` calls. These
tests hold the guard in `conftest.py` -- `offline` -- to what it promises.
"""

from __future__ import annotations

import pathlib
import socket
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestNothingRunsUnasked:
    def test_gh_is_refused(self):
        with pytest.raises(AssertionError, match="tried to run 'gh api user'"):
            subprocess.run(["gh", "api", "user"], capture_output=True)

    def test_the_tools_own_graphql_is_refused(self, tool):
        """The route #231's tests took."""
        with pytest.raises(AssertionError, match="gh api graphql"):
            tool.graphql("{ viewer { login } }")

    def test_the_tools_gh_is_refused(self, tool):
        with pytest.raises(AssertionError, match="gh issue view"):
            tool.gh(["issue", "view", "1"])

    def test_any_other_api_into_subprocess_is_refused(self):
        """`Popen` is the choke point, so `check_output` cannot slip past."""
        with pytest.raises(AssertionError, match="tried to run"):
            subprocess.check_output(["gh", "--version"])

    def test_a_local_program_is_refused_too_unless_named(self):
        """Deny by default: what a test runs is something it says."""
        with pytest.raises(AssertionError, match=r"runs\('git'\)"):
            subprocess.run(["git", "--version"], capture_output=True)

    def test_the_refusal_says_how_to_opt_in(self):
        with pytest.raises(AssertionError, match=r"Stub it, or mark the test"):
            subprocess.run(["jq", "."], capture_output=True)

    def test_a_program_named_by_path_is_still_that_program(self):
        with pytest.raises(AssertionError, match="tried to run"):
            subprocess.run(["/usr/local/bin/gh", "api", "user"], capture_output=True)

    def test_an_internet_socket_is_refused(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(AssertionError, match="open a connection"):
                sock.connect(("140.82.112.6", 443))
        finally:
            sock.close()


class TestOptingIn:
    @pytest.mark.runs("git")
    def test_a_named_program_runs(self):
        assert subprocess.run(["git", "--version"], capture_output=True).returncode == 0

    @pytest.mark.runs("git")
    def test_and_nothing_else_does(self):
        with pytest.raises(AssertionError, match="tried to run"):
            subprocess.run(["gh", "--version"], capture_output=True)

    @pytest.mark.runs("git")
    @pytest.mark.parametrize("sub", ["fetch", "pull", "push", "clone", "ls-remote", "remote"])
    def test_gits_network_subcommands_stay_refused(self, sub):
        with pytest.raises(AssertionError, match="reach a remote"):
            subprocess.run(["git", sub], capture_output=True)


class TestThereIsOneMechanism:
    def test_the_opt_in_fixture_nobody_used_is_gone(self):
        """Two mechanisms is how the unused one lingered for months."""
        assert "def no_network" not in (ROOT / "tests" / "conftest.py").read_text()

    def test_the_guard_is_autouse(self):
        text = (ROOT / "tests" / "conftest.py").read_text()
        guard = text.split("def offline(")[0].rsplit("@pytest.fixture", 1)[1]
        assert "autouse=True" in guard
