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
make merge-check   # the suite against HEAD + origin/main. Run it BEFORE merging
make ci-status     # whether main's last CI run passed
make hooks         # post-merge hook: a red main, and issues a merge left unfinished
make api-drift     # LIVE, read-only: GitHub's GraphQL schema against GitHub_API_spec.json
```

**Run `make api-drift` periodically, and before trusting a measured API fact.** GitHub changed the iteration
input underneath this tool (#290) and nothing noticed until it was found by chance. It exits 1 on drift, having
appended a timestamped summary to `GitHub_API_changelog.md` -- the changes to what the extension's GraphQL
selects or sends listed first (read from the queries in context, not from the words in comments, #299), beside GitHub's own dated changelog and the removals it has announced (#297) -- and rewritten the
snapshot; review both and commit them. With no drift it still prints any announced removal touching gh-agile
that is overdue or due within 90 days, because that warning is worth nothing once the removal lands. `make api-spec` rewrites the baseline from
scratch. Neither runs in CI, which has no token. `.github/workflows/api-drift.yml` runs the check monthly
with the workflow's own token -- introspection needs nothing more -- and on drift opens one pull request,
labelled `api-drift` and assigned to the owner, carrying both files (#298). That pull request is the
prompt: review it in a session and decide whether gh-agile must re-implement something or can add something.

**Green on a branch is not green on the merge.** Two pull requests cut from the same base, each passing
alone, left `main` red the moment both landed — and the `push: main` run that caught it told nobody, so
the next branch was cut from a broken `main`. Branch protection's *require branches to be up to date*
would prevent it, and is deliberately **not** used: this is one developer, and every such gate — required
checks, required reviews, admin enforcement — would only be admin-bypassed (#262). `main`'s protection is
deletion-only. So `merge-check` is the guard, by convention, and `hooks` is the backstop. See `docs/lessons.md`.

The three LIVE targets default to the sandbox and refuse anything else; see the testing policy below.

**Every Python target refuses to run outside `.venv`**, and `tests/conftest.py` refuses again from the inside for
anyone invoking pytest directly. Never fall back to the system interpreter: a suite that runs against whatever is
installed globally is testing a different environment on every machine.

**`make test` is offline by construction, not by convention.** `offline` in `tests/conftest.py` is autouse and
guards `subprocess.Popen`, the one place every route out passes — `gh()`, `graphql()`, any direct `["gh", ...]`
— and refuses internet sockets. No program runs unless the test names it: `@pytest.mark.runs("git")`, and
`git`'s network subcommands stay refused even then. Stub `gh`, `graphql` or `subprocess.run` instead. It exists
because an opt-in `no_network` fixture went unused and #231's tests quietly ran real `gh api graphql` (#242).

`ruff.toml` pins the rule set. Without it the rules are whatever the installed ruff defaults to, which changed
mid-project — the same code passed with one version and reported thirty findings with the next.

## Testing policy — read before touching a live repo

**Use the sandbox: `paulcaron16k/agile-test`, checked out at `../agile-test`.** See its `plan.txt`. Private,
issues enabled, its own board (project `#19`), its own profile with key `TEST` and `issue_title_prefix: key+type`.

This exists because live-repo testing did real damage: a `key:TEST` label applied to all 26 `gh-agile` issues, ~13
throwaway issues created and deleted leaving permanent holes in the issue-number sequence, 11 scratch projects, and
two export files deleted. `gh-agile` is in beta with issue tracking load-bearing, and other teams' boards
run on this tool too. Neither is a test fixture.

Order of escalation: **offline tests → agile-test → gh-agile.** Another team's repository is never an escalation
step: it is on a different board, not in this profile, and not ours to test against. Most work needs no live repo at all now.
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

## The defect the design is built around — and the fix, since #290

**A write to a project's iteration configuration that omits the iterations' ids re-mints every iteration id and
clears every item's `Sprint` value — retroactively, silently, board-wide, including closed issues in completed
sprints.**

Measured, not inferred, and still true. Renaming *one unused future sprint* unassigned four items staged across a
completed, a current and a future sprint. A pure **append** — every existing entry re-sent byte-identical plus one
new — does the same. Re-measured 2026-10-27 as a control: 10 iterations sent without ids, 0 ids kept, 13 of 13
assignments cleared.

