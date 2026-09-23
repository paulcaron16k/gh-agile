"""A verdict for every built-in workflow, not three of six. AGILE-141.

The tool reports the *symptoms* one at a time and never the cause. `validate`
says `closed but status is not Done`; `board show` marks the row and names the
repair; both are true, and neither says **why the board keeps producing that
state**. On this project the answer is one line: `Item closed` is off, so an
issue closed by a pull request's `Closes #n` keeps whatever Status it had. #123
sat in the In Progress column for twenty-two hours and #138 repeated it on
merge.

#162 built the read and named the three worth turning on. **Silence about the
other three is the defect this story is really about**: the obvious repair --
turn on what is off -- is pointless for two of them and actively harmful for
one. `Auto-close issue` looks exactly like a missing setting and is what beat
`move` to the close on the sandbox, costing `--not-planned` its reason (#96).

So each of the six carries a verdict and a reason, in **one table** read by
`init` at configuration time and `validate` when somebody is chasing a symptom.
Two lists giving different advice about one setting is the drift #157 spent five
stories on.
"""

from __future__ import annotations

import argparse

import pytest

ALL_OFF = dict.fromkeys((
    "Item closed", "Item added to project", "Auto-add sub-issues to project",
    "Auto-close issue", "Pull request merged", "Pull request linked to issue"),
    False)
#: A board configured as the table recommends: all three `enable` ones on, the
#: harmful one off, and the two pull-request ones off on a board of issues.
CORRECT = {**ALL_OFF, "Auto-add sub-issues to project": True,
           "Item closed": True, "Item added to project": True}


class TestTheTableCoversEverything:
    def test_every_workflow_has_a_verdict(self, tool):
        """Three of six is not advice: the reader turns on what is off."""
        assert len(tool.WORKFLOW_ADVICE) == 6

    @pytest.mark.parametrize("name", sorted(ALL_OFF))
    def test_each_one_by_name(self, tool, name):
        assert name in tool.WORKFLOW_ADVICE

    def test_every_verdict_is_one_of_the_three(self, tool):
        verdicts = {v for v, _why in tool.WORKFLOW_ADVICE.values()}
        assert verdicts <= {"enable", "never", "issues-only"}

    def test_every_entry_carries_a_reason(self, tool):
        assert all(len(why) > 30 for _v, why in tool.WORKFLOW_ADVICE.values())

    def test_auto_close_is_never(self, tool):
        """It races the tool's own close and wins."""
        verdict, why = tool.WORKFLOW_ADVICE["Auto-close issue"]
        assert verdict == "never"
        assert "#96" in why

    def test_the_pull_request_ones_are_scoped_to_the_board(self, tool):
        for name in ("Pull request merged", "Pull request linked to issue"):
            assert tool.WORKFLOW_ADVICE[name][0] == "issues-only"


class TestValidateReportsOnlyWhatDiverges:
    def test_an_enable_that_is_off_is_reported(self, tool):
        found = tool.workflow_findings(ALL_OFF, 0)
        assert any("Item closed is off" in line for line in found)

    def test_an_enable_that_is_on_is_not(self, tool):
        found = tool.workflow_findings(CORRECT, 0)
        assert not any("Auto-add sub-issues" in line for line in found)

    def test_a_never_that_is_off_is_not_reported(self, tool):
        """Off is correct for it; saying so on every run is noise."""
        assert not any("Auto-close" in line for line in tool.workflow_findings(CORRECT, 0))

    def test_a_never_that_is_ON_is_reported_loudly(self, tool):
        found = tool.workflow_findings({**CORRECT, "Auto-close issue": True}, 0)
        line = next(x for x in found if "Auto-close" in x)
        assert "should not be" in line and "#96" in line

    def test_a_pull_request_workflow_on_a_board_of_issues_is_reported(self, tool):
        found = tool.workflow_findings({**CORRECT, "Pull request merged": True}, 0)
        assert any("no pull-request items" in line for line in found)

    def test_but_not_on_a_board_that_holds_pull_requests(self, tool):
        """The assumption expires; the count is what notices."""
        found = tool.workflow_findings({**CORRECT, "Pull request merged": True}, 4)
        assert not any("Pull request merged" in line for line in found)

    def test_a_workflow_whose_state_is_unknown_is_skipped(self, tool):
        """Read, not guessed at."""
        assert tool.workflow_findings({}, 0) == []

    def test_a_correct_board_reports_nothing(self, tool):
        assert tool.workflow_findings(CORRECT, 0) == []


