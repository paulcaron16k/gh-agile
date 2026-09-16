"""`move --add-assignee`: who a status change claims the issue for.

Starting work sets three things -- Status, Sprint, assignee -- and the first two
were already automatic. The rule these tests hold is the one the sprint heal
follows: **an unassigned issue is a gap, an assigned one is a decision.** The
implicit claim fills the gap and never argues with the decision; the explicit
flag is how somebody says otherwise.

Offline: every `gh` call is captured, so nothing here reaches GitHub.
"""

from __future__ import annotations

import json

import pytest


class Calls(list):
    """Every `gh` argv the run made, plus who the fake GitHub says holds the issue."""

    def __init__(self):
        super().__init__()
        self.assigned = []


@pytest.fixture
def calls(monkeypatch, tool):
    """Capture `gh` argv, and answer the one read `claim_issue` makes."""
    seen = Calls()

    def fake_gh(args, **kwargs):
        seen.append(args)
        if args[:2] == ["issue", "view"]:
            return json.dumps({"assignees": [{"login": who} for who in seen.assigned]})
        return ""

    monkeypatch.setattr(tool, "gh", fake_gh)
    return seen


def edits(calls):
    return [c for c in calls if c[:2] == ["issue", "edit"]]


class TestClaimIssue:
    def test_an_unassigned_issue_is_claimed_by_the_caller(self, tool, calls):
        message = tool.claim_issue("o/r", 7, "", explicit=False)
        assert edits(calls) == [["issue", "edit", "7", "--repo", "o/r",
                                "--add-assignee", "@me"]]
        assert "assigned to @me" in message

    def test_the_caller_is_at_me_and_not_a_guessed_login(self, tool, calls):
        """`gh` resolves it against the token it owns. The tool never sees one,
        and must not infer a username from a git config that may be anybody's."""
        tool.claim_issue("o/r", 7, "", explicit=False)
        assert tool.CALLER == "@me"
        assert edits(calls)[0][-1] == "@me"

    def test_an_issue_somebody_holds_is_left_alone(self, tool, calls):
        calls.assigned.append("someone-else")
        message = tool.claim_issue("o/r", 7, "", explicit=False)
        assert edits(calls) == []
        assert "already assigned to someone-else" in message
        assert "left alone" in message

    def test_the_explicit_flag_assigns_over_an_existing_assignee(self, tool, calls):
        calls.assigned.append("someone-else")
        message = tool.claim_issue("o/r", 7, "dev", explicit=True)
        assert edits(calls)[0][-2:] == ["--add-assignee", "dev"]
        assert "assigned to dev" in message

    def test_the_explicit_flag_does_not_pay_for_the_read(self, tool, calls):
        """Nothing about the answer depends on who holds it, so nothing asks."""
        tool.claim_issue("o/r", 7, "dev", explicit=True)
        assert [c for c in calls if c[:2] == ["issue", "view"]] == []

    def test_an_explicit_empty_value_is_the_caller(self, tool, calls):
        """A bare `--add-assignee` is somebody asking to be assigned. It names
        the same person the implicit claim would, and unlike it, says so over an
        existing assignee."""
        calls.assigned.append("someone-else")
        message = tool.claim_issue("o/r", 7, "", explicit=True)
        assert edits(calls)[0][-2:] == ["--add-assignee", "@me"]
        assert "assigned to @me" in message

    def test_it_adds_rather_than_replaces(self, tool, calls):
        """`--add-assignee`, like `--add-label`: the additive primitive, so two
        people on one issue is expressible and nothing is silently dropped."""
        tool.claim_issue("o/r", 7, "dev", explicit=True)
        assert "--add-assignee" in edits(calls)[0]
        assert not any(a.startswith("--remove") for a in edits(calls)[0])


