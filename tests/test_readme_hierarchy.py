"""The README describes the object model the tool has. AGILE-160, under #157.

Audited and counted: `initiative` appeared **zero** times in the README, and
`type:task` zero. The object-model diagram -- the only picture of the hierarchy
anywhere, and the first thing a reader meets -- stopped at Epic and said "epic
holds stories" in two places.

That is the front door. #85 built the level above epic, #148 made it legible,
#132 added the level below, and someone installing the extension read a document
describing neither.

**The anti-drift mechanism is the point, not the prose.** A hand-maintained list
of levels is what fell behind `ISSUE_TYPES` in the first place, so these tests
read `ISSUE_TYPES` and require the README to keep up with it. Adding a sixth
level fails here until the README mentions it.

Orientation, not reference: the detail belongs in `USER_GUIDE.md`, and the
README linking rather than restating is what stops the two disagreeing -- the
mechanism that produced #161.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def readme():
    return (ROOT / "README.md").read_text()


@pytest.fixture(scope="module")
def flowing(readme):
    """The README with its hard wrapping normalised away -- #152's lesson."""
    return " ".join(readme.split())


class TestEveryLevelIsDescribed:
    def test_the_type_list_is_not_empty(self, tool):
        """A matcher that stops matching passes every case below vacuously."""
        assert len(tool.ISSUE_TYPES) >= 4

    def test_every_issue_type_appears(self, tool, readme):
        """Read from `ISSUE_TYPES` rather than a list kept beside it: a
        hand-maintained one is what fell behind in the first place."""
        missing = [t for t in tool.ISSUE_TYPES if f"type:{t}" not in readme]
        assert not missing, f"README does not mention {missing}"

    def test_the_diagram_names_the_levels_it_carries(self, readme):
        diagram = readme.split("```mermaid")[1].split("```")[0]
        assert "initiative to epic" in diagram
        assert "epic to story" in diagram

    def test_the_diagram_is_a_closed_fence(self, readme):
        """A broken fence renders as a wall of text on the front page."""
        assert readme.count("```mermaid") == readme.count("classDiagram")
        assert readme.count("```") % 2 == 0


class TestWhatAReaderMustNotGuess:
    def test_an_initiative_is_said_to_be_optional(self, flowing):
        """Four mandatory levels would read as ceremony the tool does not ask
        for. POLICY.md §2 says optional; so must the front door."""
        assert "optional" in flowing
        assert re.search(r"[Ii]nitiative.{0,200}optional", flowing)

    def test_the_initiative_label_is_explained_not_just_listed(self, flowing):
        """Nobody guesses why a label duplicates an edge that already exists."""
        assert "initiative:" in flowing
        assert "filter cannot traverse the hierarchy" in flowing

    def test_the_edge_is_named_as_a_sub_issue_edge(self, flowing):
        """It is a real GitHub edge, which is why a roll-up is possible at all."""
        assert "sub-issue" in flowing

    def test_the_labels_are_explained_as_the_carrier(self, flowing):
        """Labels are not a style choice: Issue Types are organization-only."""
        assert "organization-only" in flowing

    def test_a_task_is_marked_as_discouraged(self, flowing):
        """`type:task` exists so `validate` stops punishing a team that files
        them; it is not a recommendation, and the README must not read as one."""
        assert re.search(r"[Tt]ask.{0,300}checklist", flowing)


class TestItOrientsRatherThanDuplicates:
    def test_it_points_at_the_guide(self, readme):
        assert "USER_GUIDE.md" in readme

    def test_and_at_the_rules(self, readme):
        assert "POLICY.md" in readme

    def test_the_hierarchy_section_stays_short(self, readme):
        """Depth here duplicates the guide and then drifts from it, which is
        the mechanism that produced #161."""
        section = readme.split("## The hierarchy")[1].split("## The object model")[0]
        assert len(section.split()) < 400, "orientation, not reference"
