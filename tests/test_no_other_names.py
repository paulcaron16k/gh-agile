"""No other company or another team's repository is named. AGILE-249.

The repository is to be public, and a name in a public repository can read as a
recommendation or an endorsement. The rule: an Agile tool may be named as a
comparison point (Jira), and an open-source project or format where it states a
technical fact (DuckDB, Singer, Iceberg, Parquet). Nothing else -- and another
team's private repository, used for months as the running example, is now the
invented `acme/widgets`, key `WIDG`.
"""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: What a reader of the repository sees. This file spells the names to look for
#: them, so it is left out.
TRACKED = sorted(
    {ROOT / "gh-agile", ROOT / "github_catalog.json", ROOT / "Makefile"}
    | set(ROOT.glob("*.md")) | set((ROOT / "docs").glob("*.md"))
    | set((ROOT / "scripts").glob("*.py")) | set((ROOT / ".claude" / "memory").glob("*.md"))
    | set((ROOT / "templates").glob("*"))
    | {p for p in (ROOT / "tests").glob("*.py") if p.name != pathlib.Path(__file__).name})

#: Assembled, so a search of the repository finds them only as this list.
GONE = ["Zam" + "boni", "ZMB" + "NI", "Melt" + "ano", "dlt" + "Hub", "definite" + "-app",
        "ducklake" + "-definite", "merge" + "stat"]


@pytest.mark.parametrize("name", GONE)
def test_no_tracked_text_names_it(name):
    hits = [f"{p.relative_to(ROOT)}:{n}" for p in TRACKED if p.is_file()
            for n, line in enumerate(p.read_text().splitlines(), 1)
            if name.casefold() in line.casefold()]
    assert not hits, f"{name!r} is still named in: {', '.join(hits)}"


def test_dlt_is_not_named_as_a_word():
    """`dlt` is short enough to need word boundaries: it sits inside nothing else."""
    import re
    hits = [f"{p.relative_to(ROOT)}:{n}" for p in TRACKED if p.is_file()
            for n, line in enumerate(p.read_text().splitlines(), 1)
            if re.search(r"\bdlt\b", line)]
    assert not hits, f"'dlt' is still named in: {', '.join(hits)}"


def test_the_example_repository_is_the_invented_one():
    """The running example has one spelling, so a reader can follow it."""
    guide = (ROOT / "USER_GUIDE.md").read_text()
    assert "acme/widgets" in guide and "WIDG-34" in guide