**The input used to carry no id; it now does, and the tool sends it (#290).** `ProjectV2Iteration` was
`startDate`, `duration` and `title`, so there was no safe write. It gained `id` — "Include this to preserve the
iteration's identity during replacement updates" — found by chance in the schema, which is why #291 watches it.
With ids sent, measured on the sandbox 2026-10-27: an append, `sprint create`, `sprint ensure`, and a rename of
the current and a completed sprint each kept every id and every assignment, with no restore. The configuration is
still replaced wholesale, so anything omitted is deleted: every write re-sends every iteration.

`write_iterations` is the one writer, and the defences stay — as the fallback, and as disaster recovery:

1. **Save and restore**, now conditional. `write_iterations` reads the assignments first and checks the ids after;
   only if GitHub replaced one anyway does it restore them (`restore_assignments`) and heal, and say so.
2. **`require_graphql_budget`** still refuses the write when the budget could not cover a restore. It goes once the
   id path is proven in real use (#292).
3. **`sprint:YYYY-MM-DD` labels** on the issue are the real record, permanently. Dated, not named: a title is
   cosmetic and editable, a start date is identity, and dates sort. They are the backup for disaster recovery and
   for whatever GitHub Projects gets wrong next.
4. **`sprint backfill`** recovers history for issues predating the labels, from Status transitions.
5. **`sprint reconcile`** sets the field from the labels, board-wide; **`issue reconcile`** is the same repair aimed at
   one issue, at 3 GraphQL points against a whole-board read.
6. **`heal_sprint_fields`** runs that reconcile automatically after a restore.

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

**Labels carry what GitHub cannot.** `type:epic|story|bug`, `key:WIDG`, `sprint:YYYY-MM-DD`. Issue Types and
Issue Fields are organization-only (`createIssueField` resolves only an Organization node), so labels are the
carrier. Labels are also the only **additive** primitive in the API — `--add-label` appends without a
read-modify-write, unlike a title (whole-value replace) or an iteration configuration (replace-wholesale plus
collateral damage). That is why the sprint record lives on one.

**A board is reconstructed, never mirrored.** `ProjectV2View` has **no `items` field** — a view hands out its
`filter` as an opaque string, its `layout` and its grouping, and there is no API for "what does this view show".
So `board view` evaluates the filter locally against the same items `export` reads. Consequences that are not
optional: a filter term outside `FILTER_TERMS` is **refused, not ignored** (dropping `label:key:WIDG` renders one
team's board full of another team's work and looks correct); and **empty is not excluded** — a status the filter
allows but nothing occupies is reported on the `empty:` line, while one the filter removes is not mentioned, because
calling `Done` empty on a kanban board says nothing was finished.

**A board may span repositories, and `sync` is the one command that must not guess one.** `apply_defaults`
fills `--repo` from the working directory for every command that acts on a single issue. It did so for
`sync` too, which made its documented default -- every repository in the profile keys -- unreachable, so a
team responsible for several repositories could never get the rest of their issues onto the shared board.
`keys` is an ordered list for exactly this case, `issue_key` puts the key on the repository because a
project can span them, and a scrum board slices one team out with `label:key:...`. Watch the summary
count: `across 1 repo(s)` on a two-repo profile is the symptom.

**A project is a collection, not a filter.** An issue is not on a board until it is added, which is why `sync`
exists. A user-owned project gained *Auto-add to project* in 2026-10, but it covers one repository, acts only on
issues created or updated after it is on, and its filter cannot be read, so `sync` stays the backfill. Built-in
workflows cannot be enabled through the API at all — the schema has `deleteProjectV2Workflow` and nothing that
creates or updates one — and closing on merge is a *repository* setting the API cannot even read. Every one of
these is a manual web-UI step.

**Export stays CSV and standard library, and the load side is somebody else's.** The ceiling is mechanical:
`gh extension install` clones and installs nothing. A request needing an ELT framework, SQLAlchemy, Parquet or Iceberg is
**out of scope and closed as such** -- the day export must emit Parquet is the day it leaves the extension.
Loading GitHub data is a solved problem elsewhere; this repo produces silver files and says what is in them.
CSVs carry no schema, so that saying is `github_catalog.json` (`#92`) -- Singer shape, and named `github_` not
`agile_` because `agile_*` is the Gold model's namespace, which lives in `agile-reports`.

**`github_catalog.json` is the export contract**, in Singer shape: every stream, every column,
typed, nullable-or-not, keyed, with the replication method. A CSV carries no schema, so without it a
loader guesses -- and an empty `time_to_first_review` read as `0` rather than null is the same class of
error as a duration read in the wrong unit. Not `agile_*`: that is the **Gold** model's namespace, in
`agile-reports`. Two things it states that a type cannot: joined
lists stay **strings** with a `;` separator, because promising an array means owning the escaping; and
`github_events` declares **no replication key**, because the watermark filters the *issue* on
`updated_at` and an event's `occurred_at` is not the field the window was applied to.

**Adding a column to the export means adding it to `github_catalog.json`**, and `tests/test_export_catalog.py`
fails until you do — both directions, offline, by calling the row builders with fixtures. Written because
`#90` added five columns and the catalog was updated *by hand*: nothing would have caught the omission,
and the next person has no reason to know the file exists. A catalog that has drifted is worse than none,
because it is trusted.

**Export: silver tables.** `github_issues`, `github_events`, `github_prs`, `github_project`, `github_boards`, `github_sprints`.
Gold `agile_*` is a generic Agile metrics model, built from these files by a silver→gold transform, and both live
in `agile-reports` (`GOLD_MODEL.md` there); nothing here writes an `agile_*` file.

- **`event_hash` must be unique.** It covers `issue|kind|occurred|actor|previousStatus|status|detail`. Timestamps
  are per-second, and two status changes on one issue in the same second are ordinary — the earlier
  `issue|kind|occurred` produced 187 rows with 181 distinct hashes, and both the compactor and any keyed target
  drop the duplicates silently.
- **`github_prs` is the only grain with a server-side filter.** The projects API has no `updatedAt`
  filter, so the issue grains read the whole board and discard client-side; the pull-request grain asks
  search for `updated:>=<watermark>` and never transfers a pull request nobody touched. Its event hash
  includes the review's or comment's **node id**, not only the second: a batch review submits all its
  comments at once, so `pr|kind|occurred|actor` collides for exactly the rows one reviewer left in one
  pass. No `body`, no diff, no patch -- asserted against the query text itself, not just the row builder.
- **The watermark advances only on `--out-dir`.** It promises that everything up to it was delivered somewhere
  durable, and stdout is not. Reads to stdout stay incremental and say what they left alone.
- **One `state_key`.** The out-dir branch once shadowed it with the project key, so the watermark was read from
  `owner/project` and written to `AGILE`; incremental file export never advanced and only appeared to work because
  stdout runs happened to move the read key.

## Sprint naming, and renaming

**`{n:04d} W{iso_week}-{year}` — `0004 W38-2026`.** The default for a new project, and what this
project's profile now sets.

The number leads because it is the only part anyone says out loud. The ISO week is how a person places
a sprint in the year. The year is there to sort by rather than to read. Four digits is ten thousand
sprints, which at a fortnight each outlasts any board — and the leading zeros are the price of a column
that lines up, which `board view` spends eight characters on. Measured before the cap was chosen:
`0004 W38-2026` cuts to `0004 W38` and keeps the number and the week; Jira's `<Board> Sprint <n>` cuts
to `AGILE S…` and keeps neither.

**A sprint may be renamed.** Until #290 it could not be: any write to the iteration configuration re-minted
every id and cleared every assignment, so a rename bought a cosmetic change with a board-wide repair. With the
ids sent, a rename is an ordinary write and costs what adding a sprint costs. The start date, not the title, is
still a sprint's identity — the `sprint:` labels carry the date, so a rename leaves history untouched.

**The board this project runs on has a naming seam**: `AGILE Sprint 4`, `Sprint 1`, `Sprint 2`, `Sprint 3`, then
`0005 W40-2026` onward. It was left because tidying it would have cleared every assignment; it can now be tidied
or kept, as a choice rather than a constraint.

## Conventions

- **The CLI is shaped like `gh`, and a new command follows it (AGILE-200).** A noun group with verbs; an issue
  is `-t` to create and a positional to target; a named thing (board, key) takes its name positionally. Declare
  every subcommand `kind=GENERAL` or `kind=TARGETED, identifier=...` — the one declaration files it in `--help`
  *and* gives it the identifier as its first positional, and `tests/test_help_sections.py` walks the parser and
  fails on anything undeclared. Descriptions are capitalised with no full stop. No flag means two things, none is
  accepted abbreviated, and a `list` into a pipe prints tab-separated rows with no header. A rename follows
  README's *Deprecation policy*, stated there and not here; a deprecated spelling runs exactly what it ran,
  and a retired one goes in `RETIRED_TABLE` with a runnable example and fails at parsing — never
  reinterpreted as something else.
- **Every duration is an integer count of seconds, and no column name carries a unit suffix.** No `_days`, no
  `_hours`, no exceptions. In days, cycle times reported `0.0` and a median of `0.0` was published as a
  measurement; the same work reads 165, 181, 17, 76, 561 seconds. `cadence_days` is the profile's hand-authored
  spelling — a person writes 14 — and the suffix stops at the file's edge.
- **Dates are UTC.** `today_utc()`, never `date.today()`. Sprint windows are UTC dates and `@current` is decided
  in UTC; a local date puts the tool a day out of step around midnight.
- **The extension runs under the user's `python3`, not the venv's.** `gh extension install` clones a file; it
  provisions no interpreter, and the shebang is `#!/usr/bin/env python3`. So the floor is **3.10** and is not
  ours to choose. Three settings must agree — and `tests/test_version_floor.py` now checks that they do — `RUNTIME_FLOOR`, `ruff.toml`'s `target-version`, and the CI matrix,
  which has to *run* the floor: with `target-version = py312`, UP017 rewrote `dt.timezone.utc` to `dt.UTC`
  (3.11+), lint and every test stayed green because both ran in the 3.12 venv, and the tool crashed on first use
  under the system 3.10. **A floor no job tests is a promise nothing keeps.** `make venv PYTHON=python3.10`
  reproduces CI's floor job locally, and it is how the same autofix was then found lurking in `tests/test_time.py`.
  `scripts/` is exempt: it runs under `$(PY)` or `uv`, and `agile_analytics.py` declares `requires-python >=3.11`.
- **Read the board with hand-written GraphQL, never `gh project item-list` or `field-list`.** Measured: those
  two cost ~102–106 GraphQL points against 1 for the same request written out, and `field-list`'s cost does not
  even move with `-L`. `paged_project_items` takes a selection so there is one pager and two selections rather
  than two mechanisms. `fetch_items` **must stay uncached** — the iteration repairs save every
  assignment, write, restore, and then heal through `reconcile_sprints`, which reads the board again; a cache
  would hand the heal the board from before the write. One issue's item and Sprint are asked of the issue and
  the item node instead (`board_item_for`, `item_sprint`, #231), because `projectV2.items` can leave a new
  item out for an hour or more. See `docs/lessons.md`.
- **Statuses accept a hyphen.** `In-Review` and `In Progress` are the same transition, so nobody has to quote
  a status in a shell. `status_key` normalises for comparison; `canonical_status` returns the `STATUSES`
  spelling, and that is the only thing ever written to the field, because GitHub holds the option name.
- **A machine may not infer a type.** Nothing in an issue distinguishes an epic from a story from a bug, so
  `sync --adopt` sets `key:` and Status but never `type:`. `validate` reports the gap and a person decides.
- **Starting work is one call.** `issue move ISSUE "In Progress"` sets Status, assigns the current sprint when the
  field is empty, stamps the `sprint:` label, and claims the issue for the caller when nobody holds it. Each of
  those fills a gap and none overrules a decision — *an unassigned issue is a gap, an assigned one is a
  decision*, the same rule the sprint heal follows, so an issue somebody already holds is reported and left
  alone. `--add-assignee` says otherwise: given at all, it assigns whatever the status. The caller is `@me`,
  resolved by `gh`, because this tool never sees a token and must not guess a username from a git config.
- **Evidence is written on any status, and required on one.** `--evidence` was read only when the target status
  demanded a section, so on every other status it was parsed, accepted and discarded — exit 0, status changed,
  four issues on another team's board left with empty `## Evidence` and the text nowhere else. `read_template` also maps an
  unheaded blob onto the *single required* section, which is nothing when nothing is required, so
  `OPTIONAL_SECTIONS` names Evidence for that case. `Done` still refuses an empty section or a `_TBD_`; nothing
  else validates what it is given, and offering nothing still writes nothing.
- Non-obvious workarounds carry a comment saying *why*, with the measurement where there was one. Several look
  like removable dead code otherwise — they are not.
- Refuse rather than guess when the cost lands on someone else later: an illegal `issue_title_prefix` stops every
  command, an unchosen sprint cadence blocks `epic create`/`story create`/`sprint ensure`, a key must match Jira's rules.

## Where the rest of it is written down

| File | What |
|---|---|
| `docs/tasks.md` | The work breakdown for what is left, cross-referenced to board ids, **and the live state** — repositories, projects, keys, checkouts. **The board is the source of truth for status; that file carries method** — the order, and the gotcha that costs an afternoon |
| `docs/lessons.md` | Findings that cost something to learn, with the measurement. Read before repeating an experiment |
| `POLICY.md` | The conventions `validate` enforces |
| `agile-reports`' `GOLD_MODEL.md` | The Gold model the export feeds, in the sibling repository — not here, and nothing here writes it |
| `USER_GUIDE.md` | The published guide; `make check-guide` keeps it honest |
| `README.md` | **The release policy lives there**, under *Versions, and what installing gets you*: `main` is the release, tags name builds and nothing installs from one, and consumers are told not to pin. Stated where a consumer reads rather than here (#197) |

Some of it is code rather than prose, and none of it is guessable from a file name:

| File | The practice, and what enforces it |
|---|---|
| `ruff.toml` | The rule set is **pinned**, because the same code passed one ruff version and reported thirty findings with the next. `target-version` is the floor, and `tests/test_version_floor.py` fails if it drifts from `RUNTIME_FLOOR` or the CI matrix |
| `.github/workflows/ci.yml` | Every supported interpreter, **including the floor and with no gaps** — a floor no job tests is a promise nothing keeps. Same test holds the matrix to it |
| `Makefile` | The live targets default to the sandbox and refuse any other repository without `ALLOW_LIVE=1`; every Python target refuses to run outside `.venv`, and `tests/conftest.py` refuses again from the inside. `merge-check` before merging, `hooks` so a red `main` reaches you |
| `scripts/check_guide.py` | Every command in the guide exists, and the read-only ones run. It strips a trailing comment before appending `--dry-run`, because the shell ate the flag once and a real `sync` wrote 35 issues to a live board |
| `templates/` | The `post-merge` hook, and the GitHub workflows that need no stored credential |
| `GitHub_API_spec.json`, `GitHub_API_changelog.md` | The GraphQL schema as last seen, ordered so a diff is only real change, and what changed since, by date. `scripts/api_drift.py` writes both (#291) |

## Live state

**It is not here. It is in `docs/tasks.md`, and that is the only copy.**

Which repositories, which projects and project numbers, which keys, which checkouts, which profile sits
where — all of it lives in that file's *Live state* section. **Read it before touching anything live**,
because none of it is loaded automatically and this file will not tell you.

The reason it is not written here twice: a fact kept in two files eventually disagrees with itself, and
the copy that loses is the one loaded automatically — nobody thinks to correct a file they never opened.
This one said another team's repository had no issues and its work was 194 ids in a markdown file, months after that
backlog was retired and the issues were real. So: **do not restate live state in this file, and do not
"helpfully" copy it back.** Add it to `docs/tasks.md` or leave it out.

That section records *identities and locations* only, and deliberately no counts, statuses or "what is
in the current sprint". Those change on their own and are answered live — `board view`, `board list`,
`sprint list`, `validate`, `gh issue list` — and the section names which command answers what.
