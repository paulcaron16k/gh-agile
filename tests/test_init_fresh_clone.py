"""`init --key` on a fresh clone, and `--config` naming a profile not yet written. #313.

`init` is the command for a clone with no profile, and it failed there:

    $ gh agile init --key MAPC --title map-conform --sprint-template 2-week
    no repository for key 'MAPC' in the profile

`apply_defaults` resolves `--repo` before any command runs, and with `--key`
given and `--repo` not, it asked the profile which repository the key belongs
to. `init` is what *writes* that, so the profile could not know. Only `key` was
exempt; `init` declares a key the same way, so it is exempt too.

The sibling: `key add KEY --config PATH` with nothing at PATH raised a bare
`FileNotFoundError`, because `read_config` read the explicit path before the
command that would create it ran.
"""

from __future__ import annotations

import json

import pytest

CLONE = "o/new"


@pytest.fixture
def defaults(monkeypatch, tool, tmp_path):
    """`apply_defaults` on a real command line, run in an empty directory, with
    the clone's repository and the owner lookup stubbed."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tool, "resolve_owner", lambda args, cfg: None)
    monkeypatch.setattr(tool, "current_repo", lambda: CLONE)

    def go(*argv, config=None):
        if config is not None:
            monkeypatch.setattr(tool, "read_config", lambda *a, **k: config)
        args = tool.build_parser().parse_args(list(argv))
        tool.apply_defaults(args)
        return args
    return go


INIT = ("init", "--key", "MAPC", "-t", "map-conform", "--sprint-template", "2-week")


class TestInitDeclaresItsKey:
    def test_a_fresh_clone_resolves_to_the_clone(self, defaults):
        """The reported case: no profile anywhere, `--key`, no `-R`."""
        assert defaults(*INIT).repo == CLONE

    def test_a_key_recorded_elsewhere_does_not_redirect_init(self, defaults):
        """`init` sets up the clone it is run in. A profile naming the key for
        another repository must not send it there."""
        config = {"keys": [{"key": "MAPC", "repo": "o/elsewhere"}]}
        assert defaults(*INIT, config=config).repo == CLONE

    def test_an_explicit_repo_still_wins(self, defaults):
        assert defaults(*INIT, "-R", "o/named").repo == "o/named"

    def test_other_commands_still_look_the_key_up(self, defaults):
        """The exemption is for commands that declare a key. One that files work
        under a key still refuses a key the profile does not know, rather than
        filing it in whatever clone it happens to be run from."""
        with pytest.raises(SystemExit, match="no repository for key 'MAPC'"):
            defaults("epic", "create", "-t", "x", "--key", "MAPC", "--project", "4")


class TestAnExplicitConfigNotYetWritten:
    def test_read_config_is_empty_not_an_exception(self, tool, tmp_path):
        assert tool.read_config(str(tmp_path / ".github" / "agile.json")) == {}

    def test_key_add_creates_the_file(self, tool, defaults, tmp_path):
        target = tmp_path / ".github" / "agile.json"
        args = defaults("key", "add", "MAPC", "-R", CLONE, "--name", "Map conform",
                        "--config", str(target))
        assert args.func(args) == 0
        written = json.loads(target.read_text())
        assert written["keys"] == [{"key": "MAPC", "name": "Map conform", "repo": CLONE}]

    def test_a_command_needing_a_project_names_the_missing_path(self, defaults, tmp_path):
        """A typo in `--config` is reported as that path, not as a profile with no
        project number -- which would describe a file that is not there."""
        missing = tmp_path / "nope.json"
        with pytest.raises(SystemExit) as exc:
            defaults("validate", "--config", str(missing))
        message = str(exc.value)
        assert f"no profile at {missing}" in message
        assert "names no project.number" not in message
