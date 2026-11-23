# gh-agile

[![CI](https://github.com/paulcaron16k/gh-agile/actions/workflows/ci.yml/badge.svg)](https://github.com/paulcaron16k/gh-agile/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://github.com/paulcaron16k/gh-agile/blob/main/.github/workflows/ci.yml)
[![Dependencies](https://img.shields.io/badge/dependencies-none%20%28stdlib%29-brightgreen.svg)](https://github.com/paulcaron16k/gh-agile/blob/main/REFERENCE.md#requirements)
[![Status](https://img.shields.io/badge/status-beta-yellow.svg)](https://github.com/paulcaron16k/gh-agile/blob/main/REFERENCE.md#deprecation-policy)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/paulcaron16k/gh-agile/blob/main/LICENSE)

Jira-style Agile on GitHub — **initiatives, epics, stories, bugs, sprints and
boards** — run from the terminal, on GitHub Issues and Projects. Every command is
non-interactive, so a person and an AI agent type the same thing, and the work
comes back out as CSV to analyse the way you would a Jira export.

---

## Contents

- [What it does](#what-it-does)
- [Install](#install)
- [Set up a project: `gh agile init`](#set-up-a-project-gh-agile-init)
- [A worked example: Widgets](#a-worked-example-widgets)
- [A story's life cycle](#a-storys-life-cycle)
- [See the work](#see-the-work)
- [Get the data out](#get-the-data-out)
- [Commands](#commands)
- [Learn more](#learn-more)
- [License](#license)

---

## What it does

| | |
|---|---|
| **A real hierarchy** | Initiative → epic → story, plus bugs, as GitHub sub-issues — so an epic's `2/6` rolls up without anyone keeping count |
| **Jira-style keys** | `WIDG-42`, per repository, on every issue, board and export row |
| **Sprints that keep their history** | Created on demand, never on a clock. The sprint an issue was worked in is stamped on the issue as `sprint:YYYY-MM-DD`, so history survives whatever happens to the board |
| **Boards in the terminal** | Scrum, kanban, backlog and roadmap, rendered from the same filters the web UI uses |
| **One call to start work** | `issue move` sets Status, the current sprint and the assignee together |
| **Evidence to finish** | Done means a written `## Evidence` section — what was done, and how you know |
| **A checker** | `validate` reports what breaks the conventions: an orphan story, a closed issue not at Done, a missing type |
| **Data out** | Issues, status history, pull requests and sprints as CSV or JSON, with a typed catalog |
| **Nothing to install** | Python standard library only. Authentication is `gh`'s: the tool never sees a token |

---

## Install

As a `gh` extension, tracking `main`:

```bash
gh extension install paulcaron16k/gh-agile
gh auth refresh -s project        # the project scope, once
```

Or from PyPI, as a tagged release that also runs standalone as `gh-agile`:

```bash
pipx install gh-agile
gh-agile install                  # link it into gh, so `gh agile` runs it too
gh auth refresh -s project
```

Python 3.10 or later, standard library only: installing installs nothing else.
The two routes run the same file and differ only in when a fix reaches you —
[Versions, and what installing gets you](https://github.com/paulcaron16k/gh-agile/blob/main/REFERENCE.md#versions-and-what-installing-gets-you).

**What you need on GitHub:** push on the repository, because `init` writes
labels, and a place to create the project: your own account, or an organization
where you can create projects. Day-to-day work needs project *write* and repo
*push*; who needs what is in
[Team Usage](https://github.com/paulcaron16k/gh-agile/blob/main/REFERENCE.md#team-usage).

---

## Set up a project: `gh agile init`

From your repository's clone:

```bash
gh agile init --key WIDG -t "Widgets" --sprint-template 2-week
```

That one command creates:

- **`.github/agile.json`**, the profile — project number and owner, the key,
  the sprint cadence and the boards. Check it in; every teammate's clone uses it.
- **a GitHub Project** with seven fields — `Status`, `Sprint`, `Story Points`,
  `Priority`, `FR`, `Start date` and `Target date` — and the `type:` and `key:`
  labels in the repository
- **starter boards**: *Sprint board*, *Backlog* and *Roadmap*
- **a post-merge hook** in this clone, which names any issue a merge closed and
  nobody finished
- **a list of the web-UI steps** the API cannot take, with their current state

<details>
<summary><strong>Every <code>init</code> option</strong></summary>

| Option | What it sets | |
|---|---|---|
| `--key WIDG` | The key every issue carries: `WIDG-12`. Jira's rules apply | first run |
| `-t "Widgets"` | The project's title | first run |
| `--sprint-template 2-week` | The cadence: `1-week`, `2-week`, `3-week`, `4-week` or `none` | first run |
| `--project 7` | Adopt an existing project instead of creating one | optional |
| `--title-prefix key` | Titles read `WIDG-12 …`; `key+type` reads `WIDG-12 Story: …`. Off by default | optional |
| `--no-hooks` | Leave this clone's hooks alone | optional |

</details>

Run it again whenever you like: it converges rather than duplicating. A
teammate's fresh clone needs only `gh agile init`.

---

## A worked example: Widgets

*Widgets* is a fictional product with one feature plan: **offline sync**. The
plan becomes an **initiative**, each workstream an **epic** under it, and each
deliverable a **story** under its epic. Bodies come from files or flags, nothing
prompts, and every command prints what it created.

```bash
# 1. The plan becomes an initiative, and prints the slug its epics attach by
gh agile initiative create -t "Offline sync" -F plan.md --target 2026-12-18

# 2. Each workstream becomes an epic under it
gh agile epic create -t "Conflict resolution" --initiative offline-sync -F conflicts.md
gh agile epic create -t "Local cache" --initiative offline-sync -F cache.md

# 3. Each deliverable becomes a story under its epic, sized and prioritised
gh agile story create -t "Detect concurrent edits" --epic WIDG-41 --points 3 --priority high \
  --intent "Two devices editing one record must not lose either edit." \
  --acceptance "A concurrent edit is detected and both versions are kept."

# 4. A bug files under the epic it belongs to, or stands alone
gh agile bug create -t "Edits made offline are lost on reconnect" --epic WIDG-41 --priority highest
```

A body file is read as `## Heading` sections — `## Intent` and `## Acceptance` —
so the plan's own document can be the initiative's body. Every issue under the
initiative also carries the `initiative:offline-sync` label, so a board can be
filtered to the whole tree.

The initiative, its epics, and the checks `validate` runs on it:

```bash
gh agile initiative view offline-sync
```

<!-- sample: initiative-view -->
```text
WIDG-40 · initiative · open · In Progress
Offline sync
https://github.com/acme/widgets/issues/40

  priority   high
  dates      2026-11-09 .. 2026-12-18
  labels     initiative:offline-sync

  epics: 0/2 closed
    WIDG-41  epic       In Progress  Conflict resolution
    WIDG-42  epic       Todo         Local cache

  checks
    1 item(s): no problems found

## Intent
Widgets must work without a connection and reconcile when it
returns, without losing an edit made on either side.

## Acceptance
An edit made offline on two devices survives reconnecting
both, and a conflict is shown rather than resolved silently.
```

[USER_GUIDE.md §8](https://github.com/paulcaron16k/gh-agile/blob/main/USER_GUIDE.md#8-for-an-agent-working-on-a-developers-behalf)
covers driving the whole workflow from an AI agent.

---

## A story's life cycle

Five statuses, and one command to move between them. Each move fills in what
the board would otherwise get wrong:

```text
          issue move            issue move             issue close
  Todo ─"In Progress"─▶ In Progress ─"In Review"─▶ In Review ─--evidence─▶ Done
                          │   ▲
       issue move Blocked │   │ issue move "In Progress"
                          ▼   │
                         Blocked
```

| Step | Command | What changes |
|---|---|---|
| Filed | `gh agile story create … --epic WIDG-41` | `type:story`, `key:WIDG` and `initiative:` labels; on the board, under its epic |
| Planned | `gh agile issue edit WIDG-46 --field Sprint --value "0005 W48-2026"` | Put in a sprint ahead of time — optional |
| Started | `gh agile issue move WIDG-46 "In Progress"` | Status; the **current sprint** if it has none; a `sprint:2026-11-23` label; **assigned to you** if nobody holds it; an epic or initiative above it still at Todo follows to In Progress |
| Blocked | `gh agile issue move WIDG-46 Blocked --evidence "waiting on the schema change"` | Status, and the reason written into the issue's `## Evidence` |
| In review | `gh agile issue move WIDG-46 "In Review" --evidence "PR #57; covered by test_merge"` | Status, and the evidence so far |
| Done | `gh agile issue close WIDG-46` | Closed with Status Done — **refused** without an `## Evidence` section — and a second `sprint:` label if it finished in a later sprint |
| Sprint ends | `gh agile sprint carryover` | Unfinished work moves to the next sprint; finished work stays where it was done |

**Starting work is one call** because each piece it sets is something a board
gets wrong when it is left out: in-progress work outside every sprint vanishes
from the sprint report, and work nobody is assigned to answers "who has it?"
with nothing. Each fills a gap and none overrules a decision — an issue somebody
already holds is reported and left alone.

**The `sprint:` label is the record.** GitHub's Sprint field holds one value and
can be cleared by a change to the sprint configuration; the dated labels on the
issue cannot, and `gh agile sprint reconcile` rebuilds the field from them.

---

## See the work

```bash
gh agile board view sprint        # the current sprint
gh agile board view backlog       # everything not in a sprint yet
gh agile board view roadmap       # the epics, by when their work began
gh agile issue status             # stand-up: yours, waiting on review, unassigned
```

**Any unique part of a board's name is enough** — `sprint` finds *Sprint
board*, `backlog` finds *Backlog*. A part that matches two boards is refused,
and both are listed.

The Widgets sprint board: the stories and the bug in the current sprint, by
Status, with the epic and initiative they advance listed above them.

<!-- sample: sprint-board -->
```text
Sprint board
scrum · acme/projects/7 · 5 of 11 items
filter: sprint:@current

advancing (derived from the work below, not selected by the filter):
  WIDG-40  initiative  0/2  Offline sync
  WIDG-41  epic        2/6  Conflict resolution

  key      type        pts  sprint    who    title
  ───────  ──────────  ───  ────────  ─────  ───────────────────────────────────
Todo (1)
  WIDG-46  story         3  0005 W48  —      Merge edits that do not overlap

In Progress (2)
  WIDG-45  story         2  0005 W48  alice  Show a conflict banner
  WIDG-50  bug           —  0005 W48  alice  Edits made offline are lost on
                                             reconnect

In Review (1)
  WIDG-44  story         5  0005 W48  bob    Keep both versions on conflict

Done (1)
  WIDG-47  story         1  0005 W48  bob    Version-stamp every record

empty: Blocked
```

<details>
<summary><strong>The backlog</strong> — the plan's tree, for the work not yet in a sprint</summary>

<!-- sample: backlog -->
```text
Backlog
backlog · acme/projects/7 · 5 of 11 items
filter: no:sprint -status:Done
pts: story points, or closed/total sub-issues for epics and initiatives

  key        type        pts  sprint  title
  ─────────  ──────────  ───  ──────  ──────────────────────────────────────────
  WIDG-40    initiative  0/2  —       Offline sync
   WIDG-41   epic        2/6  —       Conflict resolution
   WIDG-42   epic        0/2  —       Local cache
    WIDG-48  story         5  —       Cache records on the device
    WIDG-49  story         2  —       Evict the cache by age
```

</details>

<details>
<summary><strong>The roadmap</strong> — each epic, under the sprint its work began in</summary>

<!-- sample: roadmap -->
```text
Roadmap
roadmap · acme/projects/7 · 2 of 11 items
filter: label:type:epic
sections: when the work under each item began, from the earliest sprint: label beneath it
pts: story points, or closed/total sub-issues for epics and initiatives

  key      type  pts  sprint  title
  ───────  ────  ───  ──────  ──────────────────────────────────────────────────
0004 W46-2026 · from 2026-11-09 (1)
  WIDG-41  epic  2/6  —       Conflict resolution

(not started) (1)
  WIDG-42  epic  0/2  —       Local cache
```

</details>

<details>
<summary><strong>Stand-up</strong> — <code>gh agile issue status</code>, for alice</summary>

<!-- sample: issue-status -->
```text
0005 W48-2026  2026-11-23 .. 2026-12-06  -- the current sprint, for alice

Assigned to you
  In Progress
    WIDG-45  Show a conflict banner
    WIDG-50  Edits made offline are lost on reconnect

In Review, not yours
  WIDG-44  Keep both versions on conflict  (bob)

In the sprint, and nobody holds it
  WIDG-46  Merge edits that do not overlap
```

</details>

Every board also renders as JSONL with `--format jsonl`, or as JSON with
`--json`, and every `list` piped elsewhere prints tab-separated rows.

---

## Get the data out

```bash
gh agile export --grain issues,events --format csv --out-dir exports/
```

One row per work item, and one per timeline event — status changes with who
made them and when — so `cycle_time` and `lead_time` come out in seconds, ready
to chart. Pull requests, sprints and boards are grains of their own. Every
column is typed in
[`github_catalog.json`](https://github.com/paulcaron16k/gh-agile/blob/main/github_catalog.json).
JSON is the default format; `--format csv` writes the CSV files a loader or a
spreadsheet takes. Runs into `--out-dir` are incremental.

---

## Commands

Every command takes `--help`. A command that acts on one issue takes it as a
number, a key such as `WIDG-42`, or its URL.

<details>
<summary><strong>Work items</strong> — <code>initiative</code>, <code>epic</code>, <code>story</code>, <code>bug</code>, <code>task</code></summary>

| Command | What it does |
|---|---|
| `initiative create` | File the initiative issue, board it, and mint its slug |
| `initiative list` / `view` | List initiatives by Status; view one, its children and its checks |
| `initiative reconcile` | Bring `initiative:<slug>` into line with the hierarchy |
| `epic create` | File an epic and put it on the board |
| `epic list` / `view` | List epics by Status; view one, its children and its checks |
| `story create` | File a story, attach it to its epic, and set its fields |
| `story list` / `view` | List stories by Status; view one |
| `bug create` | File a bug, under its epic if it has one, and set its fields |
| `bug list` / `view` | List bugs by Status; view one |
| `task create` / `list` | File a task under its story; list them with their story. A checklist in the story is usually better |

</details>

<details>
<summary><strong>Moving work</strong> — <code>issue</code></summary>

| Command | What it does |
|---|---|
| `issue move` | Change status, with the evidence that status requires |
| `issue status` | The current sprint: yours by Status, what is in review, what nobody holds |
| `issue edit` | `gh issue edit`'s flags, plus the board's fields and the plan |
| `issue close` / `reopen` | As `gh` does, and set Status to Done, or move it back |
| `issue list` / `view` | Every work item on the board by Status; any one item, its children and its checks |
| `issue reconcile` | Repair one issue's Sprint field from its `sprint:` labels |

</details>

<details>
<summary><strong>Sprints</strong> — <code>sprint</code></summary>

| Command | What it does |
|---|---|
| `sprint list` / `view` | Every sprint, active and completed; one sprint's window and items |
| `sprint ensure` | Add sprints until one is current and enough lie ahead |
| `sprint create` | Add one sprint |
| `sprint edit` | Rename a sprint; every item keeps its assignment |
| `sprint carryover` | Move a sprint's unfinished work to the next sprint |
| `sprint reconcile` | Set every item's Sprint field from its `sprint:` labels |
| `sprint backfill` | Add `sprint:` labels to issues that predate them, from history |
| `sprint unstamp` | Remove `sprint:` labels from epics and initiatives |

</details>

<details>
<summary><strong>Boards and the project</strong> — <code>board</code>, <code>project</code>, <code>key</code>, <code>sync</code></summary>

| Command | What it does |
|---|---|
| `init` | From a fresh clone to a working board, in one command; safe to re-run |
| `install` | Link a copy installed from PyPI into `gh`, so `gh agile` runs it |
| `board list` / `view` | Every board on the project; one board as text or JSONL |
| `board create` | Create a board, or converge the one with exactly this name |
| `project view` / `edit` | The project's owner, number, keys, cadence and title prefix; change the cadence or the prefix |
| `key list` / `add` / `delete` | The repository keys in the profile; `delete` is refused while issues carry it |
| `sync` | Add issues that belong on the board and are not on it; `--adopt` gives them a key and a Status |

</details>

<details>
<summary><strong>Checking and data</strong> — <code>validate</code>, <code>export</code>, <code>unfinished</code></summary>

| Command | What it does |
|---|---|
| `validate` | Check the conventions in POLICY.md |
| `export` | Export items, field values, status history, pull requests and sprints |
| `unfinished` | Name the issues a merge closed and nobody finished — what the post-merge hook runs |

</details>

---

## Learn more

- **[USER_GUIDE.md](https://github.com/paulcaron16k/gh-agile/blob/main/USER_GUIDE.md)** —
  the walkthrough: every property, sprints, boards, the workflow end to end, and
  export, with a full command reference.
- **[REFERENCE.md](https://github.com/paulcaron16k/gh-agile/blob/main/REFERENCE.md)** —
  how it works and why: versions and the deprecation policy, the hierarchy and
  object model, how sprint history is kept, the export, team permissions, and
  what it does not do.
- **[POLICY.md](https://github.com/paulcaron16k/gh-agile/blob/main/POLICY.md)** —
  the conventions `gh agile validate` enforces.

---

## License

[Apache License 2.0](https://github.com/paulcaron16k/gh-agile/blob/main/LICENSE).
Copyright 2026 Paul Caron; see
[NOTICE](https://github.com/paulcaron16k/gh-agile/blob/main/NOTICE).
