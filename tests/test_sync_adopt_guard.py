"""`sync --adopt` counts before it writes. docs/review-2026-08.md S7.

`--adopt` is the one sync path that writes to the *issues* rather than only to
the board: a `key:` label on each, and a rename when a title prefix is
configured. With `--state open --limit 200` and no confirmation it has already
swept a whole live repository once, which is in docs/lessons.md.

The tool refuses before less consequential acts -- `require_graphql_budget`
before an iteration write, the Makefile's title check before a teardown -- so
this was the loudest thing with no gate. Plain `sync` is deliberately still
ungated: adding an item to a board writes nothing to the issue.
"""

from __future__ import annotations

import argparse
import json

import pytest


def issues(count: int, start: int = 1) -> list[dict]:
    return [
        {"number": n, "title": f"issue {n}", "url": f"https://github.com/o/r/issues/{n}",
         "state": "OPEN", "labels": []}
        for n in range(start, start + count)
    ]


@pytest.fixture
def board(monkeypatch, tool):
    """An empty board, and every `gh` call answered locally. Records the adds."""
    added: list[str] = []
    adopted: list[int] = []

    def fake_gh(cmd, **_kwargs):
        if cmd[:2] == ["issue", "list"]:
            return json.dumps(fake_gh.listing)
        if cmd[:2] == ["project", "item-add"]:
            url = cmd[cmd.index("--url") + 1]
            added.append(url)
            return json.dumps({"id": f"PVTI_{len(added)}"})
        raise AssertionError(f"unexpected gh call: {cmd}")

    fake_gh.listing = []
    monkeypatch.setattr(tool, "gh", fake_gh)
    monkeypatch.setattr(tool, "board_items", lambda *a, **k: [])
    monkeypatch.setattr(tool, "adopt_issue",
                        lambda args, repo, issue, item_id: adopted.append(issue["number"]))
    return argparse.Namespace(gh=fake_gh, added=added, adopted=adopted)


def args_for(*, adopt=False, yes=False, dry_run=False, limit=200):
    return argparse.Namespace(
        repo="o/r", state="open", query=None, limit=limit, dry_run=dry_run,
        adopt=adopt, yes=yes, owner="o", project=4, _config={},
        command="sync", config=None,
    )


class TestAdoptGuard:
    def test_above_the_threshold_it_refuses_and_writes_nothing(self, tool, board, capsys):
        board.gh.listing = issues(12)
        with pytest.raises(SystemExit) as exit_info:
            tool.cmd_sync(args_for(adopt=True))
        message = str(exit_info.value)
        assert "12 issues" in message
        assert str(tool.ADOPT_CONFIRM_ABOVE) in message
        assert "--dry-run" in message and "--yes" in message
        # Nothing was written: the count is taken before the first add.
        assert board.added == []
        assert board.adopted == []

    def test_the_refusal_shows_a_sample_and_says_how_many_more(self, tool, board):
        board.gh.listing = issues(12)
        with pytest.raises(SystemExit) as exit_info:
            tool.cmd_sync(args_for(adopt=True))
        message = str(exit_info.value)
        assert "o/r#1" in message
        assert "and 7 more" in message          # five shown, twelve found

    def test_yes_proceeds(self, tool, board):
        board.gh.listing = issues(12)
        assert tool.cmd_sync(args_for(adopt=True, yes=True)) == 0
        assert len(board.added) == 12
        assert len(board.adopted) == 12

    def test_at_the_threshold_it_does_not_ask(self, tool, board):
        """Ten is the number it stops asking about, not the number it refuses."""
        board.gh.listing = issues(tool.ADOPT_CONFIRM_ABOVE)
        assert tool.cmd_sync(args_for(adopt=True)) == 0
        assert len(board.adopted) == tool.ADOPT_CONFIRM_ABOVE

    def test_plain_sync_is_not_gated_however_many(self, tool, board):
        """Adding an item to a board writes nothing to the issue, so it needs no gate."""
        board.gh.listing = issues(50)
        assert tool.cmd_sync(args_for(adopt=False)) == 0
        assert len(board.added) == 50
        assert board.adopted == []

    def test_dry_run_lists_everything_and_writes_nothing(self, tool, board, capsys):
        board.gh.listing = issues(12)
        assert tool.cmd_sync(args_for(adopt=True, dry_run=True)) == 0
        out = capsys.readouterr().out
        assert "would add 12" in out
        assert board.added == [] and board.adopted == []

    def test_issues_already_on_the_board_are_not_counted(self, tool, board, monkeypatch):
        """The count is candidates, not the listing -- otherwise it nags about no-ops."""
        board.gh.listing = issues(12)
        monkeypatch.setattr(tool, "board_items", lambda *a, **k: [
            {"id": f"PVTI_{n}", "content": {"number": n, "repository": "o/r", "type": "Issue"}}
            for n in range(1, 12)          # eleven of the twelve already present
        ])
        assert tool.cmd_sync(args_for(adopt=True)) == 0
        assert board.adopted == [12]
