"""The initiative an issue belongs to is read from the hierarchy, not its label (#309).

`initiative:<slug>` is a copy of the sub-issue hierarchy, kept because GitHub's
view filter cannot traverse the tree. The copy drifted: on one board 29 of 36
issues in an initiative's tree were unlabelled -- stories made before #281, and
parents set in the web UI -- while `validate` reported "no problems found",
because every reader trusted the label.

So the readers that can see the hierarchy now read it. Every board item already
carries its parent's repository, number and labels, so `initiative_chains` walks
the board just read and costs no call. `export` writes what it finds, and
`validate` compares it with the label in both directions. The one thing it
cannot do is follow a chain off the board, and it says so -- `None`,
*undetermined* -- rather than guess `""`, which is a claim.

Board filters are the exception, on purpose: they stay on the label, because a
saved board is evaluated by GitHub and `board view` must agree with it.
"""

from __future__ import annotations

import argparse

import pytest

INITIATIVE = ("type:initiative", "initiative:big")


def node(number, *labels, parent=None, repo="o/r", typename="Issue", updated="2026-10-01"):
    """A `fetch_items` item. `parent` is `(number, labels)` or `(repo, number, labels)`."""
    if parent is not None:
        p_repo, p_number, p_labels = parent if len(parent) == 3 else (repo, *parent)
        parent = {"number": p_number, "title": f"parent {p_number}",
                  "repository": {"nameWithOwner": p_repo},
                  "labels": {"nodes": [{"name": n} for n in p_labels]}}
    return {
        "id": f"PVTI_{number}", "isArchived": False, "updatedAt": f"{updated}T00:00:00Z",
        "fieldValues": {"nodes": []},
        "content": {
            "__typename": typename, "id": f"I_{number}", "number": number,
            "title": f"issue {number}", "url": "u", "state": "OPEN", "stateReason": None,
            "createdAt": "2026-09-01T00:00:00Z", "updatedAt": f"{updated}T00:00:00Z",
            "closedAt": None, "author": {"login": "dev"},
            "repository": {"nameWithOwner": repo},
            "labels": {"nodes": [{"name": n} for n in labels]},
            "assignees": {"nodes": []}, "milestone": None, "parent": parent,
            "subIssuesSummary": {"total": 0, "completed": 0},
            "closedByPullRequestsReferences": {"nodes": []},
        },
    }


def tree():
    """Initiative #1 > epic #2 > story #3, and a story #4 standing alone.

    Only the initiative is labelled: the epic and the story are the issue's
    case exactly -- members of the tree the label never reached.
    """
    return [
        node(1, *INITIATIVE),
        node(2, "type:epic", parent=(1, INITIATIVE)),
        node(3, "type:story", parent=(2, ["type:epic"])),
        node(4, "type:story"),
    ]


