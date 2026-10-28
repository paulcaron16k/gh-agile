# gh-agile — changes since v0.5.0

Not yet tagged. `main` is the release, so `gh extension upgrade agile` already
brings these; the tag, when one is cut, names the build.

## What changed spelling

| Was | Is | Stage |
|---|---|---|
| Every spelling v0.4.0 retired: `epic`/`story`/`task TITLE`, top-level `move`, `set`, `fix` and `plan`, `validate --id`, `board show`, `setup`, `hooks`, `project create`/`owner`/`sprint-template`/`title-prefix`, bare `key` and `key --key`, `export --csv`/`--state`/`--grain both`, `sync --query`, bare `--add-assignee` | See [v0.4.0's note](release-v0.4.0.md) | Removed |
| `--format json` on a list, view or status (retired in v0.5.0) | `--json [fields]`, with `-q/--jq` and `-t/--template` | Removed |

**The hints are gone** (AGILE-307), as the v0.4.0 and v0.5.0 notes said they
would be. Each old spelling still fails at argument parsing, before anything
runs, and none is reinterpreted as something else; it now fails like any other
typo, with the command's usage rather than a line naming the replacement.
