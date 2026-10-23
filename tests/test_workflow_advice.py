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
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

ALL_OFF = dict.fromkeys((
    "Item closed", "Item added to project", "Auto-add sub-issues to project",
    "Auto-add to project",
    "Auto-close issue", "Pull request merged", "Pull request linked to issue"),
    False)
#: A board configured as the table recommends: the two `enable` ones on, the
#: harmful one off, the two pull-request ones off on a board of issues -- and
#: `Item closed` **off**, which #186 changed. It writes Status and nothing else,
#: so an issue it touches reads Done with no Evidence and no closing sprint
#: label; the post-merge hook asks a person to finish it instead.
CORRECT = {**ALL_OFF, "Auto-add sub-issues to project": True,
           "Item added to project": True, "Auto-add to project": True}


class TestTheTableCoversEverything:
    def test_every_workflow_has_a_verdict(self, tool):
        """Three of six is not advice: the reader turns on what is off. Seven
        since a user-owned project gained `Auto-add to project` (#237)."""
        assert len(tool.WORKFLOW_ADVICE) == 7

    @pytest.mark.parametrize("name", sorted(ALL_OFF))
    def test_each_one_by_name(self, tool, name):
        assert name in tool.WORKFLOW_ADVICE

    def test_every_verdict_is_one_of_the_five(self, tool):
        verdicts = {v for v, _why in tool.WORKFLOW_ADVICE.values()}
        assert verdicts <= {"enable", "filtered", "never", "issues-only", "by-hand"}

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
        assert any("Item added to project is off" in line for line in found)

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


class TestAutoAddToProject:
    """The seventh workflow, new to user-owned projects in 2026-10 (#237). Its
    default filter adds only items labelled exactly `bug`, and the API reads
    `enabled` but never the filter -- so on is not the same as right."""

    def test_it_is_recommended_with_a_filter(self, tool):
        verdict, why = tool.WORKFLOW_ADVICE["Auto-add to project"]
        assert verdict == "filtered"
        assert "`is:issue is:open`" in why

    def test_the_filter_names_no_pull_requests_and_no_key(self, tool):
        _verdict, why = tool.WORKFLOW_ADVICE["Auto-add to project"]
        recommended = why.split("Filter ")[1].split(",")[0]
        assert "pr" not in recommended and "label:" not in recommended

    def test_it_says_why_the_default_is_wrong(self, tool):
        _verdict, why = tool.WORKFLOW_ADVICE["Auto-add to project"]
        assert "label:bug" in why and "ANDs" in why

    def test_off_is_reported_by_validate(self, tool):
        found = tool.workflow_findings({**CORRECT, "Auto-add to project": False}, 0)
        assert any(line.startswith("Auto-add to project is off") for line in found)

    def test_on_is_not(self, tool):
        assert tool.workflow_findings(CORRECT, 0) == []

    def test_on_still_prints_the_filter_in_init(self, tool):
        """Being on says nothing about the filter, which nothing can read."""
        lines = tool.render_workflow_table(CORRECT, 0)
        i = next(n for n, line in enumerate(lines) if line.endswith("  Auto-add to project"))
        assert "[on]" in lines[i] and "is:issue is:open" in lines[i + 1]

    def test_the_pull_request_workflows_are_still_the_last_two(self, tool):
        """The table's closing line says the last two carry no recommendation."""
        assert list(tool.WORKFLOW_ADVICE)[-2:] == [
            "Pull request merged", "Pull request linked to issue"]


class TestTheRepositorySetting:
    """`Auto-close issues with merged linked pull requests` is the repository's,
    not the project's, and the API cannot read it (#237): a before-and-after
    snapshot of every readable setting differed only in a clone token."""

    @pytest.fixture
    def printed(self, tool, monkeypatch, capsys):
        monkeypatch.setattr(tool, "project_workflows", lambda login, number: CORRECT)
        monkeypatch.setattr(tool, "pull_request_items", lambda login, number: 0)

        def run(repos):
            tool.report_manual_steps("o", 4, repos)
            return capsys.readouterr().out
        return run

    def test_init_names_it(self, printed):
        out = printed(["o/a"])
        assert "Auto-close issues with merged linked pull requests" in out
        assert "Settings -> General -> Issues" in out

    def test_once_per_repository_with_where_to_find_it(self, printed):
        out = printed(["o/a", "o/b"])
        assert "https://github.com/o/a/settings" in out
        assert "https://github.com/o/b/settings" in out

    def test_it_is_never_shown_as_on_or_off(self, printed):
        """Unreadable is said, not guessed at."""
        line = next(x for x in printed(["o/a"]).splitlines()
                    if "Auto-close issues with merged" in x)
        assert "[?]" in line

    def test_it_says_leave_it_on_because_it_is_the_default(self, printed):
        """Off here only because it was disabled with every other auto-close
        while the #96 race was fixed. AGILE-239."""
        out = printed(["o/a"])
        assert "On by default: leave it on" in out
        assert "never raced this tool" in out

    def test_it_is_not_the_project_workflow_of_a_similar_name(self, tool):
        """`Auto-close issue` closes on Status Done and stays `never`; this one
        closes on merge and is recommended. Confusing the two is the mistake."""
        assert tool.WORKFLOW_ADVICE["Auto-close issue"][0] == "never"
        assert "Auto-close issues with merged" not in tool.WORKFLOW_ADVICE