class TestMoveClaimsTheIssue:
    """The wiring: which statuses claim, and which leave the issue alone."""

    @pytest.fixture
    def move(self, monkeypatch, tool, calls):
        """`cmd_move` with everything but the assignee decision stubbed out."""
        claims = []
        monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 7))
        monkeypatch.setattr(tool, "board_item_for", lambda *a, **k: {"id": "PVTI_7"})
        monkeypatch.setattr(tool, "set_field", lambda *a, **k: None)
        monkeypatch.setattr(tool, "sprint_assignments", lambda *a, **k: {"PVTI_7": "s"})
        monkeypatch.setattr(tool, "record_sprint_label", lambda *a, **k: None)
        # Its own story (#117); stubbed so these tests stay about `move`.
        monkeypatch.setattr(tool, "promote_parents", lambda *a, **k: None)
        monkeypatch.setattr(tool, "claim_issue",
                            lambda repo, issue, wanted, *, explicit:
                                claims.append((wanted, explicit)) or "  claimed")

        def run(status, add_assignee=None):
            args = argparse_namespace(tool, status=status, add_assignee=add_assignee)
            tool.cmd_move(args)
            return claims

        return run

    def test_in_progress_claims_without_the_flag(self, tool, move):
        assert move("In Progress") == [("", False)]

    def test_the_hyphen_spelling_claims_too(self, tool, move):
        """`In-Progress` and `In Progress` are the same transition everywhere else."""
        assert move("In-Progress") == [("", False)]

    def test_another_status_does_not_claim_on_its_own(self, tool, move):
        assert move("Blocked") == []

    def test_the_flag_claims_whatever_the_status(self, tool, move):
        assert move("Blocked", add_assignee="dev") == [("dev", True)]

    def test_a_bare_flag_claims_whatever_the_status(self, tool, move):
        """Given at all is somebody asking. Found live: this printed nothing at
        all on `--status Blocked --add-assignee`, because "" was read as "not
        given" rather than "given, meaning me"."""
        assert move("Blocked", add_assignee="") == [("", True)]

    def test_a_bare_flag_is_explicit_even_where_the_rule_would_have_claimed(self, tool, move):
        assert move("In Progress", add_assignee="") == [("", True)]

    def test_whitespace_is_not_a_login_but_is_still_a_request(self, tool, move):
        assert move("In Progress", add_assignee="  ") == [("", True)]

    def test_a_login_is_stripped(self, tool, move):
        assert move("In Progress", add_assignee=" dev ") == [("dev", True)]


def argparse_namespace(tool, **overrides):
    import argparse
    args = argparse.Namespace(
        issue="7", repo="o/r", owner="o", project=1, close=False, not_planned=False,
        evidence=None, evidence_file=None, add_assignee=None,
        _config={"sprint": {"cadence_days": 14}},
    )
    for name, value in overrides.items():
        setattr(args, name, value)
    return args


class TestTheFlagIsParsed:
    """Through the real parser, because `nargs="?"` is the whole point: without
    it a bare `--add-assignee` is an argparse error rather than "me"."""

    @staticmethod
    def parsed(tool, monkeypatch, argv):
        import sys as _sys
        captured = {}

        def capture(args):
            captured["args"] = args
            return 0

        monkeypatch.setattr(tool, "require_interpreter", lambda: None)
        monkeypatch.setattr(tool, "apply_defaults", lambda args: None)
        monkeypatch.setattr(tool, "cmd_move", capture)
        monkeypatch.setattr(_sys, "argv", ["gh-agile", *argv])
        tool.main()
        return captured["args"]

    @pytest.mark.parametrize("extra,want", [
        ([], None),
        (["--add-assignee"], ""),
        (["--add-assignee", "dev"], "dev"),
        (["--add-assignee", ""], ""),
    ])
    def test_absent_empty_and_named(self, tool, monkeypatch, extra, want):
        args = self.parsed(tool, monkeypatch,
                           ["move", "7", "--status", "In Progress", *extra])
        assert args.add_assignee == want

    def test_a_bare_flag_does_not_swallow_the_next_option(self, tool, monkeypatch):
        args = self.parsed(tool, monkeypatch,
                           ["move", "7", "--add-assignee", "--status", "In Progress"])
        assert args.add_assignee == "" and args.status == "In Progress"
