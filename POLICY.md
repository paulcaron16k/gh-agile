# Agile management on GitHub: policy and procedure

What is tracked, where, by whom, and which parts a machine does. Written because
the alternative — conventions held in one person's head and applied by hand — is
how a backlog quietly stops meaning anything.

The companion reference for *how GitHub works* is
`Agile_Project_Management_using_GitHub_Projects.md`. This document is the *rules*.

---

## 1. Why any policy at all

GitHub gives you two primitives — the **issue** and the **project field** — and
nothing else. There is no epic, no story, no sprint, no story point. Every one of
those is a convention layered on top, which means:

- **A convention that is not enforced is a suggestion.** One issue created
  without its epic link is invisible to every roll-up thereafter, and nothing
  complains.
- **A convention that is enforced by hand is a rota.** It holds while someone is
  paying attention and decays the week they are not.

So the rule this document exists to state: **anything the tooling can check, the
tooling checks.** Everything else is written down here, in one place, in the
language a person reads before creating an issue.

---

## 2. The object model

| Agile concept | GitHub representation | Why this and not something else |
|---|---|---|
| **Epic** | An issue labelled `type:epic`, holding stories as **sub-issues** | Sub-issues give a real parent/child edge the API can traverse and roll up. Issue *types* would be better but are an organization-only feature |
| **Story** | An issue labelled `type:story`, attached as a sub-issue of exactly one epic | One parent, always. An orphan story is a validation failure, not a style choice |
| **Task** | A markdown checklist inside the story | Tasks below story level are working notes. Promoting them to issues buys ceremony and costs signal |
| **Bug** | An issue labelled `type:bug`; may or may not have an epic | Bugs arrive without asking whether they fit a plan |
| **Sprint** | Project **iteration** field named `Sprint` | The one field GitHub genuinely provides for this |
| **Status** | Project single-select: `Todo`, `In progress`, `Blocked`, `In review`, `Done` | Deliberately five. Every extra column is a state someone must decide between |
| **Estimate** | Project number field `Points` | Number, not select, so it can be summed |
| **Traceability** | Project text field `FR`, free text | Carries the requirement id where one exists |

**Identifiers.** GitHub's issue number is the address; it is assigned in one
sequence shared with pull requests, starts at 1, and cannot be namespaced or
reserved. Where a project already has its own scheme — Zamboni's `ZMBNI-1817` —
that identifier stays **in the issue title**, because existing references in code
and documentation resolve to it and `#7` never will.

---

## 3. What a person does, and what a machine does

The split is the point of this section. If you are doing something in the left
column by hand, that is a bug in the tooling.

| Action | Who | How |
|---|---|---|
| Decide something is worth doing | Person | Judgement. Not automatable, not worth pretending |
| Write the issue body: intent, acceptance, evidence | Person | The body is the artifact that survives; see §4 |
| Create the project and its fields | **Machine** | `gh agile setup --spec agile.yml`, idempotent |
| Create an epic or story with its labels, parent and fields | **Machine** | `gh agile epic` / `gh agile story` — one call, no multi-step dance |
| Attach a story to its epic | **Machine** | Part of creation. Doing it after the fact is how orphans happen |
| Move an item across the board | Person | The board is the interface; dragging is fine |
| Set status from a merged pull request | **Machine** | `Fixes #N` closes the issue; a workflow sets `Done` |
| Check every story has an epic, statuses are legal, closed items are dated | **Machine** | `gh agile validate`, in CI |
| Export the backlog with history for analysis | **Machine** | `gh agile export` |
| Decide what the export means | Person | See §6 |

---

## 4. Procedure: the issue body

Three headings, always, because an issue with a title and no body is a reminder
rather than a record.

```markdown
## Intent
What changes for whom, and why it is worth doing. One paragraph.

## Acceptance
The condition under which this is done. Written so someone else can check it.

## Evidence
Filled in as work proceeds: what was measured, what was tried, what was ruled
out and why. This is what makes the closed issue worth reading a year later.
```