class TestTheFullTableIsForConfiguring:
    def test_it_names_all_seven(self, tool):
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


class TestItemClosedIsOffOnPurpose:
    """AGILE-186 reversed this one, and the reversal has to be legible.

    It was `enable`, on a real measurement: #123 sat closed and In Progress for
    twenty-two hours and #138 repeated it. What that missed is what the workflow
    *cannot* do -- it writes Status and nothing else, so the issue reads Done
    with no Evidence, no closing `sprint:` label and no completed-or-not-planned.
    A visibly unfinished issue costs one command; one that looks finished is
    indistinguishable from work somebody did.
    """

    def test_the_verdict_is_by_hand(self, tool):
        verdict, _why = tool.WORKFLOW_ADVICE["Item closed"]
        assert verdict == "by-hand"

    def test_the_reason_says_what_it_cannot_write(self, tool):
        _verdict, why = tool.WORKFLOW_ADVICE["Item closed"]
        assert "Evidence" in why and "sprint:" in why

    def test_and_names_what_replaces_it(self, tool):
        """A verdict that only forbids leaves the reader with the gap."""
        _verdict, why = tool.WORKFLOW_ADVICE["Item closed"]
        assert "issue move ISSUE Done --evidence" in why and "#186" in why

    def test_off_is_not_reported(self, tool):
        """The whole point: `validate` stopped arguing with the decision."""
        assert not any("Item closed" in line for line in tool.workflow_findings(CORRECT, 0))

    def test_all_off_no_longer_reports_it_either(self, tool):
        assert not any("Item closed" in line for line in tool.workflow_findings(ALL_OFF, 0))

    def test_ON_is_reported(self, tool):
        found = tool.workflow_findings({**CORRECT, "Item closed": True}, 0)
        line = next(x for x in found if "Item closed" in x)
        assert "is ON" in line and "by hand" in line

    def test_the_table_marks_it_by_hand(self, tool):
        lines = tool.render_workflow_table(CORRECT, 0)
        assert any("by hand" in line and "Item closed" in line for line in lines)

    def test_the_table_carries_its_reason_although_it_is_off(self, tool):
        """It is off on a correct board and looks exactly like an oversight --
        more so than the others, because it was recommended until #186."""
        text = "\n".join(tool.render_workflow_table(CORRECT, 0))
        assert "writes Status and nothing else" in text


class TestTheGuideAgreesWithTheTable:
    """Two places say which workflows to turn on, and they can disagree.

    The table is what `init` and `validate` print; the guide is what somebody
    reads while configuring the project. #186 changed one verdict, and a guide
    still recommending the opposite would be the more persuasive of the two.
    """

    def guide(self):
        return (ROOT / "USER_GUIDE.md").read_text()

    def test_the_guide_does_not_recommend_item_closed(self):
        row = next(line for line in self.guide().splitlines()
                   if line.startswith("| **Item closed**"))
        assert "**no**" in row

    def test_the_guide_gives_the_reason_the_table_gives(self):
        assert "writes Status and *nothing else*" in self.guide()

    def test_the_guide_names_what_replaces_it(self):
        """And names it as the command a consumer can run, not as a Makefile
        target of this repository -- #193."""
        text = self.guide()
        assert "gh agile init" in text and "post-merge" in text

    def test_auto_close_is_still_refused_in_both(self, tool):
        row = next(line for line in self.guide().splitlines()
                   if line.startswith("| **Auto-close issue**"))
        assert "**no**" in row
        assert tool.WORKFLOW_ADVICE["Auto-close issue"][0] == "never"
