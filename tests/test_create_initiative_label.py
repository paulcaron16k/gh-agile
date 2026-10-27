"""A story or bug filed under an epic carries the epic's initiative. AGILE-281.

Found live while testing AGILE-270: `story create --epic 63`, where #63 sits
under an initiative and carries `initiative:rp-a-1120`, made a story labelled
`type:story,key:TEST` only. The sub-issue edge was right, and a board filtered
to the initiative still left the story out until `initiative reconcile` ran.
"""

from __future__ import annotations

import argparse
import json

import pytest


@pytest.fixture
def create(monkeypatch, tool, capsys):
    """`story create` or `bug create` under a stubbed epic with `epic_labels`."""
    def go(command, epic_labels, epic="9"):
        record = {"created": [], "ensured": []}
        monkeypatch.setattr(tool, "require_sprint_config", lambda *a, **k: None)
        monkeypatch.setattr(tool, "require_key_for_prefix", lambda *a, **k: None)
        monkeypatch.setattr(tool, "ensure_labels",
                            lambda repo, labels: record["ensured"].extend(labels))
        monkeypatch.setattr(tool, "create_issue",
                            lambda *a, **k: record["created"].append(a) or (7, "I_7"))
        monkeypatch.setattr(tool, "apply_title_prefix", lambda *a, **k: a[-1])
        monkeypatch.setattr(tool, "add_to_project", lambda *a, **k: "PVTI_7")
        monkeypatch.setattr(tool, "set_field", lambda *a, **k: None)
        monkeypatch.setattr(tool, "graphql", lambda q, **v: {"data": {}})
        monkeypatch.setattr(tool, "gh", lambda a, **k: json.dumps(
            {"id": "I_9", "labels": [{"name": n} for n in epic_labels]}))
        args = argparse.Namespace(
            title="A piece of work", repo="o/r", key="A", epic=epic, points=None,
            priority=None, intent=None, acceptance=None, owner="o", project=1, _config={})
        getattr(tool, command)(args)
        capsys.readouterr()
        return record
    return go


@pytest.mark.parametrize("command", ["cmd_story", "cmd_bug"])
def test_the_epics_initiative_is_on_the_new_issue(create, command):
    record = create(command, ["type:epic", "key:A", "initiative:big-thing"])
    labels = record["created"][0][3]
    assert "initiative:big-thing" in labels
    assert "initiative:big-thing" in record["ensured"]


@pytest.mark.parametrize("command", ["cmd_story", "cmd_bug"])
def test_an_epic_under_no_initiative_adds_none(create, command):
    labels = create(command, ["type:epic", "key:A"])["created"][0][3]
    assert not [label for label in labels if label.startswith("initiative:")]


def test_a_bug_standing_alone_has_none(create):
    labels = create("cmd_bug", [], epic=None)["created"][0][3]
    assert not [label for label in labels if label.startswith("initiative:")]


def test_only_initiative_labels_are_inherited(create):
    """The epic's own `type:` and `key:` are its business, not the story's."""
    labels = create("cmd_story", ["type:epic", "key:OTHER", "initiative:x", "area:ui"])[
        "created"][0][3]
    assert "type:epic" not in labels and "key:OTHER" not in labels
    assert "area:ui" not in labels and "initiative:x" in labels
