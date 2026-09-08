"""Say whether the default branch's last CI run passed, loudly if it did not.

**CI already caught the failure this exists for. Nobody was told.** Two pull
requests, each green on its own branch, left `main` red on the merge; the
`push: branches: [main]` run fired and failed at `ebd4b4d`, and `main` then sat
red while the next branch was cut from it, a pull request was opened, reviewed
and merged. It was found by running `make test` for an unrelated reason.

The mechanism that would normally prevent it -- branch protection with *require
branches to be up to date before merging*, which re-runs a pull request's checks
when the base moves -- is not available here:

    $ gh api repos/paulcaron16k/gh-agile/branches/main/protection
    403  Upgrade to GitHub Pro or make this repository public to enable this
         feature.

So this is the backstop: a check cheap enough to run from a git hook after every
pull, which is the moment somebody is already looking at the terminal.

Read-only. It calls `gh run list` and nothing else, and it never writes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

#: Runs still in flight say nothing about the branch yet, and a cancelled one
#: says only that somebody stopped it.
DECIDED = ("success", "failure", "startup_failure", "timed_out", "action_required")


def runs(branch: str, limit: int) -> list[dict]:
    """The newest workflow runs on `branch`, newest first."""
    if not shutil.which("gh"):
        # The same failure mode `gh-agile` documents: PATH is minimal in a hook
        # and in cron, and a traceback is a poor way to learn it.
        raise SystemExit("the `gh` CLI is not on PATH; this check shells out to it")
    result = subprocess.run(
        ["gh", "run", "list", "--branch", branch, "--limit", str(limit),
         "--json", "conclusion,status,headSha,displayTitle,workflowName,url,createdAt"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"gh run list failed: {result.stderr.strip()}")
    return json.loads(result.stdout or "[]")


def newest_decided(entries: list[dict]) -> dict | None:
    """The newest run that reached a verdict, or `None` if none has."""
    return next((r for r in entries if r.get("conclusion") in DECIDED), None)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ci_status", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--limit", type=int, default=10,
                        help="runs to look back through for one that has a verdict")
    parser.add_argument("--quiet", action="store_true",
                        help="print nothing when the branch is green; for a git hook")
    args = parser.parse_args()

    run = newest_decided(runs(args.branch, args.limit))
    if run is None:
        if not args.quiet:
            print(f"  no finished CI run on {args.branch} yet")
        return 0
    if run["conclusion"] == "success":
        if not args.quiet:
            print(f"  {args.branch} is green: {run['headSha'][:7]} {run['displayTitle'][:60]}")
        return 0

    # Loud, and on stderr, because the whole defect was a failure that scrolled
    # past. A quiet hook that whispers is the thing being replaced.
    print(f"\n  !! {args.branch} is RED -- {run['conclusion']}\n"
          f"     {run['headSha'][:7]}  {run['displayTitle'][:60]}\n"
          f"     {run['workflowName']}: {run['url']}\n"
          f"     Fix it before building on this branch: what you just pulled is broken.\n",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
