# gh-agile — work breakdown

Project key **AGILE**, board [`paulcaron16k/projects/4`](https://github.com/users/paulcaron16k/projects/4).

## What this file is, and what it is not

**The board is the source of truth for identity and status.** `AGILE-24` *is* issue `#24` — the tool
parses a reference by splitting on the last hyphen — so nothing here mints an `AGILE-n` id, and nothing
here records status for work that has an issue. Look at the board for that.

**This file carries method.** The decomposition, the order, the gotcha that will cost an afternoon if it
is not known in advance. An issue title cannot hold "labels survive a transfer only if they already exist
in the destination", and that sentence is the difference between a migration that works and one that
silently strips every label. So: `WBS-n` ids for the breakdown, cross-referenced to board ids where the
work is filed.

The distinction matters here more than in most repositories, because `#11` is *"Migrate ZMBNI off
tasks.md"* — this project's stated direction is away from markdown backlogs. A second backlog in `docs/`
would be the thing the tool exists to replace. A plan is not a backlog.

The `status` column below reads:

| Status | Meaning |
|---|---|
| `done` | Delivered and verified, with the verification named |
| `inproject` | Started, not finished |
| `todo` | Not started |
| `blocked` | Cannot start; the entry says what on |
| `decided` | Deliberately not doing, or accepted as-is. The entry says why |

**This file also carries the live state** — which repositories, which projects, which keys, which
checkouts. It is the one place those are written down, so CLAUDE.md points here rather than repeating
them: a fact kept in two files is a fact that will eventually disagree with itself, and the one that is
loaded automatically is the one nobody thinks to correct.

---

## Live state

Verified 2026-09-07. **What goes here: identities and locations — things that change when somebody
decides they should.** What does not go here: counts, statuses, which sprint is current, what is on a
board. Those change by themselves, a written-down copy is stale within the day, and every one of them
has a command that answers it live:

| Question | Ask |
|---|---|
| What is on a board, and in which column | `gh agile board show <number\|name>` |
| Which boards exist on a project | `gh agile board list` |
| Which sprint is current, and what has run | `gh agile sprint list` |
| Do the conventions hold | `gh agile validate` |
| What is open, and what is it labelled | `gh issue list --repo <owner/name>` |

### Checkouts

| Path | What |
|---|---|
| `~/checkout/prj_mgmt/gh-agile` | **this repo** (`paulcaron16k/gh-agile`), branch `main` |
| `~/checkout/prj_mgmt/agile-test` | **the sandbox** (`paulcaron16k/agile-test`). See its `plan.txt` |
| `~/checkout/iceberg/Zamboni` | Zamboni (`paulcaron16k/Zamboni`) |
| `~/checkout/db/` | the dbt-duckdb work, unrelated |
| `~/checkout/prj_mgmt/gitstats`, `~/checkout/prj_mgmt/mergestat` | third-party tools, unrelated to this repo |

`~/checkout/prj_mgmt/my-gh-agile` was a duplicate clone and is **gone**. Recorded so nobody goes looking
for it on the strength of an older note.

### Projects

| Key | Where | Profile |
|---|---|---|
| `AGILE` | `paulcaron16k/projects/4` | `.github/agile.json` in this repo. Boards: `Engineering: all work` (kanban), `Backlog`, `Team: AGILE` (scrum), `Team: ZMBNI` (scrum), plus GitHub's default `View 1`. No `issue_title_prefix`, so titles are unprefixed |
| `ZMBNI` | `paulcaron16k/projects/23` | `~/checkout/iceberg/Zamboni/.github/agile.json`. Boards: `Sprint board` (scrum), `Kanban`. `issue_title_prefix: key`, so titles read `ZMBNI-34 ...`. **The profile records no `project.owner`** — a number without an account is not an identity, and `gh agile project owner` is the fix |
| `TEST` | `paulcaron16k/projects/19` | `~/checkout/prj_mgmt/agile-test/.github/agile.json`. Boards: `Engineering: all work`, `Backlog`, `Team: TEST` (scrum), `Roadmap`. `issue_title_prefix: key+type`. Issue numbers `#1` and `#2` are already spent by a `self-test` run |

**Zamboni's markdown backlog is retired.** `~/checkout/iceberg/Zamboni/docs/tasks.md` no longer exists;
that work is GitHub issues on project `23` now, which is what `#11`, `#20`, `#21` and `#22` were for.

**The AGILE sprint series has a naming seam**: `AGILE Sprint 4` came before `Sprint 1`, `Sprint 2`,
`Sprint 3`. Known and accepted, and left alone deliberately — renaming an iteration clears every
assignment on the board, which is the defect this whole tool is built around.

**Export** for AGILE goes to `exports/AGILE/` (gitignored), watermark in `.gh_agile_export.json`.

---

## Filed on the board

Everything below is an open issue. The WBS section named beside it holds the method; the issue holds the
status.

| id | title | WBS |
|---|---|---|
| `#12` | Analysis pipeline to the Gold model | [WBS-5.2](#wbs-5--filed-but-unbroken-down) |
| `#37` | Export pull requests, reviews and comments as events | [WBS-5.2](#wbs-5--filed-but-unbroken-down) |

Everything else that was listed here is closed. `#9` read side, `#10` write side, `#26` the guided
workflow and `#70` repository engineering all closed on the roll-up as their last story landed, which is
the check `#60` added doing its job. `#24` is closed as **not planned for this repository** — see WBS-5.1.

**Not filed:** WBS-1, WBS-3, and the WBS-4 / WBS-6 entries. Filing them is a live write to board `#4` and
is the owner's call; the breakdown below is written so that each leaf is one issue if they want it to be.

Everything below is an issue the Zamboni team will transition from gh-agile to their own issues list. 
Leave these issues alone for now, until the Zamboni team issue transition is complete.

| id | title | WBS |
|---|---|---|
| `#11` | Migrate ZMBNI off tasks.md | [WBS-2](#wbs-2--migrate-the-zamboni-work-off-tasksmd) |
| `#20` | Migrate the 11 open ZMBNI stories | [WBS-2](#wbs-2--migrate-the-zamboni-work-off-tasksmd) |
| `#21` | Freeze tasks.md as the archive | [WBS-2](#wbs-2--migrate-the-zamboni-work-off-tasksmd) |
| `#22` | Port the tasks.md tests to `gh agile validate` | [WBS-2](#wbs-2--migrate-the-zamboni-work-off-tasksmd) |

---

## WBS-1 — Sandbox fidelity

The sandbox exists (2026-08-17: `paulcaron16k/agile-test`, project `#19`, key `TEST`; `make self-test`
green; the Makefile refuses non-sandbox live targets). What it cannot yet do is reproduce the bugs worth
reproducing.

| id | title | description | status |
|---|---|---|---|
| WBS-1 | Sandbox fidelity | A sandbox that can host the sprint experiments | `inproject` |
| WBS-1.1 | Stand up the repo, board and guard | Private repo, project `#19`, key `TEST`, four boards, `TEST Sprint 1..3`, Makefile guard on all three live targets, offline CI | `done` 2026-08-17 |
| WBS-1.2 | Seed the sandbox from an export | Load `exports/AGILE/` into `#19` so it has items, closed sprints and a timeline | `todo` |
| WBS-1.3 | Decide what "seeded" has to mean | See below — this is the design question, and 1.2 cannot start without it | `todo` |

**WBS-1.3 is the real work.** A clean board cannot reproduce anything that needs items staged across a
completed, a current and a future sprint — which is precisely the shape that proved the iteration defect.
But an export cannot be replayed faithfully either:

- **Timeline events cannot be forged.** `github_events` rows come from GitHub's own timeline; creating an
  issue today and setting Status four times gives four events dated today. Cycle times computed from a
  seeded board are not the original cycle times. Decide whether the experiments care.
- **Closed sprints cannot be created.** An iteration's `startDate` is what decides whether it is
  completed, so a past sprint has to be created with a past start date and left to be historical.
- **Issue numbers will not match.** `#1` and `#2` in `agile-test` are already spent by a `self-test` run,
  so a seeded `AGILE-24` lands on a different number. Anything asserting on a number needs a mapping.

Minimum viable seed, if the answer is "the experiments only need shape": *n* items spread over three
iterations, one of them completed, with `sprint:` labels consistent with the field. That is enough to
prove or disprove WBS-3, which is the reason to build it.

---

## WBS-3 — Does the web UI destroy sprint assignments too?

**Not filed, and the highest-value unfiled item.** Every measurement of the iteration defect so far went
through the public GraphQL mutation. The web UI may use an internal endpoint that behaves better.

If it is non-destructive, the damage is a public-API defect rather than a data-model one, and the six
workarounds in `CLAUDE.md` could shrink. If it is destructive, that is worth knowing too: it closes off
"just use the web page" as advice, permanently.

| id | title | description | status |
|---|---|---|---|
| WBS-3.1 | Capture pre-state | Iteration ids, every item's `Sprint` value, every `sprint:` label, into `tmp/pre-web-add-sprint.json` | `todo` |
| WBS-3.2 | Hand over, and stop | The owner adds one sprint through the web page by hand. Nothing automated touches the project in between | `todo` |
| WBS-3.3 | Diff and record | Re-read the same three things. Iteration ids re-minted? Assignments cleared? Labels intact (they must be — they are on the issue) | `todo` |
| WBS-3.4 | Act on the answer | Non-destructive → re-scope the workarounds and say so in `CLAUDE.md`. Destructive → record the measurement beside the API one | `blocked` on 3.3 |

**Run this on the sandbox, not on board `#4`.** It is a destructive-write experiment by construction.
It also needs WBS-1.2 first: a board with nothing on it cannot show assignments being cleared.

---

## WBS-4 — Finish the unit-suffix convention

The rule is *every duration is an integer count of seconds, and no column name carries a unit suffix*.
Two loose ends remain, one inside this repo and one outside it.

| id | title | description | status |
|---|---|---|---|
| WBS-4.1 | Decide `cadence_days` | The last `_days` name in the repo. Deliberate — it is hand-authored config, a person writes `14`, and the suffix stops at the file's edge — but the rule was stated as "no exceptions", so whether it stays is the owner's call | `blocked` on owner |
| WBS-4.2 | Rename the Gold catalog's `*_hours` | `GOLD_MODEL.md` is already fixed. The authoritative `agile_data_model.md` and `agile_catalog.json` live **outside this repo** and must change too, or the silver→gold transform reintroduces the unit. Related: `#12` | `todo` |

WBS-4.2 is the one that actually breaks something. A convention enforced on one side of a transform and
not the other is not a convention.

---

## WBS-5 — Filed, but unbroken-down

Listed so that "not in the WBS" does not read as "not needed".

| id | title | description | status |
|---|---|---|---|
| WBS-5.1 | Synthesise custom-field history | **Moved out of this repository, 2026-09-08.** GitHub emits a timeline event for `Status` and for nothing else, so points / sprint / priority history has to come from **diffing scheduled exports** — a transform over silver, not an extraction from GitHub, and `GOLD_MODEL.md` puts `agile_*` outside this repo. It also wants a query engine, and the extension is standard-library-only permanently. `scripts/agile_analytics.py` is the home. `#24` closed as not planned. **The requirement survives the move and is time-sensitive: the export cadence is a data-model decision, not an ops one, and it cannot be retrofitted — the snapshots nobody took do not exist** | `decided` |
| WBS-5.2 | Export PRs, reviews and comments as events | `#37`. No diff hunks, no patches — events only. **Stays here**: it extends `github_events`, which is silver and this tool's own table, and it needs `gh`, the pager, the `event_hash` rule and the watermark. A separate tool would re-implement all of that to append rows to a table this repository already writes | `todo` |

---

## WBS-6 — Known and accepted

Not work. Recorded so nobody spends a morning rediscovering them, and so nobody "fixes" the third one.

| id | title | description | status |
|---|---|---|---|
| WBS-6.1 | `sprint:` labels are per repository, not per project | An issue on two boards carries one set of dates, matching only one series; `reconcile` reports the other as unresolvable. One board per repository avoids it entirely | `decided` |
| WBS-6.2 | No locking on profile writes | Every profile write is a read-modify-write, and two concurrent runs lose one of them. **The owner reviewed this and accepted the risk — do not "fix" it without asking.** A single-user tool with a checked-in profile does not need a lock file | `decided` |
| WBS-6.3 | The tool is one file | And it will stay one file: `gh extension install` clones and installs nothing, so a package layout buys nothing and a second module is a second thing to keep on `sys.path`. The offline suite is what keeps it tractable | `decided` |

---

## Ideas not yet triaged

Captured verbatim from the untracked `todo.txt` at the repository root. They are unshaped, and shaping
them is itself work — none has an owner, a size or an acceptance test yet. **`todo.txt` can be deleted
once these are confirmed captured**; it is left in place because it is not this file's to remove.

- Investigate workflows and PR-comment triggers in
  [CynicDog/agile-github-starter](https://github.com/CynicDog/agile-github-starter/tree/main).
- A knowledge base under `wiki/` or `.claude/knowledge_base/`.
- Adversarial code review, including token usage.
- Token usage in normal use and in testing. Development ran out of budget several times, and
  `require_graphql_budget` exists because of it — but nothing measures the *ordinary* cost of a command.
