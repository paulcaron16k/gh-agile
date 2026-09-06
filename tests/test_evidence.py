"""`move --evidence`: the text is written whatever the status.

It used to be read only when the target status *demanded* a section:

    required = tuple(REQUIRED_FOR.get(args.status.casefold(), ()))
    sections = read_template(args, required=required) if required else {}

so on every status but the cycle end the flags were parsed, accepted and thrown
away -- no warning, exit 0, and the status change succeeded, which is every
reason to believe the text landed. Measured on the Zamboni board: four issues
moved to `In Review` with substantial `--evidence`, all four bodies left with an
empty `## Evidence`, noticed days later when the text existed nowhere else.

The asymmetry was the trap. The flag worked on the one transition where it is
mandatory and was a no-op everywhere else, which is the opposite of what a reader
of `--help` would guess. These tests are the guarantee that it never again exits
0 having discarded the text.

Offline: every `gh` call is captured, so nothing here reaches GitHub.
"""

from __future__ import annotations

import json

import pytest

BODY = "## Intent\nwhy\n\n## Acceptance\nwhat\n\n## Evidence\n"


@pytest.fixture
def run(monkeypatch, tool):
    """`cmd_move` with the board stubbed out, capturing every `gh` call."""
    calls = []

    def fake_gh(args, **kwargs):
        calls.append(args)
        if args[:2] == ["issue", "view"]:
            return json.dumps({"body": BODY})
        return ""

    monkeypatch.setattr(tool, "gh", fake_gh)
    monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 7))
    monkeypatch.setattr(tool, "board_item_for", lambda *a, **k: {"id": "PVTI_7"})
    monkeypatch.setattr(tool, "set_field", lambda *a, **k: None)
    monkeypatch.setattr(tool, "sprint_assignments", lambda *a, **k: {"PVTI_7": "s"})
    monkeypatch.setattr(tool, "record_sprint_label", lambda *a, **k: None)

    def go(status, **flags):
        import argparse
        args = argparse.Namespace(
            issue="7", repo="o/r", owner="o", project=1, close=False,
            not_planned=False, evidence=None, evidence_file=None, add_assignee=None,
            _config={"sprint": {"cadence_days": 14}},
        )
        args.status = status
        for name, value in flags.items():
            setattr(args, name, value)
        calls.clear()
        tool.cmd_move(args)
        return calls

    go.written = lambda calls: next(
        (c[c.index("--body") + 1] for c in calls
         if c[:2] == ["issue", "edit"] and "--body" in c), None)
    return go


class TestEvidenceOnAStatusThatDoesNotRequireIt:
    @pytest.mark.parametrize("status", ["In Review", "Blocked", "In Progress", "Todo"])
    def test_the_text_is_written(self, tool, run, status):
        body = run.written(run(status, evidence="a probe table and the numbers"))
        assert body is not None, f"{status}: the body was never written"
        assert "a probe table and the numbers" in body

    def test_it_lands_under_Evidence(self, tool, run):
        """A bare blob has no headings, and with nothing *required* there was no
        section to map it onto -- so it vanished a second way, past the first fix."""
        body = run.written(run("In Review", evidence="the measurement"))
        assert body.index("## Evidence") < body.index("the measurement")

    def test_explicit_headings_are_honoured(self, tool, run):
        body = run.written(run("Blocked", evidence="## Evidence\nwaiting on the API"))
        assert "waiting on the API" in body

    def test_a_file_works_the_same(self, tool, run, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("## Evidence\nfrom a file\n")
        body = run.written(run("In Review", evidence_file=str(note)))
        assert "from a file" in body

    def test_the_run_says_what_it_wrote(self, tool, run, capsys):
        run("In Review", evidence="the measurement")
        assert "body updated: Evidence" in capsys.readouterr().out

    def test_the_status_is_still_set(self, tool, run, capsys):
        """The write is additional to the move, not instead of it."""
        run("In Review", evidence="the measurement")
        assert "Status = In Review" in capsys.readouterr().out


class TestNoEvidenceOffered:
    @pytest.mark.parametrize("status", ["In Review", "Blocked", "In Progress"])
    def test_the_body_is_left_alone(self, tool, run, status):
        """Nothing offered means nothing read and nothing written -- no cost, and
        no `## Evidence` heading appearing on an issue that never asked for one."""
        calls = run(status)
        assert [c for c in calls if c[:2] in (["issue", "view"], ["issue", "edit"])] == []

    def test_and_no_prompt_is_raised(self, tool, run, capsys):
        """`read_template` prompts at a terminal. A plain `move --status Blocked`
        must not start asking questions."""
        run("Blocked")
        assert ">" not in capsys.readouterr().out


class TestDoneIsUnchanged:
    def test_done_still_writes_the_evidence(self, tool, run):
        body = run.written(run("Done", evidence="what proves it"))
        assert "what proves it" in body

    def test_done_still_refuses_an_empty_body(self, tool, run):
        with pytest.raises(SystemExit) as exit_info:
            run("Done", evidence="   ")
        assert "not complete" in str(exit_info.value)

    def test_done_still_refuses_the_placeholder(self, tool, run):
        with pytest.raises(SystemExit) as exit_info:
            run("Done", evidence=tool.PLACEHOLDER)
        assert tool.PLACEHOLDER in str(exit_info.value)

    def test_a_status_that_requires_nothing_does_not_validate(self, tool, run):
        """The placeholder check belongs to the transition after which nobody
        revisits the issue. Refusing `_TBD_` on Blocked would be ceremony."""
        body = run.written(run("Blocked", evidence=tool.PLACEHOLDER))
        assert tool.PLACEHOLDER in body
