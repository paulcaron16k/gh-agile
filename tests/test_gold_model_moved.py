"""The Gold model lives in agile-reports, and nothing here names one company's. AGILE-248.

gh-agile is the Agile tool and its export; the generic Agile metrics model the
export feeds, and the KPIs built on it, are the agile-reports repository's. Both
are to be public, and the model used to be written as one company's, fed by one
company's pipeline. These hold the move to what it promised.
"""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The text a reader of this repository sees: docs, the tool, its catalog, its
#: scripts, its tests and the memory files it tracks. This file is left out,
#: because it has to spell the names to look for them.
TRACKED = sorted(
    {ROOT / "gh-agile", ROOT / "github_catalog.json"}
    | set(ROOT.glob("*.md")) | set((ROOT / "docs").glob("*.md"))
    | set((ROOT / "scripts").glob("*.py")) | set((ROOT / ".claude" / "memory").glob("*.md"))
    | {p for p in (ROOT / "tests").glob("*.py") if p.name != pathlib.Path(__file__).name})

#: Assembled rather than written, so a search of the repository for them finds
#: nothing but this list's purpose.
GONE = ["Experience" + "Flow", "I" + "WS pipeline", "I" + "WS Partner", "org_master" + "_employees",
        "agile" + "_catalog.json", "agile" + "_data_model.md"]


def test_the_document_is_not_kept_here_as_well():
    """One copy: two would disagree the first time either was edited."""
    assert not (ROOT / "GOLD_MODEL.md").exists()


@pytest.mark.parametrize("name", GONE)
def test_no_tracked_text_names_it(name):
    hits = [f"{p.relative_to(ROOT)}:{n}" for p in TRACKED
            for n, line in enumerate(p.read_text().splitlines(), 1)
            if name.casefold() in line.casefold()]
    assert not hits, f"{name!r} is still named in: {', '.join(hits)}"


def test_the_docs_point_at_its_new_home():
    url = "github.com/paulcaron16k/agile-reports/blob/main/GOLD_MODEL.md"
    for doc in ("README.md", "USER_GUIDE.md"):
        assert url in (ROOT / doc).read_text(), doc
