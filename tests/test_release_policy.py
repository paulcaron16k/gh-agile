"""The release policy is a decision, and a document is what holds it. AGILE-197.

No test can hold *tag for the record, track main* -- it is a choice, not
behaviour. What a test can hold is that the choice is still written down, in the
place a consumer reads, and that the two files saying it have not drifted into
saying different things.

Filed because there was no decision at all: no tags, no releases, and the only
stability claim in the repository was one line of `CLAUDE.md`, which is guidance
for working *on* the tool rather than documentation *of* it.

Offline: three files on disk.
"""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def readme():
    return (ROOT / "README.md").read_text()


class TestTheDecisionIsWhereAConsumerReads:
    def test_the_readme_has_the_section(self, readme):
        assert "## Versions, and what installing gets you" in readme

    def test_it_says_main_is_the_release(self, readme):
        assert "`main` is the release" in readme

    def test_it_says_what_makes_that_safe(self, readme):
        """A promise about `main` rather than an absence of process -- and the
        three things that enforce it are named, because otherwise it is a hope."""
        for enforcement in ("merge-check", "3.10 through 3.13", "sandbox"):
            assert enforcement in readme

    def test_it_tells_consumers_not_to_pin(self, readme):
        """The cost is measured, not theoretical: a pinned clone stops receiving
        fixes silently, which is how an extension ends up older than the git
        hook that calls it -- #192."""
        assert "Do not pin" in readme
        assert "older than the git" in readme

    def test_it_says_what_a_tag_is_for(self, readme):
        assert "nothing installs from one" in readme

    def test_it_states_the_stability(self, readme):
        """The claim that used to live only in CLAUDE.md, where a consumer
        never looks."""
        assert "near alpha" in readme

    def test_it_names_what_is_treated_as_a_contract(self, readme):
        """*No compatibility promise* is not the same as *nothing is stable*,
        and a reader deciding whether to build on this needs the difference."""
        assert "github_catalog.json" in readme


class TestTheOtherTwoFilesAgree:
    def test_the_guide_points_at_the_readme(self):
        guide = (ROOT / "USER_GUIDE.md").read_text()
        assert "Versions, and what installing gets you" in guide
        assert "no tag is consulted" in guide

    def test_claude_md_points_at_it_rather_than_restating_it(self):
        """A fact kept in two files eventually disagrees with itself, and the
        copy that loses is the one loaded automatically."""
        claude = (ROOT / "CLAUDE.md").read_text()
        assert "The release policy lives there" in claude
        assert "Do not pin" not in claude


class TestNothingReadsTheTag:
    def test_the_tool_does_not_parse_a_tag(self):
        """Tags name builds and nothing depends on them. #196 derives a version
        from the checkout, which works pinned or not -- if the tool ever starts
        requiring a tag, this policy has quietly changed."""
        tool = (ROOT / "gh-agile").read_text()
        assert "git describe" not in tool
        assert "--pin" not in tool
