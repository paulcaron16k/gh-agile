"""Initiatives: a level above epic, which Jira's standard hierarchy does not have.

Jira tops out at Epic and charges for the levels above it, so free-tier teams
emulate an initiative with a label, a component or a custom field -- and then have
nowhere to write the plan down. GitHub's sub-issues nest, and across
repositories, so the level costs a label and a command here.

Measured before it was designed (sandbox, probes deleted): three levels link
cleanly, a child may live in another repository, roll-up counts children in both,
and roll-up is **not transitive** -- closing a story took its epic to 1/1 while
the initiative stayed 0/1.

**Two things, because they answer different questions.** The sub-issue edge is the
truth and rolls up; the `initiative:<slug>` label is what a board filter can see,
since a filter cannot traverse the hierarchy -- `FILTER_TERMS` evaluates one item
at a time. The hierarchy is the truth, the label is the index, which is the split
already made for sprints.

Offline: every `gh` call is captured.
"""

from __future__ import annotations

import json

import pytest


class TestTheSlug:
    @pytest.mark.parametrize("title,want", [
        ("Large new feature", "large-new-feature"),
        ("Export: the Gold model", "export-the-gold-model"),
        ("  spaces  everywhere  ", "spaces-everywhere"),
        ("PyIceberg 0.12", "pyiceberg-0-12"),
        (":::", "initiative"),
    ])
    def test_it_is_readable(self, tool, title, want):
        """Readable rather than an issue reference. The sprint precedent argues
        the other way -- a date is identity, a title is cosmetic -- but
        initiatives are few and long-lived, and `initiative:AGILE-91` on a card
        tells a person nothing."""
        assert tool.initiative_slug(title) == want

    def test_the_label_uses_a_colon(self, tool):
        """Like `type:`, `key:` and `sprint:`. `initiative-large-new-feature` has
        no unambiguous boundary between the prefix and the slug."""
        assert tool.INITIATIVE_LABEL == "initiative:"

    def test_initiative_is_a_type(self, tool):
        assert "initiative" in tool.ISSUE_TYPES


class Calls(list):
    """Captured `gh` argv, with what the fake GitHub should answer."""

    def __init__(self):
        super().__init__()
        self.state = {"listed": {}, "view": {}}


@pytest.fixture
def calls(monkeypatch, tool):
    """Capture `gh`, and let a test say which issues each repository holds."""
    seen = Calls()
    state = seen.state

    def fake_gh(args, **kwargs):
        seen.append(args)
        if args[:2] == ["issue", "list"]:
            repo = args[args.index("--repo") + 1]
            label = args[args.index("--label") + 1] if "--label" in args else ""
            return json.dumps(state["listed"].get((repo, label), []))
        if args[:2] == ["issue", "view"]:
            return json.dumps(state["view"])
        if args[:2] == ["issue", "create"]:
            return "https://github.com/o/r/issues/7\n"
        return "{}"

    monkeypatch.setattr(tool, "gh", fake_gh)
    monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
    return seen


CONFIG = {"keys": [{"key": "A", "repo": "o/one"}, {"key": "B", "repo": "o/two"}],
          "sprint": {"cadence_days": 14}}


class TestFindInitiative:
    def test_it_searches_every_repository_in_the_profile(self, tool, calls):
        """An initiative may span repositories -- that is the case it exists for --
        so this cannot be scoped to the clone the caller is standing in."""
        tool.find_initiative(CONFIG, "big-thing")
        searched = [c[c.index("--repo") + 1] for c in calls if c[:2] == ["issue", "list"]]
        assert sorted(searched) == ["o/one", "o/two"]

    def test_it_asks_for_both_labels(self, tool, calls):
        """The slug label alone would match every issue in the tree; the type
        label is what narrows it to the initiative itself."""
        tool.find_initiative(CONFIG, "big-thing")
        first = next(c for c in calls if c[:2] == ["issue", "list"])
        assert "initiative:big-thing" in first and "type:initiative" in first

    def test_it_finds_the_owner(self, tool, calls):
        calls.state["listed"][("o/two", "initiative:big-thing")] = [{"number": 12}]
        assert tool.find_initiative(CONFIG, "big-thing") == ("o/two", 12)

    def test_an_unclaimed_slug_is_none(self, tool, calls):
        assert tool.find_initiative(CONFIG, "big-thing") is None


