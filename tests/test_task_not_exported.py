"""A task is not exported. AGILE-137, under #132.

**The decision was the deliverable**, taken before any of this was written: a
task has no metric and no KPI. It is story-internal housekeeping -- many teams
keep the same thing in a markdown checklist -- and a grain exists to be measured.
#135 already makes a task change no number anywhere, and a row that changes no
number is not a measurement.

That settled all three options at once. A `github_tasks` table nobody queries is
a promise this repo would have to keep for nothing, and an extra row shape in
`github_issues` is a cost paid by every downstream join for data with no
consumer. It also made the awkward case moot: a task would have been the first
row ever to carry a populated `parent_key` with an empty `epic_key`, which every
join would have had to learn.

**A stated rule with a test, not an accident of a filter** somebody later
"fixes".
"""

from __future__ import annotations

import json
import pathlib

import pytest


def row(number, kind, *, extra_labels=""):
    return {"issue_key": f"A-{number}", "number": number, "repository": "o/r",
            "labels": f"type:{kind};key:AGILE" + extra_labels}


class TestWithoutTasks:
    def test_a_task_row_is_removed(self, tool):
        kept, skipped = tool.without_tasks([row(1, "task")])
        assert kept == [] and skipped == 1

    @pytest.mark.parametrize("kind", ["story", "epic", "initiative", "bug"])
    def test_every_other_level_survives(self, tool, kind):
        kept, skipped = tool.without_tasks([row(1, kind)])
        assert len(kept) == 1 and skipped == 0

    def test_the_count_is_what_was_dropped(self, tool):
        data = [row(1, "task"), row(2, "story"), row(3, "task")]
        kept, skipped = tool.without_tasks(data)
        assert [r["number"] for r in kept] == [2]
        assert skipped == 2

    def test_a_label_merely_containing_task_is_not_a_task(self, tool):
        """`;`-joined labels are matched whole, not by substring -- a
        `type:story` row carrying `area:tasking` must survive."""
        kept, _skipped = tool.without_tasks([row(1, "story", extra_labels=";area:tasking")])
        assert len(kept) == 1

    def test_a_row_with_no_labels_survives(self, tool):
        kept, skipped = tool.without_tasks([{"issue_key": "A-1", "number": 1,
                                             "repository": "o/r", "labels": ""}])
        assert len(kept) == 1 and skipped == 0

    def test_nothing_to_drop_reports_zero(self, tool):
        assert tool.without_tasks([row(1, "story")])[1] == 0


class TestTheContractSaysSo:
    """A contract silent about an exclusion reads as an oversight, which is what
    #92 and #94 exist to prevent."""

    @staticmethod
    def catalog():
        path = pathlib.Path(__file__).resolve().parent.parent / "github_catalog.json"
        return json.loads(path.read_text())

    def test_the_catalog_is_still_valid_json(self):
        assert self.catalog()["streams"]

    def test_it_states_that_tasks_are_absent(self):
        text = "\n".join(self.catalog()["_comment"])
        assert "type:task" in text
        assert "NOT exported" in text

    def test_and_says_why(self):
        text = "\n".join(self.catalog()["_comment"])
        assert "no metric" in text

    def test_no_task_stream_was_added(self):
        ids = [s["tap_stream_id"] for s in self.catalog()["streams"]]
        assert not any("task" in i for i in ids)


# `TestTheBoundaryIsRecorded` read GOLD_MODEL.md's "Tasks: below the boundary".
# That document moved to agile-reports with the model (#248); the boundary as
# this repository states it -- the catalog's exclusion and no task stream -- is
# asserted above.
