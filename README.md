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
