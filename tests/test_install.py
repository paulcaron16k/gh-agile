"""gh-agile from PyPI: `gh-agile install`, the running version, and the file it ships. #316.

`pip install gh-agile` puts `gh-agile` on PATH, and `gh` does not look there --
it runs only what is in its own extensions directory. `gh-agile install` links
the installed script in as a *local* extension, the mechanism `gh extension
install .` uses for a checkout.

Three things measured while building it, each held here:

- **A pip-installed copy has no checkout**, so `git describe` beside it answers
  nothing -- or, in a project's `.venv`, answers with *that project's* version.
  The version comes from the package's own metadata instead, and only when the
  metadata's script is this file.
- **An installer can put code before the first line of the script.** When the
  interpreter's path is too long for a shebang, pip and uv write a `/bin/sh`
  trampoline: `'''exec' python "$0" "$@"` and then the file. A `from __future__`
  import is then no longer first, and the tool died with a SyntaxError for
  anyone whose environment path is long.
- **A local `gh` extension needs no git repository**: a directory named
  `gh-agile` holding an executable of the same name is enough, and `gh extension
  list` shows it with an empty repository column.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "gh-agile").read_text()


class TestTheShippedFileSurvivesAnInstaller:
    def test_no_future_import(self):
        """The file itself, not a test module: tests run under pytest and never
        meet a trampoline."""
        assert not re.search(r"^from __future__ import", SOURCE, re.MULTILINE)

    def test_it_compiles_behind_the_trampoline(self):
        """What pip and uv write when the interpreter's path is too long."""
        trampoline = "#!/bin/sh\n'''exec' '/a/very/long/path/bin/python' \"$0\" \"$@\"\n' '''\n"
        compile(trampoline + SOURCE.split("\n", 1)[1], "gh-agile", "exec")


class TestTheRunningVersion:
    def test_a_checkout_answers_with_git(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "is_checkout", lambda *a: True)
        monkeypatch.setattr(tool, "checkout_version", lambda *a: ("v0.5.0-3-gabc", "main"))
        assert tool.running_version() == ("v0.5.0-3-gabc", "main")

    def test_a_package_answers_with_its_metadata(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "is_checkout", lambda *a: False)
        monkeypatch.setattr(tool, "installed_version", lambda: "0.6.0")
        assert tool.running_version() == ("0.6.0", "package")

    def test_neither_is_unknown_and_git_is_not_asked(self, tool, monkeypatch):
        """Outside its own checkout, `git describe` would describe whatever
        repository contains the file -- a project's `.venv`, typically."""
        monkeypatch.setattr(tool, "is_checkout", lambda *a: False)
        monkeypatch.setattr(tool, "installed_version", lambda: None)
        monkeypatch.setattr(tool, "checkout_version",
                            lambda *a: pytest.fail("asked git outside a checkout"))
        assert tool.running_version() == ("unknown", "")

    def test_a_checkout_is_git_beside_the_file(self, tool, tmp_path):
        assert not tool.is_checkout(tmp_path)
        (tmp_path / ".git").write_text("gitdir: elsewhere\n")      # a worktree
        assert tool.is_checkout(tmp_path)


class Dist:
    """An `importlib.metadata.Distribution`, trimmed to what is read."""

    def __init__(self, script: pathlib.Path, version="0.6.0"):
        self.version, self._script = version, script
        self.files = [pathlib.PurePosixPath("gh_agile-0.6.0.dist-info/METADATA"),
                      pathlib.PurePosixPath("../../bin/gh-agile")]

    def locate_file(self, entry):
        return self._script if entry.name == "gh-agile" else pathlib.Path("/nowhere")


class TestInstalledVersion:
    @pytest.fixture
    def metadata(self, monkeypatch):
        import importlib.metadata

        def install(dist):
            def distribution(name):
                if dist is None:
                    raise importlib.metadata.PackageNotFoundError(name)
                return dist
            monkeypatch.setattr(importlib.metadata, "distribution", distribution)
        return install

    def test_the_package_whose_script_this_is(self, tool, metadata):
        metadata(Dist(pathlib.Path(tool.__file__).resolve()))
        assert tool.installed_version() == "0.6.0"

    def test_another_install_is_not_this_copy(self, tool, metadata, tmp_path):
        metadata(Dist(tmp_path / "gh-agile"))
        assert tool.installed_version() is None

    def test_not_installed(self, tool, metadata):
        metadata(None)
        assert tool.installed_version() is None


class Done:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


