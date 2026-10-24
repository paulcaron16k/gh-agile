"""Choosing a project item to write to, across repositories.

A project may span repositories, and each one numbers its issues independently
from 1, so two of them sharing a number is ordinary. `set` and `move` both
matched an item on the issue number alone: `set` resolved the repository and
discarded it, `move` kept it for the `gh issue` calls and still matched on the
number. A single `move B-12 --status Done --close` could therefore stamp Status
and a `sprint:` label onto an unrelated #12 in repository A while correctly
closing #12 in repository B, silently, reporting success.

These are the tests that would have caught it. Since #231 `board_item_for` asks
the issue rather than the board list, so the fixture is a stubbed `graphql`, and
the board read is forbidden outright.
"""

from __future__ import annotations

import pathlib

import pytest

#: What `board_items` returns. It once came from `gh project item-list` and now
#: comes from a lean GraphQL query adapted into the same shape -- `content.type`
#: carries the `__typename`, and `content.repository` is always `owner/name`.
BOARD = [
    {"id": "PVTI_a",
     "content": {"number": 12, "repository": "owner/repo-a", "type": "Issue"}},
    {"id": "PVTI_b",
     "content": {"number": 12, "repository": "owner/repo-b", "type": "Issue"}},
    {"id": "PVTI_pr",
     "content": {"number": 12, "repository": "owner/repo-c", "type": "PullRequest"}},
    # A draft issue has content with no number, and a genuinely empty item has none.
    {"id": "PVTI_draftish",
     "content": {"number": None, "repository": None, "type": "DraftIssue"}},
    {"id": "PVTI_none", "content": None},
]


@pytest.fixture
def board(monkeypatch, tool):
    """`board_items` stubbed, so no test here touches the network."""
    monkeypatch.setattr(tool, "board_items", lambda *a, **k: BOARD)


class TestSameRepo:
    """`content.repository` has had two shapes across `gh` versions."""

    def test_owner_name_on_both_sides_compares_in_full(self, tool):
        assert tool.same_repo("owner/repo-a", "owner/repo-a")
        assert not tool.same_repo("owner/repo-a", "owner/repo-b")

    def test_a_different_owner_is_a_different_repo(self, tool):
        """The looseness `sync` tolerates is not tolerable when choosing a write target."""
        assert not tool.same_repo("alice/api", "bob/api")

    def test_a_bare_name_falls_back_to_the_trailing_segment(self, tool):
        """Older `gh` reported a bare name; matching nothing would read as "not on the board"."""
        assert tool.same_repo("repo-a", "owner/repo-a")
        assert not tool.same_repo("repo-a", "owner/repo-b")

    def test_case_is_not_significant(self, tool):
        assert tool.same_repo("Owner/Repo-A", "owner/repo-a")

    def test_absent_repository_never_matches(self, tool):
        assert not tool.same_repo(None, "owner/repo-a")
        assert not tool.same_repo("", "owner/repo-a")


def item(item_id, number=1, owner="owner", archived=False):
    return {"id": item_id, "isArchived": archived,
            "project": {"number": number, "owner": {"login": owner}}}


#: What `ITEM_FROM_ISSUE_QUERY` answers, keyed by `(repository name, number)`.
#: Two repositories share #12; repo-c's #12 is a pull request.
ISSUES = {
    ("repo-a", 12): {"__typename": "Issue", "projectItems": {"nodes": [item("PVTI_a")]}},
    ("repo-b", 12): {"__typename": "Issue", "projectItems": {"nodes": [item("PVTI_b")]}},
    ("repo-c", 12): {"__typename": "PullRequest"},
    # On two projects; only the second is project 1.
    ("repo-a", 20): {"__typename": "Issue", "projectItems": {"nodes": [
        item("PVTI_other", number=7), item("PVTI_20")]}},
    # On a project 1 -- somebody else's.
    ("repo-a", 30): {"__typename": "Issue", "projectItems": {"nodes": [
        item("PVTI_theirs", owner="stranger")]}},
    ("repo-a", 40): {"__typename": "Issue", "projectItems": {"nodes": [
        item("PVTI_archived", archived=True)]}},
    ("repo-a", 50): {"__typename": "Issue", "projectItems": {"nodes": []}},
}


