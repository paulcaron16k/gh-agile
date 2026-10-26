"""`scripts/agile_analytics.py` runs against the DuckDB a user gets. AGILE-272.

The script declared `duckdb>=1.0`, `uv` resolved 2.0, and 2.0 had removed
`fetchone()` from a relation: `metrics` crashed on its first cell and `compact`
on its first row count. Nothing ran the script, so nothing noticed. DuckDB is
now a development requirement within the script's own bounds, and these tests
run both commands on a small export.

The script needs Python 3.11 (`dt.UTC`), so the floor job skips the DuckDB
tests; the source check runs everywhere.
"""

from __future__ import annotations

import csv
import datetime as dt
import importlib.util
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "agile_analytics.py"

COLUMNS = ["issue_key", "number", "created_at", "added_to_board_at", "started_at",
           "done_at", "cycle_time", "lead_time", "field_story_points",
           "sprint_closed_in", "exported_at"]


def test_nothing_calls_fetchone():
    """Removed from a relation in DuckDB 2.0, and the source says so in prose only."""
    code = [line for line in SCRIPT.read_text().splitlines()
            if not line.lstrip().startswith("#")]
    assert not [line for line in code if ".fetchone()" in line]


def test_the_dev_requirement_matches_the_scripts_bounds():
    """CI must install what `uv run` would, or it tests a different DuckDB."""
    declared = next(line.split('"')[1] for line in SCRIPT.read_text().splitlines()
                    if line.startswith("# dependencies"))
    assert any(line.startswith(declared + ";")
               for line in (ROOT / "requirements-dev.txt").read_text().splitlines())


def test_timestamps_are_read_in_utc(analytics):
    """A row exported at midnight UTC on the 1st belongs to that month."""
    assert analytics.duckdb.sql(
        "SELECT strftime(CAST(TIMESTAMPTZ '2026-10-01T00:00:00Z' AS TIMESTAMP), '%Y%m')"
    ).fetchall() == [("202610",)]


@pytest.fixture(scope="module")
def analytics():
    if sys.version_info < (3, 11):
        pytest.skip("the script requires Python 3.11")
    pytest.importorskip("duckdb")
    spec = importlib.util.spec_from_file_location("agile_analytics", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})


def issue(number, exported, *, done=True, cycle=600, key="WIDG"):
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    return {"issue_key": f"{key}-{number}", "number": number,
            "created_at": f"{today}T01:00:00Z", "added_to_board_at": f"{today}T01:00:00Z",
            "started_at": f"{today}T02:00:00Z",
            "done_at": f"{today}T03:00:00Z" if done else "",
            "cycle_time": cycle if done else "", "lead_time": 7200 if done else "",
            "field_story_points": 3, "exported_at": exported}


def test_metrics_reports_the_current_period(analytics, tmp_path, capsys):
    write(tmp_path / "github_issues_1.csv",
          [issue(1, "2026-10-01T00:00:00Z", cycle=600),
           issue(2, "2026-10-01T00:00:00Z", cycle=1800),
           issue(3, "2026-10-01T00:00:00Z", done=False)])
    analytics.metrics(tmp_path, "quarterly", None, "key")
    # The matrix is the block after the dashes; the legend follows a blank line.
    matrix = capsys.readouterr().out.split("---\n", 1)[1].split("\n\n", 1)[0]
    lines = {" ".join(line.split()[:3]) if " - " in line else line.split()[0]: line.split()
             for line in matrix.splitlines()}
    assert lines["throughput"][-1] == "2"
    assert lines["cycle_time_median"][-1] == "1200"
    assert lines["carryover"][-1] == "1"
    assert lines["WIDG - throughput"][-1] == "2"


def test_metrics_headers_do_not_run_together(analytics, tmp_path, capsys):
    write(tmp_path / "github_issues_1.csv", [issue(1, "2026-10-01T00:00:00Z")])
    analytics.metrics(tmp_path, "quarterly", None, "project")
    header = next(line for line in capsys.readouterr().out.splitlines()
                  if line.lstrip().startswith("context"))
    assert header.endswith("in-progress")
    # Every period label is separated from the next by at least two spaces.
    labels = [label for label, _f, _l in analytics.periods("quarterly", None)]
    for earlier, later in zip(labels, labels[1:], strict=False):
        assert re.search(rf"{earlier} {{2,}}{later}", header), header


def test_compact_keeps_the_newest_row_per_issue(analytics, tmp_path, capsys):
    write(tmp_path / "github_issues_a.csv",
          [issue(1, "2026-10-01T00:00:00Z", cycle=100), issue(2, "2026-10-01T00:00:00Z")])
    write(tmp_path / "github_issues_b.csv",
          [issue(1, "2026-10-02T00:00:00Z", cycle=900)])
    assert analytics.compact(tmp_path, None, keep=False) == 1
    assert "github_issues_monthly_202610.csv: 2 row(s) from 2 daily file(s)" \
        in capsys.readouterr().out
    with (tmp_path / "github_issues_monthly_202610.csv").open() as handle:
        rows = {row["number"]: row for row in csv.DictReader(handle)}
    assert rows["1"]["cycle_time"] == "900"
    assert not list(tmp_path.glob("github_issues_[ab].csv"))
