"""`gh agile plan` -- dates on an epic or initiative that already exists. AGILE-183.

**The dates arrive after the plan does.** A team designs, breaks the work into
epics, and schedules later -- when somebody is free, when a quarter is agreed,
when a dependency lands. `--start` on `epic` and `initiative` only works while
the issue is being created, which is the one moment a team usually does not know.

Its own command rather than a mode on three others, on the precedent of `move`:
starting work is one call because Status, Sprint, the label and the assignee are
one decision. Both dates are one decision too, and `set` writes one field per
invocation.

Offline. `set_field` and `clear_field` are captured, because what is under test
here is which of them is called with what -- the argv each builds is
`tests/test_set_field_types.py`.
"""

from __future__ import annotations

import argparse

import pytest

EPIC = ["type:epic", "key:AGILE"]
INITIATIVE = ["type:initiative", "key:AGILE"]
STORY = ["type:story", "key:AGILE"]


class TestPlannedDates:
    """Parsing, with no board in sight."""

    def test_both_dates_are_returned_in_field_order(self, tool):
        assert tool.planned_dates("2026-10-01", "2026-12-19") == [
            ("Start date", "2026-10-01"), ("Target date", "2026-12-19")]

    def test_the_fields_are_the_same_two_creation_writes(self, tool):
        got = [name for name, _ in tool.planned_dates("2026-10-01", "2026-12-19")]
        assert tuple(got) == tool.DATE_FIELDS

    def test_one_alone_says_nothing_about_the_other(self, tool):
        assert tool.planned_dates(None, "2026-12-19") == [("Target date", "2026-12-19")]

    def test_none_is_a_clear_not_a_date(self, tool):
        assert tool.planned_dates("none", None) == [("Start date", None)]

    def test_clearing_is_case_insensitive_and_forgives_a_space(self, tool):
        assert tool.planned_dates(" None ", None) == [("Start date", None)]

    def test_absent_and_cleared_stay_tellable_apart(self, tool):
        """Both are falsey and they are different instructions."""
        assert tool.planned_dates(None, None) == []
        assert tool.planned_dates("none", "none") == [
            ("Start date", None), ("Target date", None)]

    def test_the_same_parser_as_creation_decides(self, tool):
        """Not a second parser. A second one is free to disagree about a date,
        and `2026-1-5` -- not ISO, and plausible -- is where it would."""
        with pytest.raises(SystemExit) as through_plan:
            tool.planned_dates("2026-1-5", None)
        with pytest.raises(SystemExit) as at_creation:
            tool.iso_date("2026-1-5", "--start")
        assert str(through_plan.value) == str(at_creation.value)

    def test_a_bad_date_is_refused_naming_its_flag(self, tool):
        with pytest.raises(SystemExit) as caught:
            tool.planned_dates("2026-10-01", "soon")
        assert "--target" in str(caught.value)


@pytest.fixture
def plan(monkeypatch, tool, capsys):
    """Drive `cmd_plan`, capturing every write and never touching a board."""
    def go(start=None, target=None, *, labels=EPIC, on_board=True):
        written, cleared = [], []
        monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 7))
        monkeypatch.setattr(tool, "issue_labels", lambda *a, **k: labels)
        monkeypatch.setattr(tool, "board_item_for",
                            lambda *a, **k: {"id": "PVTI_7"} if on_board else None)
        monkeypatch.setattr(tool, "set_field",
                            lambda login, project, item, name, v: written.append((name, v)))
        monkeypatch.setattr(tool, "clear_field",
                            lambda login, project, item, name: cleared.append(name))
        go.written, go.cleared = written, cleared    # survive a SystemExit
        args = argparse.Namespace(issue="7", repo="o/r", owner="o", project=1,
                                  start=start, target=target, _config={})
        tool.cmd_plan(args)
        return written, cleared, capsys.readouterr().out
    return go


class TestWhatItWrites:
    def test_both_dates_in_one_call(self, plan):
        written, _cleared, _out = plan("2026-10-01", "2026-12-19")
        assert written == [("Start date", "2026-10-01"), ("Target date", "2026-12-19")]

    def test_one_alone_leaves_the_other_untouched(self, plan):
        written, cleared, _out = plan(target="2026-12-19")
        assert written == [("Target date", "2026-12-19")]
        assert cleared == []

    def test_none_clears_rather_than_writing(self, plan):
        written, cleared, _out = plan(start="none")
        assert written == []
        assert cleared == ["Start date"]

    def test_a_date_and_a_clear_in_the_same_call(self, plan):
        """Re-planning: the target moves, the start comes off."""
        written, cleared, _out = plan(start="none", target="2027-03-31")
        assert written == [("Target date", "2027-03-31")]
        assert cleared == ["Start date"]

    def test_an_initiative_is_planned_the_same_way(self, plan):
        written, _cleared, _out = plan("2026-10-01", labels=INITIATIVE)
        assert written == [("Start date", "2026-10-01")]

    def test_it_says_what_it_wrote(self, plan):
        _w, _c, out = plan("2026-10-01", "none")
        assert "Start date = 2026-10-01" in out
        assert "Target date cleared" in out