class TestTheFullTableIsForConfiguring:
    def test_it_names_all_six(self, tool):
        text = "\n".join(tool.render_workflow_table(CORRECT, 0))
        for name in ALL_OFF:
            assert name in text

    def test_a_never_carries_its_reason_even_when_correct(self, tool):
        """**The point of the table.** `Auto-close issue` is off on a correct
        board and looks exactly like a missing setting, so a reader scanning
        things that are off would turn on the one that cost `--not-planned`
        its reason."""
        text = "\n".join(tool.render_workflow_table(CORRECT, 0))
        assert "races this tool's own close" in text

    def test_an_issues_only_carries_its_reason_even_when_correct(self, tool):
        text = "\n".join(tool.render_workflow_table(CORRECT, 0))
        assert "acts on pull-request items" in text

    def test_a_satisfied_enable_needs_no_explanation(self, tool):
        """It is working; saying why would be noise."""
        lines = tool.render_workflow_table(CORRECT, 0)
        i = next(n for n, line in enumerate(lines) if "Auto-add sub-issues" in line)
        assert "every story created" not in lines[i + 1]

    def test_the_pull_request_count_is_stated(self, tool):
        text = "\n".join(tool.render_workflow_table(CORRECT, 0))
        assert "holds 0 pull-request item(s)" in text
        assert "holds 4 pull-request item(s)" in "\n".join(
            tool.render_workflow_table(CORRECT, 4))

    def test_an_unreadable_state_still_shows_the_verdicts(self, tool):
        text = "\n".join(tool.render_workflow_table({}, 0))
        assert "[?]" in text
        assert "Auto-close issue" in text


class TestItIsAdviceNeverAFailure:
    @pytest.fixture
    def validate(self, monkeypatch, tool, capsys):
        def go(state, *, pull_requests=0, rows=()):
            monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
            monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
                [{"title": "S2", "startDate": "2026-08-31", "duration": 14}], []))
            # Opting back in to the real wiring: conftest stubs
            # `automation_notes` for every other test, so this is the one place
            # `cmd_validate` -> advice is exercised end to end.
            monkeypatch.setattr(tool, "project_workflows", lambda *a: state)
            monkeypatch.setattr(tool, "pull_request_items", lambda *a: pull_requests)
            monkeypatch.setattr(tool, "automation_notes",
                                lambda login, project: tool.workflow_findings(
                                    state, pull_requests))
            code = tool.cmd_validate(argparse.Namespace(owner="o", project=1,
                                                         _config={}, id=None))
            return code, capsys.readouterr().out
        return go

    def test_a_board_with_every_workflow_off_still_validates(self, tool, validate):
        """There is no mutation that could turn one on, so this can only point
        at the web UI. A failure would be a check nobody can satisfy."""
        code, out = validate(ALL_OFF)
        assert code == 0
        assert "project automation" in out

    def test_it_appears_under_notes(self, tool, validate):
        _code, out = validate(ALL_OFF)
        assert out.index("notes -- reported") < out.index("project automation")

    def test_a_correct_board_says_nothing_about_automation(self, tool, validate):
        _code, out = validate(CORRECT)
        assert "project automation" not in out

    def test_id_narrows_it_away(self, tool, monkeypatch, capsys):
        """`--id` reports on one issue; a project's automation is not about it,
        and the same reasoning skips the board-wide sprint checks there."""
        monkeypatch.setattr(tool, "rows", lambda *a, **k: [])
        monkeypatch.setattr(tool, "select_by_ref", lambda data, ref, cfg: [])
        monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
            [{"title": "S2", "startDate": "2026-08-31", "duration": 14}], []))
        asked = []
        monkeypatch.setattr(tool, "automation_notes",
                            lambda *a: asked.append(1) or ["x"])
        tool.cmd_validate(argparse.Namespace(owner="o", project=1, _config={},
                                             id="AGILE-9"))
        out = capsys.readouterr().out
        assert "project automation" not in out
        assert asked == [], "the workflow read should not happen under --id"


class TestThePullRequestCount:
    def test_it_counts_pull_request_items(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "board_items", lambda *a, **k: [
            {"content": {"type": "PullRequest"}}, {"content": {"type": "Issue"}},
            {"content": {"type": "PullRequest"}}])
        assert tool.pull_request_items("o", 1) == 2

    def test_a_board_of_issues_is_zero(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "board_items", lambda *a, **k: [
            {"content": {"type": "Issue"}}])
        assert tool.pull_request_items("o", 1) == 0

    def test_an_item_with_no_content_does_not_break_it(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "board_items", lambda *a, **k: [{"content": None}])
        assert tool.pull_request_items("o", 1) == 0
