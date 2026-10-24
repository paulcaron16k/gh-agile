"""Adding an issue GitHub has already boarded. AGILE-257.

Every `create` adds its new issue with `gh project item-add`. GitHub's own
workflows -- *Auto-add sub-issues*, and *Auto-add to project*, enabled on this
board on 2026-10-23 -- often get there first, and the add is refused with
`Content already exists in this project`. The fallback looked for the existing
item in the board list (`projectV2.items`), which #231 measured leaving a new
item out for hours, and matched on the number alone. #256 was on the board in
Todo; the lookup missed it, the command exited, and its priority was never set.
"""

from __future__ import annotations

import json

import pytest

URL = "https://github.com/o/r/issues/256"


class Ran:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


@pytest.fixture
def add(monkeypatch, tool):
    """`add_to_project` with `item-add` answering as given, and the board list
    forbidden: the point of #257 is that it is never read for this."""
    asked = []
    monkeypatch.setattr(tool, "board_items", lambda *a, **k: pytest.fail(
        "the board list was read to find one issue's item"))

    def go(answer, found=None):
        monkeypatch.setattr(tool.subprocess, "run", lambda cmd, **k: answer)
        monkeypatch.setattr(tool, "board_item_for",
                            lambda login, project, repo, number:
                            asked.append((login, project, repo, number)) or found)
        return tool.add_to_project("o", 4, URL)
    go.asked = asked
    return go


ALREADY = Ran(1, stderr="Content already exists in this project")


def test_a_fresh_add_returns_its_new_item(add):
    assert add(Ran(0, stdout=json.dumps({"id": "PVTI_new"}))) == "PVTI_new"


def test_an_issue_already_boarded_is_found_from_the_issue(add):
    """The item GitHub's workflow made, found at once -- #256's case."""
    assert add(ALREADY, found={"id": "PVTI_256"}) == "PVTI_256"


def test_by_repository_and_number(add):
    """Not the number alone: another repository on the board has a #256 too."""
    add(ALREADY, found={"id": "PVTI_256"})
    assert add.asked == [("o", 4, "o/r", 256)]


def test_an_item_that_truly_cannot_be_found_still_refuses(add):
    with pytest.raises(SystemExit, match="no item for it can be found"):
        add(ALREADY, found=None)


def test_any_other_failure_is_reported_as_itself(add):
    with pytest.raises(SystemExit, match="item-add failed: rate limited"):
        add(Ran(1, stderr="rate limited"))


def test_a_create_whose_add_raced_still_sets_its_fields(tool, monkeypatch, capsys):
    """End to end through `bug create`: the fields land on the found item."""
    written = []
    monkeypatch.setattr(tool, "require_sprint_config", lambda *a, **k: None)
    monkeypatch.setattr(tool, "require_key_for_prefix", lambda *a, **k: None)
    monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
    monkeypatch.setattr(tool, "create_issue", lambda *a, **k: (256, "I_256"))
    monkeypatch.setattr(tool, "apply_title_prefix", lambda *a, **k: a[-1])
    monkeypatch.setattr(tool.subprocess, "run", lambda cmd, **k: ALREADY)
    monkeypatch.setattr(tool, "board_item_for", lambda *a: {"id": "PVTI_256"})
    monkeypatch.setattr(tool, "board_items", lambda *a, **k: pytest.fail("board list read"))
    monkeypatch.setattr(tool, "set_field",
                        lambda o, p, item, name, value: written.append((item, name, value)))
    import argparse
    args = argparse.Namespace(title="t", repo="o/r", key="A", epic=None, points=None,
                              priority="low", intent=None, acceptance=None, owner="o",
                              project=4, _config={})
    assert tool.cmd_bug(args) == 0
    assert ("PVTI_256", "Priority", "low") in written and ("PVTI_256", "Status", "Todo") in written
