"""Choosing a project item to write to, across repositories.

A project may span repositories, and each one numbers its issues independently
from 1, so two of them sharing a number is ordinary. `set` and `move` both
matched an item on the issue number alone: `set` resolved the repository and
discarded it, `move` kept it for the `gh issue` calls and still matched on the
number. A single `move B-12 --status Done --close` could therefore stamp Status
and a `sprint:` label onto an unrelated #12 in repository A while correctly
closing #12 in repository B, silently, reporting success.

These are the tests that would have caught it. They are pure -- `board_item_for`
takes the item list from `board_items`, so the fixture is the list.
"""

from __future__ import annotations

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


class TestBoardItemFor:
    def test_the_number_alone_is_not_enough(self, tool, board):
        """The defect: two repositories, one number, and a write went to the wrong one."""
        a = tool.board_item_for("owner", 1, "owner/repo-a", 12)
        b = tool.board_item_for("owner", 1, "owner/repo-b", 12)
        assert a["id"] == "PVTI_a"
        assert b["id"] == "PVTI_b"
        assert a["id"] != b["id"]

    def test_a_pull_request_sharing_the_number_is_skipped(self, tool, board):
        assert tool.board_item_for("owner", 1, "owner/repo-c", 12) is None

    def test_draft_items_and_empty_content_do_not_raise(self, tool, board):
        assert tool.board_item_for("owner", 1, "owner/nowhere", 12) is None
        assert tool.board_item_for("owner", 1, "owner/repo-a", None) is None

    def test_absent_issue_returns_none_rather_than_guessing(self, tool, board):
        assert tool.board_item_for("owner", 1, "owner/repo-a", 99) is None


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