@pytest.fixture
def install(tool, monkeypatch, tmp_path):
    """`cmd_install` with `gh` stubbed and both data directories in tmp_path.

    Returns a runner taking what `gh extension list` prints, and the calls
    made to `gh`."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("GH_DATA_DIR", raising=False)
    monkeypatch.setattr(tool, "is_checkout", lambda *a: False)
    monkeypatch.setattr(tool.os, "name", "posix")
    calls = []

    def go(listed=""):
        def run(command, **kwargs):
            calls.append((command, kwargs.get("cwd")))
            if command[:3] == ["gh", "extension", "list"]:
                return Done(0, listed)
            if command[:3] == ["gh", "extension", "install"]:
                return Done(0)
            raise AssertionError(command)
        monkeypatch.setattr(tool.subprocess, "run", run)
        return tool.cmd_install(tool.build_parser().parse_args(["install"]))
    go.calls = calls
    return go


class TestInstall:
    def test_it_links_this_file_and_installs_the_link(self, tool, install, tmp_path, capsys):
        assert install() == 0
        link = tmp_path / "data" / "gh-agile-package" / "gh-agile" / "gh-agile"
        assert link.is_symlink()
        assert link.resolve() == pathlib.Path(tool.__file__).resolve()
        assert (["gh", "extension", "install", "."], link.parent) in install.calls
        assert "To undo: gh extension remove agile" in capsys.readouterr().out

    def test_run_again_it_refreshes_its_own_link(self, tool, install, tmp_path, capsys):
        folder = tmp_path / "data" / "gh-agile-package" / "gh-agile"
        folder.mkdir(parents=True)
        (folder / "gh-agile").symlink_to(tmp_path / "an-older-copy")
        entry = tmp_path / "data" / "gh" / "extensions" / "gh-agile"
        entry.parent.mkdir(parents=True)
        entry.symlink_to(folder)
        assert install(listed="gh agile\t\t\n") == 0
        assert (folder / "gh-agile").resolve() == pathlib.Path(tool.__file__).resolve()
        assert not any(c[0][:3] == ["gh", "extension", "install"] for c in install.calls)
        assert "already installed" in capsys.readouterr().out

    def test_a_clone_is_not_replaced(self, install, tmp_path):
        with pytest.raises(SystemExit, match="installed from paulcaron16k/gh-agile"):
            install(listed="gh agile\tpaulcaron16k/gh-agile\taf1cdba4\n")
        assert not (tmp_path / "data" / "gh-agile-package").exists()

    def test_somebody_elses_local_link_is_not_replaced(self, install, tmp_path):
        """A developer's `gh extension install .` from their checkout also has
        an empty repository column; it is theirs."""
        entry = tmp_path / "data" / "gh" / "extensions" / "gh-agile"
        entry.parent.mkdir(parents=True)
        entry.symlink_to(tmp_path)
        with pytest.raises(SystemExit, match="linked to"):
            install(listed="gh agile\t\t\n")

    def test_a_checkout_is_sent_to_gh(self, tool, install, monkeypatch):
        monkeypatch.setattr(tool, "is_checkout", lambda *a: True)
        with pytest.raises(SystemExit, match="gh extension install paulcaron16k/gh-agile"):
            install()
        assert not install.calls

    def test_gh_data_dir_is_where_gh_looks_first(self, tool, monkeypatch, tmp_path):
        monkeypatch.setenv("GH_DATA_DIR", str(tmp_path / "ghdata"))
        assert tool.gh_extension_entry() == tmp_path / "ghdata" / "extensions" / "gh-agile"

    def test_it_needs_no_project_or_profile(self, tool):
        assert tool.build_parser().parse_args(["install"]).projectless is True


@pytest.fixture(scope="module")
def pyproject():
    """`tomllib` is 3.11+, and the suite runs on the 3.10 floor too; the newer
    jobs hold the file, which is the same file on every interpreter."""
    tomllib = pytest.importorskip("tomllib")
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


@pytest.fixture(scope="module")
def project(pyproject):
    return pyproject["project"]


class TestThePackage:
    """`pyproject.toml` describes the file the extension already is."""

    def test_no_dependencies(self, project):
        assert project["dependencies"] == []

    def test_the_floor_is_the_runtime_floor(self, tool, project):
        floor = ".".join(str(n) for n in tool.RUNTIME_FLOOR)
        assert project["requires-python"] == f">={floor}"

    def test_the_version_is_derived_not_declared(self, project):
        assert "version" not in project and "version" in project["dynamic"]

    def test_the_wheel_ships_the_script_and_nothing_else(self, pyproject):
        build = pyproject["tool"]["hatch"]["build"]
        assert build["targets"]["wheel"]["shared-scripts"] == {"gh-agile": "gh-agile"}
        assert build["targets"]["wheel"]["bypass-selection"] is True