class TestCreating:
    @pytest.fixture
    def create(self, monkeypatch, tool, calls, capsys):
        monkeypatch.setattr(tool, "create_issue", lambda *a, **k: (7, "I_7"))
        monkeypatch.setattr(tool, "apply_title_prefix", lambda *a, **k: a[-1])
        monkeypatch.setattr(tool, "add_to_project", lambda *a, **k: "PVTI_7")
        monkeypatch.setattr(tool, "set_field", lambda *a, **k: None)

        def go(title, **flags):
            import argparse
            args = argparse.Namespace(title=title, slug=None, repo="o/one", key="A",
                                      intent=None, acceptance=None, owner="o", project=1,
                                      _config=CONFIG)
            for name, value in flags.items():
                setattr(args, name, value)
            tool.cmd_initiative(args)
            return capsys.readouterr().out
        return go

    def test_it_labels_the_initiative_with_its_own_slug(self, tool, create, monkeypatch):
        """The issue carries the label, so it is the single authority for what the
        slug means."""
        labelled = {}
        monkeypatch.setattr(tool, "create_issue",
                            lambda repo, title, body, labels: labelled.setdefault(
                                "labels", labels) and (7, "I_7") or (7, "I_7"))
        create("Large new feature")
        assert "type:initiative" in labelled["labels"]
        assert "initiative:large-new-feature" in labelled["labels"]

    def test_it_reports_the_slug(self, tool, create):
        assert "initiative:large-new-feature" in create("Large new feature")

    def test_an_override(self, tool, create):
        assert "initiative:lnf" in create("Large new feature", slug="lnf")

    def test_a_taken_slug_is_refused(self, tool, create, calls):
        """Two initiatives answering to one slug put both trees behind one board
        filter and look entirely correct -- the failure an unreadable filter term
        is refused to avoid."""
        calls.state["listed"][("o/one", "initiative:large-new-feature")] = [{"number": 3}]
        with pytest.raises(SystemExit) as exit_info:
            create("Large new feature")
        message = str(exit_info.value)
        assert "already taken by o/one#3" in message and "--slug" in message


class TestAttaching:
    @pytest.fixture
    def attach(self, monkeypatch, tool, calls, capsys):
        linked = []
        monkeypatch.setattr(tool, "graphql",
                            lambda q, **v: linked.append(v) or {"data": {}})

        def go(ref, *, parent_labels=("type:initiative", "initiative:big-thing")):
            import argparse
            calls.state["view"] = {"id": "I_parent",
                                   "labels": [{"name": n} for n in parent_labels]}
            args = argparse.Namespace(initiative=ref, _config=CONFIG, repo="o/one")
            tool.attach_to_initiative(args, "o/one", 7, "I_7")
            return linked, capsys.readouterr().out
        return go

    def test_it_makes_the_sub_issue_edge(self, tool, attach, calls):
        calls.state["listed"][("o/one", "initiative:big-thing")] = [{"number": 3}]
        linked, _ = attach("big-thing")
        assert linked == [{"parent": "I_parent", "child": "I_7"}]

    def test_it_also_applies_the_label(self, tool, attach, calls):
        """Both, because a board filter cannot traverse the hierarchy."""
        calls.state["listed"][("o/one", "initiative:big-thing")] = [{"number": 3}]
        attach("big-thing")
        edits = [c for c in calls if c[:2] == ["issue", "edit"]]
        assert edits and edits[0][-2:] == ["--add-label", "initiative:big-thing"]

    def test_a_key_reference_works_too(self, tool, attach, calls):
        """`--initiative AGILE-91` as well as `--initiative big-thing`."""
        linked, out = attach("A-3")
        assert linked and "initiative:big-thing" in out

    def test_an_issue_that_is_not_an_initiative_is_refused(self, tool, attach):
        with pytest.raises(SystemExit) as exit_info:
            attach("A-3", parent_labels=("type:epic",))
        assert "is not an initiative" in str(exit_info.value)
