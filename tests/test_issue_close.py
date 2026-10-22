"""`issue close` and `issue reopen`, and the one door Status goes through. #202.

`move --close --not-planned` was the only close, and `--not-planned` without
`--close` was parsed, accepted and dropped. `gh issue close -r "not planned" -c`
is the spelling `gh` users already have -- the cleanup of ZMBNI-185 was exactly
that -- so it is the spelling here.

**Nothing reaches Done without evidence.** `issue move` is where Done asks for
it, and there were two other routes that did not: `story --status Done`, and
`set --field Status`. Both are gone. `issue close -r completed` is the Done path
entire, and only `-r "not planned"` -- where nothing was done -- skips the
evidence and the `sprint:` label.

Every door is tried below, through the real `cmd_move`, with only GitHub stubbed.
"""

from __future__ import annotations

import argparse

import pytest

FILLED = "## Intent\nx\n\n## Acceptance\ny\n\n## Evidence\nthe numbers\n"
EMPTY = "## Intent\nx\n\n## Acceptance\ny\n\n## Evidence\n_TBD_\n"


@pytest.fixture
def board(monkeypatch, tool):
    """Every write `cmd_move` makes, against one issue whose body is settable."""
    record = {"order": [], "closed": [], "labels": [], "status": [], "gh": [],
              "body": FILLED}

    def fake_gh(argv, **kwargs):
        record["gh"].append(argv)
        return ""

    monkeypatch.setattr(tool, "gh", fake_gh)
    monkeypatch.setattr(tool, "board_item_for", lambda *a, **k: {"id": "PVTI_7"})
    monkeypatch.setattr(tool, "issue_body", lambda *a, **k: record["body"])
    monkeypatch.setattr(tool, "issue_labels", lambda *a, **k: ["type:story"])
    monkeypatch.setattr(tool, "sprint_assignments", lambda *a, **k: {"PVTI_7": "s"})
    monkeypatch.setattr(tool, "promote_parents", lambda *a, **k: None)
    monkeypatch.setattr(tool, "claim_issue", lambda *a, **k: "  claimed")

    def close_issue(repo, issue, *, not_planned, comment=None):
        record["order"].append("close")
        record["closed"].append((not_planned, comment))

    def set_field(owner, project, item, field, value):
        record["order"].append(f"{field}={value}")
        record["status"].append(value)

    def record_sprint_label(args, repo, issue, item, *, not_planned=False):
        record["labels"].append(not_planned)
        return None if not_planned else "sprint:2026-10-12"

    monkeypatch.setattr(tool, "close_issue", close_issue)
    monkeypatch.setattr(tool, "set_field", set_field)
    monkeypatch.setattr(tool, "record_sprint_label", record_sprint_label)
    return record


def parsed(tool, *argv):
    args = tool.build_parser().parse_args(list(argv))
    args.owner, args.project, args.repo = "o", 1, "o/r"
    args._config = {"sprint": {"cadence_days": 14},
                    "keys": [{"key": "ZMBNI", "repo": "o/zamboni"}]}
    return args


class TestCloseCompleted:
    def test_it_is_the_done_path(self, tool, board):
        tool.cmd_close(parsed(tool, "issue", "close", "7"))
        assert board["closed"] == [(False, None)]
        assert board["status"] == ["Done"]
        assert board["labels"] == [False]

    def test_it_closes_before_it_writes_status(self, tool, board):
        """A project's auto-close-on-Done workflow would otherwise get there first
        and record `COMPLETED` over the reason asked for (#96)."""
        tool.cmd_close(parsed(tool, "issue", "close", "7"))
        assert board["order"][:2] == ["close", "Status=Done"]

    def test_it_needs_evidence(self, tool, board):
        board["body"] = EMPTY
        with pytest.raises(SystemExit):
            tool.cmd_close(parsed(tool, "issue", "close", "7"))
        assert board["closed"] == [] and board["status"] == []

    def test_offered_evidence_satisfies_it(self, tool, board):
        board["body"] = EMPTY
        tool.cmd_close(parsed(tool, "issue", "close", "7", "--evidence", "the numbers"))
        assert board["status"] == ["Done"]

    def test_the_comment_goes_with_the_close(self, tool, board):
        tool.cmd_close(parsed(tool, "issue", "close", "7", "-c", "shipped in #208"))
        assert board["closed"] == [(False, "shipped in #208")]


