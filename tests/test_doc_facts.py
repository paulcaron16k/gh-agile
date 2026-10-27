"""The user docs state what the code does, read from the code. AGILE-266.

The beta product review found the README and the guide stating facts the code
contradicts: a default sprint name two templates old, export columns that had
lost their `_days` suffix in the catalog but not in the prose, four of the
seven fields `init` creates, three of the four export grains. Each was right
once and nothing noticed when the code moved. These tests read the fact from
the code and fail when a document says otherwise.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
GUIDE = (ROOT / "USER_GUIDE.md").read_text()
POLICY = (ROOT / "POLICY.md").read_text()
USER_DOCS = {"README.md": README, "USER_GUIDE.md": GUIDE, "POLICY.md": POLICY}


def table_rows(text, first_cell):
    """Every markdown table row whose first cell is `first_cell`."""
    return [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in text.splitlines()
            if line.startswith(f"| {first_cell} |")]


class TestSprintDefaults:
    """The guide's profile table carries every `sprint` property with its
    default; since #269 it is the only copy, and the README links to it."""

    @pytest.mark.parametrize("prop", ["cadence_days", "start_day", "ahead", "autocreate",
                                      "name_template", "record_label"])
    def test_the_default_is_the_codes(self, tool, prop):
        (row,) = table_rows(GUIDE, f"`sprint.{prop}`")
        expected = json.dumps(tool.SPRINT_DEFAULTS[prop])
        assert row[3].endswith(f"Default `{expected}`") or f"Default `{expected}` " in row[3], \
            f"sprint.{prop}: {row[3]}"

    @pytest.mark.parametrize("doc", ["README.md", "USER_GUIDE.md"])
    def test_there_is_no_second_copy(self, doc):
        assert not table_rows(USER_DOCS[doc], "`name_template`")


class TestExportColumns:
    def test_no_column_carries_a_unit(self):
        """Every duration is integer seconds with no suffix. `cadence_days` is
        the profile's hand-written spelling, not a column."""
        for name, text in USER_DOCS.items():
            found = set(re.findall(r"`([a-z_]+_(?:days|hours|minutes))`", text))
            assert found <= {"cadence_days"}, f"{name}: {sorted(found)}"

    def test_the_time_columns_named_are_in_the_catalog(self):
        catalog = json.loads((ROOT / "github_catalog.json").read_text())
        columns = {column for stream in catalog["streams"]
                   for column in stream["schema"]["properties"]}
        for column in ("cycle_time", "lead_time"):
            assert f"`{column}`" in README and column in columns
        assert "`cycle_time`" in GUIDE

    def test_the_medians_are_seconds(self):
        for metric in ("cycle_time_median", "lead_time_median"):
            (row,) = table_rows(GUIDE, f"`{metric}`")
            assert row[1].startswith("median seconds")


class TestInitFields:
    def test_the_readme_names_every_field(self, tool):
        bullet = README.split("- **a GitHub Project**", 1)[1].split("\n- ", 1)[0]
        for field in tool.DEFAULT_SPEC["fields"]:
            assert f"`{field['name']}`" in bullet, field["name"]

    def test_init_help_lists_every_field(self, tool, capsys):
        with pytest.raises(SystemExit):
            tool.build_parser().parse_args(["init", "--help"])
        listed = capsys.readouterr().out.split("project fields created:", 1)[1]
        for field in tool.DEFAULT_SPEC["fields"]:
            assert f"\n  {field['name']}  " in listed, field["name"]


class TestExportGrains:
    def test_the_guide_tables_every_grain(self, tool):
        for grain in tool.EXPORT_GRAINS:
            assert table_rows(GUIDE, f"`{grain}`"), grain

    def test_the_guide_counts_them(self, tool):
        words = {3: "Three", 4: "Four", 5: "Five"}
        assert f"{words[len(tool.EXPORT_GRAINS)]} grains" in GUIDE


def test_the_guide_does_not_send_the_hook_to_a_retired_spelling():
    """`validate --id` is retired; the guide may say so, not recommend it."""
    for match in re.finditer(r"validate\s+--id", GUIDE):
        nearby = GUIDE[max(0, match.start() - 200):match.end() + 200]
        assert "retired" in nearby or "is now" in nearby or "issue view" in nearby


def test_the_command_reference_names_every_command():
    """§12 is the one list of everything; it left out `bug`, `initiative
    reconcile`, `task list` and `unfinished` (#269). Every leaf `--help` shows."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_guide

    reference = GUIDE.split("## 12. Command reference", 1)[1]
    named = set(re.findall(r"^\| ((?:`[^`]+`(?: / )?)+) \|", reference, re.MULTILINE))
    commands = {name for cell in named for name in re.findall(r"`([^`]+)`", cell)}
    leaves = {" ".join(leaf) for leaf in check_guide.parser_leaves()}
    assert leaves <= commands, sorted(leaves - commands)


def test_the_guide_has_a_table_of_contents():
    toc = GUIDE.split("## Contents", 1)[1].split("\n## ", 1)[0]
    for heading in re.findall(r"^## (\d+\. .+)$", GUIDE, re.MULTILINE):
        assert heading.split(" ", 1)[1].split(":")[0].replace("`", "") in \
            toc.replace("`", ""), heading


def test_no_user_doc_cites_maintainer_files_or_history():
    for name, text in USER_DOCS.items():
        assert "docs/" not in text, name
        assert "this repository made" not in text, name
        assert not re.search(r"until (AGILE-|#|`#)\d", text), name
