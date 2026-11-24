"""The README is a front page: how to use the extension, and nothing else. AGILE-253, #315.

The README is the first thing a developer sees -- the repository's front page,
and on PyPI the package's. It opened with an export pitch, the versioning policy,
the hierarchy and the object model, and *Getting started* sat at line 369 of
1,033. #253 put usage first; #315 moved the reference half out to `REFERENCE.md`
so the page is short enough to read, with a worked example, a story's life cycle
and the boards it produces.

PyPI renders the README itself, which adds two rules GitHub never enforced: a
relative link resolves against pypi.org and goes nowhere, and Mermaid is shown as
source. Both are checked here rather than discovered on the published page.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The sections, in order.
SECTIONS = ["Contents", "What it does", "Install", "Set up a project: `gh agile init`",
            "A worked example: Widgets", "A story's life cycle", "See the work",
            "Get the data out", "Commands", "Learn more", "License"]

#: Long enough for the example and the samples, short enough to be a front page.
#: The README it replaced was 1,175 lines. Folded `<details>` count too: closed,
#: they cost a reader one line, but the cap is what keeps them from growing.
MAX_LINES = 500


@pytest.fixture(scope="module")
def readme():
    return (ROOT / "README.md").read_text()


def headings(text):
    """`## ` headings outside fenced blocks: a sample may print `## Intent`."""
    out, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            out.append(line[3:].strip())
    return out


def section(text, name):
    return text.split(f"\n## {name}\n", 1)[1].split("\n---\n", 1)[0]


def guard():
    spec = importlib.util.spec_from_file_location("check_guide", ROOT / "scripts" / "check_guide.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestShape:
    def test_the_sections_are_these_in_order(self, readme):
        assert headings(readme) == SECTIONS

    def test_the_contents_list_every_section(self, readme):
        contents = section(readme, "Contents")
        for name in SECTIONS[1:]:
            assert f"[{name}](#" in contents, name

    def test_it_is_short(self, readme):
        assert len(readme.splitlines()) <= MAX_LINES

    def test_the_reference_is_linked_not_inlined(self, readme):
        """The policy, the object model and the sprint internals live in
        REFERENCE.md now; the front page points there."""
        assert "REFERENCE.md" in readme
        reference = (ROOT / "REFERENCE.md").read_text()
        for moved in ("## Versions, and what installing gets you", "## The hierarchy",
                      "## Sprint management", "## Team Usage"):
            assert moved in reference and moved not in readme, moved


class TestItRendersOnPyPI:
    def test_every_link_is_absolute(self, readme):
        """Relative links resolve against pypi.org there. An in-page anchor is fine."""
        targets = re.findall(r"\]\(([^)]+)\)", readme)
        assert targets, "the extraction stopped matching"
        relative = [t for t in targets if not t.startswith(("https://", "#"))]
        assert not relative, relative

    def test_no_mermaid(self, readme):
        assert "```mermaid" not in readme

    def test_every_details_block_is_closed(self, readme):
        assert readme.count("<details>") == readme.count("</details>") > 0

    def test_fences_balance(self, readme):
        assert sum(line.startswith("```") for line in readme.splitlines()) % 2 == 0


class TestWhatItShows:
    def test_init_shows_every_first_run_flag_and_the_options(self, readme):
        text = section(readme, "Set up a project: `gh agile init`")
        for flag in ("--key", "-t", "--sprint-template", "--project", "--title-prefix",
                     "--no-hooks"):
            assert f"`{flag}" in text, flag
        assert ".github/agile.json" in text

    def test_a_plan_becomes_initiative_epics_and_stories(self, readme):
        text = section(readme, "A worked example: Widgets")
        at = [text.index(f"gh agile {level} create")
              for level in ("initiative", "epic", "story", "bug")]
        assert at == sorted(at), "initiative, then epic, then story, then a bug"
        assert "--initiative offline-sync" in text and "--epic WIDG-41" in text
        assert "<!-- sample: initiative-view -->" in text
        assert "agent" in text

    def test_the_life_cycle_names_every_status(self, tool, readme):
        text = section(readme, "A story's life cycle")
        for status in tool.STATUSES:
            assert status in text, status
        for command in ("gh agile issue move", "gh agile issue close", "gh agile sprint carryover"):
            assert command in text, command

    def test_boards_are_named_by_any_unique_part(self, readme):
        """`sprint` and `backlog` are what people type; the README says it works."""
        text = section(readme, "See the work")
        assert "gh agile board view sprint" in text and "gh agile board view backlog" in text
        assert "Any unique part of a board's name is enough" in text
        for sample in ("sprint-board", "backlog", "roadmap", "issue-status"):
            assert f"<!-- sample: {sample} -->" in text, sample

    def test_the_commands_section_names_every_command(self, tool, readme):
        """Folded, but complete: a leaf missing here is a command a PyPI reader
        never learns exists. A `list` / `view` row names both."""
        text = section(readme, "Commands")
        named = set()
        for cell in re.findall(r"^\| `([^|]+)` \|", text, re.MULTILINE):
            first, *rest = [part.strip(" `") for part in cell.split("/")]
            noun = first.split()[0] if " " in first else None
            named.add(first)
            named.update(f"{noun} {verb}" if noun else verb for verb in rest)
        leaves = {" ".join(leaf) for leaf in guard().parser_leaves()}
        assert len(leaves) > 20, "the parser walk stopped finding commands"
        assert leaves <= named, sorted(leaves - named)


def test_check_guide_reads_the_readme_and_the_reference():
    """Every command on the front page and in the reference is checked to
    exist, and the safe ones run."""
    module = guard()
    readme = [c for _line, c in module.documented_commands(module.README)]
    assert any(c.startswith("gh agile init --key") for c in readme)
    assert any(c.startswith("gh agile board view sprint") for c in readme)
    assert [c for _line, c in module.documented_commands(module.REFERENCE)]