class TestCloseNotPlanned:
    def test_nothing_was_done_so_no_evidence_is_asked(self, tool, board):
        board["body"] = EMPTY
        tool.cmd_close(parsed(tool, "issue", "close", "7", "-r", "not planned"))
        assert board["closed"] == [(True, None)]

    def test_status_still_becomes_done(self, tool, board):
        """A closed issue on any other Status is live work to every board filter."""
        tool.cmd_close(parsed(tool, "issue", "close", "7", "-r", "not planned"))
        assert board["status"] == ["Done"]

    def test_no_sprint_label_is_stamped(self, tool, board):
        """A `sprint:` label asserts the sprint work was done in."""
        tool.cmd_close(parsed(tool, "issue", "close", "7", "-r", "not planned"))
        assert board["labels"] == [True]

    def test_the_zmbni_185_cleanup_is_one_command(self, tool, board):
        tool.cmd_close(parsed(tool, "issue", "close", "ZMBNI-185",
                              "-r", "not planned", "-c", "created by mistake"))
        assert board["closed"] == [(True, "created by mistake")]

    def test_only_gh_reasons_are_accepted(self, tool):
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args(["issue", "close", "7", "-r", "wontfix"])


class TestReopen:
    def test_it_reopens_and_moves_status_back_to_todo(self, tool, board):
        tool.cmd_reopen(parsed(tool, "issue", "reopen", "7"))
        assert board["gh"][0][:3] == ["issue", "reopen", "7"]
        assert board["status"] == ["Todo"]
        assert board["closed"] == []

    def test_a_status_can_be_named(self, tool, board):
        tool.cmd_reopen(parsed(tool, "issue", "reopen", "7", "--status", "in-progress"))
        assert board["status"] == ["In Progress"]

    def test_the_comment_goes_with_it(self, tool, board):
        tool.cmd_reopen(parsed(tool, "issue", "reopen", "7", "-c", "not finished"))
        assert board["gh"][0][-2:] == ["--comment", "not finished"]


class TestEveryOtherDoorIsShut:
    def test_move_no_longer_closes(self, tool):
        for flag in ("--close", "--not-planned"):
            with pytest.raises(SystemExit):
                tool.build_parser().parse_args(["issue", "move", "7", "Done", flag])

    @pytest.mark.parametrize("field", ["Status", "status", " STATUS "])
    def test_edit_refuses_status_and_names_move(self, tool, board, field):
        args = parsed(tool, "issue", "edit", "7", "--field", field, "--value", "Done")
        with pytest.raises(SystemExit) as exit_info:
            tool.cmd_edit(args)
        assert "issue move ISSUE STATUS" in str(exit_info.value)
        assert board["status"] == []

    def test_story_create_has_no_status(self, tool):
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args(
                ["story", "create", "-t", "T", "--epic", "none", "--status", "Done"])

    def test_a_new_story_is_todo(self, tool, monkeypatch, board):
        import json
        monkeypatch.setattr(tool, "gh", lambda a, **k: json.dumps({"id": "I_1", "labels": []}))
        monkeypatch.setattr(tool, "require_sprint_config", lambda *a, **k: None)
        monkeypatch.setattr(tool, "require_key_for_prefix", lambda *a, **k: None)
        monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
        monkeypatch.setattr(tool, "create_issue", lambda *a, **k: (7, "I_7"))
        monkeypatch.setattr(tool, "apply_title_prefix", lambda *a, **k: a[-1])
        monkeypatch.setattr(tool, "add_to_project", lambda *a, **k: "PVTI_7")
        monkeypatch.setattr(tool, "graphql", lambda *a, **k: {"data": {}})
        args = argparse.Namespace(title="T", repo="o/r", key="A", epic="none",
                                  points=None, priority=None, intent=None,
                                  acceptance=None, owner="o", project=1, _config={})
        tool.cmd_story(args)
        assert board["status"] == ["Todo"]


class TestTheRetiredSpellings:
    @pytest.mark.parametrize("argv,suggested", [
        (["move", "185", "--status", "Done", "--not-planned", "--close"],
         "gh agile issue close 185 -r 'not planned'"),
        (["move", "ZMBNI-34", "--status", "Done", "--close", "--evidence-file", "e.md"],
         "gh agile issue close ZMBNI-34 --evidence-file e.md"),
        (["story", "create", "-t", "S", "--epic", "none", "--status", "In Progress"],
         "gh agile issue move <number> 'In Progress'"),
        (["story", "S", "--epic", "none", "--status=Blocked"],
         "gh agile story create -t S --epic none"),
    ])
    def test_each_names_its_replacement(self, tool, argv, suggested):
        assert suggested in tool.retired_spelling(argv)

    def test_a_todo_status_needs_no_second_command(self, tool):
        hint = tool.retired_spelling(["story", "create", "-t", "S", "--epic", "none",
                                      "--status", "Todo"])
        assert "issue move" not in hint
