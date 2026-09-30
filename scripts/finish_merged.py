"""Name the issues this merge closed and did not finish, at the terminal.

**A project workflow cannot close an issue properly, so this board does not let
one try.** GitHub's built-in `Item closed -> Status = Done` writes one field: no
Evidence, no closing `sprint:` label, no choice between completed and not
planned. An issue it touches reads `Done` while being unfinished, which is worse
than one visibly left `In Progress` -- the second costs a command, the first is
indistinguishable from work somebody actually did.

So the workflow stays off and the wrap-up is a person's. What that needs is for
the person to be *told*, at the moment they are already at the terminal, rather
than at the next time somebody remembers to run `validate`. `#123` sat closed
and `In Progress` for twenty-two hours, `#138` repeated it on the next merge,
and `#174` was still in that state days later. None of those is an argument for
the workflow; every one is an argument for this.

**Two states, because a merge leaves either one** (`#190`). GitHub may close the
issue and leave the board behind, or -- just as often here -- not close it at
all: `#186`'s own merge left it open. They need different commands, so this
reads the state once and says which.

The same moment, and the same reasoning, as `ci_status.py`: `git pull` on `main`
after a merge is when somebody is looking.

**Read-only, and it never fails a pull.** It runs `git log`, `gh pr view` and
`gh agile validate --id`, and returns 0 on every path -- no `gh`, no network, no
board, no `ORIG_HEAD`. A hook that can stop you pulling is a hook people delete.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys

#: How a merged pull request appears in `git log --format=%s`. Both spellings,
#: because the repository's merge style is a setting somebody can change and a
#: parser that knows only today's is one that silently stops reporting.
MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+)\b")
SQUASH_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")


def run(command: list[str]) -> str | None:
    """Stdout, or None if the command is unavailable or failed.

    None rather than an exception: every caller here would turn it into a quiet
    return anyway, because nothing this script reports is worth interrupting a
    pull for.
    """
    if not shutil.which(command[0]):
        return None
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def pull_requests(subjects: list[str]) -> list[int]:
    """The pull requests in these commit subjects, in order, without repeats."""
    found = []
    for subject in subjects:
        for pattern in (MERGE_SUBJECT, SQUASH_SUBJECT):
            match = pattern.search(subject)
            if match and int(match.group(1)) not in found:
                found.append(int(match.group(1)))
    return found


def closing_issues(pull_request: int) -> list[int]:
    """Which issues that pull request closes, **as GitHub computed it**.

    Not by parsing `Closes #n` out of the commit message: in this repository the
    reference lives in the pull request *body*, and the merge commit says only
    which pull request it was. `closingIssuesReferences` is the resolved answer
    and costs one call.
    """
    out = run(["gh", "pr", "view", str(pull_request), "--json",
               "closingIssuesReferences"])
    if out is None:
        return []
    refs = (json.loads(out or "{}") or {}).get("closingIssuesReferences") or []
    return [ref["number"] for ref in refs]


def unfinished(issue: int) -> str | None:
    """What `validate` says about this one issue, or None if it is in order.

    The rule is not restated here. `validate --id` already knows what a closed
    issue should look like -- Status `Done`, a `sprint:` label, a tally that
    agrees -- and a second copy of that list is one that can disagree with it.
    Its exit code is the seam: 1 when it found something, 0 when it did not.
    """
    if not shutil.which("gh"):
        return None
    result = subprocess.run(["gh", "agile", "validate", "--id", str(issue)],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 1 and result.stdout.strip() else None


def issue_state(issue: int) -> str | None:
    """`OPEN` or `CLOSED`, or None if it cannot be read.

    Read **once**, with both branches turning on it. Asking twice -- once to
    decide which message to print and once to decide which command -- is how the
    two end up disagreeing about what finished means.
    """
    out = run(["gh", "issue", "view", str(issue), "--json", "state"])
    return (json.loads(out or "{}") or {}).get("state") if out is not None else None


#: The two states a merge can leave an issue in, and what each one needs. They
#: are different commands, which is why this is not a filter over one message.
#:
#: **GitHub's auto-close is not reliable here.** Measured across five
#: consecutive pull requests: `closingIssuesReferences` was registered for every
#: one of them -- #189 -> 186, #188 -> 187, #185 -> 183, #184 -> 182, #181 ->
#: 179 -- and the close fired for some and not others. #186's own merge left it
#: open, which is how this gap was found. So the open case is at least as common
#: as the closed one, and a prompt covering only the closed one reads, to
#: somebody watching it stay quiet, as an assurance that nothing is outstanding.
STILL_OPEN = (
    "is still open, although a merged pull request in this range says it closes it.",
    "--close, because nothing else has closed it and the reason is this tool's\n"
    "      to choose -- `completed`, or `--not-planned` if that is what happened.",
)
CLOSED_NOT_DONE = (
    "was closed by this merge, and the board has not caught up:",
    "no --close: it is already closed, and closing an issue twice is a\n"
    "      no-op that exits 0 -- which is how a close reason gets lost.",
)


def outstanding(issue: int) -> tuple[str, str, str] | None:
    """`(what is wrong, the command, why that command)`, or None if it is done.

    An issue left **open** is not a convention violation and `validate` rightly
    says nothing about it: the board cannot see pull requests, and a story left
    open after a partial merge is ordinary. What makes it reportable is local to
    the merge being pulled -- a pull request in this range said it closed it --
    which is exactly where this is standing, so the knowledge stays here rather
    than becoming a rule the validator cannot fairly hold.
    """
    state = issue_state(issue)
    if state is None:
        return None
    if state == "OPEN":
        detail, why = STILL_OPEN
        return detail, f"gh agile move {issue} --status Done --close --evidence \"...\"", why
    found = unfinished(issue)
    if not found:
        return None
    detail, why = CLOSED_NOT_DONE
    return f"{detail}\n{found}", f"gh agile move {issue} --status Done --evidence \"...\"", why


def report(issue: int, detail: str, command: str, why: str) -> str:
    """What the developer sees. One issue, what is wrong, and the command."""
    body = "\n".join(f"      {line}" for line in detail.splitlines()[1:] if line.strip())
    headline = detail.splitlines()[0]
    return (
        f"\n  #{issue} {headline}\n"
        + (f"{body}\n" if body.strip() else "")
        + f"\n      finish it:  {command}\n"
        f"      {why}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="finish_merged", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--range", default="ORIG_HEAD..HEAD",
                        help="the revision range just merged (default: %(default)s)")
    parser.add_argument("--quiet", action="store_true",
                        help="print nothing when there is nothing to finish; for a git hook")
    args = parser.parse_args()

    log = run(["git", "log", "--format=%s", args.range])
    if log is None:
        # No ORIG_HEAD on a first clone, no git on PATH, a range that does not
        # resolve. Silence rather than a complaint: this is a prompt, not a check.
        return 0
    issues = []
    for pull_request in pull_requests(log.splitlines()):
        for issue in closing_issues(pull_request):
            if issue not in issues:
                issues.append(issue)
    reports = [report(issue, *entry)
               for issue in issues if (entry := outstanding(issue))]
    if not reports:
        if not args.quiet:
            print(f"  nothing closed by {args.range} is waiting to be finished")
        return 0
    # On stderr and unmissable, for the reason the red-build report is: the
    # whole defect is a line that scrolled past.
    for text in reports:
        print(text, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
