"""The post-merge hook lands where git runs it, worktree or not. AGILE-223.

`install_hook` took its directory from `git rev-parse --git-dir`, which in a
linked worktree is `.git/worktrees/<name>`. Git reads hooks from
`$GIT_COMMON_DIR/hooks` -- what `git rev-parse --git-path hooks` names -- so a
hook installed from a worktree was never run, under a message saying it would
be. Measured on Zamboni with git 2.34.1. Worktrees are routine where agent
sessions work, one per story.

These run **real git** in a temporary directory: the defect was a wrong belief
about where git looks, and a stub encodes the belief rather than testing it.
Offline -- nothing here has a remote.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

#: Every test here builds and asks a real repository, which is the point: the
#: bug was in what git answers from a worktree. Local only (#242).
pytestmark = [pytest.mark.skipif(shutil.which("git") is None, reason="needs git"),
              pytest.mark.runs("git")]


def git(cwd, *argv) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *argv], cwd=cwd, check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


@pytest.fixture
def clone(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q")
    git(main, "commit", "-q", "--allow-empty", "-m", "first")
    return main


@pytest.fixture
def worktree(clone, tmp_path):
    path = tmp_path / "wt"
    git(clone, "worktree", "add", "-q", str(path))
    return path


def where_git_runs_hooks(cwd):
    return (cwd / git(cwd, "rev-parse", "--git-path", "hooks")).resolve() / "post-merge"


def install_from(tool, monkeypatch, cwd):
    monkeypatch.chdir(cwd)
    return tool.install_hook()


class TestFromALinkedWorktree:
    def test_it_lands_where_git_runs_hooks(self, tool, monkeypatch, worktree, clone):
        install_from(tool, monkeypatch, worktree)
        hook = where_git_runs_hooks(worktree)
        assert hook.read_text() == tool.POST_MERGE_HOOK
        assert hook == (clone / ".git" / "hooks" / "post-merge").resolve()

    def test_not_in_the_worktrees_private_git_dir(self, tool, monkeypatch, worktree, clone):
        install_from(tool, monkeypatch, worktree)
        assert not list((clone / ".git" / "worktrees").rglob("post-merge"))

    def test_it_says_the_path_it_wrote_and_that_every_worktree_runs_it(
            self, tool, monkeypatch, worktree):
        said = install_from(tool, monkeypatch, worktree)
        assert str(where_git_runs_hooks(worktree)) in said
        assert "every worktree" in said

    def test_a_second_run_from_the_worktree_finds_it_present(self, tool, monkeypatch, worktree):
        install_from(tool, monkeypatch, worktree)
        assert install_from(tool, monkeypatch, worktree).startswith("present")

    def test_somebody_elses_hook_there_is_still_not_replaced(
            self, tool, monkeypatch, worktree):
        hook = where_git_runs_hooks(worktree)
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\n# another tool's marker\necho mine\n")
        said = install_from(tool, monkeypatch, worktree)
        assert "not mine to replace" in said
        assert hook.read_text() == "#!/bin/sh\n# another tool's marker\necho mine\n"


class TestFromTheMainClone:
    def test_it_lands_in_dot_git_hooks(self, tool, monkeypatch, clone):
        said = install_from(tool, monkeypatch, clone)
        assert (clone / ".git" / "hooks" / "post-merge").read_text() == tool.POST_MERGE_HOOK
        assert "every worktree" not in said

    def test_from_a_subdirectory_too(self, tool, monkeypatch, clone):
        sub = clone / "a" / "b"
        sub.mkdir(parents=True)
        install_from(tool, monkeypatch, sub)
        assert (clone / ".git" / "hooks" / "post-merge").exists()


class TestCoreHooksPath:
    def test_a_relative_hooks_path_is_honoured(self, tool, monkeypatch, clone):
        git(clone, "config", "core.hooksPath", ".githooks")
        sub = clone / "deep"
        sub.mkdir()
        install_from(tool, monkeypatch, sub)
        assert (clone / ".githooks" / "post-merge").read_text() == tool.POST_MERGE_HOOK
        assert not (clone / ".git" / "hooks" / "post-merge").exists()

    def test_and_from_a_worktree(self, tool, monkeypatch, clone, worktree):
        git(clone, "config", "core.hooksPath", str(clone / "shared-hooks"))
        install_from(tool, monkeypatch, worktree)
        assert (clone / "shared-hooks" / "post-merge").exists()


class TestOutsideARepository:
    def test_it_says_so(self, tool, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
        assert "not inside a git repository" in tool.install_hook()