@pytest.fixture
def asked(monkeypatch, tool):
    """`graphql` answering from `ISSUES`, and the board read forbidden: the
    point of #231 is that the item comes from the issue, never the list."""
    queries = []

    def fake(query, **variables):
        queries.append(variables)
        found = ISSUES.get((variables["name"], variables["number"]))
        return {"data": {"repository": {"issueOrPullRequest": found}}}
    monkeypatch.setattr(tool, "graphql", fake)
    monkeypatch.setattr(tool, "board_items", lambda *a, **k: pytest.fail(
        "the board was read to find one issue's item"))
    return queries


class TestBoardItemFor:
    """The item is asked of the issue (#231). GitHub can leave a new item out of
    `projectV2.items` for an hour or more while it exists -- another team's #228 was
    refused as "not on project N" from 71 minutes to ~10.5 hours."""

    def test_an_item_the_board_list_leaves_out_is_found(self, tool, asked):
        assert tool.board_item_for("owner", 1, "owner/repo-a", 12) == {"id": "PVTI_a"}

    def test_one_small_query_per_issue(self, tool, asked):
        tool.board_item_for("owner", 1, "owner/repo-a", 12)
        assert asked == [{"owner": "owner", "name": "repo-a", "number": 12}]

    def test_the_number_alone_is_not_enough(self, tool, asked):
        """The defect it was first written for: two repositories, one number."""
        assert tool.board_item_for("owner", 1, "owner/repo-a", 12)["id"] == "PVTI_a"
        assert tool.board_item_for("owner", 1, "owner/repo-b", 12)["id"] == "PVTI_b"

    def test_a_pull_request_with_the_number_is_refused(self, tool, asked):
        assert tool.board_item_for("owner", 1, "owner/repo-c", 12) is None

    def test_the_right_project_among_several(self, tool, asked):
        assert tool.board_item_for("owner", 1, "owner/repo-a", 20) == {"id": "PVTI_20"}

    def test_an_issue_on_another_project_only_is_refused(self, tool, asked):
        assert tool.board_item_for("owner", 9, "owner/repo-a", 12) is None

    def test_another_accounts_project_with_the_number_is_refused(self, tool, asked):
        """A project number is only an identity with its owner."""
        assert tool.board_item_for("owner", 1, "owner/repo-a", 30) is None

    def test_the_owner_is_compared_without_case(self, tool, asked):
        assert tool.board_item_for("OWNER", 1, "owner/repo-a", 12) == {"id": "PVTI_a"}

    def test_an_archived_item_is_not_on_the_board(self, tool, asked):
        assert tool.board_item_for("owner", 1, "owner/repo-a", 40) is None

    def test_an_issue_on_no_project_returns_none(self, tool, asked):
        assert tool.board_item_for("owner", 1, "owner/repo-a", 50) is None

    def test_an_unknown_number_returns_none(self, tool, asked):
        assert tool.board_item_for("owner", 1, "owner/repo-a", 99) is None

    def test_a_repository_it_cannot_read_keeps_its_reason(self, tool, monkeypatch):
        def unreadable(query, **variables):
            raise SystemExit("gh api graphql failed: Could not resolve to a Repository")
        monkeypatch.setattr(tool, "graphql", unreadable)
        with pytest.raises(SystemExit, match="could not read issue owner/nowhere#12: .*Could not resolve"):
            tool.board_item_for("owner", 1, "owner/nowhere", 12)


class TestTheSprintComesFromTheItem:
    """A missing item read as one with no sprint (#231): `move` would have
    put it in the current sprint over whatever it held."""

    def test_item_sprint_asks_the_node(self, tool, monkeypatch):
        seen = []
        monkeypatch.setattr(tool, "graphql", lambda q, **v: seen.append((q, v)) or {
            "data": {"node": {"fieldValueByName": {"title": "0006 W42-2026"}}}})
        assert tool.item_sprint("PVTI_a") == "0006 W42-2026"
        assert seen[0][1] == {"i": "PVTI_a"} and "fieldValueByName" in seen[0][0]

    def test_an_empty_field_is_none(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "graphql",
                            lambda q, **v: {"data": {"node": {"fieldValueByName": None}}})
        assert tool.item_sprint("PVTI_a") is None

    def test_move_and_the_label_never_read_the_whole_board_for_it(self):
        """`sprint_assignments` pages `projectV2.items`, the list that left
        another team's #228 out. It stays for the iteration repairs, which need the
        whole board; one issue's move does not."""
        source = (pathlib.Path(__file__).resolve().parent.parent / "gh-agile").read_text()
        for name in ("def cmd_move", "def record_sprint_label"):
            body = source.split(name)[1].split("\ndef ")[0]
            assert "sprint_assignments(" not in body, name


