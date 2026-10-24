"""Project keys, issue references, and the issue-title prefix."""

from __future__ import annotations

import pytest

PROFILE = {
    "keys": [
        {"key": "WIDG", "repo": "o/widgets"},
        {"key": "PARTS", "repo": "o/widgets"},
        {"key": "AGILE", "repo": "o/gh-agile"},
    ],
    "project": {"number": 4, "key": "AGILE"},
}


class TestKeyFormat:
    """Jira's rules, plus one of ours that is load-bearing."""

    @pytest.mark.parametrize("key", ["ZM", "WIDG", "AGILE", "A1", "PROJECT123"])
    def test_legal_keys(self, tool, key):
        assert tool.key_problem(key) is None

    @pytest.mark.parametrize("key,because", [
        ("A", "too short"),
        ("VERYLONGPROJECTKEY", "over ten characters"),
        ("1ABC", "does not start with a letter"),
        ("my_key", "lowercase"),
        ("MY_KEY", "underscore"),
        ("MY KEY", "space"),
        ("", "empty"),
    ])
    def test_illegal_keys(self, tool, key, because):
        assert tool.key_problem(key) is not None, because

    def test_hyphen_is_rejected_because_it_breaks_references(self, tool):
        """`WIDG-34` is split on the last hyphen. A key containing one makes
        every reference ambiguous, so this is not merely Jira convention."""
        assert tool.key_problem("MY-KEY") is not None

    def test_the_message_says_what_is_wrong(self, tool):
        assert "letter" in tool.key_problem("1ABC")
        assert "2 to 10" in tool.key_problem("A")


class TestIssueReferences:
    def test_key_number_resolves_to_its_repository(self, tool):
        assert tool.parse_issue_ref("WIDG-34", PROFILE, None) == ("o/widgets", 34)

    def test_a_bare_number_uses_the_fallback_repository(self, tool):
        assert tool.parse_issue_ref("34", PROFILE, "o/gh-agile") == ("o/gh-agile", 34)

    def test_a_second_key_on_one_repo_resolves_to_the_same_repo(self, tool):
        """Mono-repo support: several keys may name one repository."""
        assert tool.parse_issue_ref("PARTS-7", PROFILE, None)[0] == "o/widgets"

    def test_an_unknown_key_is_refused(self, tool):
        with pytest.raises(SystemExit):
            tool.parse_issue_ref("NOPE-1", PROFILE, None)


class TestProfileLookups:
    def test_keys_for_repo_preserves_profile_order(self, tool):
        """The order is the default: the first key for a repo is the one used
        when --key is not given."""
        assert tool.keys_for_repo(PROFILE, "o/widgets") == ["WIDG", "PARTS"]

    def test_repo_for_key(self, tool):
        assert tool.repo_for_key(PROFILE, "AGILE") == "o/gh-agile"
        assert tool.repo_for_key(PROFILE, "MISSING") is None

    def test_issue_key_falls_back_to_repo_and_number(self, tool):
        """The column is never empty, so a row is always identifiable."""
        assert tool.issue_key("o/other", 9, {}) == "o/other#9"


class TestTitlePrefix:
    def test_off_is_the_default(self, tool):
        assert tool.title_prefix_mode({}) == "off"
        assert tool.title_prefix_mode({"project": {}}) == "off"

    @pytest.mark.parametrize("mode,expected", [
        ("off", "Retention policy"),
        ("key", "WIDG-34 Retention policy"),
        ("key+type", "WIDG-34 Epic: Retention policy"),
    ])
    def test_each_mode(self, tool, mode, expected):
        assert tool.prefixed_title(mode, "WIDG", 34, "epic", "Retention policy") == expected

    def test_story_capitalises_its_own_type(self, tool):
        assert tool.prefixed_title("key+type", "Z", 1, "story", "T") == "Z-1 Story: T"

    def test_booleans_are_accepted_as_hand_edits(self, tool):
        assert tool.title_prefix_mode({"project": {"issue_title_prefix": True}}) == "key"
        assert tool.title_prefix_mode({"project": {"issue_title_prefix": False}}) == "off"

    @pytest.mark.parametrize("bad", ["key-type", "KEY", "yes", "on", "key+"])
    def test_an_unrecognised_value_stops_the_run(self, tool, bad):
        """No nearest-legal guess: this setting decides what every issue is
        called, and a guess is written into issue titles."""
        with pytest.raises(SystemExit):
            tool.title_prefix_mode({"project": {"issue_title_prefix": bad}})

    def test_the_refusal_lists_the_legal_values(self, tool):
        with pytest.raises(SystemExit) as exit_info:
            tool.title_prefix_mode({"project": {"issue_title_prefix": "key-type"}})
        message = str(exit_info.value)
        assert all(mode in message for mode in tool.TITLE_PREFIX_MODES)