class TestWhatItRefuses:
    def test_neither_flag_is_refused(self, plan):
        with pytest.raises(SystemExit) as caught:
            plan()
        assert "--start" in str(caught.value) and "--target" in str(caught.value)

    def test_neither_flag_writes_nothing(self, plan):
        """A command that changes nothing should say so, not exit 0 quietly."""
        with pytest.raises(SystemExit):
            plan()
        assert plan.written == [] and plan.cleared == []

    def test_a_story_is_refused(self, plan):
        with pytest.raises(SystemExit) as caught:
            plan("2026-10-01", labels=STORY)
        assert "not an epic or an initiative" in str(caught.value)

    def test_the_refusal_says_what_a_story_uses_instead(self, plan):
        with pytest.raises(SystemExit) as caught:
            plan("2026-10-01", labels=STORY)
        assert "sprint" in str(caught.value).casefold()

    def test_a_story_is_written_nothing(self, plan):
        with pytest.raises(SystemExit):
            plan("2026-10-01", labels=STORY)
        assert plan.written == [] and plan.cleared == []

    def test_an_untyped_issue_is_refused(self, plan):
        """A machine may not infer a type, so it does not plan one either."""
        with pytest.raises(SystemExit):
            plan("2026-10-01", labels=["key:AGILE"])
        assert plan.written == []

    def test_an_issue_not_on_the_board_is_refused(self, plan):
        with pytest.raises(SystemExit) as caught:
            plan("2026-10-01", on_board=False)
        assert "is not on project" in str(caught.value)

    def test_one_bad_date_writes_neither(self, plan):
        """Half a plan is worse than a refusal: the good half looks deliberate."""
        with pytest.raises(SystemExit):
            plan("2026-10-01", "soon")
        assert plan.written == [] and plan.cleared == []


class TestSetRefusesTheSameThing:
    """The sanctioned path and the generic one agree, or the rule is a hope."""

    @pytest.fixture
    def setter(self, monkeypatch, tool):
        def go(field, labels):
            written = []
            monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 7))
            monkeypatch.setattr(tool, "board_item_for", lambda *a, **k: {"id": "PVTI_7"})
            monkeypatch.setattr(tool, "issue_labels", lambda *a, **k: labels)
            monkeypatch.setattr(tool, "set_field",
                                lambda login, project, item, name, v: written.append((name, v)))
            go.written = written
            args = argparse.Namespace(issue="7", repo="o/r", owner="o", project=1,
                                      field=field, value="2026-10-01", number=None, _config={})
            tool.cmd_set(args)
            return written
        return go

    @pytest.mark.parametrize("field", ["Start date", "Target date", "target date"])
    def test_a_date_on_a_story_is_refused(self, setter, field):
        with pytest.raises(SystemExit) as caught:
            setter(field, STORY)
        assert "not an epic or an initiative" in str(caught.value)

    def test_the_refusal_names_plan(self, setter):
        with pytest.raises(SystemExit) as caught:
            setter("Start date", STORY)
        assert "gh agile plan" in str(caught.value)

    def test_nothing_is_written(self, setter):
        with pytest.raises(SystemExit):
            setter("Start date", STORY)
        assert setter.written == []

    def test_a_date_on_an_epic_still_goes_through(self, setter):
        assert setter("Start date", EPIC) == [("Start date", "2026-10-01")]

    def test_another_field_on_a_story_is_untouched(self, setter):
        assert setter("FR", STORY) == [("FR", "2026-10-01")]


class TestEveryIssueCommandCanResolveARepository:
    """A command that names an issue and is not in `NEEDS_REPO` cannot take a
    bare number, even from inside the right clone.

    `plan` shipped that way for an hour: `plan 19` answered *needs a
    repository: run inside one*, from inside one. `set --issue 26` had the same
    hour years earlier, which is what put the comment above that set. The set is
    hand-maintained and the parser is the record of which commands touch an
    issue, so this compares the two rather than trusting either.
    """

    def leaves(self, tool):
        """`(name, parser)` for every subcommand, including nested ones."""
        import argparse
        found = []

        def walk(parser, prefix=""):
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    for name, sub in action.choices.items():
                        walk(sub, prefix or name)
                        found.append((prefix or name, sub))
        walk(tool.build_parser())
        return found

    def test_the_walk_finds_something(self, tool):
        """A test over an empty list passes for the wrong reason."""
        assert len(self.leaves(tool)) > 10

    def test_every_command_naming_an_issue_needs_a_repo(self, tool):
        needs = tool.NEEDS_REPO
        # `issue` only, not `--id`: `validate --id 24` filters the board read and
        # never resolves a repository, which the walk reported the first time this
        # ran. The dest under test is the one that becomes an issue reference.
        missing = sorted({
            name for name, parser in self.leaves(tool)
            if any(a.dest == "issue" for a in parser._actions) and name not in needs
        })
        assert missing == [], f"not in NEEDS_REPO: {missing}"
