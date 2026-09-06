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
make test          # offline unit tests, no network, no GitHub account, under a second
make lint          # ast parse + ruff over gh-agile, tests/, scripts/
make check-guide   # every command in USER_GUIDE.md exists; read-only ones run in a cron-like env
make coverage      # unit tests with a coverage report
make self-test     # LIVE: stands up a scratch project, exercises it, tears it down
make scratch       # LIVE: leaves a scratch project standing;  make teardown NUM=<n>
make metrics DIR=exports/AGILE
```

The three LIVE targets default to the sandbox and refuse anything else; see the testing policy below.

**Every Python target refuses to run outside `.venv`**, and `tests/conftest.py` refuses again from the inside for
anyone invoking pytest directly. Never fall back to the system interpreter: a suite that runs against whatever is
installed globally is testing a different environment on every machine.

`ruff.toml` pins the rule set. Without it the rules are whatever the installed ruff defaults to, which changed
mid-project — the same code passed with one version and reported thirty findings with the next.

## Testing policy — read before touching a live repo

**Use the sandbox: `paulcaron16k/agile-test`, checked out at `../agile-test`.** See its `plan.txt`. Private,
issues enabled, its own board (project `#19`), its own profile with key `TEST` and `issue_title_prefix: key+type`.

This exists because live-repo testing did real damage: a `key:TEST` label applied to all 26 `gh-agile` issues, ~13
throwaway issues created and deleted leaving permanent holes in the issue-number sequence, 11 scratch projects, and
two export files deleted. `gh-agile` is near alpha with issue tracking now load-bearing, and `Zamboni` is heading
for production. Neither is a test fixture.

Order of escalation: **offline tests → agile-test → gh-agile → Zamboni.** Most work needs no live repo at all now.
Only `self-test`, sprint destruction/repair and `sync --adopt` must hit real GitHub.

**The Makefile enforces this rather than asking.** `OWNER` and `REPO` default to the sandbox, and `self-test` and
`scratch` refuse any other repository unless `ALLOW_LIVE=1` names it on the same command line — two explicit acts,
because the old default was the real repository and that default is how the damage above happened. `teardown` reads
the project's title first and deletes only what the live targets create (`gh-agile scratch <time>`, `gh-agile
self-test`); `make teardown NUM=4` refuses, and so does the sandbox's own `#19`. A title it cannot read also
refuses — during a GitHub outage `gh project view` reported "unknown owner type" for a request that was fine, and
a guard that looks broken is a guard someone overrides.

`agile-test` cannot reproduce bugs that need a board with history — 25 items, four sprints, months of timeline.
Seed it from an export rather than testing on the real board.

**CI runs `lint` and `test` only** (`.github/workflows/ci.yml`), on the floor interpreter and the current one. It
gets no token and calls no `gh`. `check-guide` is read-only but *not* offline — it executes the guide's read
commands against whichever board the profile in the checkout names — so it stays a local target, and a green CI
run says the pure logic is sound and nothing about the write side.

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
5. **`sprint reconcile`** sets the field from the labels, board-wide; **`fix --id`** is the same repair aimed at
   one issue, at 3 GraphQL points against a whole-board read.
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
repos and cannot rot into a dead link. `apply_defaults` fills `--project`, `--repo`, `--key` and `--owner`, and
**refuses** when `--project` or `--owner` disagrees with the profile — that mismatch is almost always the right
flag in the wrong clone.

**`project.owner` is part of the project's identity, not a convenience.** A number alone means "project N
belonging to whoever ran this", which is invisibly correct for the owner and wrong for everyone else: the
read-only commands fail for a teammate who has project read, or resolve to an unrelated project of theirs.
`resolve_owner` takes the flag, then `project.owner`, then the caller; `--owner @me` always forces the caller,
which is why the flag has no argparse default — `default="@me"` could not distinguish "not given" from "me".

**Labels carry what GitHub cannot.** `type:epic|story|bug`, `key:ZMBNI`, `sprint:YYYY-MM-DD`. Issue Types and
Issue Fields are organization-only (`createIssueField` resolves only an Organization node), so labels are the
carrier. Labels are also the only **additive** primitive in the API — `--add-label` appends without a
read-modify-write, unlike a title (whole-value replace) or an iteration configuration (replace-wholesale plus
collateral damage). That is why the sprint record lives on one.

