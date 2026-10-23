# gh-agile — changes since v0.4.0

Not yet tagged. `main` is the release, so `gh extension upgrade agile` already
brings these; the tag, when one is cut, names the build.

## What changed spelling

| Was | Is |
|---|---|
| `--format json` on a list, view or status | `--json [fields]`, with `-q/--jq` and `-t/--template` |

`--format jsonl` stays on the lists, `board view` and `sprint view`, where it
streams one object per line, and `export --format json|csv` stays: `gh` has no
flag for either. The old spelling fails at argument parsing and, for one
release, names `--json`.

## New

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
