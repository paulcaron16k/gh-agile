"""`issue edit --epic` and `--initiative`: moving an issue in the hierarchy. AGILE-270.

`--epic` existed only on `story create` and `bug create`, and `--initiative` only
on `epic create`, so moving a story to another epic -- ordinary backlog grooming
in Jira -- was web-UI only, and left the `initiative:` label wrong until somebody
ran `initiative reconcile`. A move is now one `addSubIssue` with `replaceParent`,
then a reconcile of every initiative it touched.
"""

from __future__ import annotations

import pytest

#: The issues on a small board: number -> (labels, parent number or None).
BOARD = {
    10: (["type:initiative", "initiative:alpha"], None),
    11: (["type:initiative", "initiative:beta"], None),
    20: (["type:epic", "initiative:alpha"], 10),
    21: (["type:epic", "initiative:beta"], 11),
    22: (["type:epic"], None),
    30: (["type:story", "initiative:alpha"], 20),
    31: (["type:bug"], None),
    32: (["type:story"], 22),
    33: (["type:story"], 20),
    40: (["type:task"], 30),
}


def node(number):
    labels, parent = BOARD[number]
    out = {"id": f"I_{number}", "number": number, "repository": {"nameWithOwner": "o/r"},
           "labels": {"nodes": [{"name": n} for n in labels]}}
    if parent is not None:
        out["parent"] = node(parent)
    return out


@pytest.fixture
def move(monkeypatch, tool, capsys, edit_args):
    """`issue edit` against `BOARD`, recording mutations and reconciles."""
    def go(*argv):
        calls = go.calls = {"mutations": [], "reconciled": []}

        def graphql(query, **variables):
            if query.lstrip().startswith("mutation"):
                calls["mutations"].append((query.split("(input:")[0].split("{")[-1].strip(),
                                           variables, "replaceParent: true" in query))
                return {"data": {}}
            return {"data": {"repository": {"issue": node(variables["number"])}}}

        monkeypatch.setattr(tool, "graphql", graphql)
        monkeypatch.setattr(tool, "parse_issue_ref",
                            lambda ref, cfg, repo: ("o/r", int(str(ref).rsplit("-", 1)[-1])))
        monkeypatch.setattr(tool, "gh", lambda a, **k: pytest.fail(f"gh {a}"))
        monkeypatch.setattr(tool, "resolve_initiative",
                            lambda cfg, ref, repo: ("o/r", int(ref)))
        monkeypatch.setattr(tool, "initiative_target", lambda cfg, ref, repo: {
            "repo": "o/r", "number": int(ref), "id": f"I_{ref}",
            "slug": BOARD[int(ref)][0][1].split(":", 1)[1]})
        slugs = {"alpha": ("o/r", 10), "beta": ("o/r", 11)}
        monkeypatch.setattr(tool, "find_initiative", lambda cfg, slug: slugs.get(slug))
        monkeypatch.setattr(tool, "reconcile_initiative",
                            lambda args, target: calls["reconciled"].append(target["slug"]))
        code = tool.cmd_edit(edit_args(*argv))
        calls["out"] = capsys.readouterr().out
        return code, calls
    return go


class TestAStoryChangesEpic:
    def test_one_call_replaces_the_parent(self, move):
        _code, calls = move("30", "--epic", "21")
        assert calls["mutations"] == [
            ("addSubIssue", {"parent": "I_21", "child": "I_30"}, True)]
        assert "#30 under epic #21 (was #20)" in calls["out"]

    def test_both_initiatives_are_reconciled(self, move):
        """It leaves alpha's tree and joins beta's: both labels change."""
        _code, calls = move("30", "--epic", "21")
        assert calls["reconciled"] == ["alpha", "beta"]

    def test_an_epic_under_no_initiative_reconciles_only_the_old_one(self, move):
        _code, calls = move("30", "--epic", "22")
        assert calls["reconciled"] == ["alpha"]

    def test_the_old_epics_initiative_counts_even_unlabelled(self, move):
        """`story create` does not stamp `initiative:`; the old parent says it."""
        _code, calls = move("33", "--epic", "21")
        assert calls["reconciled"] == ["alpha", "beta"]

    def test_a_bug_moves_too(self, move):
        _code, calls = move("31", "--epic", "22")
        assert calls["mutations"][0][1] == {"parent": "I_22", "child": "I_31"}
        assert "#31 under epic #22" in calls["out"] and "was" not in calls["out"]

    def test_none_takes_it_off_its_epic(self, move):
        _code, calls = move("30", "--epic", "none")
        assert calls["mutations"] == [
            ("removeSubIssue", {"parent": "I_20", "child": "I_30"}, False)]
        assert "#30 off epic #20, standing alone" in calls["out"]
        assert calls["reconciled"] == ["alpha"]

    def test_the_same_epic_changes_nothing(self, move):
        _code, calls = move("30", "--epic", "20")
        assert calls["mutations"] == [] and calls["reconciled"] == []
        assert "already" in calls["out"]


class TestAnEpicChangesInitiative:
    def test_moved_and_both_trees_reconciled(self, move):
        _code, calls = move("20", "--initiative", "11")
        assert calls["mutations"] == [
            ("addSubIssue", {"parent": "I_11", "child": "I_20"}, True)]
        assert calls["reconciled"] == ["alpha", "beta"]
        assert "#20 under initiative #11 (was #10)" in calls["out"]

    def test_an_epic_under_none_joins_one(self, move):
        _code, calls = move("22", "--initiative", "10")
        assert calls["reconciled"] == ["alpha"]


class TestRefusedBeforeAnyWrite:
    @pytest.mark.parametrize("argv,said", [
        (("30", "--initiative", "10"), "A story goes under an epic: --epic"),
        (("20", "--epic", "21"), "An epic goes under an initiative"),
        (("40", "--epic", "20"), "is a task"),
        (("30", "--epic", "31"), "is a bug, not an epic"),
        (("30", "--epic", "21", "--initiative", "10"), "give one of them"),
    ])
    def test_the_wrong_level(self, move, argv, said):
        with pytest.raises(SystemExit) as refused:
            move(*argv)
        assert said.casefold() in str(refused.value).casefold()

    def test_one_bad_issue_stops_them_all(self, move):
        """`issue edit 30 40 --epic 21`: the task is refused, and the story,
        named first, is not moved either."""
        with pytest.raises(SystemExit) as refused:
            move("30", "40", "--epic", "21")
        assert "is a task" in str(refused.value)
        assert move.calls["mutations"] == [] and move.calls["reconciled"] == []


class TestDryRun:
    def test_says_and_writes_nothing(self, move):
        _code, calls = move("30", "--epic", "21", "--dry-run")
        assert calls["mutations"] == [] and calls["reconciled"] == []
        assert "would move #30 under epic #21 (was #20)" in calls["out"]
        assert "would reconcile initiative:alpha" in calls["out"]
        assert "would reconcile initiative:beta" in calls["out"]
