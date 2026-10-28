"""POLICY.md says what the tool does, and renders. AGILE-267.

The beta product review found it citing a companion document that is not in
the repository, its object-model table cut in two by a block of prose -- so the
last five rows had no header and rendered as text -- and two places saying
automation sets `Done` on merge, when the post-merge hook exists because
nothing does. It also named `gh agile epic` and `gh agile story`, spellings
retired by AGILE-200.
"""

from __future__ import annotations

import pathlib
import re
import shlex

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
POLICY = (ROOT / "POLICY.md").read_text()


def section(number):
    return POLICY.split(f"\n## {number}. ", 1)[1].split("\n## ", 1)[0]


def test_the_object_model_is_one_table():
    """Header, separator, then every concept, with no line between that is not a row."""
    lines = section(2).splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("| Agile concept"))
    table = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        table.append(line)
    concepts = [re.match(r"\| \*\*(\w+)\*\*", row).group(1) for row in table[2:]]
    assert concepts == ["Initiative", "Epic", "Story", "Task", "Bug", "Sprint", "Status",
                        "Estimate", "Traceability"]
    assert not re.search(r"^\| \*\*", section(2).split(table[-1], 1)[1], re.MULTILINE)


def test_every_file_it_names_exists():
    for name in set(re.findall(r"`?([\w.-]+\.md)`?", POLICY)):
        assert (ROOT / name).exists(), name


@pytest.mark.parametrize("spelling", [
    "automation sets `Done`", "a workflow sets `Done`", "moving an\nitem to `Done` on merge",
    "release workflow",
])
def test_it_does_not_say(spelling):
    assert spelling not in POLICY


def test_finishing_is_a_person_prompted_by_the_hook():
    assert "post-merge hook" in section(3) and "post-merge hook" in section(5)
    assert 'issue close N --evidence' in section(3)


def subcommands(parser):
    for action in parser._actions:
        if action.__class__.__name__ == "_SubParsersAction":
            return action.choices
    return {}


def test_every_command_it_names_exists(tool):
    """Named, not necessarily runnable: `epic create` is mentioned without its
    `-t`. What must hold is that the noun and verb exist and are not retired."""
    commands = re.findall(r"`gh agile ([^`]+)`", POLICY)
    assert commands
    for command in commands:
        words = shlex.split(command)
        parser, depth = tool.build_parser(), 0
        while subcommands(parser):
            assert depth < len(words), f"{command}: names a group, not a command"
            assert words[depth] in subcommands(parser), command
            parser, depth = subcommands(parser)[words[depth]], depth + 1


def test_the_guide_agrees_about_dragging():
    guide = (ROOT / "USER_GUIDE.md").read_text()
    safe = guide.split("**Safe in the web UI**", 1)[1].split("**Do in the tool", 1)[0]
    assert "In Progress" not in safe and "Done" not in safe
    assert "Dragging a card to `Todo`, `Blocked` or `In Review`" in safe
    assert "Move an item to `Todo`, `Blocked` or `In Review`" in section(3)