class TestTheWalk:
    def test_every_level_of_the_tree_reaches_the_initiative(self, tool):
        chains = tool.initiative_chains(tree())
        assert chains[("o/r", 1)] == "big", "an initiative is in its own tree"
        assert chains[("o/r", 2)] == "big"
        assert chains[("o/r", 3)] == "big", "two levels down, with no label anywhere"

    def test_no_initiative_above_is_empty_not_unknown(self, tool):
        assert tool.initiative_chains(tree())[("o/r", 4)] == ""

    def test_a_parent_set_outside_the_tool(self, tool):
        """The web UI makes the edge and stamps nothing; the walk sees the edge."""
        items = [node(1, *INITIATIVE), node(5, "type:epic", parent=(1, INITIATIVE))]
        assert tool.initiative_chains(items)[("o/r", 5)] == "big"

    def test_an_off_board_initiative_one_level_up_still_names_the_slug(self, tool):
        """The item carries its parent's labels, so one level past the board is
        known -- an initiative living on another project, in another repository."""
        items = [node(2, "type:epic", parent=("other/repo", 1, INITIATIVE))]
        assert tool.initiative_chains(items)[("o/r", 2)] == "big"

    def test_a_chain_leaving_the_board_is_undetermined(self, tool):
        """The epic is off the board, and what is above it is not known."""
        items = [node(3, "type:story", parent=(2, ["type:epic"]))]
        assert tool.initiative_chains(items)[("o/r", 3)] is None

    def test_an_initiative_without_a_slug_is_undetermined(self, tool):
        items = [node(1, "type:initiative"), node(2, "type:epic", parent=(1, ["type:initiative"]))]
        chains = tool.initiative_chains(items)
        assert chains[("o/r", 1)] is None and chains[("o/r", 2)] is None

    def test_the_hierarchy_beats_a_stale_label(self, tool):
        items = [node(1, *INITIATIVE),
                 node(4, "type:story", "initiative:big")]  # detached, label left behind
        assert tool.initiative_chains(items)[("o/r", 4)] == ""

    def test_the_same_number_in_two_repositories_is_two_issues(self, tool):
        items = [node(1, *INITIATIVE), node(1, "type:epic", repo="o/s")]
        chains = tool.initiative_chains(items)
        assert chains[("o/r", 1)] == "big" and chains[("o/s", 1)] == ""

    def test_drafts_and_pull_requests_are_not_walked(self, tool):
        items = [node(1, *INITIATIVE), node(8, typename="PullRequest"),
                 {"id": "PVTI_D", "content": {"__typename": "DraftIssue"}}]
        assert set(tool.initiative_chains(items)) == {("o/r", 1)}

    def test_a_cycle_does_not_hang(self, tool):
        items = [node(2, "type:epic", parent=(3, ["type:story"])),
                 node(3, "type:story", parent=(2, ["type:epic"]))]
        chains = tool.initiative_chains(items)
        assert chains[("o/r", 2)] is None and chains[("o/r", 3)] is None


@pytest.fixture
def exported(monkeypatch, tool):
    def go(items, since=None):
        monkeypatch.setattr(tool, "read_config", lambda *a, **k: {
            "keys": [{"key": "AGILE", "repo": "o/r"}]})
        monkeypatch.setattr(tool, "fetch_items", lambda *a, **k: ("t", items))
        return {r["number"]: r["initiative_slug"]
                for r in tool.rows("o", 1, with_history=False, since=since)}
    return go


class TestExport:
    def test_the_slug_comes_from_the_tree_not_the_label(self, exported):
        assert exported(tree()) == {1: "big", 2: "big", 3: "big", 4: ""}

    def test_a_stale_label_is_not_exported(self, exported):
        assert exported([node(1, *INITIATIVE), node(4, "type:story", "initiative:big")])[4] == ""

    def test_undetermined_is_null_not_empty(self, exported):
        """CSV writes both as empty; JSON, and `validate`, keep the difference."""
        assert exported([node(3, "type:story", parent=(2, ["type:epic"]))])[3] is None

    def test_an_ancestor_outside_the_watermark_still_counts(self, exported):
        """Incremental export drops untouched rows, but not from the walk: the
        epic nobody edited still decides which initiative the story is in."""
        items = tree()
        items[0] = node(1, *INITIATIVE, updated="2026-01-01")
        items[1] = node(2, "type:epic", parent=(1, INITIATIVE), updated="2026-01-01")
        assert exported(items, since="2026-06-01T00:00:00Z") == {3: "big", 4: ""}


def row(number, labels, slug, *, title=None):
    """A `rows()` row as `validate` reads it, with the derived slug on it."""
    return {
        "number": number, "title": title or f"issue {number}", "repository": "o/r",
        "issue_key": f"AGILE-{number}", "state": "OPEN", "state_reason": "",
        "labels": ";".join(labels), "field_status": "Todo", "field_sprint": "",
        "epic_number": None, "sub_issues_total": 1, "sub_issues_done": 0,
        "started_at": "", "done_at": "", "assignees": "dev",
        "initiative_slug": slug,
    }


