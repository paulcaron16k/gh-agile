"""The README opens with how to use the extension. AGILE-253.

The README is the first thing a developer sees -- the repository's front page.
It opened with an export pitch, the versioning policy, the hierarchy and the
object model, and *Getting started* sat at line 369 of 1,033. Usage now comes
first, in the order somebody needs it; the reference material follows.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The opening sections, in order. Everything after them is reference.
OPENING = ["Install", "Set up a project: `gh agile init`", "See the work",
           "Turn a feature plan into work", "Day to day", "Get the data out", "Where next"]


@pytest.fixture(scope="module")
def readme():
    return (ROOT / "README.md").read_text()


def headings(text):
    return [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]


def section(text, name):
    return text.split(f"## {name}\n", 1)[1].split("\n## ", 1)[0]


def test_usage_comes_first_and_in_order(readme):
    assert headings(readme)[:len(OPENING)] == OPENING


def test_the_reference_follows(readme):
    rest = headings(readme)[len(OPENING):]
    assert "Versions, and what installing gets you" in rest and "The hierarchy" in rest


def test_init_shows_every_first_run_flag_and_the_options(readme):
    text = section(readme, "Set up a project: `gh agile init`")
    for flag in ("--key", "-t", "--sprint-template", "--project", "--title-prefix", "--no-hooks"):
        assert f"`{flag}" in text, flag
    assert ".github/agile.json" in text


def test_boards_are_named_by_any_unique_part(readme):
    """`sprint` and `backlog` are what people type; the README says it works."""
    text = section(readme, "See the work")
    assert "gh agile board view sprint" in text and "gh agile board view backlog" in text
    assert "Any unique part of a board's name is enough" in text


def test_a_plan_becomes_initiative_epics_and_stories(readme):
    text = section(readme, "Turn a feature plan into work")
    at = [text.index(f"gh agile {level} create") for level in ("initiative", "epic", "story")]
    assert at == sorted(at), "initiative, then epic, then story"
    assert "--initiative offline-sync" in text and "--epic WIDG-41" in text
    assert "agent" in text


def test_the_day_to_day_includes_filing_a_bug(readme):
    text = section(readme, "Day to day")
    assert "gh agile bug create" in text and "gh agile issue move" in text


def test_check_guide_reads_the_readme():
    """Every command on the front page is checked to exist, and the safe ones run."""
    spec = importlib.util.spec_from_file_location("check_guide", ROOT / "scripts" / "check_guide.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    commands = [c for _line, c in guard.documented_commands(guard.README)]
    assert any(c.startswith("gh agile init --key") for c in commands)
    assert any(c.startswith("gh agile board view sprint") for c in commands)