class TestReconcileMatchesTheOwnerToo:
    def test_another_accounts_project_is_not_this_one(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "graphql", lambda q, **v: {"data": {"repository": {"issue": {
            "labels": {"nodes": []},
            "projectItems": {"nodes": [item("PVTI_theirs", owner="stranger")]}}}}})
        with pytest.raises(SystemExit, match="is not on project 1"):
            tool.issue_project_item("owner/repo-a", 30, 1, "owner")

    def test_its_own_is(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "graphql", lambda q, **v: {"data": {"repository": {"issue": {
            "labels": {"nodes": [{"name": "sprint:2026-10-12"}]},
            "projectItems": {"nodes": [{**item("PVTI_a"),
                                        "fieldValueByName": {"title": "0006"}}]}}}}})
        assert tool.issue_project_item("owner/repo-a", 12, 1, "owner") == (
            "PVTI_a", ["sprint:2026-10-12"], "0006")


class TestSelectByRef:
    """`validate --id`: a bare number is ambiguous across repositories, so refuse."""

    ROWS = [
        {"number": 12, "repository": "owner/repo-a", "title": "A's twelfth"},
        {"number": 12, "repository": "owner/repo-b", "title": "B's twelfth"},
        {"number": 13, "repository": "owner/repo-a", "title": "only one thirteen"},
    ]
    PROFILE = {"keys": [{"key": "AAA", "repo": "owner/repo-a"},
                        {"key": "BBB", "repo": "owner/repo-b"}]}

    def test_an_unambiguous_number_selects_one_row(self, tool):
        got = tool.select_by_ref(self.ROWS, "13", self.PROFILE)
        assert [r["repository"] for r in got] == ["owner/repo-a"]

    def test_an_ambiguous_number_refuses_and_names_both(self, tool, capsys):
        with pytest.raises(SystemExit) as exit_info:
            tool.select_by_ref(self.ROWS, "12", self.PROFILE)
        message = str(exit_info.value)
        assert "more than one repository" in message
        assert "owner/repo-a#12" in message and "owner/repo-b#12" in message

    def test_a_keyed_reference_disambiguates(self, tool):
        got = tool.select_by_ref(self.ROWS, "BBB-12", self.PROFILE)
        assert [r["repository"] for r in got] == ["owner/repo-b"]

    def test_a_missing_issue_refuses(self, tool):
        with pytest.raises(SystemExit):
            tool.select_by_ref(self.ROWS, "404", self.PROFILE)


class TestStatusAliases:
    """`In Progress` needs shell quoting; `In-Progress` does not, so both work."""

    @pytest.mark.parametrize("typed,canonical", [
        ("In-Progress", "In Progress"),
        ("in-progress", "In Progress"),
        ("In_Progress", "In Progress"),
        ("In Progress", "In Progress"),
        ("in progress", "In Progress"),
        ("In-Review", "In Review"),
        ("in-review", "In Review"),
        ("done", "Done"),
        ("DONE", "Done"),
        ("  Todo  ", "Todo"),
        ("blocked", "Blocked"),
    ])
    def test_aliases_canonicalise(self, tool, typed, canonical):
        assert tool.canonical_status(typed) == canonical

    def test_the_canonical_spelling_is_what_gets_written(self, tool):
        """GitHub holds the option name, so a hyphen must never reach the field."""
        for status in tool.STATUSES:
            assert tool.canonical_status(status.replace(" ", "-")) == status

    @pytest.mark.parametrize("bad", ["", "In Progres", "Reviewing", "In--Review-x", "closed"])
    def test_an_unknown_status_is_refused_and_lists_the_legal_ones(self, tool, bad):
        with pytest.raises(SystemExit) as exit_info:
            tool.canonical_status(bad)
        assert "In Progress" in str(exit_info.value)

    def test_same_status_sees_through_separators(self, tool):
        assert tool.same_status("In-Review", "In Review")
        assert tool.same_status("in_progress", "In Progress")
        assert not tool.same_status("In Review", "In Progress")
        assert not tool.same_status(None, "Todo")

    def test_cycle_boundaries_still_match_their_constants(self, tool):
        """Aliasing must not break the cycle-time clock."""
        assert tool.same_status("in-progress", tool.CYCLE_START)
        assert tool.same_status("Done", tool.CYCLE_END)
