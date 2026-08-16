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


#: Period-shaped metrics. Each returns one number per period, so the report is
#: a matrix: metrics down, periods across.
#:
#: Weekly and daily are deliberately absent from the choices. A fortnight's
#: throughput on a small team is three items, and a week's is one -- a number
#: that swings 100% on one story tells you nothing about the process.
PERIOD_METRICS = {
    "throughput": ("items reaching Done",
                   "count(*) FILTER (WHERE done_at IS NOT NULL)"),
    "points_done": ("story points completed",
                    "coalesce(sum(field_story_points) FILTER (WHERE done_at IS NOT NULL), 0)"),
    "created": ("items created", "count(*)"),
    "cycle_time_median": ("median days In Progress -> Done",
                          "round(median(cycle_time_days), 2)"),
    "lead_time_median": ("median days on board -> Done",
                         "round(median(lead_time_days), 2)"),
    "carryover": ("started but not finished",
                  "count(*) FILTER (WHERE started_at IS NOT NULL AND done_at IS NULL)"),
}

RANGES = {"yearly": "year", "quarterly": "quarter", "monthly": "month"}


def periods(kind: str, start_date, count: int = 5) -> list[tuple[str, object, object]]:
    """The last `count` periods ending with the one containing today.

    Quarters start 1 January, as asked, so the boundaries are calendar ones a
    finance or planning cycle already uses rather than N days back from today.
    """
    import datetime as dt

    today = dt.date.today()
    out = []
    if kind == "quarterly":
        q = (today.month - 1) // 3
        year, index = today.year, q
        for _ in range(count):
            first = dt.date(year, index * 3 + 1, 1)
            last = (dt.date(year + (index == 3), (index * 3 + 4) if index < 3 else 1, 1)
                    - dt.timedelta(days=1))
            out.append((f"{year}-Q{index + 1}", first, last))
            index -= 1
            if index < 0:
                index, year = 3, year - 1
    elif kind == "monthly":
        year, month = today.year, today.month
        for _ in range(count):
            first = dt.date(year, month, 1)
            last = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1))
            out.append((f"{year}-{month:02d}", first, last))
            month -= 1
            if month == 0:
                month, year = 12, year - 1
    else:
        for offset in range(count):
            year = today.year - offset
            out.append((str(year), dt.date(year, 1, 1), dt.date(year, 12, 31)))
    out.reverse()
    if start_date:
        out = [p for p in out if p[2] >= start_date]
    return out


def metrics(directory: Path, kind: str, start_date, context: str) -> int:
    issues = str(directory / "agile_issues_*.csv")
    if not list(directory.glob("agile_issues_*.csv")):
        sys.exit(f"no agile_issues_*.csv in {directory}")
    duckdb.sql(f"CREATE OR REPLACE VIEW issues AS "
               f"SELECT * FROM read_csv_auto('{issues}', union_by_name = true)")

    spans = periods(kind, start_date)
    # The last column is the period we are inside, and it is labelled so nobody
    # reads a third of a quarter as a decline.
    headers = [label for label, _s, _e in spans[:-1]] + [f"{spans[-1][0]} in-progress"]

    keys = ["(all)"]
    if context == "key":
        keys += [
            row[0] for row in duckdb.sql(
                "SELECT DISTINCT split_part(issue_key, '-', 1) AS k FROM issues "
                "WHERE issue_key IS NOT NULL ORDER BY k"
            ).fetchall()
        ]

    print(f"  {kind}, {context} context, {len(spans)} periods\n")
    rows = []
    for key in keys:
        where_key = "" if key == "(all)" else (
            f" AND split_part(issue_key, '-', 1) = '{key}'"
        )
        for metric, (about, expression) in PERIOD_METRICS.items():
            label = metric if key == "(all)" else f"{key} - {metric}"
            values = []
            for _name, first, last in spans:
                # Items are attributed to a period by when they *finished*,
                # except `created`, which is attributed by when it began --
                # otherwise nothing created and unfinished would ever appear.
                column = "created_at" if metric == "created" else "coalesce(done_at, started_at)"
                sql = (f"SELECT {expression} FROM issues WHERE CAST({column} AS DATE) "
                       f"BETWEEN DATE '{first}' AND DATE '{last}'{where_key}")
                value = duckdb.sql(sql).fetchone()[0]
                values.append("" if value is None else value)
            rows.append((label, about, values))

    width = max(len(r[0]) for r in rows) + 2
    print("  " + "context".ljust(width) + "".join(h.rjust(20) for h in headers))
    print("  " + "-" * (width + 20 * len(headers)))
    for label, _about, values in rows:
        print("  " + label.ljust(width) + "".join(str(v).rjust(20) for v in values))
    print()
    for metric, (about, _e) in PERIOD_METRICS.items():
        print(f"    {metric:20} {about}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="agile_analytics", description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, required=True, help="a project key's export directory")
    sub = parser.add_subparsers(dest="command", required=True)

    fold = sub.add_parser("compact", help="fold daily exports into monthly, newest row wins")
    fold.add_argument("--month", help="YYYYMM; default every month present")
    fold.add_argument("--keep", action="store_true", help="do not delete the daily files")
    fold.set_defaults(func=lambda a: compact(a.dir, a.month, a.keep))

    report = sub.add_parser("metrics", help="Agile metrics by period")
    report.add_argument("--time-range", default="quarterly", choices=sorted(RANGES),
                        help="weekly and daily are omitted: too few items per period "
                             "to mean anything (default: %(default)s)")
    report.add_argument("--start-date", help="ISO date; drop periods ending before it")
    report.add_argument("--context", default="project", choices=["project", "key"],
                        help="project is every issue together; key groups by the issue's "
                             "key label (default: %(default)s)")
    report.set_defaults(func=lambda a: metrics(
        a.dir, a.time_range,
        __import__("datetime").date.fromisoformat(a.start_date) if a.start_date else None,
        a.context))

    args = parser.parse_args()
    if not args.dir.is_dir():
        sys.exit(f"{args.dir} is not a directory")
    return args.func(args) and 0 or 0


if __name__ == "__main__":
    sys.exit(main())
