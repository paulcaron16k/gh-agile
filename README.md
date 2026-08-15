# gh-agile

A `gh` extension for running Agile work on GitHub Projects v2 — and, more to the
point, for **getting the data back out** in a form you can analyse the way you
would a Jira export.

```bash
gh extension install paulcaron16k/gh-agile

gh agile --project 1 validate          # do the conventions hold?
gh agile --project 1 export --csv      # backlog with status history
```

## Why not just `gh project item-list`?

Because that gives you a **snapshot**. `ProjectV2Item` exposes `createdAt`,
`updatedAt` and the current field values — and nothing else. No history. So a
snapshot cannot answer when an item entered *In progress*, which is every flow
question worth asking.

The history does exist, but on the **issue timeline**, as
`ProjectV2ItemStatusChangedEvent` and `AddedToProjectV2Event`. `gh agile export`
runs both queries and joins them on the issue node ID, so each row carries:

| | |
|---|---|
| `added_to_board_at` | when the item joined the project |
| `started_at` | first transition to *In progress* |
| `done_at` | arrival at *Done* |
| `cycle_time_days` | `started_at` → `done_at` |
| `lead_time_days` | `added_to_board_at` → `done_at` |

plus every custom field flattened to a `field_*` column, the epic from the
sub-issue parent, labels, assignees and sub-issue roll-up counts.

Use `--no-history` to skip the per-issue timeline query. It is much faster and
the result is a snapshot with no cycle time — which is fine for a board dump and
useless for a flow report, so it is opt-in rather than the default.

## The fields it creates

`gh agile setup` is idempotent and converges: it creates what is missing and
adds missing *options* to a single-select that already exists, never removing
one — removing an option silently clears the field on every item holding it.

| Field | Type | Gold model |
|---|---|---|
| `Story Points` | number | `story_points` |
| `Priority` | single-select — `lowest…highest` | `priority_id` |
| `FR` | text | requirement traceability |
| `Sprint` | iteration | `sprint_id` |
| `Status` | single-select — `Todo`, `In Progress`, `Blocked`, `In Review`, `Done` | `state_id` |

`Status` exists on every new project with three options; the other two are added,
because `blocked_hours` and `review_hours` are computed from time spent in them
and are otherwise permanently null. Epic, parent and sub-issue progress need no
custom field — GitHub provides them natively.

## Jira-style keys

GitHub projects have a `title` and a `shortDescription` and **no key of any
kind**. Since the issue-number sequence is per *repository* — and a project can
span repositories — the key is recorded per repository:

```bash
gh agile key --repo paulcaron16k/Zamboni --key ZMBNI
gh agile --project 4 key --repo paulcaron16k/gh-agile --key AGILE \
         --name "gh-agile: Agile management on GitHub"
gh agile key                                    # list what is recorded
```

The export then carries `issue_key` — `AGILE-14`, `ZMBNI-1817` — which is the
Gold model's `issue_key`. Without a recorded key it falls back to
`owner/repo#14`, so the column is never empty. `--name` additionally writes
`"<name> [<KEY>]"` to the project's `shortDescription`, the nearest thing GitHub
has to a place for the pair.

## Incremental export

For feeding another system on a schedule:

```bash
gh agile --project 4 export --csv --out-dir exports/     # full; writes a watermark
gh agile --project 4 export --csv --out-dir exports/     # since the watermark
gh agile --project 4 export --since 2026-08-01T00:00:00Z # explicit override
gh agile --project 4 export --no-state                   # always full
```

Files are named `agile_issues_<ISO8601 basic>.csv` — `agile_issues_20260814T184850Z.csv`
— which has no colons, so it is a legal filename everywhere, and still sorts
lexicographically. A loader can import a directory in order without parsing the
names. Each row also carries `exported_at`, so concatenated exports keep their
ordering without re-deriving it from a path.

State lives in `.gh_agile_export.json`, keyed by `owner/project`, so one file can
track several boards:

```json
{ "paulcaron16k/4": { "last_export_at": "…", "watermark": "…", "rows": 4 } }
```

**The watermark is deliberately pulled back**, by `--overlap-seconds` (default
900). A status change takes time to reach the timeline — measured at ~75s and
variable — so an item whose `updatedAt` has already moved may still be missing
its newest event. Cutting exactly at the last watermark would skip that event
permanently, because the item never updates again. Re-reading a window emits the
row twice, which the target resolves latest-wins on its primary key. **A
duplicate is free; a hole is not.**

Incrementality does not reduce the items query, which has no server-side
`updatedAt` filter and is fetched in full. It reduces the *timeline* queries,
which are one per issue and the real cost.

> JSON rather than the `.yml` the design sketch suggested: there is no YAML
> parser in the standard library, and a partial one that reads only what this
> tool writes is a trap the first time someone edits it by hand.

## What it does not do yet

Creation. `setup`, `epic` and `story` are the next iteration; until then use
`gh project item-create` and the web UI. The read side came first deliberately:
the export schema is the one thing that cannot be changed later without
re-analysing everything already exported.

## Requirements

`gh`, authenticated with `project` scope:

```bash
gh auth refresh -s project
```

Python 3.9+. Standard library only — no dependencies, and no token is ever read,
stored or passed by this tool. Authentication is `gh`'s job.

## Mapping to the Gold Agile data model

[GOLD_MODEL.md](GOLD_MODEL.md) maps every column onto ExperienceFlowAI's
`agile_issues` and `agile_events`, so GitHub and Jira land in one shape. It also
records the two things measurement turned up rather than documentation:
GitHub emits **no event for a Projects v2 custom field change** (only Status has
one), and the timeline is **eventually consistent** — a transition can take a
minute or more to become readable.

## The rules it enforces

`gh agile validate` checks what a machine can: every story has an epic, every
epic has stories, statuses come from the declared set, closed items are *Done*
and open ones are not, and everything carries a `type:` label. The conventions
themselves — and which parts a person owns rather than a machine — are in
[POLICY.md](POLICY.md).
