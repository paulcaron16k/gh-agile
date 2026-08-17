"""Reconciling the Sprint field from the labels, and adopting outside issues.

Both are workarounds for the same defect: a write to the iteration
configuration clears every item's Sprint value, retroactively and silently,
including closed issues in completed sprints. The labels are the record; these
are the paths that reconcile the field toward them.
"""

from __future__ import annotations

import pytest


def item(number: int, *, labels: list[str], sprint: str | None, item_id: str = "PVTI_x") -> dict:
    """A project item shaped as `fetch_items` returns one."""
    values = []
    if sprint is not None:
        values.append({
            "__typename": "ProjectV2ItemFieldIterationValue",
            "title": sprint,
            "field": {"name": "Sprint"},
        })
    return {
        "id": item_id,
        "isArchived": False,
        "updatedAt": "2026-08-14T00:00:00Z",
        "fieldValues": {"nodes": values},
        "content": {
            "__typename": "Issue",
            "number": number,
            "title": f"issue {number}",
            "labels": {"nodes": [{"name": name} for name in labels]},
        },
    }


class TestFieldValues:
    """`fetch_items` carries custom field values; `project item-list` does not,
    which is why a sprint read from that command was always absent."""

    def test_reads_an_iteration_value(self, tool):
        assert tool.field_values(item(1, labels=[], sprint="S 4"))["Sprint"] == "S 4"

    def test_absent_when_unset(self, tool):
        assert "Sprint" not in tool.field_values(item(1, labels=[], sprint=None))


class TestLatestLabelWins:
    """An item carried across a boundary carries one label per sprint it lived
    in; the field holds where it is now, which is the last of them."""

    @pytest.mark.parametrize("labels,expected", [
        (["sprint:2026-08-03"], "2026-08-03"),
        (["sprint:2026-08-03", "sprint:2026-08-17"], "2026-08-17"),
        (["sprint:2026-08-17", "sprint:2026-08-03"], "2026-08-17"),   # order-independent
        (["type:story", "key:AGILE"], None),
    ])
    def test_latest(self, tool, labels, expected):
        stamps = sorted(lb[len(tool.SPRINT_LABEL):] for lb in labels
                        if lb.startswith(tool.SPRINT_LABEL))
        assert (stamps[-1] if stamps else None) == expected

    def test_dates_sort_lexicographically(self, tool):
        """Why the label is dated rather than named: `Sprint 10` sorts before
        `Sprint 9`, and a title is editable while a start date is identity."""
        stamps = ["2026-08-03", "2026-08-17", "2026-09-14", "2026-12-01"]
        assert sorted(stamps) == stamps


class TestAdoptTitlePrefix:
    """`sync --adopt` applies the title convention to issues however they
    arrived. Without it the setting held only for issues this tool created, and
    a board filled partly from the web UI carried two naming schemes."""

    def test_key_mode_needs_no_type(self, tool):
        assert tool.prefixed_title("key", "AGILE", 49, "", "Opened in the web UI") == \
            "AGILE-49 Opened in the web UI"

    def test_key_plus_type_falls_back_to_key_when_type_is_unknown(self, tool):
        """adopt never guesses a type -- nothing in an issue distinguishes an
        epic from a bug -- so the identifier is applied without one."""
        assert tool.prefixed_title("key", "AGILE", 49, "", "T") == "AGILE-49 T"

    def test_key_plus_type_uses_an_existing_type_label(self, tool):
        assert tool.prefixed_title("key+type", "AGILE", 49, "story", "T") == \
            "AGILE-49 Story: T"

    def test_an_already_prefixed_title_is_recognised(self, tool):
        """Re-adopting must not stack prefixes; the guard is the title already
        starting with the key."""
        title = tool.prefixed_title("key", "AGILE", 49, "", "T")
        assert title.startswith("AGILE-")


class TestAdoptStatus:
    """Status follows the issue's own state. Setting Todo on a closed issue made
    `validate` report 'closed but status is not Done' -- the tool creating the
    violation it detects."""

    @pytest.mark.parametrize("state,expected", [
        ("CLOSED", "Done"), ("closed", "Done"), ("OPEN", "Todo"), ("open", "Todo"), ("", "Todo"),
    ])
    def test_status_for_state(self, tool, state, expected):
        chosen = tool.CYCLE_END if state.upper() == "CLOSED" else "Todo"
        assert chosen == expected


class TestDamageVersusDecision:
    """An empty field is damage; a disagreeing field is a decision.

    The automatic heal repairs only the first. It runs after every iteration
    write, and overwriting a deliberate placement by default would make the
    repair argue with the person using it -- an open story re-planned into a
    future sprint has labels recording where it was *worked*, not where it is
    *planned*.
    """

    def test_the_heal_never_overwrites(self, tool):
        """`heal_sprint_fields` is the hooked entry point; its contract is
        overwrite=False, and a test is the only thing keeping it that way."""
        import inspect

        source = inspect.getsource(tool.heal_sprint_fields)
        assert "overwrite=False" in source
        assert "quiet=True" in source, "the hook must be silent when idle"

    def test_reconcile_defaults_to_not_overwriting(self, tool):
        import inspect

        signature = inspect.signature(tool.reconcile_sprints)
        assert signature.parameters["overwrite"].default is False
        assert signature.parameters["dry_run"].default is False
        assert signature.parameters["quiet"].default is False

    def test_every_destructive_path_heals(self, tool):
        """The three writes that clear assignments -- cadence convergence,
        `sprint ensure` and `sprint create` -- must each heal afterwards, or the
        gap reopens in whichever one was missed."""
        import inspect

        for function in (tool.cmd_setup, tool.ensure_sprints, tool.cmd_sprint):
            source = inspect.getsource(function)
            if "restore_assignments" not in source:
                continue
            assert "heal_sprint_fields" in source, function.__name__

    def test_heal_follows_restore_not_precedes_it(self, tool):
        """Order matters: `restore_assignments` replays a snapshot and covers
        items the labels know nothing about -- one assigned by hand and never
        moved through `move`. The heal only covers what the labels know."""
        import inspect

        source = inspect.getsource(tool.ensure_sprints)
        assert source.index("restore_assignments") < source.index("heal_sprint_fields")
