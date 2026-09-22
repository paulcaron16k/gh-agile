"""The guide documents what the boards now print. AGILE-159, under #157.

Counted before writing: `closed/total` 0, `advancing` 0, `not started` 0,
`started_on` 0 across both documents. Everything #114 and #148 shipped was
invisible in the documentation, so a reader following the guide's *Reading a
board from the terminal* met a board printing things it never mentioned and
ordering rows in a way it did not explain.

**Worse than absent, in one place.** The guide said an epic *is* flagged when in
progress with nobody on it -- "exempt from the sprint, not from having somebody
driving it". #117 reversed exactly that: a container is never claimed
implicitly, `validate` never demands one, and `render_who` prints the em dash.
The guide was asserting the opposite of the shipped rule, and the docs audit
that produced this epic did not catch it -- only writing the section did.

These tests hold the guide against the tool's own behaviour rather than against
a list, so the next change to a board's rendering fails here.
"""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def guide():
    return (ROOT / "USER_GUIDE.md").read_text()


@pytest.fixture(scope="module")
def flowing(guide):
    """Hard wrapping normalised away -- #152's lesson, applied by default."""
    return " ".join(guide.split())


class TestTheTally:
    def test_the_column_is_described(self, flowing):
        assert "closed/total" in flowing

    def test_it_says_closed_rather_than_done(self, flowing):
        """GitHub's field is named `completed` and counts NOT_PLANNED children.
        Abandoned is not completed, so nothing calls that number done."""
        assert "NOT_PLANNED" in flowing
        assert "Abandoned is not completed" in flowing

    def test_it_says_the_tally_is_per_level(self, flowing):
        assert "never transitive" in flowing or "not transitive" in flowing
        assert "0/1" in flowing and "1/1" in flowing

    def test_the_legend_the_tool_prints_is_quoted(self, tool, guide):
        """The guide must quote what the board actually says, not a paraphrase
        that drifts from it."""
        legend = "pts: story points, or closed/total sub-issues for epics and initiatives"
        assert legend in guide


class TestTheAssigneeRule:
    def test_the_guide_no_longer_claims_a_container_is_flagged(self, flowing):
        """#117 reversed this. The guide asserted the opposite of the rule for
        as long as it took someone to write the next section."""
        assert "exempt from the sprint, not from having somebody driving it" not in flowing

    def test_it_states_the_rule_that_shipped(self, flowing):
        assert "never claims one implicitly" in flowing

    def test_and_why_it_is_a_guess(self, flowing):
        """An epic holds stories worked by several people."""
        assert "only right on a team of one" in flowing

    def test_it_matches_what_render_who_does(self, tool, flowing):
        """Asserted against the behaviour, not against a remembered rule."""
        started_epic = {"type": "epic", "assignees": [], "status": "In Progress"}
        assert tool.render_who(started_epic) == "—"
        assert tool.render_who({**started_epic, "type": "story"}) == tool.NOBODY
        assert "Nor is an epic or an initiative" in flowing


class TestHierarchyOrdering:
    def test_the_indent_is_explained(self, flowing):
        assert "one space per level" in flowing

    def test_the_ordering_is_named_as_the_point(self, flowing):
        """Indentation alone would duplicate the `type` column."""
        assert "cannot say **whose child**" in flowing or "whose child" in flowing

    def test_loose_work_is_said_to_come_last(self, flowing):
        assert "after the trees" in flowing

    def test_a_grouped_board_is_said_to_be_untouched(self, flowing):
        assert "status-grouped board is left alone" in flowing


class TestTheContextBand:
    def test_it_is_described(self, flowing):
        assert "advancing" in flowing

    def test_membership_is_said_to_be_derived(self, flowing):
        assert "derived from the sprint's own contents" in flowing

    def test_the_heading_the_tool_prints_is_quoted(self, tool, guide):
        assert tool.BAND_HEADING in guide

    def test_it_says_the_band_is_counted_by_nothing(self, flowing):
        assert "counted by nothing" in flowing


class TestTheRoadmap:
    def test_the_axis_is_explained(self, flowing):
        assert "earliest" in flowing and "sprint:` label" in flowing

    def test_the_naming_seam_is_explained(self, flowing):
        """`AGILE Sprint 4` above `Sprint 2` looks wrong until you know a
        sprint is never renamed."""
        assert "never renamed" in flowing
        assert "oldest" in flowing

    def test_not_started_is_documented(self, tool, flowing):
        assert tool.NOT_STARTED in flowing


class TestTheJsonlFields:
    @pytest.mark.parametrize("field", [
        "depth", "parent_key", "parent_type", "sub_issues_total",
        "started_in", "started_on"])
    def test_each_new_field_is_named(self, flowing, field):
        assert field in flowing

    def test_the_container_record_kind_is_documented(self, flowing):
        assert '"kind":"container"' in flowing

    def test_depth_is_called_a_rendering_property(self, flowing):
        assert "property of *this rendering*" in flowing or "this rendering" in flowing


class TestTheSampleIsNotStale:
    @staticmethod
    def sample(guide):
        """The rendered-board block in the `board show` section.

        Found by content rather than by counting fences: the section opens with
        a `bash` block, so an index is one renumbering away from asserting
        against the wrong thing -- which it did on the first attempt.
        """
        section = guide.split("### Reading a board from the terminal")[1]
        blocks = section.split("```")
        return next(b for b in blocks if "backlog · " in b)

    def test_it_shows_a_tally(self, guide):
        """The old sample showed `AGILE-9 epic —`, from before #116."""
        assert "3/5" in self.sample(guide)

    def test_it_shows_the_indentation(self, guide):
        assert "\n   AGILE-" in self.sample(guide), "expected an indented child row"

    def test_it_shows_the_legend(self, guide):
        assert "pts: story points" in self.sample(guide)
