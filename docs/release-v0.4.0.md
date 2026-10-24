# gh-agile v0.4.0 — a CLI shaped like `gh`

**This release breaks spellings, on purpose, and none silently.** `gh agile epic list`
filed an epic called "list" (WIDG-185): `epic` took its first word as a title. The
fault was the tool's shape, so AGILE-200 (#200) reshaped it on `gh`'s own rules —
measured against `gh` 2.86's help, not remembered.

Every spelling below **fails at argument parsing**; nothing retired is reinterpreted as
something else. For this one release the error also **names the replacement, rebuilt
from what you typed**:

```
$ gh agile epic "Snapshot expiry" --key AGILE
gh agile: `epic TITLE` is now `epic create -t TITLE`, as `gh issue create -t` takes it:
  gh agile epic create -t 'Snapshot expiry' --key AGILE
```

The release after this one removes the hints, and an old spelling becomes an ordinary
usage error.

## What changed spelling

| Was | Is |
|---|---|
| `epic`/`story`/`task TITLE` | `epic`/`story`/`task create -t TITLE` |
| `initiative create TITLE` | `initiative create -t TITLE` |
| `story create ... --status S` | `story create ...`, then `issue move N S` |
| `move ISSUE --status S` | `issue move ISSUE S` |
| `move ISSUE --close [--not-planned]` | `issue close ISSUE [-r "not planned"]` |
| `set --issue N --field F --value V` | `issue edit N --field F --value V` |
| `set`/`issue edit ... --number N` | `issue edit ... --value N` |
| `fix --id N` | `issue reconcile N` |
| `validate --id N` | `issue view N` |
| `plan ISSUE --start/--target/--for` | `issue edit ISSUE --start/--target/--for` |
| `--add-assignee` with no value | `--add-assignee @me` |
| `board show` | `board view` |
| `board create --name N` | `board create N` |
| `setup` | `init` |
| `project create` | `init` |
| `project owner` | `init` |
| `hooks` | `init` (installs the hook; `--no-hooks` to skip) |
| `project sprint-template --template T` | `project edit --sprint-template T` |
| `project title-prefix --mode M` | `project edit --title-prefix M` |
| `key --key K` | `key add K` |
| `key` | `key list` |
| `export --csv` | `export --format csv` |
| `export --state F` | `export --state-file F` |
| `export --grain both` | `export --grain issues,events` |
| `sync --query` | `sync --search` |

Missing the short `move`? `gh` has the answer for that:

```bash
gh alias set mv 'agile issue move'
gh mv WIDG-34 "In Progress"
```

## The rules it now follows

- **Work items are noun groups.** `initiative`, `epic`, `story` and `task` each have
  `create`, `list` and (except `task`) `view`; a title is `-t`, never a positional.
  `issue` acts on any of them: `list`, `status`, `view`, `move`, `edit`, `close`,
  `reopen`, `reconcile`.
- **General and targeted.** `--help` splits **GENERAL COMMANDS** (no identifier) from
  **TARGETED COMMANDS** (the identifier first, every time), as `gh issue --help` does. A
  group with one kind prints one **AVAILABLE COMMANDS** list.
- **`gh issue`'s flags.** Every `create` takes `-b`, `-F`, `-a`, `-l`, `-m`;
  `issue edit` takes several issues and `gh issue edit`'s flags, plus the board's
  fields, and `-t` keeps the `KEY-n` prefix that plain `gh issue edit -t` drops.
- **Status has one door.** Only `issue move` and `issue close` change Status, and
  nothing reaches Done without Evidence.
- **One way to stand a project up.** `init` creates or adopts the project, converges its
  fields, labels and boards, records `project.owner`, and installs the post-merge hook.
  Run it again to converge.
- **One meaning per flag.** `--state` is open/closed/all everywhere; `--format` is
  `json`, `jsonl` or `csv`; no flag is accepted abbreviated. A `list` into a pipe
  prints tab-separated rows with no header, as `gh issue list` does.

## New

- `gh agile issue status` — the current sprint at stand-up: yours by Status, what is in
  review, what nobody holds.
- `list` and `view` for every level; `sprint view [SPRINT]`; `project view`;
  `key list | add | delete`; `-w/--web` on lists and views.

## Security review

Reviewed before tagging; the result is recorded here, because a review with no written
result is indistinguishable from a skipped one.

Scope: `v0.3.0..` the release commit — AGILE-196, -197, -201 through -207, -210,
-211; 40 files. Done 2026-10-22, before tagging.

- **No credential is read, stored or passed.** No new code touches a token; every API
  call still shells out to `gh`. The caller is `gh api user`, never a git config.
  No credential-shaped literal in any shipped file (`ghp_`, `github_pat_` searched).
- **No shell.** No `shell=True`, `os.system`, `eval` or `exec`; every subprocess is
  an argument list.
- **Every new GraphQL document takes its values as variables** — the search in
  `key delete` and `task list`, the issue view. The one interpolated mutation, the
  iteration write in `sprint create`, is unchanged and still validates its dates and
  `json.dumps` its titles.
- **New writes, and what guards each.** `init` now writes `.git/hooks/post-merge` by
  default: fixed content, executable, replaced only when it carries this tool's marker,
  and `--no-hooks` skips it. `key delete` refuses while any issue carries the key.
  `issue edit` checks every refusal on every issue before any write. `create -l`
  refuses the labels the tool owns, before the issue exists.
- **No destructive default changed.** The iteration write still saves, budgets,
  restores and heals. `export` now *refuses* several grains to stdout where it
  silently printed only the issues.
- **Nothing retired is reinterpreted.** Flag abbreviation is off: `export --state`
  had been parsing as `--state-file` by prefix.
- `make check-guide` executes only read commands; the four it gained — `key list`,
  `project view`, `sprint view`, `issue status` — write nothing.

**Result: no finding. The release may be tagged.**
