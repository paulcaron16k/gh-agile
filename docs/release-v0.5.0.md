# gh-agile v0.5.0 — beta, and sprints that keep their assignments

**The first build since gh-agile was declared beta** (AGILE-264). It has run three
boards for months, so the README now says *beta*, and its new *Deprecation policy*
says how a command or flag is renamed from here on: deprecated (the old spelling
still runs and warns), then retired (it fails and names the replacement), then
removed. The profile and the export columns follow the same stages.

**The release's largest change is one GitHub made.** The input that rewrites a
project's sprints gained an `id` field on 2026-10-01. Until then every sprint write
cleared every item's Sprint field board-wide and had to be repaired; now the tool
sends each sprint's id, so creating, topping up or renaming a sprint keeps every
assignment. Measured on this project's own board: 133 assignments, none lost.
And so that the next such change is found on purpose rather than by chance, the
repository now watches GitHub's GraphQL schema every month.

`main` is the release, so `gh extension upgrade agile` already brings all of this;
the tag names the build.

## What changed spelling

| Was | Is | Stage |
|---|---|---|
| `--format json` on a list, view or status | `--json [fields]`, with `-q/--jq` and `-t/--template` | Retired |

`--format jsonl` stays on the lists, `board view` and `sprint view`, where it
streams one object per line, and `export --format json|csv` stays: `gh` has no
flag for either. The old spelling fails at argument parsing and, for one
release, names `--json`. *Stage* is the README's
[deprecation policy](../README.md#deprecation-policy); this rename predates it.

**The hints for v0.4.0's retired spellings stay in this build.** v0.4.0's note
said the release after it would remove them; it does not. The deprecation policy
written since allows a retired spelling to keep its hint for at least one more
tagged build, and removing them is a code change this release does not make.
Every one of them still fails at argument parsing, as before.

## Changed behaviour

- **Sprint writes keep every assignment** (AGILE-290). Every write sends each
  existing sprint's id; if GitHub ever replaced one anyway, the tool says so,
  re-applies the assignments and heals from the `sprint:` labels. The refusal
  when the GraphQL budget could not cover a full restore is gone (AGILE-292),
  removed once measured on a real board. **A sprint may now be renamed**, which
  the old behaviour forbade.
- **Starting work keeps `ahead` sprints stocked** (AGILE-288). `issue move N
  "In Progress"` runs `sprint ensure` whenever no sprint covers today or fewer
  than the profile's `ahead` lie beyond it, not only when none is active.
- **`issue close` finishes an issue that is already closed** (AGILE-285). A merge
  closes the issue first; `issue close` now skips the close and writes the
  evidence, sets Done and stamps the closing `sprint:` label, and says so. A
  reason other than the one GitHub recorded is refused with the reopen-and-close
  that changes it. `issue move N Done` still works; the post-merge hook,
  `board view` and `sprint carryover` now suggest `issue close`.
- **`sprint create` names a sprint from `name_template`** (AGILE-209), as
  `sprint ensure` always did; `--title` still overrides.
- **`story create` and `bug create` stamp the epic's `initiative:` label**
  (AGILE-281), so a board filtered to the initiative shows the new issue at once.

## New

- **`sprint carryover [SPRINT] [--to SPRINT]`** (AGILE-283): a sprint's
  unfinished work moves to the next, as Jira's *complete sprint* does. Finished
  work stays; it runs `sprint ensure` first.
- **`sprint edit SPRINT --title`** (AGILE-290): rename a sprint, keeping every
  assignment.
- **`issue edit --epic E|none` and `--initiative I|none`** (AGILE-270): move a
  story or bug to another epic, or an epic to another initiative, in one call,
  relabelling every initiative it touched. `issue edit --dry-run` says what
  would change.
- **`bug create`, `bug list` and `bug view`** (AGILE-252): a bug is a first-class
  level, with `--epic` optional.
- **`validate --json`**, with `-q/--jq` and `-t/--template` (AGILE-284), for a
  scheduled job or CI; the exit status is unchanged, and `validate --help` now
  states it (AGILE-271).
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

## Fixed

- **`issue edit`, `move` and `close` find the board item from the issue**
  (AGILE-231), not from the board's item list, which GitHub can leave a new item
  out of for hours. Creating an issue that a project workflow boarded first now
  finds it the same way (AGILE-257).
- **The post-merge hook asks GitHub which pull requests a merge brought in**
  (AGILE-225) rather than parsing commit subjects, and follows a local merge
  commit into its second parent (AGILE-233), so a pull that could not
  fast-forward is checked rather than reported clean.
- **`init` recognises a hook that already calls `gh agile unfinished`**
  (AGILE-234) instead of asking for the line again.
- **`--help` says each thing once** (AGILE-268): no default stated twice, refused
  `gh` flags listed apart, one wording per meaning of `-R`, and top-level commands
  grouped as SETUP, BOARD and GENERAL.
- **`key list` with no profile refuses** (AGILE-271), naming the paths it
  searched, instead of printing nothing.

## For maintainers

- **GitHub API drift is tracked** (AGILE-291, 297, 298, 299).
  `GitHub_API_spec.json` is the GraphQL schema as last seen, ordered so a diff is
  only real change. `make api-drift` compares it with the live schema and, on
  drift, appends an entry to `GitHub_API_changelog.md`: what changed, listed
  first where it touches what gh-agile's own GraphQL selects or sends, beside
  GitHub's dated changelog and the removals GitHub has announced. A workflow
  runs it monthly and opens a pull request assigned to the owner.
- **CI runs the interpreter it names** (AGILE-275): every job had built its venv
  from 3.12, so 3.10, 3.11 and 3.13 were never tested until now.
- **`make test` is offline by construction** (AGILE-242), not by convention.
- **`scripts/agile_analytics.py` works with DuckDB 2** (AGILE-272), and buckets
  months in UTC.
