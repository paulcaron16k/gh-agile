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


def touches_the_body(call: list[str]) -> bool:
    """A `gh` call that reads or writes the issue body, as opposed to one that
    reads or writes the assignees."""
    return ("--body" in call) or (call[:2] == ["issue", "view"] and "body" in call)


@pytest.fixture
def run(monkeypatch, tool):
    """`cmd_move` with the board stubbed out, capturing every `gh` call."""
    calls = []
    state = {"body": BODY}

    def fake_gh(args, **kwargs):
        calls.append(args)
        if args[:2] == ["issue", "view"]:
            # Both reads `move` makes: the body, for the evidence sections, and
            # the assignees, for the claim that starting work performs. One fake
            # answering only `--json body` broke the moment the two landed
            # together -- each was green on its own branch and the combination
            # was never built until both merged.
            return json.dumps({"body": state["body"], "assignees": []})
        return ""

    monkeypatch.setattr(tool, "gh", fake_gh)
    monkeypatch.setattr(tool, "parse_issue_ref", lambda *a, **k: ("o/r", 7))
    monkeypatch.setattr(tool, "board_item_for", lambda *a, **k: {"id": "PVTI_7"})
    monkeypatch.setattr(tool, "set_field", lambda *a, **k: None)
    monkeypatch.setattr(tool, "sprint_assignments", lambda *a, **k: {"PVTI_7": "s"})
    monkeypatch.setattr(tool, "record_sprint_label", lambda *a, **k: None)
    # Its own story (#117); stubbed so these tests stay about the evidence.
    monkeypatch.setattr(tool, "promote_parents", lambda *a, **k: None)

    def go(status, **flags):
        import argparse
        args = argparse.Namespace(
            issue="7", repo="o/r", owner="o", project=1, close=False,
            not_planned=False, evidence=None, evidence_file=None, add_assignee=None,
            _config={"sprint": {"cadence_days": 14}},
        )
        args.status = status
        state["body"] = flags.pop("body", BODY)
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
        no `## Evidence` heading appearing on an issue that never asked for one.

        The body specifically: `In Progress` also reads assignees and may write
        one, which is a different command's business.
        """
        assert [c for c in run(status) if touches_the_body(c)] == []

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


class AtATerminal:
    """Stands in for `sys.stdin` where a person is present to be prompted."""

    @staticmethod
    def isatty():
        return True


#: A body that already carries what `Done` demands.
COMPLETE = "## Intent\nwhy\n\n## Acceptance\nwhat\n\n## Evidence\nthe measurement, written at In Review\n"


class TestDoneChecksTheBodyNotJustTheFlags:
    """`require_sections` validated the text *supplied on the command line* and
    never looked at the body.

    Harmless while `Done` was the only status that could write evidence: supplied
    and resulting were the same thing. Since evidence can be written at
    `In Review`, the common shape is write-then-close -- and that was exactly the
    shape this refused. AGILE-62's own body carried a full Evidence section and
    `move 62 --status Done` still exited with "no text supplied".

    The cost was never the message. Retyping a long section invites
    `--evidence "see above"`, and a one-line placeholder that satisfies the
    validator is the erosion POLICY.md §4 exists to prevent.
    """

    def test_a_body_that_already_satisfies_it_is_enough(self, tool, run, capsys):
        """No flags, no prompt, no refusal -- the move simply happens."""
        calls = run("Done", body=COMPLETE)
        assert "Status = Done" in capsys.readouterr().out
        assert run.written(calls) is None                # nothing rewritten

    def test_and_the_body_is_left_byte_identical(self, tool, run):
        calls = run("Done", body=COMPLETE)
        assert [c for c in calls if touches_the_body(c) and "--body" in c] == []

    def test_and_it_says_why_it_did_not_ask(self, tool, run, capsys):
        run("Done", body=COMPLETE)
        assert "Evidence already in the body" in capsys.readouterr().out

    def test_an_empty_section_still_refuses(self, tool, run):
        with pytest.raises(SystemExit) as exit_info:
            run("Done", body=BODY)                       # ## Evidence present but empty
        assert "## Evidence is missing or empty" in str(exit_info.value)

    def test_a_missing_section_still_refuses(self, tool, run):
        with pytest.raises(SystemExit) as exit_info:
            run("Done", body="## Intent\nwhy\n")
        assert "## Evidence is missing or empty" in str(exit_info.value)

    def test_a_placeholder_still_refuses(self, tool, run):
        with pytest.raises(SystemExit) as exit_info:
            run("Done", body=f"## Evidence\n{'_TBD_'}\n")
        assert "_TBD_" in str(exit_info.value)

    def test_the_refusal_names_the_body_not_a_missing_flag(self, tool, run):
        """The old message said only "no text supplied", which sent people looking
        for a flag when the answer was to write the section."""
        with pytest.raises(SystemExit) as exit_info:
            run("Done", body=BODY)
        message = str(exit_info.value)
        assert "issue body does not carry" in message
        assert "move to Done requires" in message
        assert "--evidence" in message           # the flag is still offered as a way out

    def test_supplied_text_still_wins_over_a_complete_body(self, tool, run):
        """Nothing about the existing path changes: given text, it is written."""
        body = run.written(run("Done", body=COMPLETE, evidence="a newer measurement"))
        assert "a newer measurement" in body

    def test_supplied_text_is_still_validated(self, tool, run):
        """A good body does not excuse a bad `--evidence`."""
        with pytest.raises(SystemExit) as exit_info:
            run("Done", body=COMPLETE, evidence=" ")
        assert "not complete" in str(exit_info.value)


class TestWhatTheBodyCheckCosts:
    def test_one_read_and_no_write_when_the_body_is_good(self, tool, run):
        reads = [c for c in run("Done", body=COMPLETE) if touches_the_body(c)]
        assert len(reads) == 1 and "--body" not in reads[0]

    def test_the_read_is_reused_rather_than_repeated(self, tool, run, monkeypatch):
        """A bad body at a terminal prompts, and the text is written back onto the
        body already in hand -- not onto a second fetch of it."""
        monkeypatch.setattr(tool, "read_template", lambda *a, **k: {"Evidence": "typed"})
        monkeypatch.setattr(tool.sys, "stdin", AtATerminal())
        calls = run("Done", body=BODY)
        assert len([c for c in calls if c[:2] == ["issue", "view"] and "body" in c]) == 1
        assert "typed" in run.written(calls)

    def test_a_status_requiring_nothing_never_reads_the_body(self, tool, run):
        assert [c for c in run("In Review") if touches_the_body(c)] == []

    def test_nor_does_one_that_was_given_text(self, tool, run):
        """Supplied text is what gets validated, so nothing needs reading first --
        the body is fetched later, to write into."""
        calls = run("Done", evidence="what proves it")
        assert len([c for c in calls if c[:2] == ["issue", "view"] and "body" in c]) == 1
