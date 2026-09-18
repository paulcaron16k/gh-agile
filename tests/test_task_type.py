"""`type:task`, and the policy that admits it. AGILE-133, under #132.

**A policy change, not a feature.** POLICY.md §2 said a task was a markdown
checklist and that promoting one to an issue buys ceremony and costs signal. That
reason stands and is not overturned; nothing here recommends filing tasks as
issues. What changes is what happens to a team that does it anyway -- and GitHub's
sub-issues make it two clicks, so they will.

Today the tool punishes them permanently: `validate` demands a `type:` label on
every issue, so a five-task checklist is five findings that never clear. The only
way to silence it is `type:story`, which is worse -- the task then carries points,
counts in velocity, and inflates the story count with one person's private
breakdown.

So the type exists to be *nameable*, and every other story under #132 is about it
changing no number. The text moves with the code in the same commit, which is the
rule #91 established: a tool that contradicts its own written convention is the
failure this repo has hit twice.
"""

from __future__ import annotations

import pathlib


class TestTheType:
    def test_task_is_one_of_the_issue_types(self, tool):
        assert "task" in tool.ISSUE_TYPES

    def test_the_levels_are_in_hierarchy_order(self, tool):
        """Read top-down, so the tuple itself says what contains what."""
        assert tool.ISSUE_TYPES == ("initiative", "epic", "story", "task", "bug")

    def test_a_task_is_not_a_container(self, tool):
        """It holds nothing, so none of the container rules reach it."""
        assert tool.container_level(["type:task"]) is None

    def test_the_label_is_created_by_setup(self, tool):
        names = [lb["name"] for lb in tool.DEFAULT_SPEC["labels"]]
        assert "type:task" in names

    def test_every_issue_type_has_a_label_to_create(self, tool):
        """A type nothing creates is a type nobody can apply."""
        names = {lb["name"] for lb in tool.DEFAULT_SPEC["labels"]}
        assert {f"type:{t}" for t in tool.ISSUE_TYPES} <= names


class TestTheTitlePrefix:
    """`key+type` mode writes the level into the title, and `strip_title_prefix`
    has to recognise exactly what `prefixed_title` writes -- for every type, or a
    backfill double-prefixes the ones it does not know."""

    def test_a_task_title_is_prefixed(self, tool):
        assert tool.prefixed_title("key+type", "AGILE", 140, "task",
                                   "a task") == "AGILE-140 Task: a task"

    def test_and_stripped_again(self, tool):
        assert tool.strip_title_prefix("AGILE-140 Task: a task", "AGILE") == "a task"


class TestThePolicyMovedWithTheCode:
    """#91's rule: a tool that contradicts its own written convention is a
    failure this repo has hit twice, so the text lands in the same commit."""

    @staticmethod
    def policy():
        return (pathlib.Path(__file__).resolve().parent.parent / "POLICY.md").read_text()

    def test_the_task_row_admits_the_issue_form(self):
        row = next(line for line in self.policy().splitlines()
                   if line.startswith("| **Task**"))
        assert "type:task" in row

    def test_it_keeps_the_original_reason_rather_than_deleting_it(self):
        """The old rule was right and is still the default; only the punishment
        for ignoring it is being removed."""
        row = next(line for line in self.policy().splitlines()
                   if line.startswith("| **Task**"))
        assert "checklist" in row
        assert "ceremony" in row

    def test_it_states_the_consequence(self):
        row = next(line for line in self.policy().splitlines()
                   if line.startswith("| **Task**"))
        assert "changes no number" in row