**The Evidence section is not optional and not decoration.** A backlog whose
closed items say only "done" has thrown away the reasoning that made the decision
defensible. When a question is reopened — and it will be — this is the difference
between re-deciding and re-reading.

**Closing an issue means the acceptance condition is met**, not that work stopped.
Work that stopped for another reason is closed with a comment saying which, or
labelled `wontfix` and closed as **not planned** so the two are distinguishable in
the export.

---

## 5. Procedure: the cycle

1. **Refine** — anything in `Todo` without an epic, an estimate, or an acceptance
   condition is not ready. `gh agile validate` lists these; it is the agenda.
2. **Plan** — assign items to the current `Sprint` iteration. Capacity is last
   sprint's completed points, not optimism.
3. **Work** — one item in `In progress` per person. Moving to `In review` means a
   pull request exists and references the issue with `Fixes #N`.
4. **Close** — the merge closes the issue; automation sets `Done`.
5. **Review** — export, look at the numbers in §6, write down one thing to change.

**A sprint is optional.** For a queue where everything is blocked upstream, an
iteration field measures waiting rather than work. Adopt sprints when work
actually flows; until then the backlog and epic views are the whole system.

---

## 6. Analysis: what can and cannot be measured

This is where GitHub differs from Jira in a way that matters, and it is better
known before designing a report than after.

**Jira exports carry a per-field changelog. GitHub's project items do not.**
`ProjectV2Item` exposes `createdAt`, `updatedAt`, and current field values —
nothing else. An export built only from `gh project item-list` is a **snapshot**,
and no amount of post-processing recovers when an item entered `In progress`.

The history exists, but on the **issue timeline**:

| Event | What it gives you |
|---|---|
| `ProjectV2ItemStatusChangedEvent` | Every status transition, with its timestamp |
| `IssueFieldChangedEvent` | Other field changes |
| `AddedToProjectV2Event` | When the item entered the board |

So the export **joins two queries on the issue node ID**: current state from the
project, history from the timeline. Any tool that skips the second gives you a
board dump that cannot answer a single flow question.

What that makes measurable:

| Metric | Derived from |
|---|---|
| **Cycle time** | First `In progress` → `Done`, per item |
| **Lead time** | `AddedToProjectV2Event` → `Done` |
| **Throughput** | Items reaching `Done` per iteration |
| **Blocked time** | Duration in `Blocked` |
| **Estimate accuracy** | `Points` against cycle time |

What stays unmeasurable, and should not be faked: **anything before the item
joined a project.** An issue that sat open for a year and was added to the board
yesterday has one day of lead time by this definition. State that in the report
rather than papering over it.

---

## 7. Automation boundaries

Three rules, each with a reason.

**Automation may set a field; it may not decide the work.** A workflow moving an
item to `Done` on merge is bookkeeping. A workflow that closes stale issues is
making a product decision on a timer, and it will close something that mattered.

**Automation runs on a token with the narrowest scope that works.** `GITHUB_TOKEN`
cannot reach user or organization projects, so project automation needs a PAT with
`project` scope or a GitHub App token in a repository secret. That is a stored
credential — the one thing the release workflow deliberately does not have. Weigh
each automation against that cost; local scripts run on your own already-scoped
token and add no secret at all.

**Validation fails loudly, in CI, on a schedule.** A validator nobody runs is a
document. `gh agile validate` belongs in a scheduled workflow so a drifting
backlog is a red tick rather than a discovery.

---

## 8. Migration policy

When a project already has a file-based backlog:

- **Migrate open work only.** Closed items are a historical record; re-creating
  them as closed issues loses their formatting and gains nothing browsable.
- **Freeze the file, do not delete it.** It stays as the archive, with a header
  saying where current work now lives.
- **Keep the old identifiers in issue titles**, so every existing reference in
  code and docs still resolves.
- **Port the file's checks.** If tests asserted the backlog's shape — statuses
  legal, closed items dated, epics consistent — those become `gh agile validate`
  rules. Migrating without them trades a checked backlog for an unchecked one.
