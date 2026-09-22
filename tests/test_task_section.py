"""A `## Tasks` section is named, and never damaged. AGILE-164.

POLICY.md §2 has always recommended a markdown checklist inside the story rather
than issues-as-tasks. #132 built `type:task` so the tool would stop *punishing* a
team that files them as issues -- that was the right fix for that problem and is
not reverted -- but it left the supported path being the discouraged one and the
recommended path unsupported.

**The decision (AGILE-164): name the shape, and stay out of the way.**

- **Read?** `parse_sections` already returns a `## Tasks` block, so reading is
  free. Nothing *displays* it, which is the question that mattered.
- **Write?** Never. A body is a whole-value replace with no additive primitive,
  so two people ticking boxes would overwrite each other. GitHub's own UI ticks
  them safely; there is nothing to add and something to lose.
- **On a board?** No. The `pts` cell holds a container's `closed/total`, and a
  story showing `2/3` for a checklist would be the same shape meaning something
  else -- the ambiguity #116's legend exists to prevent. A checklist is one
  person's private breakdown; a shared board is the wrong surface.
- **Exported?** No. #137 decided a task has no metric and no KPI; a checkbox has
  less, and it changes under people's hands between exports.

So what this story delivers is a **named shape** and a **guarantee**: every body
the tool writes preserves the section. That was true by accident before these
tests and is true on purpose now.
"""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

TASKS = """## Intent
why

## Tasks
- [x] the first thing
- [ ] the second thing
  - [ ] a nested one
- [ ] the third thing

## Acceptance
what

## Evidence
_TBD_
"""


class TestTheSectionIsReadableIfAnythingEverWantsIt:
    def test_it_parses_as_a_section(self, tool):
        assert "Tasks" in tool.parse_sections(TASKS)

    def test_the_boxes_survive_parsing(self, tool):
        body = tool.parse_sections(TASKS)["Tasks"]
        assert "- [x] the first thing" in body
        assert "- [ ] a nested one" in body, "nesting is the author's business"


class TestNoBodyWriteDamagesIt:
    """The guarantee this story exists to give. It held by accident before
    these tests; it holds on purpose now."""

    def test_writing_evidence_leaves_it_alone(self, tool):
        out = tool.replace_section(TASKS, "Evidence", "PR #1, merged.")
        assert "- [x] the first thing" in out
        assert "- [ ] a nested one" in out

    def test_and_writes_the_evidence_it_was_asked_to(self, tool):
        out = tool.replace_section(TASKS, "Evidence", "PR #1, merged.")
        assert tool.parse_sections(out)["Evidence"].strip() == "PR #1, merged."

    @pytest.mark.parametrize("section", ["Intent", "Acceptance", "Evidence"])
    def test_rewriting_any_other_section_leaves_it_alone(self, tool, section):
        out = tool.replace_section(TASKS, section, "replaced")
        assert tool.parse_sections(out)["Tasks"] == tool.parse_sections(TASKS)["Tasks"]

    def test_a_section_appended_after_it_leaves_it_alone(self, tool):
        """`replace_section` appends a heading that is absent."""
        out = tool.replace_section(TASKS, "Notes", "something")
        assert "- [x] the first thing" in out
        assert "## Notes" in out

    def test_two_writes_in_a_row_are_still_safe(self, tool):
        """`move` replaces every section it was given, in sequence."""
        out = tool.replace_section(TASKS, "Evidence", "PR #1.")
        out = tool.replace_section(out, "Intent", "a better why")
        assert tool.parse_sections(out)["Tasks"] == tool.parse_sections(TASKS)["Tasks"]


class TestItChangesNoNumberAndNoGate:
    def test_the_done_gate_ignores_it(self, tool):
        """A checklist with unticked boxes must not block a close: the boxes
        are working notes, not acceptance."""
        body = TASKS.replace("_TBD_", "PR #1, merged.")
        assert tool.section_problems(tool.parse_sections(body), ("Evidence",)) == []

    def test_an_unticked_box_does_not_block_done(self, tool):
        body = TASKS.replace("_TBD_", "PR #1, merged.")
        assert "- [ ] the third thing" in body
        assert tool.section_problems(tool.parse_sections(body), ("Evidence",)) == []

    def test_no_tally_is_derived_from_it(self, tool):
        """A story's `pts` cell shows its estimate, never its checklist: the
        same shape meaning something else is what #116's legend prevents."""
        row = {"type": "story", "story_points": 3.0, "sub_issues_total": 0,
               "sub_issues_done": 0}
        assert tool.render_progress(row) == "3"

    def test_and_a_story_with_no_estimate_still_shows_nothing(self, tool):
        row = {"type": "story", "story_points": None, "sub_issues_total": 0,
               "sub_issues_done": 0}
        assert tool.render_progress(row) == "—"


class TestTheTemplateStaysEmptyOfIt:
    def test_story_does_not_create_the_heading(self, tool):
        """An empty `## Tasks` on every issue is the ceremony POLICY warns
        about. Add it when there is something to put in it."""
        assert "## Tasks" not in tool.BODY_TEMPLATE

    def test_the_template_is_still_the_three_it_was(self, tool):
        headings = [ln for ln in tool.BODY_TEMPLATE.splitlines() if ln.startswith("## ")]
        assert headings == ["## Intent", "## Acceptance", "## Evidence"]


class TestPolicyNamesTheShape:
    @staticmethod
    def policy():
        return (ROOT / "POLICY.md").read_text()

    def test_the_heading_is_specified(self):
        """A convention two teams write differently is one nothing can rely on."""
        assert "## Tasks" in self.policy()

    def test_the_syntax_is_specified(self):
        assert "- [ ] not done" in self.policy()
        assert "- [x] done" in self.policy()

    def test_it_says_the_tool_stays_out_of_the_way(self):
        flowing = " ".join(self.policy().split())
        assert "reads nothing, writes nothing" in flowing

    def test_it_says_why_writing_would_be_wrong(self):
        flowing = " ".join(self.policy().split())
        assert "overwrite each other" in flowing

    def test_it_says_an_absent_section_is_normal(self):
        flowing = " ".join(self.policy().split())
        assert "absent section is the normal case" in flowing

    def test_the_issue_form_is_still_described_as_tolerated(self):
        """Both forms coexist and neither team is told it is doing it wrong."""
        row = next(line for line in self.policy().splitlines()
                   if line.startswith("| **Task**"))
        assert "type:task" in row and "does not punish" in row
