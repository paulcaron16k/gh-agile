"""The parent edge, and which level each column is true at.

**`epic_number` was the parent's number whatever the parent was.** Harmless while
the hierarchy had one edge, and wrong the moment an epic can sit under an
initiative: that epic's `epic_number` would hold an *initiative*, with nothing
saying so. So `parent_*` is the edge at any level and `epic_*` is populated only
when the parent really is an epic.

**And the keys are strings, which is the point rather than a preference.** GitHub
numbers issues per repository, so a board spanning repositories has two `#12` --
`github_issues` is keyed on `(repository, number)` for exactly that reason. The
old `epic_number` then handed out a parent reference with **no repository beside
it**, so a consumer joining it back to `number` could match the wrong
repository's issue silently. That is the defect `board_item_for` carries a comment
about, in the other direction.
"""

from __future__ import annotations

KEYS = {"o/one": "AGILE", "o/two": "REPORTS"}


def parent(number=9, repo="o/one", title="a parent", types=("epic",), keys=()):
    labels = [f"type:{t}" for t in types] + [f"key:{k}" for k in keys]
    return {"number": number, "title": title,
            "repository": {"nameWithOwner": repo},
            "labels": {"nodes": [{"name": n} for n in labels]}}


class TestNoParent:
    def test_every_column_is_empty(self, tool):
        row = tool.parent_columns(None, KEYS)
        assert row["parent_key"] == "" and row["parent_type"] == ""
        assert row["epic_key"] == "" and row["epic_number"] is None

    def test_epic_number_is_null_not_empty_string(self, tool):
        """An empty string in an integer column makes the type a union a loader
        cannot turn into DDL."""
        assert tool.parent_columns(None, KEYS)["epic_number"] is None


class TestAStoryUnderAnEpic:
    def test_the_edge_and_the_epic_agree(self, tool):
        row = tool.parent_columns(parent(9), KEYS)
        assert row["parent_key"] == "AGILE-9" and row["parent_type"] == "epic"
        assert row["epic_key"] == "AGILE-9" and row["epic_number"] == 9

    def test_epic_number_is_unchanged_from_before(self, tool):
        """No existing consumer's column changes meaning: every parent on a board
        today is an epic, because until now nothing else could be one."""
        assert tool.parent_columns(parent(9), KEYS)["epic_number"] == 9


class TestAnEpicUnderAnInitiative:
    def test_the_edge_is_recorded(self, tool):
        row = tool.parent_columns(parent(91, types=("initiative",)), KEYS)
        assert row["parent_key"] == "AGILE-91" and row["parent_type"] == "initiative"

    def test_but_it_is_not_called_an_epic(self, tool):
        """The whole reason `parent_*` exists. An epic's `epic_number` holding an
        initiative would be a join that silently returns the wrong row."""
        row = tool.parent_columns(parent(91, types=("initiative",)), KEYS)
        assert row["epic_key"] == "" and row["epic_number"] is None
        assert row["epic_title"] == ""


class TestKeysRatherThanNumbers:
    def test_a_parent_in_another_repository_is_unambiguous(self, tool):
        """Two repositories on one board both have a `#12`. A key says which."""
        row = tool.parent_columns(parent(12, repo="o/two"), KEYS)
        assert row["parent_key"] == "REPORTS-12"

    def test_the_same_number_in_two_repositories_gives_two_keys(self, tool):
        one = tool.parent_columns(parent(12, repo="o/one"), KEYS)["parent_key"]
        two = tool.parent_columns(parent(12, repo="o/two"), KEYS)["parent_key"]
        assert one == "AGILE-12" and two == "REPORTS-12" and one != two

    def test_the_parents_own_key_label_wins(self, tool):
        """Explicit beats assumed, the same rule `issue_key` follows, so a parent
        and the issue it parents cannot disagree about its name."""
        row = tool.parent_columns(parent(12, repo="o/one", keys=("WIDG",)), KEYS)
        assert row["parent_key"] == "WIDG-12"

    def test_a_repository_with_no_key_falls_back_to_the_github_form(self, tool):
        """Which an integer column cannot hold at all."""
        row = tool.parent_columns(parent(12, repo="o/other"), KEYS)
        assert row["parent_key"] == "o/other#12"

    def test_it_matches_what_issue_key_would_produce(self, tool):
        """So the self-join is `epic_key = issue_key`, one column, no ambiguity."""
        assert tool.parent_columns(parent(9), KEYS)["parent_key"] == \
            tool.key_for_issue(9, "o/one", [], KEYS)


class TestAnUntypedParent:
    def test_the_edge_is_still_recorded(self, tool):
        row = tool.parent_columns(parent(9, types=()), KEYS)
        assert row["parent_key"] == "AGILE-9" and row["parent_type"] == ""

    def test_but_nothing_is_claimed_about_the_level(self, tool):
        """A machine may not infer a type. Better an empty column than a guess."""
        assert tool.parent_columns(parent(9, types=()), KEYS)["epic_key"] == ""
