"""An epic follows its children into progress. AGILE-117, under #114.

Nothing moved an epic out of `Todo`. Its stories started, ran and closed beneath
it while it read as untouched, and the only thing that ever changed it was
somebody remembering to -- the bookkeeping this tool exists to remove. On the
backlog an epic in `Todo` with a child in flight is indistinguishable from one
nobody has touched, which is what #114 was raised for.

`validate` already did this arithmetic in both *closed* directions -- an epic
finished over an open child, and an epic left open with every child closed. The
third case, a child started under a parent that has not, was missing, and it is
the one that misreads a board daily rather than at the end.

Two halves. `move` carries a start upward; `validate` reports the divergence for
a status set by hand or work begun outside the tool.

**Promoted only from `Todo` or empty, never demoted.** The rule the sprint heal
already follows: an empty field is damage, a set one is a decision. An epic
somebody put in `Blocked` is a decision, and a tool that overwrites it argues
with the person using it.

Offline: the parent-chain query and every write are stubbed.
"""

from __future__ import annotations

import argparse

import pytest

PROJECT = 1


def level(number, kind, status, *, on_board=True, project=PROJECT, parent=None):
    """A node as `PARENT_CHAIN_QUERY` returns one."""
    items = []
    if on_board:
        items.append({
            "id": f"PVTI_{number}",
            "project": {"number": project},
            "fieldValueByName": {"name": status} if status else None,
        })
    node = {
        "number": number,
        "repository": {"nameWithOwner": "o/r"},
        "labels": {"nodes": [{"name": f"type:{kind}"}]},
        "projectItems": {"nodes": items},
    }
    if parent is not None:
        node["parent"] = parent
    return node


@pytest.fixture
def promote(monkeypatch, tool, capsys):
    """`promote_parents` with the chain query answered from a fixture."""
    def run(chain, *, raises=None):
        written = []

        def fake_graphql(query, **variables):
            if raises:
                raise raises
            return {"data": {"repository": {"issue": {"parent": chain}}}}

        monkeypatch.setattr(tool, "graphql", fake_graphql)
        monkeypatch.setattr(tool, "set_field",
                            lambda login, project, item, name, value:
                                written.append((item, name, value)))
        args = argparse.Namespace(owner="o", project=PROJECT, _config={})
        tool.promote_parents(args, "o/r", 7)
        out = capsys.readouterr()
        return written, out.out, out.err
    return run


class TestItCarriesTheStartUpward:
    def test_a_todo_epic_is_promoted(self, tool, promote):
        written, out, _ = promote(level(9, "epic", "Todo"))
        assert written == [("PVTI_9", "Status", "In Progress")]
        assert "#9 epic follows its child" in out

    def test_an_unset_status_is_damage_and_is_filled(self, tool, promote):
        written, _, _ = promote(level(9, "epic", None))
        assert written == [("PVTI_9", "Status", "In Progress")]

    def test_the_initiative_above_follows_too(self, tool, promote):
        """Both levels: an initiative is as invisible as the epic was."""
        chain = level(9, "epic", "Todo", parent=level(5, "initiative", "Todo"))
        written, _, _ = promote(chain)
        assert written == [("PVTI_9", "Status", "In Progress"),
                           ("PVTI_5", "Status", "In Progress")]

    def test_an_epics_own_start_promotes_only_the_initiative(self, tool, promote):
        written, _, _ = promote(level(5, "initiative", "Todo"))
        assert written == [("PVTI_5", "Status", "In Progress")]

    def test_the_promotion_is_reported(self, tool, promote):
        """Never silent: a field written without a word is a field nobody knows about."""
        _written, out, _ = promote(level(9, "epic", "Todo"))
        assert "Status = In Progress" in out


class TestItNeverArguesWithADecision:
    @pytest.mark.parametrize("status", ["Blocked", "In Review", "In Progress", "Done"])
    def test_any_other_status_is_left_alone(self, tool, promote, status):
        written, out, _ = promote(level(9, "epic", status))
        assert written == []
        assert out == "", "a non-event should not be reported on every start"

    def test_nothing_is_ever_demoted(self, tool, promote):
        """A parent does not return to Todo because a child paused."""
        written, _, _ = promote(level(9, "epic", "Done"))
        assert written == []

    def test_a_partly_started_chain_promotes_only_what_is_stalled(self, tool, promote):
        chain = level(9, "epic", "In Progress", parent=level(5, "initiative", "Todo"))
        written, _, _ = promote(chain)
        assert written == [("PVTI_5", "Status", "In Progress")]


class TestWhatItWillNotTouch:
    def test_a_parent_that_is_not_a_spanning_level_is_left_alone(self, tool, promote):
        """Once tasks exist, a task starting must not move its story."""
        written, _, _ = promote(level(9, "story", "Todo"))
        assert written == []

    def test_a_parent_not_on_this_board_is_left_alone(self, tool, promote):
        """`sync` is what puts it there; promoting something absent is not this
        command's business."""
        written, _, _ = promote(level(9, "epic", "Todo", on_board=False))
        assert written == []

    def test_a_parent_on_another_project_is_not_matched(self, tool, promote):
        written, _, _ = promote(level(9, "epic", "Todo", project=99))
        assert written == []

    def test_no_parent_at_all_is_not_an_error(self, tool, promote):
        written, out, err = promote(None)
        assert written == [] and out == "" and err == ""


