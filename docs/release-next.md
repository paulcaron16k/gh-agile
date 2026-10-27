# gh-agile — changes since v0.4.0

Not yet tagged. `main` is the release, so `gh extension upgrade agile` already
brings these; the tag, when one is cut, names the build.

## What changed spelling

| Was | Is | Stage |
|---|---|---|
| `--format json` on a list, view or status | `--json [fields]`, with `-q/--jq` and `-t/--template` | Retired |

`--format jsonl` stays on the lists, `board view` and `sprint view`, where it
streams one object per line, and `export --format json|csv` stays: `gh` has no
flag for either. The old spelling fails at argument parsing and, for one
release, names `--json`. *Stage* is the README's
[deprecation policy](../README.md#deprecation-policy); this rename predates it.

## Changed behaviour

- **`issue close` on an issue that is already closed finishes it** (AGILE-285).
  It used to call `gh issue close`, which is a no-op on a closed issue that
  exits 0, so the command did nothing while looking like it worked, and
  finishing a merged issue needed `issue move N Done --evidence`. Now it skips
  the close and writes the evidence, sets Status to Done and stamps the closing
  `sprint:` label, and says it did. A reason other than the one GitHub
  recorded (`-r "not planned"` on an issue closed as completed, or the reverse)
  is refused with the reopen-and-close that changes it. `issue move N Done`
  still works; the post-merge hook, `board view` and `sprint carryover` now
  suggest `issue close`.
- **Sprint writes keep every assignment** (AGILE-290). The iteration input
  gained an `id`, and every write sends it, so creating or renaming a sprint no
  longer clears each item's Sprint and re-applies it.
- **Starting work keeps `ahead` sprints stocked** (AGILE-288): `issue move N
  "In Progress"` runs `sprint ensure` whenever fewer than `ahead` sprints lie
  beyond today, not only when none is active.

## New

- **`sprint carryover`** (AGILE-283): a sprint's unfinished work moves to the
  next, as Jira's *complete sprint* does; it runs `sprint ensure` first.
- **`sprint edit SPRINT --title`** (AGILE-290): rename a sprint, keeping every
  assignment.
- **`validate --json`**, with `-q/--jq` and `-t/--template` (AGILE-284), for a
  scheduled job or CI; the exit status is unchanged.
- **`--json`, `-q/--jq` and `-t/--template` on every list, view and status**
  (AGILE-219), with `gh`'s meanings. `--jq` runs the `jq` program; `--template`
  is a subset of Go's templates and refuses the rest by name.
- **`-a`, `-A`, `-l` and `-m` on every list** (AGILE-220), as `gh issue list`
  takes them, ANDed with the list's own filter and `-S`.
- **Every command's `--help` is in `gh`'s layout** (AGILE-222), each flag
  described once from the parser; the `fields:` tables, which disagreed with it,
  are gone.
- **An unknown flag is reported against its command** (AGILE-221), with that
  command's usage.
- **`init` installs the post-merge hook where git runs it** from a linked
  worktree or with `core.hooksPath` (AGILE-223).
