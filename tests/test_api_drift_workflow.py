"""The monthly api-drift workflow. AGILE-298.

`make api-drift` ran only when someone remembered. The workflow runs it monthly
and, on drift, opens one pull request assigned to the owner -- GitHub's own
notification is the email. Read as text: the properties that matter are what
triggers it and what it may do, and a YAML parser would be a dependency for
asserting a handful of lines.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "api-drift.yml").read_text()
CODE = "\n".join(line for line in WORKFLOW.splitlines() if not line.lstrip().startswith("#"))


def block(name: str) -> str:
    """The top-level `name:` block, up to the next top-level key."""
    return re.search(rf"^{name}:\n((?:[ \t].*\n|\n)*)", CODE, re.MULTILINE).group(1)


def test_it_runs_monthly_and_by_hand_only():
    on = block("on")
    assert re.search(r"cron: '\d+ \d+ 1 \* \*'", on)
    assert "workflow_dispatch" in on
    assert "pull_request" not in CODE and "push:" not in on


def test_it_may_only_push_its_branch_and_open_its_pull_request():
    granted = dict(re.findall(r"^\s+([\w-]+): (\w+)", block("permissions"), re.MULTILINE))
    assert granted == {"contents": "write", "pull-requests": "write", "issues": "write"}


def test_it_holds_no_secret_but_its_own_token():
    assert "secrets." not in CODE
    assert "GH_TOKEN: ${{ github.token }}" in CODE


def test_it_runs_the_check_and_writes_the_entry_for_the_body():
    assert re.search(r"python3 scripts/api_drift\.py check --summary \S+", CODE)


def test_exit_two_fails_the_run():
    """No snapshot, or no schema: a red run, which GitHub reports, rather than
    a quiet month that checked nothing."""
    assert re.search(r"\*\) exit \$code", CODE)


def test_one_pull_request_assigned_to_the_owner_and_updated_not_duplicated():
    assert "gh pr list --head" in CODE and "gh pr edit" in CODE
    assert '--assignee "${{ github.repository_owner }}"' in CODE
    assert "--label api-drift" in CODE


def test_only_the_two_data_files_are_committed():
    assert re.search(r"git add GitHub_API_spec\.json GitHub_API_changelog\.md\n", CODE)
