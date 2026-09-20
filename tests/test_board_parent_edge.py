"""`board_row` carries the parent edge. AGILE-149, under #148.

`board_row` kept `epic_number` and nothing else about the parent -- enough to say
*this has a parent*, not enough to say *which one*. A board may span
repositories and each numbers its issues independently from 1, so two `#12` on
one board is ordinary rather than unlucky: a number cannot name a parent and a
key can. Nothing can be ordered into a tree until a row can say whose child it
is, which is why this comes before #150.

**It also carried the pre-#90 defect.** The line was
`content.parent.number` -- the parent's number *whatever the parent was* -- so
since #85 built the level above, an epic under an initiative reported an
initiative in a column called `epic_number`, with nothing saying so. The export
rows were fixed for this in #90 and `board_row` simply never called the same
builder.

Verified live before the fix: `AGILE-114`, an epic under initiative `AGILE-119`,
came out of the JSONL rendering with `epic_number: 119`.
"""

from __future__ import annotations

import argparse
import json

KEYS = {"o/r": "AGILE", "o/other": "OTHER"}
VIEW = {"name": "b", "layout": "TABLE_LAYOUT", "filter": ""}


def parent(number, kind, *, repo="o/r", title="the parent"):
    return {"number": number, "title": title,
            "repository": {"nameWithOwner": repo},
            "labels": {"nodes": ([{"name": f"type:{kind}"}] if kind else [])}}


def item(number=10, *, kind="story", parent_node=None, repo="o/r"):
    content = {
        "__typename": "Issue", "number": number, "title": f"issue {number}",
        "url": "u", "state": "OPEN", "repository": {"nameWithOwner": repo},
        "labels": {"nodes": [{"name": f"type:{kind}"}, {"name": "key:AGILE"}]},
        "assignees": {"nodes": []}, "subIssuesSummary": {"total": 0, "completed": 0},
    }
    if parent_node is not None:
        content["parent"] = parent_node
    return {"id": f"PVTI_{number}", "isArchived": False,
            "fieldValues": {"nodes": []}, "content": content}


class TestTheEdgeIsCarried:
    def test_the_parent_key_names_it_unambiguously(self, tool):
        row = tool.board_row(item(parent_node=parent(9, "epic")), KEYS)
        assert row["parent_key"] == "AGILE-9"

    def test_the_parent_title_and_type_come_too(self, tool):
        row = tool.board_row(item(parent_node=parent(9, "epic", title="an epic")), KEYS)
        assert row["parent_title"] == "an epic"
        assert row["parent_type"] == "epic"

    def test_a_parent_in_another_repository_is_still_named(self, tool):
        """The whole reason a key beats a number: two `#12` on one board is
        ordinary, and a bare number cannot tell them apart."""
        row = tool.board_row(item(parent_node=parent(12, "epic", repo="o/other")), KEYS)
        assert row["parent_key"] == "OTHER-12"

    def test_no_parent_is_empty_rather_than_absent(self, tool):
        row = tool.board_row(item(), KEYS)
        assert row["parent_key"] == "" and row["parent_type"] == ""

    def test_a_parent_with_no_type_label_has_no_type(self, tool):
        """A machine may not infer one, so the column is empty and says so."""
        row = tool.board_row(item(parent_node=parent(9, None)), KEYS)
        assert row["parent_key"] == "AGILE-9" and row["parent_type"] == ""


class TestEpicNumberMeansWhatItSays:
    """The pre-#90 defect, still living in `board_row` until now."""

    def test_an_epic_parent_populates_it(self, tool):
        row = tool.board_row(item(parent_node=parent(9, "epic")), KEYS)
        assert row["epic_number"] == 9 and row["epic_key"] == "AGILE-9"

    def test_an_initiative_parent_does_not(self, tool):
        """`AGILE-114` reported `epic_number: 119` -- an initiative in a column
        called `epic_number`, with nothing saying so."""
        row = tool.board_row(item(kind="epic", parent_node=parent(119, "initiative")),
                             KEYS)
        assert row["epic_number"] is None and row["epic_key"] == ""
        assert row["parent_key"] == "AGILE-119" and row["parent_type"] == "initiative"

    def test_it_is_null_never_an_empty_string(self, tool):
        """A union of int and str is a type no loader can turn into a DDL type."""
        assert tool.board_row(item(), KEYS)["epic_number"] is None


class TestOneBuilderNotTwo:
    def test_the_row_matches_parent_columns_exactly(self, tool):
        """A second implementation is one that can disagree with the export."""
        node = parent(9, "epic")
        row = tool.board_row(item(parent_node=node), KEYS)
        expected = tool.parent_columns(node, KEYS)
        assert {k: row[k] for k in expected} == expected

    def test_the_source_calls_it_rather_than_reimplementing(self, tool):
        import pathlib
        body = pathlib.Path(tool.__file__).read_text()
        body = body.split("def board_row(")[1].split("\ndef ")[0]
        assert "parent_columns(" in body
        assert 'content.get("parent") or {}).get("number")' not in body


class TestTheTextRenderingIsUnchanged:
    def test_no_new_column_appears(self, tool):
        """This adds fields to a row; nothing displays them yet."""
        rows = [tool.board_row(item(parent_node=parent(9, "epic", title="an epic")),
                               KEYS)]
        out = tool.render_board(VIEW, "backlog", rows, [("", rows)], "o", 4, 1, "", 80)
        assert "an epic" not in out
        assert "parent" not in out

    def test_a_row_with_a_parent_renders_as_one_without(self, tool):
        with_parent = [tool.board_row(item(parent_node=parent(9, "epic")), KEYS)]
        without = [tool.board_row(item(), KEYS)]
        def render(rows):
            return tool.render_board(VIEW, "backlog", rows, [("", rows)],
                                     "o", 4, 1, "", 80)

        assert render(with_parent) == render(without)


class TestTheJsonlCarriesThem:
    def test_the_fields_reach_a_reader(self, tool):
        rows = [tool.board_row(item(parent_node=parent(9, "epic")), KEYS)]
        out = tool.board_jsonl(VIEW, "backlog", rows, [("", rows)],
                               argparse.Namespace(owner="o", project=4), "", 1,
                               "2026-09-20T00:00:00Z")
        row = json.loads(out.splitlines()[1])
        assert row["parent_key"] == "AGILE-9" and row["parent_type"] == "epic"
