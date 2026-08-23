"""Whose project is this? docs/review-2026-08.md S3.

`--owner` defaulted to `@me` and the profile recorded a project *number* with no
owner, so `project.number: 4` meant "project 4 belonging to whoever typed this".
Invisibly correct for the owner, which is why it lasted. For anyone else it
resolves to nothing -- so `export`, `validate`, `sprint list` and `board list` do
not work even with project read access -- or, worse, to an unrelated project 4 of
their own, onto which `sync --adopt` would then label issues.

Precedence, most explicit first: the flag, then `project.owner`, then the caller.
"""

from __future__ import annotations

import argparse

import pytest

DECLARED = {"project": {"number": 4, "owner": "boardowner"}}
NO_OWNER = {"project": {"number": 4}}


@pytest.fixture
def caller(monkeypatch, tool):
    """Stub the `gh api user` call, and record whether it happened at all."""
    calls = []

    def login():
        calls.append(1)
        return "thecaller"

    monkeypatch.setattr(tool, "caller_login", login)
    return calls


def args_for(owner=None, command="validate"):
    return argparse.Namespace(owner=owner, command=command)


class TestResolveOwner:
    def test_the_profile_wins_when_no_flag_is_given(self, tool, caller):
        args = args_for()
        tool.resolve_owner(args, DECLARED)
        assert args.owner == "boardowner"

    def test_the_profile_saves_the_api_call_entirely(self, tool, caller):
        """One fewer REST round trip per invocation, and REST is the tighter budget."""
        tool.resolve_owner(args_for(), DECLARED)
        assert caller == []

    def test_the_caller_is_the_fallback_when_the_profile_is_silent(self, tool, caller):
        args = args_for()
        tool.resolve_owner(args, NO_OWNER)
        assert args.owner == "thecaller"
        assert len(caller) == 1

    def test_an_explicit_owner_wins_over_the_profile_when_they_agree(self, tool, caller):
        args = args_for("boardowner")
        tool.resolve_owner(args, DECLARED)
        assert args.owner == "boardowner"
        assert caller == []

    @pytest.mark.parametrize("spelling", ["BoardOwner", "BOARDOWNER", "boardowner"])
    def test_a_login_is_matched_case_insensitively(self, tool, caller, spelling):
        """GitHub logins are case-insensitive; refusing on case would be a lie."""
        args = args_for(spelling)
        tool.resolve_owner(args, DECLARED)
        assert args.owner == spelling

    @pytest.mark.parametrize("me", ["@me", "me", "  @me  ", "@ME"])
    def test_at_me_always_means_the_caller_even_when_the_profile_names_someone_else(
        self, tool, caller, me,
    ):
        args = args_for(me)
        tool.resolve_owner(args, DECLARED)
        assert args.owner == "thecaller"
        assert len(caller) == 1

    def test_an_explicit_owner_is_used_when_the_profile_declares_none(self, tool, caller):
        args = args_for("someoneelse")
        tool.resolve_owner(args, NO_OWNER)
        assert args.owner == "someoneelse"
        assert caller == []

    def test_a_disagreeing_owner_is_refused_and_both_are_named(self, tool, caller):
        """The same reasoning as a disagreeing --project: right flag, wrong clone."""
        with pytest.raises(SystemExit) as exit_info:
            tool.resolve_owner(args_for("someoneelse"), DECLARED)
        message = str(exit_info.value)
        assert "someoneelse" in message
        assert "boardowner" in message
        assert "project.owner" in message

    def test_self_test_is_exempt_from_the_refusal(self, tool, caller):
        """It builds its own scratch project, as it is exempt from the --project check."""
        args = args_for("someoneelse", command="self-test")
        tool.resolve_owner(args, DECLARED)
        assert args.owner == "someoneelse"

    def test_an_empty_profile_falls_back_to_the_caller(self, tool, caller):
        args = args_for()
        tool.resolve_owner(args, {})
        assert args.owner == "thecaller"

    def test_a_missing_owner_attribute_does_not_raise(self, tool, caller):
        """`self-test` builds synthetic namespaces; not every one carries `owner`."""
        args = argparse.Namespace(command="validate")
        tool.resolve_owner(args, DECLARED)
        assert args.owner == "boardowner"
