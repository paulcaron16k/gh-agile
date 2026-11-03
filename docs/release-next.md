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

## What changed behaviour

**`validate` checks the `initiative:` label against the sub-issue tree** (AGILE-309),
in both directions: an issue in an initiative's tree without the label, and a label
on an issue that has left the tree. Both are problems, so **a board that passed
before can now fail** -- typically stories created before story create began
stamping the label, or issues given a parent in GitHub's web UI. `initiative
reconcile <slug>` fixes them; each finding names it. Where the parent chain leaves
the board, the label is a note that it cannot be checked, never a failure.

**`github_issues.initiative_slug` is read from the hierarchy, not the label**, and
is now nullable: empty when the issue is under no initiative, null when the parent
chain leaves the board before it can tell. It used to be blank wherever the label
had drifted. CSV writes both as empty; `github_catalog.json` states the type.
`board view --filter initiative:` still reads the label, so it agrees with the
saved board GitHub evaluates.
