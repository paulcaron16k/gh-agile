"""The catalog says what a container's progress is. AGILE-152, under #148.

`github_issues` has carried `sub_issues_total` and `sub_issues_done` since before
#116 displayed them, typed and catalogued, so an initiative's progress **is**
answerable to a loader. Nothing said those two columns were the answer, or what
the answer means.

`github_catalog.json` exists precisely so nothing has to be inferred -- *a CSV
carries no schema, so without it a loader guesses* -- and the guesses available
here are the same class of error the file was written against: an empty
`time_to_first_review` read as `0` rather than null, `cycle_time_days` against
`cycle_time_hours`.

Three things a type cannot say, each of which has produced a wrong number:
per level rather than transitive, `done` meaning *closed* including
`NOT_PLANNED`, and `0/0` being a leaf rather than nought percent.

Documentation only. If this test file finds itself asserting anything about the
*export*, the story has grown into a different one.
"""

from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def catalog():
    return json.loads((ROOT / "github_catalog.json").read_text())


@pytest.fixture(scope="module")
def preamble(catalog):
    return "\n".join(catalog["_comment"])


def flowing(text: str) -> str:
    """Prose with its line breaks normalised away.

    These files are hard-wrapped, so a phrase worth asserting on lands across two
    lines as often as not. Asserting on the wrapped form tests the wrapping.
    """
    return " ".join(text.split())


@pytest.fixture(scope="module")
def issue_props(catalog):
    stream = next(s for s in catalog["streams"]
                  if s["tap_stream_id"] == "github_issues")
    return stream["schema"]["properties"]


class TestThePairIsNamed:
    def test_the_contract_says_which_columns_answer_progress(self, preamble):
        assert "PROGRESS OF A CONTAINER" in preamble
        assert "`sub_issues_done` over `sub_issues_total`" in preamble

    def test_it_is_stated_where_the_other_cross_column_rules_are(self, catalog):
        """The point is the relationship between two columns, so it does not
        belong buried in one column's description."""
        headings = [line for line in catalog["_comment"] if line[:6].isupper()
                    and line.strip()]
        assert any(h.startswith("PROGRESS OF A CONTAINER") for h in headings)


class TestTheThreeThingsATypeCannotSay:
    def test_per_level_not_transitive(self, preamble):
        assert "PER LEVEL, NOT TRANSITIVE" in preamble
        assert "DIRECT children" in preamble

    def test_the_measurement_is_kept_not_just_the_rule(self, preamble):
        """1/1 on the epic while the initiative stayed 0/1 -- the reason anyone
        believes the rule."""
        assert "1/1" in preamble and "0/1" in preamble

    def test_done_means_closed_not_completed(self, preamble):
        assert "MEANS CLOSED, NOT COMPLETED" in preamble
        assert "NOT_PLANNED" in preamble

    def test_and_says_so_on_the_column_too(self, issue_props):
        """A loader reading one column's description alone must not be misled."""
        assert "NOT_PLANNED" in issue_props["sub_issues_done"]["description"]
        assert "not `completed`" in issue_props["sub_issues_done"]["description"]

    def test_zero_over_zero_is_a_leaf(self, preamble):
        assert "0/0 IS A LEAF" in preamble
        assert "ZERO PERCENT" in preamble

    def test_the_total_column_says_direct_children_and_leaf(self, issue_props):
        described = issue_props["sub_issues_total"]["description"]
        assert "DIRECT children" in described
        assert "leaf" in described


class TestGoldAgrees:
    @staticmethod
    @pytest.fixture(scope="class")
    def gold():
        return flowing((ROOT / "GOLD_MODEL.md").read_text())

    def test_it_says_where_container_progress_belongs(self, gold):
        assert "Container progress is silver's, not Gold's" in gold

    def test_and_why_gold_does_not_copy_the_pair(self, gold):
        """Two definitions of one number disagree the first time an issue closes
        between two exports."""
        assert "second definition" in gold

    def test_it_warns_against_treating_it_as_transitive(self, gold):
        assert "must not do is treat `sub_issues_done` as transitive" in gold


class TestNothingElseChanged:
    def test_no_column_was_added_or_removed(self, issue_props):
        """The data was already right and already catalogued. If this story
        changed the export, it grew into a different story."""
        assert {"sub_issues_total", "sub_issues_done"} <= set(issue_props)

    def test_the_types_are_untouched(self, issue_props):
        assert issue_props["sub_issues_total"]["type"] == "integer"
        assert issue_props["sub_issues_done"]["type"] == "integer"

    def test_no_task_stream_appeared(self, catalog):
        ids = [s["tap_stream_id"] for s in catalog["streams"]]
        assert not any("task" in i for i in ids)