class TestAFailedReadIsNotFatal:
    def test_it_reports_and_returns(self, tool, promote):
        """The status write has already succeeded; failing here would report an
        error for an issue that moved correctly."""
        written, _out, err = promote(None, raises=SystemExit("boom"))
        assert written == []
        assert "could not read the parents" in err


class TestValidateReportsTheDivergence:
    @pytest.fixture
    def validate(self, monkeypatch, tool, capsys):
        def go(*rows, only=None, selected=None):
            monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
            monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
                [{"title": "S2", "startDate": "2026-08-31", "duration": 14}], []))
            if selected is not None:
                monkeypatch.setattr(tool, "select_by_ref",
                                    lambda data, ref, cfg: list(selected))
            tool.cmd_validate(argparse.Namespace(owner="o", project=PROJECT,
                                                 _config={}, id=only))
            return capsys.readouterr().out
        return go

    @staticmethod
    def issue(number, key, kind, status, *, parent_key="", parent_type="",
              state="OPEN"):
        return {
            "number": number, "issue_key": key, "title": f"issue {number}",
            "repository": "o/r", "state": state, "state_reason": "",
            "labels": f"type:{kind}", "field_status": status, "field_sprint": "S2",
            "assignees": "someone",
            "epic_number": None, "parent_key": parent_key, "parent_type": parent_type,
            "sub_issues_total": 1 if kind in ("epic", "initiative") else 0,
            "sub_issues_done": 0, "started_at": "", "done_at": "",
        }

    def test_a_todo_epic_over_a_started_child_is_reported(self, tool, validate):
        out = validate(
            self.issue(9, "A-9", "epic", "Todo"),
            self.issue(10, "A-10", "story", "In Progress",
                       parent_key="A-9", parent_type="epic"),
        )
        assert "epic is Todo with a child In Progress" in out
        assert "A-9" in out

    def test_one_finding_per_parent_not_per_child(self, tool, validate):
        """The thing to fix is the parent, once."""
        out = validate(
            self.issue(9, "A-9", "epic", "Todo"),
            *[self.issue(n, f"A-{n}", "story", "In Progress",
                         parent_key="A-9", parent_type="epic") for n in (10, 11, 12)],
        )
        assert out.count("A-9 (Todo)") == 1

    def test_a_started_parent_is_not_reported(self, tool, validate):
        out = validate(
            self.issue(9, "A-9", "epic", "In Progress"),
            self.issue(10, "A-10", "story", "In Progress",
                       parent_key="A-9", parent_type="epic"),
        )
        assert "with a child In Progress" not in out

    def test_a_parent_somebody_chose_a_status_for_is_not_reported(self, tool, validate):
        """Same rule as the promotion: a set field is a decision."""
        out = validate(
            self.issue(9, "A-9", "epic", "Blocked"),
            self.issue(10, "A-10", "story", "In Progress",
                       parent_key="A-9", parent_type="epic"),
        )
        assert "with a child In Progress" not in out

    def test_a_story_parent_is_not_reported(self, tool, validate):
        out = validate(
            self.issue(9, "A-9", "story", "Todo"),
            self.issue(10, "A-10", "story", "In Progress",
                       parent_key="A-9", parent_type="story"),
        )
        assert "with a child In Progress" not in out

    def test_the_parent_is_found_even_when_id_narrows_the_report(self, tool, validate):
        """`--id` narrows what is *reported*; the parent's status is still needed
        to judge the child, and the parent may not be among the issues asked
        about. Read from the whole board for exactly that reason."""
        epic = self.issue(9, "A-9", "epic", "Todo")
        story = self.issue(10, "A-10", "story", "In Progress",
                           parent_key="A-9", parent_type="epic")
        out = validate(epic, story, only="10", selected=[story])
        assert "with a child In Progress" in out


class TestAContainerIsNeverClaimed:
    """Promotion sets a status and nothing else.

    An epic holds stories worked by several people, so there is no single *who
    has this*. Filling it from whoever started the first story is a guess that is
    only ever right at team size one -- and it is the same guess `sync --adopt`
    refuses to make about a type.
    """

    def test_the_promotion_writes_only_the_status(self, tool, promote):
        written, _out, _err = promote(level(9, "epic", "Todo"))
        assert [name for _item, name, _value in written] == ["Status"]

    def test_it_does_not_reach_for_the_assignee(self, tool, monkeypatch, promote):
        claimed = []
        monkeypatch.setattr(tool, "claim_issue",
                            lambda *a, **k: claimed.append(a) or "  claimed")
        promote(level(9, "epic", "Todo", parent=level(5, "initiative", "Todo")))
        assert claimed == []