**A board is reconstructed, never mirrored.** `ProjectV2View` has **no `items` field** — a view hands out its
`filter` as an opaque string, its `layout` and its grouping, and there is no API for "what does this view show".
So `board show` evaluates the filter locally against the same items `export` reads. Consequences that are not
optional: a filter term outside `FILTER_TERMS` is **refused, not ignored** (dropping `label:key:ZMBNI` renders one
team's board full of another team's work and looks correct); and **empty is not excluded** — a status the filter
allows but nothing occupies is reported on the `empty:` line, while one the filter removes is not mentioned, because
calling `Done` empty on a kanban board says nothing was finished.

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
- **The extension runs under the user's `python3`, not the venv's.** `gh extension install` clones a file; it
  provisions no interpreter, and the shebang is `#!/usr/bin/env python3`. So the floor is **3.10** and is not
  ours to choose. Three settings must agree — `RUNTIME_FLOOR`, `ruff.toml`'s `target-version`, and the CI matrix,
  which has to *run* the floor: with `target-version = py312`, UP017 rewrote `dt.timezone.utc` to `dt.UTC`
  (3.11+), lint and every test stayed green because both ran in the 3.12 venv, and the tool crashed on first use
  under the system 3.10. **A floor no job tests is a promise nothing keeps.** `make venv PYTHON=python3.10`
  reproduces CI's floor job locally, and it is how the same autofix was then found lurking in `tests/test_time.py`.
  `scripts/` is exempt: it runs under `$(PY)` or `uv`, and `agile_analytics.py` declares `requires-python >=3.11`.
- **Read the board with hand-written GraphQL, never `gh project item-list` or `field-list`.** Measured: those
  two cost ~102–106 GraphQL points against 1 for the same request written out, and `field-list`'s cost does not
  even move with `-L`. `paged_project_items` takes a selection so there is one pager and two selections rather
  than two mechanisms. `fetch_items` **must stay uncached** — `move` writes a Sprint value and
  `record_sprint_label` reads it back, so a cache there silently stops the `sprint:` label being written.
  See `docs/lessons.md`.
- **Statuses accept a hyphen.** `In-Review` and `In Progress` are the same transition, so nobody has to quote
  a status in a shell. `status_key` normalises for comparison; `canonical_status` returns the `STATUSES`
  spelling, and that is the only thing ever written to the field, because GitHub holds the option name.
- **A machine may not infer a type.** Nothing in an issue distinguishes an epic from a story from a bug, so
  `sync --adopt` sets `key:` and Status but never `type:`. `validate` reports the gap and a person decides.
- Non-obvious workarounds carry a comment saying *why*, with the measurement where there was one. Several look
  like removable dead code otherwise — they are not.
- Refuse rather than guess when the cost lands on someone else later: an illegal `issue_title_prefix` stops every
  command, an unchosen sprint cadence blocks `epic`/`story`/`ensure`, a key must match Jira's rules.

## Where the rest of it is written down

| File | What |
|---|---|
| `docs/tasks.md` | The work breakdown for what is left, cross-referenced to board ids. **The board is the source of truth for status; that file carries method** — the order, and the gotcha that costs an afternoon |
| `docs/lessons.md` | Findings that cost something to learn, with the measurement. Read before repeating an experiment |
| `POLICY.md` | The conventions `validate` enforces |
| `GOLD_MODEL.md` | The silver→gold boundary, and what this repo does not write |
| `USER_GUIDE.md` | The published guide; `make check-guide` keeps it honest |

## Live state

Paths, because this work spans four checkouts:

| Path | What |
|---|---|
| `~/checkout/prj_mgmt/gh-agile` | this repo (`paulcaron16k/gh-agile`), branch `main` |
| `~/checkout/prj_mgmt/agile-test` | **the sandbox** (`paulcaron16k/agile-test`) |
| `~/checkout/prj_mgmt/my-gh-agile` | a duplicate clone, no local changes. Probably a staging step; **ask before deleting** |
| `~/checkout/iceberg/Zamboni` | Zamboni, whose `docs/tasks.md` still holds 194 `ZMBNI-` ids |
| `~/checkout/db/` | the dbt-duckdb work, unrelated |

| | |
|---|---|
| Project | `paulcaron16k/projects/4`, key `AGILE`, 25 issues, all carrying `key:AGILE` |
| Sandbox | `paulcaron16k/agile-test` at `../agile-test`, project `#19`, key `TEST`, no issues. `TEST Sprint 1..3` from 2026-08-17, 2-week cadence. Boards: kanban, backlog, scrum `label:key:TEST`, roadmap. Issue numbers `#1`/`#2` are already spent by a `self-test` run |
| Sprints | `AGILE Sprint 4` (2026-08-03..16), then `Sprint 1`, `Sprint 2`, `Sprint 3` — the naming seam is known and accepted; renaming clears assignments |
| Zamboni | `paulcaron16k/Zamboni`, **0 issues**; work is in `docs/tasks.md` (194 `ZMBNI-` ids) at `~/checkout/iceberg/Zamboni` |
| Export | `exports/AGILE/` (gitignored), watermark in `.gh_agile_export.json` |
