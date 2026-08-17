# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`gh-agile` is a **`gh` CLI extension** providing Jira-style Agile project management over GitHub Issues and
GitHub Projects v2. It is one executable file — `gh-agile`, no `.py` suffix — plus documentation and tests.

**Standard library only, permanently.** `gh extension install` clones the repository and installs nothing, so
there is no dependency step for a script extension; an `import duckdb` in the extension would break every install
that happened not to have it. Analysis that needs third-party packages lives in `scripts/agile_analytics.py`,
which declares them with PEP 723 inline metadata and runs under `uv`.

Authentication is never handled here. Every API call shells out to `gh`, which owns the token. The tool never
sees one, and no command takes a `--token` flag.

## Commands

```bash
make venv          # create .venv from requirements-dev.txt -- do this first
make test          # 123 offline unit tests, no network, no GitHub account, ~0.4s
make lint          # ast parse + ruff over gh-agile, tests/, scripts/
make check-guide   # every command in USER_GUIDE.md exists; read-only ones run in a cron-like env
make coverage      # unit tests with a coverage report
make self-test     # LIVE: stands up a scratch project, exercises it, tears it down
make scratch       # LIVE: leaves a scratch project standing;  make teardown NUM=<n>
make metrics DIR=exports/AGILE
```

**Every Python target refuses to run outside `.venv`**, and `tests/conftest.py` refuses again from the inside for
anyone invoking pytest directly. Never fall back to the system interpreter: a suite that runs against whatever is
installed globally is testing a different environment on every machine.

`ruff.toml` pins the rule set. Without it the rules are whatever the installed ruff defaults to, which changed
mid-project — the same code passed with one version and reported thirty findings with the next.

## Testing policy — read before touching a live repo

**Use the sandbox: `paulcaron16k/agile-test`, checked out at `../agile-test`.** See its `plan.txt`.

This exists because live-repo testing did real damage: a `key:TEST` label applied to all 26 `gh-agile` issues, ~13
throwaway issues created and deleted leaving permanent holes in the issue-number sequence, 11 scratch projects, and
two export files deleted. `gh-agile` is near alpha with issue tracking now load-bearing, and `Zamboni` is heading
for production. Neither is a test fixture.

Order of escalation: **offline tests → agile-test → gh-agile → Zamboni.** Most work needs no live repo at all now.
Only `self-test`, sprint destruction/repair and `sync --adopt` must hit real GitHub.

`agile-test` cannot reproduce bugs that need a board with history — 25 items, four sprints, months of timeline.
Seed it from an export rather than testing on the real board.

## The defect the design is built around

**Any write to a project's iteration configuration re-mints every iteration id and clears every item's `Sprint`
value — retroactively, silently, board-wide, including closed issues in completed sprints.**

Measured, not inferred. Renaming *one unused future sprint* unassigned four items staged across a completed, a
current and a future sprint. A pure **append** — every existing entry re-sent byte-identical plus one new — does
the same, and that append is the routine fortnightly act.

`ProjectV2Iteration`, the input object the mutation accepts, carries `startDate`, `duration` and `title` and **no
id**, so the configuration is replaced wholesale. There is no safe write.

Six workarounds exist for this one field, and they are not optional:

1. **Save and restore** every assignment around any iteration write (`sprint_assignments` / `restore_assignments`).
2. **`require_graphql_budget`** refuses the destructive write when the budget cannot cover the restore — the repair
   is one call per item with no transaction, and running out halfway loses assignments permanently.
3. **`sprint:YYYY-MM-DD` labels** on the issue are the real record. Dated, not named: a title is cosmetic and
   editable, a start date is identity, and dates sort.
4. **`sprint backfill`** recovers history for issues predating the labels, from Status transitions.
5. **`sprint reconcile`** sets the field from the labels.
6. **`heal_sprint_fields`** runs that reconcile automatically after `restore_assignments` in all three destructive
   paths.

**Field for the present, labels for the past.** The field is live UI state, allowed to be lossy because it is
re-derivable, and is the only thing that can answer "what is in the current sprint" — no label drives
`sprint:@current`. The labels are immutable history. Where they disagree, believe the labels.

**An empty field is damage; a disagreeing field is a decision.** The automatic heal fills empty fields only. An
open story deliberately re-planned into a future sprint has labels recording where it was *worked* — overwriting
that automatically would make the repair argue with the user. `sprint reconcile --overwrite` acts on it when asked.

