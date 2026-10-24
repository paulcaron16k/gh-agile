"""What `export --out-dir` says it writes is what it writes. AGILE-256.

The `--out-dir` help said `agile_issues_<ISO8601>.<ext>`, as did the module
docstring and a comment, long after the silver tables became `github_*` --
pointing a loader's file glob at a name that never appears, and at the Gold
model's `agile_*` namespace, which lives in agile-reports.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def source():
    return (ROOT / "gh-agile").read_text()


def help_text(tool):
    sub = tool.build_parser()._subparsers._group_actions[0].choices["export"]
    return next(a.help for a in sub._actions if "--out-dir" in a.option_strings)


def test_the_help_names_the_files_the_export_writes(tool):
    written = re.search(r'directory / f"(github)_\{grain\}_\{file_stamp', source())
    assert written, "the export no longer writes github_<grain>_<stamp>; update this test"
    assert "github_<table>_<ISO8601>" in help_text(tool)


def test_no_export_text_names_an_agile_file(tool):
    """`agile_*` is the Gold model's; nothing here writes one."""
    assert "agile_" not in help_text(tool)
    assert not re.search(r"agile_issues_[<.]", source())
