#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["duckdb>=1.0"]
# ///
"""Compact daily exports into monthly files, and compute Agile metrics.

**Why this is not part of `gh-agile`.** `gh extension install` clones the
repository and installs nothing -- there is no dependency step for a script
extension -- so an `import duckdb` in the extension itself would break every
install that happens not to have it. The extension therefore stays standard
library only, and analysis lives here, where PEP 723 inline metadata lets `uv`
fetch DuckDB into an ephemeral environment:

    uv run scripts/agile_analytics.py compact --dir exports/ZMBNI
    uv run scripts/agile_analytics.py metrics --dir exports/ZMBNI

DuckDB rather than pandas: it reads a glob of CSVs directly, deduplicates with a
window function, and writes CSV in one statement -- no dataframe assembly, and
nothing has to fit in memory. Either would work; this is less code.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

#: Deduplication keys per grain. Exports overlap on purpose -- an incremental
#: run re-reads a window because the timeline is eventually consistent -- so the
#: same row arrives many times and the newest must win.
GRAINS = {
    "issues": ("number", "exported_at"),
    "events": ("event_hash", "exported_at"),
}


def compact(directory: Path, month: str | None, keep: bool) -> int:
    """Fold daily exports into one file per month, newest row per key winning."""
    written = 0
    for grain, (key, order) in GRAINS.items():
        pattern = str(directory / f"agile_{grain}_*.csv")
        daily = sorted(directory.glob(f"agile_{grain}_*.csv"))
        # Monthly outputs must not be re-read as inputs, or each run folds its
        # own output back in and the file grows without bound.
        daily = [p for p in daily if "_monthly_" not in p.name]
        if not daily:
            continue

        months = duckdb.sql(
            f"SELECT DISTINCT strftime(CAST(exported_at AS TIMESTAMP), '%Y%m') AS m "
            f"FROM read_csv_auto('{pattern}', union_by_name = true) ORDER BY m"
        ).fetchall()
        for (stamp,) in months:
            if month and stamp != month:
                continue
            out = directory / f"agile_{grain}_monthly_{stamp}.csv"
            duckdb.sql(f"""
                COPY (
                    SELECT * EXCLUDE (rn) FROM (
                        SELECT *, row_number() OVER (
                            PARTITION BY {key} ORDER BY {order} DESC
                        ) AS rn
                        FROM read_csv_auto('{pattern}', union_by_name = true)
                        WHERE strftime(CAST(exported_at AS TIMESTAMP), '%Y%m') = '{stamp}'
                    ) WHERE rn = 1
                ) TO '{out}' (HEADER, DELIMITER ',')
            """)
            rows = duckdb.sql(f"SELECT count(*) FROM read_csv_auto('{out}')").fetchone()[0]
            print(f"  {out.name}: {rows} row(s) from {len(daily)} daily file(s)")
            written += 1

        if not keep:
            for path in daily:
                path.unlink()
            print(f"  removed {len(daily)} daily {grain} file(s)")
    return written


#: Six metrics, each one line of SQL over the compacted export. Deliberately
#: simple: a metric nobody can derive by hand is a metric nobody trusts.
METRICS = {
    "throughput": (
        "items reaching Done, by month",
        """SELECT strftime(CAST(done_at AS TIMESTAMP), '%Y-%m') AS month, count(*) AS done
           FROM issues WHERE done_at IS NOT NULL GROUP BY 1 ORDER BY 1""",
    ),
    "cycle_time": (
        "days from first In Progress to Done",
        """SELECT count(*) AS completed,
                  round(avg(cycle_time_days), 2) AS mean_days,
                  round(median(cycle_time_days), 2) AS median_days,
                  round(max(cycle_time_days), 2) AS worst_days
           FROM issues WHERE cycle_time_days IS NOT NULL""",
    ),
    "lead_time": (
        "days from joining the board to Done",
        """SELECT round(avg(lead_time_days), 2) AS mean_days,
                  round(median(lead_time_days), 2) AS median_days
           FROM issues WHERE lead_time_days IS NOT NULL""",
    ),
    "wip": (
        "items in each status right now",
        """SELECT coalesce(field_status, '(none)') AS status, count(*) AS items
           FROM issues GROUP BY 1 ORDER BY items DESC""",
    ),
    "sprint_load": (
        "points and items per sprint",
        """SELECT coalesce(field_sprint, '(unassigned)') AS sprint,
                  count(*) AS items,
                  sum(coalesce(field_story_points, 0)) AS points,
                  sum(CASE WHEN field_status = 'Done' THEN 1 ELSE 0 END) AS done
           FROM issues GROUP BY 1 ORDER BY 1""",
    ),
    "flow_churn": (
        "status changes per item -- high counts mean thrash",
        """SELECT i.issue_key,
                  count(*) FILTER (WHERE e.event_category = 'state_change') AS state_changes
           FROM issues i JOIN events e ON e.process_id = i.number
           GROUP BY 1 HAVING state_changes > 2 ORDER BY state_changes DESC LIMIT 10""",
    ),
}


def metrics(directory: Path, only: str | None) -> int:
    issues = str(directory / "agile_issues_*.csv")
    events = str(directory / "agile_events_*.csv")
    if not list(directory.glob("agile_issues_*.csv")):
        sys.exit(f"no agile_issues_*.csv in {directory}")

    duckdb.sql(f"CREATE OR REPLACE VIEW issues AS "
               f"SELECT * FROM read_csv_auto('{issues}', union_by_name = true)")
    if list(directory.glob("agile_events_*.csv")):
        duckdb.sql(f"CREATE OR REPLACE VIEW events AS "
                   f"SELECT * FROM read_csv_auto('{events}', union_by_name = true)")

    for name, (about, sql) in METRICS.items():
        if only and name != only:
            continue
        if "events" in sql and not list(directory.glob("agile_events_*.csv")):
            print(f"\n{name} -- skipped, no event export found")
            continue
        print(f"\n{name} -- {about}")
        try:
            print(duckdb.sql(sql))
        except duckdb.Error as exc:
            print(f"  failed: {str(exc).splitlines()[0]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="agile_analytics", description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, required=True, help="a project key's export directory")
    sub = parser.add_subparsers(dest="command", required=True)

    fold = sub.add_parser("compact", help="fold daily exports into monthly, newest row wins")
    fold.add_argument("--month", help="YYYYMM; default every month present")
    fold.add_argument("--keep", action="store_true", help="do not delete the daily files")
    fold.set_defaults(func=lambda a: compact(a.dir, a.month, a.keep))

    report = sub.add_parser("metrics", help="six Agile metrics over the export")
    report.add_argument("--only", choices=sorted(METRICS))
    report.set_defaults(func=lambda a: metrics(a.dir, a.only))

    args = parser.parse_args()
    if not args.dir.is_dir():
        sys.exit(f"{args.dir} is not a directory")
    return args.func(args) and 0 or 0


if __name__ == "__main__":
    sys.exit(main())
