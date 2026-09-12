"""Which repositories `sync` looks at, and why the default is all of them.

**A board may span repositories, and that is the feature.** A team responsible
for several repositories sees and manages all of their issues on one scrum board
and one kanban board. `keys` is an ordered *list* for exactly that, `issue_key`
puts the key on the repository rather than the project because a project can
span them, and a scrum board slices one team's work out of the shared board with
`label:key:...`.

`sync` is the only way an issue arrives on a board at all -- a project is a
collection, not a filter -- so when `apply_defaults` filled `--repo` from the
working directory, the documented default of *every repository in the profile*
became unreachable and a shared board could never be filled. The summary line
said `across 1 repo(s)` on a profile listing two, which is what gave it away.

Every *other* command here acts on one issue in one repository, so the clone you
are standing in is the right guess for those and must stay.
"""

from __future__ import annotations

import pytest

PROFILE = {
    "project": {"number": 4, "owner": "o", "key": "AGILE"},
    "keys": [
        {"key": "AGILE", "repo": "o/gh-agile"},
        {"key": "ZMBNI", "repo": "o/zamboni"},
    ],
}


@pytest.fixture
def defaults(monkeypatch, tool):
    """`apply_defaults` with the profile and the working directory stubbed."""
    def go(command, *, repo=None, key=None, cwd_repo="o/gh-agile", config=None):
        import argparse
        monkeypatch.setattr(tool, "read_config", lambda *a, **k: config or PROFILE)
        monkeypatch.setattr(tool, "current_repo", lambda: cwd_repo)
        monkeypatch.setattr(tool, "resolve_owner", lambda args, cfg: None)
        args = argparse.Namespace(command=command, project=4, owner="o",
                                  repo=repo, key=key)
        tool.apply_defaults(args)
        return args
    return go


class TestSyncDefaultsToEveryRepository:
    def test_no_flag_leaves_the_repository_unset(self, tool, defaults):
        """Unset is what `cmd_sync` reads as "sweep the profile". Filling it from
        the working directory is what made the documented default unreachable."""
        assert defaults("sync").repo is None

    def test_an_explicit_repo_still_narrows(self, tool, defaults):
        assert defaults("sync", repo="o/zamboni").repo == "o/zamboni"

    def test_a_key_still_resolves_to_its_repository(self, tool, defaults):
        """`--key ZMBNI` names a repository on its own, and that is more explicit
        than the clone you happen to be standing in."""
        assert defaults("sync", key="ZMBNI").repo == "o/zamboni"

    def test_it_does_not_need_to_be_run_inside_a_clone(self, tool, defaults):
        """Filling a shared board is not a thing you do from one of its
        repositories in particular."""
        assert defaults("sync", cwd_repo=None).repo is None


class TestEveryOtherCommandKeepsItsWorkingDirectoryDefault:
    @pytest.mark.parametrize("command", ["epic", "story", "set", "move", "fix", "project"])
    def test_the_clone_is_the_right_guess(self, tool, defaults, command):
        assert defaults(command).repo == "o/gh-agile"

    @pytest.mark.parametrize("command", ["set", "move", "fix"])
    def test_and_outside_a_clone_they_still_refuse(self, tool, defaults, command):
        with pytest.raises(SystemExit) as exit_info:
            defaults(command, cwd_repo=None)
        assert "not inside a GitHub repository" in str(exit_info.value)


class TestTheSweep:
    @pytest.fixture
    def sync(self, monkeypatch, tool, capsys):
        """`cmd_sync` with the board empty and every repository holding one issue."""
        def go(repo=None, config=None):
            import argparse
            import json as _json
            listed = {
                "o/gh-agile": [{"number": 1, "title": "an AGILE issue", "url": "u",
                                "state": "OPEN", "labels": []}],
                "o/zamboni": [{"number": 2, "title": "a ZMBNI issue", "url": "u",
                               "state": "OPEN", "labels": []}],
            }

            def fake_gh(args, **kwargs):
                if args[:2] == ["issue", "list"]:
                    return _json.dumps(listed.get(args[args.index("--repo") + 1], []))
                return "[]"

            monkeypatch.setattr(tool, "gh", fake_gh)
            monkeypatch.setattr(tool, "board_items", lambda *a, **k: [])
            args = argparse.Namespace(
                owner="o", project=4, repo=repo, state="open", query=None,
                limit=200, dry_run=True, adopt=False, _config=config or PROFILE)
            tool.cmd_sync(args)
            return capsys.readouterr().out
        return go

    def test_an_unset_repo_sweeps_every_repository_in_the_profile(self, tool, sync):
        out = sync(repo=None)
        assert "o/gh-agile#1" in out and "o/zamboni#2" in out
        assert "across 2 repo(s)" in out

    def test_an_explicit_repo_sweeps_only_that_one(self, tool, sync):
        out = sync(repo="o/zamboni")
        assert "o/zamboni#2" in out and "o/gh-agile#1" not in out
        assert "across 1 repo(s)" in out

    def test_a_repository_listed_twice_is_swept_once(self, tool, sync):
        """A mono-repo carries several keys against one repository."""
        config = dict(PROFILE, keys=[{"key": "A", "repo": "o/gh-agile"},
                                     {"key": "B", "repo": "o/gh-agile"}])
        assert "across 1 repo(s)" in sync(repo=None, config=config)