@pytest.fixture
def validate(monkeypatch, tool, capsys):
    def go(*rows, only=None):
        monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
        monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
            [{"title": "Sprint 2", "startDate": "2026-08-31", "duration": 14}], []))
        args = argparse.Namespace(owner="o", project=1, _config={}, id=only)
        tool.cmd_validate(args)
        return capsys.readouterr().out
    return go


MISSING = "in the tree of initiative:big but not labelled"
STALE = "labelled initiative:big but not in its tree"
UNCHECKABLE = "initiative:big cannot be checked from this board"


class TestValidate:
    def test_a_tree_member_without_the_label_is_reported(self, validate):
        out = validate(row(1, INITIATIVE, "big"), row(3, ["type:story"], "big"))
        assert MISSING in out and "#3" in out
        assert "initiative reconcile big" in out

    def test_a_labelled_tree_member_is_silent(self, validate):
        out = validate(row(1, INITIATIVE, "big"), row(3, ["type:story", "initiative:big"], "big"))
        assert MISSING not in out and STALE not in out

    def test_a_label_the_tree_does_not_support_is_reported(self, validate):
        """The direction that is easy to forget, and worse: the initiative's
        board shows work that has left it, and looks correct."""
        out = validate(row(1, INITIATIVE, "big"), row(4, ["type:story", "initiative:big"], ""))
        assert STALE in out and "#4" in out

    def test_moved_to_another_initiative_is_both_findings(self, validate):
        out = validate(row(1, INITIATIVE, "big"),
                       row(6, ["type:initiative", "initiative:small"], "small"),
                       row(4, ["type:epic", "initiative:big"], "small"))
        assert STALE in out
        assert "in the tree of initiative:small but not labelled" in out

    def test_undetermined_is_a_note_never_missing(self, validate):
        out = validate(row(1, INITIATIVE, "big"),
                       row(3, ["type:story", "initiative:big"], None))
        assert UNCHECKABLE in out
        assert MISSING not in out and STALE not in out

    def test_undetermined_with_no_label_is_silent(self, validate):
        """No claim to check, and no gap anyone can see from here."""
        out = validate(row(1, INITIATIVE, "big"), row(3, ["type:story"], None))
        assert "cannot be checked" not in out and MISSING not in out

    def test_a_slug_naming_no_initiative_is_reported_once(self, validate):
        """The set's finding already covers it; a second heading is noise."""
        out = validate(row(4, ["type:story", "initiative:ghost"], ""))
        assert "initiative:ghost names no initiative on this board" in out
        assert "labelled initiative:ghost but not in its tree" not in out
        out = validate(row(3, ["type:story", "initiative:ghost"], None))
        assert "initiative:ghost cannot be checked" not in out

    def test_a_task_is_out_of_scope(self, validate):
        """Tasks are off the board by design, and the label is for board filters."""
        out = validate(row(1, INITIATIVE, "big"), row(9, ["type:task"], "big"))
        assert MISSING not in out

    def test_it_runs_under_id(self, validate):
        """A property of one issue, so `--id` reports it -- judged against the
        initiatives on the whole board."""
        out = validate(row(1, INITIATIVE, "big"), row(3, ["type:story"], "big"),
                       row(4, ["type:story", "initiative:big"], ""), only=3)
        assert MISSING in out and STALE not in out

    def test_a_row_that_was_not_derived_says_nothing(self, validate):
        stray = row(3, ["type:story"], "big")
        del stray["initiative_slug"]
        assert MISSING not in validate(row(1, INITIATIVE, "big"), stray)


class TestBoardFiltersStayOnTheLabel:
    def test_the_filter_term_reads_the_label_not_the_tree(self, tool):
        """A saved board is `label:initiative:<slug>`, which GitHub evaluates. If
        `board view` followed the tree instead, previewing `--filter initiative:x`
        and viewing the saved board would show different sets -- the one thing a
        reconstructed board must never do. Drift is `validate`'s to report."""
        unlabelled, stale = tree()[2], node(4, "type:story", "initiative:big")
        terms = tool.parse_filter("initiative:big")
        assert not tool.item_matches(unlabelled, terms, current_sprint=None)
        assert tool.item_matches(stale, terms, current_sprint=None)