## Architecture

**Profile** — `.github/agile.json`, visible and checked in (a dotfile would hide the convention from anyone
cloning). `keys` is an **ordered list**; the first entry for a repository is the default when `--key` is omitted.
`read_config` follows a `config_from: "owner/main-repo"` pointer, resolved through the API so it works for private
repos and cannot rot into a dead link. `apply_defaults` fills `--project`, `--repo` and `--key`, and **refuses**
when `--project` disagrees with `project.number` — that mismatch is almost always the right flag in the wrong clone.

**Labels carry what GitHub cannot.** `type:epic|story|bug`, `key:ZMBNI`, `sprint:YYYY-MM-DD`. Issue Types and
Issue Fields are organization-only (`createIssueField` resolves only an Organization node), so labels are the
carrier. Labels are also the only **additive** primitive in the API — `--add-label` appends without a
read-modify-write, unlike a title (whole-value replace) or an iteration configuration (replace-wholesale plus
collateral damage). That is why the sprint record lives on one.

**A project is a collection, not a filter.** An issue is not on a board until it is added, which is why `sync`
exists. A user-owned project has six built-in workflows and *auto-add repository issues is not among them*, and
built-in workflows cannot be enabled through the API at all — the schema has `deleteProjectV2Workflow` and nothing
that creates or updates one. Every project automation is a manual web-UI step.

**Export: silver tables.** `github_issues`, `github_events`, `github_project`, `github_boards`, `github_sprints`.
Gold `agile_*` belongs to the ExperienceFlow model and is produced by a silver→gold transform in the IWS pipeline;
nothing here writes an `agile_*` file. See `GOLD_MODEL.md`.

- **`event_hash` must be unique.** It covers `issue|kind|occurred|actor|previousStatus|status|detail`. Timestamps
  are per-second, and two status changes on one issue in the same second are ordinary — the earlier
  `issue|kind|occurred` produced 187 rows with 181 distinct hashes, and both the compactor and any keyed target
  drop the duplicates silently.
- **The watermark advances only on `--out-dir`.** It promises that everything up to it was delivered somewhere
  durable, and stdout is not. Reads to stdout stay incremental and say what they left alone.
- **One `state_key`.** The out-dir branch once shadowed it with the project key, so the watermark was read from
  `owner/project` and written to `AGILE`; incremental file export never advanced and only appeared to work because
  stdout runs happened to move the read key.

## Conventions

- **Every duration is an integer count of seconds, and no column name carries a unit suffix.** No `_days`, no
  `_hours`, no exceptions. In days, cycle times reported `0.0` and a median of `0.0` was published as a
  measurement; the same work reads 165, 181, 17, 76, 561 seconds. `cadence_days` is the profile's hand-authored
  spelling — a person writes 14 — and the suffix stops at the file's edge.
- **Dates are UTC.** `today_utc()`, never `date.today()`. Sprint windows are UTC dates and `@current` is decided
  in UTC; a local date puts the tool a day out of step around midnight.
- **A machine may not infer a type.** Nothing in an issue distinguishes an epic from a story from a bug, so
  `sync --adopt` sets `key:` and Status but never `type:`. `validate` reports the gap and a person decides.
- Non-obvious workarounds carry a comment saying *why*, with the measurement where there was one. Several look
  like removable dead code otherwise — they are not.
- Refuse rather than guess when the cost lands on someone else later: an illegal `issue_title_prefix` stops every
  command, an unchosen sprint cadence blocks `epic`/`story`/`ensure`, a key must match Jira's rules.

## Live state

| | |
|---|---|
| Project | `paulcaron16k/projects/4`, key `AGILE`, 25 issues, all carrying `key:AGILE` |
| Sprints | `AGILE Sprint 4` (2026-08-03..16), then `Sprint 1`, `Sprint 2`, `Sprint 3` — the naming seam is known and accepted; renaming clears assignments |
| Zamboni | `paulcaron16k/Zamboni`, **0 issues**; work is in `docs/tasks.md` (194 `ZMBNI-` ids) at `~/checkout/iceberg/Zamboni` |
| Export | `exports/AGILE/` (gitignored), watermark in `.gh_agile_export.json` |
