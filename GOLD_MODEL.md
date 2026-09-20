# Mapping GitHub to the Gold Agile data model

> **What this tool exports is silver.** `github_issues`, `github_events` and `github_prs` are
> GitHub's facts under GitHub's names. The Gold `agile_*` tables belong to the
> ExperienceFlow model and are the output of a **silver → gold transform that
> lives in the IWS Partner pipeline**, not here — that is where
> `org_master_employees` exists to resolve a login into an `actor_id`, and
> where `team_id` can be synthesised. Measured against the catalog, the gap is
> real and the transform is not optional:
>
> | | Gold fields | Silver columns | Names matching |
> |---|---|---|---|
> | issues | 58 | 32 | **2** |
> | events | 22 | 18 | **14** |
>
> The events grain was built to Gold's vocabulary and is close. The issues grain
> is not: names differ (`number` → `process_id`, `created_at` → `created_date`)
> and so do **units** — `cycle_time_days` against `cycle_time_hours`, a factor
> of 24 that would corrupt a dashboard quietly rather than fail loudly. The
> transform must rename, convert, derive `process_guid`, resolve employee ids,
> and leave what GitHub cannot supply null.

How GitHub Projects v2 fills `agile_issues` and `agile_events`, where it matches
Jira, and the one place it genuinely cannot.

The target is ExperienceFlowAI's Gold model — `agile_catalog.json`,
`agile_data_model.md` — in which both Jira and GitHub are *sources* feeding one
shape. Every claim below was measured against a live project on 2026-08-14, not
read from documentation.

---

## The headline: can GitHub do Jira's changelog?

**Mostly yes, and for state changes it is arguably better. For custom fields, no.**

Jira's changelog is one uniform stream per issue: every field, with `from` and
`to` and a timestamp. GitHub's equivalent is the **issue timeline**, which is 51
distinct typed events rather than one stream. Measured, on a real transition:

```
AddedToProjectV2Event            2026-08-14T16:58:59Z
ProjectV2ItemStatusChangedEvent  2026-08-14T16:59:00Z  (none) -> Todo
LabeledEvent
ProjectV2ItemStatusChangedEvent  2026-08-14T16:59:32Z  Todo -> In Progress
ClosedEvent
```

`ProjectV2ItemStatusChangedEvent` carries `previousStatus`, `status`, `actor`,
`createdAt` **and `wasAutomated`** — which is more than Jira's changelog gives
you, because it distinguishes a human moving a card from a rule doing it.

| `agile_events` column | GitHub source |
|---|---|
| `occurred_at` | `createdAt` on the timeline event |
| `event_category` = `state_change` | `ProjectV2ItemStatusChangedEvent` |
| `state` / `prior_state` | `status` / `previousStatus` |
| `state_changed` | `status != previousStatus` |
| `actor_name` / `ext_actor_id` | `actor.login` |
| `event_category` = `activity` | `AssignedEvent`, `LabeledEvent`, `MilestonedEvent`, `ClosedEvent`, `ReopenedEvent`, `SubIssueAddedEvent`, `CrossReferencedEvent`, and ~40 more |
| `event_category` = `data_change`, with `data_from` / `data_to` | `IssueFieldChangedEvent` — `previousValue`/`newValue`, `previousOptions`/`newOptions` |

### The gap, stated precisely

**A change to a Projects v2 *custom* field emits no event.** Status is special —
it has its own event type. Points, Sprint, Priority and any custom text field do
not: setting `Story Points = 5` was measured to leave nothing on the timeline,
and `ProjectV2Item` carries only `updatedAt` to show for it.

`IssueFieldChangedEvent` looks like it should cover this and does not — it
belongs to GitHub's newer *issue* fields, not to project custom fields.

So of the Gold model's `data_from` / `data_to`, GitHub natively fills:

| Field kind | Change history |
|---|---|
| Status | **Yes** — dedicated event, with previous value |
| Assignee, labels, milestone, title, state, parent | **Yes** — one typed event each |
| Projects v2 custom fields (points, sprint, priority, …) | **No** |

**The mitigation is snapshots.** Run `gh agile export --no-history` on a schedule,
keep the dated output, and diff consecutive snapshots to synthesise
`data_change` events for the custom fields. Resolution equals snapshot interval,
which is worse than Jira's exact timestamps and is enough for burndown and
estimate-accuracy work. Record it honestly in the export rather than implying the
timestamps are exact.

### A second measured caveat: the timeline is eventually consistent

A status change is **not** visible on the timeline immediately. Measured by
polling every 15s: a transition made at **17:01:48Z became readable at
17:03:57Z — a lag of ~75 seconds**, while an earlier one was readable within
seconds. So the delay is real, variable, and on the order of a minute.

Consequence for any scheduled export: **do not treat the latest export as
complete for the last few minutes**, and prefer re-exporting a window rather than
appending only what is new.

---

## Project keys: name yes, key no

`ProjectV2` carries `title`, `shortDescription` and `readme`. There is **no key,
slug, prefix or abbreviation field** — checked against the schema, not assumed.
So a Jira-style `ZMBNI-1817` has to be synthesised.

**And it must be keyed on the repository, not the project.** Jira can put the key
on the project because there the issue-number sequence *is* the project's. On
GitHub the sequence is per **repository**, and `ProjectV2.repositories` is
plural — a board may hold items from several. A project-level key would make
`KEY-12` ambiguous the moment a second repository joined.

So `gh agile key --repo owner/name --key ZMBNI` records the mapping in
`.gh_agile.json`, and the export emits `issue_key` from it. Passing `--name` as
well writes `"<name> [<KEY>]"` into the project's `shortDescription`, which is
the closest GitHub offers to storing the pair where a person will see it:

```
title:            gh-agile
shortDescription: gh-agile: Agile management on GitHub [AGILE]
```

The config is deliberately a different file from the export watermark: one is
configuration a person writes, the other is state a machine rewrites, and a `rm`
to reset the watermark should not lose the keys.

## `agile_issues` field mapping

| Gold field | GitHub source | Notes |
|---|---|---|
| `ext_process_id` | `Issue.id` (node ID) | Stable across renames and transfers |
| `issue_key` | `KEY-number`, from `.gh_agile.json` | GitHub has no key of any kind — see below. Falls back to `owner/repo#number` when no key is recorded |
| `state_id` / `state_name` | Project `Status` field | Map the option to the FSM: `new\|ready\|in_progress\|in_review\|in_qa\|blocked\|done` |
| `issue_type_id` | `type:` label | Issue *types* would be better but are organization-only |
| `created_date` | `Issue.createdAt` | |
| `updated_date` | `Issue.updatedAt` | Replication key |
| `closed_date` | `Issue.closedAt` | |
| `project_id` | Project number + owner | |
| `epic_id` | `Issue.parent.id` (sub-issue parent) | |
| `parent_id` | same | GitHub has one parent edge, not two |
| `assignee_ext_id` | `assignees.nodes[].login` | Gold expects one; GitHub allows many — take the first, keep the rest in `data` |
| `reporter_ext_id` | `Issue.author.login` | |
| `story_points` | Project number field | |
| `priority_id` | Project single-select | |
| `labels` | `labels.nodes[].name` | |
| `sprint_id` | Project iteration field | |
| `subtask_count` | `subIssuesSummary.total` | |
| `lead_time` | `AddedToProjectV2Event` → done | **Not** created→done: an issue open a year and boarded yesterday has one day of lead time by this definition. State it |
| `cycle_time` | first `In Progress` → `Done` | From the timeline |
| `blocked_time`, `review_time`, `qa_time` | Sum of intervals in each status | Derivable from the status events, since each carries its previous value |
| `status_change_count`, `reopen_count`, `was_blocked` | Count of status events | |
| `data` | Everything unmapped | Where the extra assignees and any custom field goes |

**Unfillable from GitHub, and better left null than faked:** `business_value`,
`severity_id`, `released_date` and the release-linked features — GitHub has no
release object tied to an issue the way Jira's `fixVersion` is. `team_id` needs
the org synthesis rules; GitHub has no team edge on an issue.

---

## Rate limits are a design constraint, not an afterthought

GraphQL is budgeted at **5000 points an hour**, and creating a dozen stories
exhausted it. The cause was not volume but chattiness: setting one field
re-fetched the entire field list and re-resolved the project id, three round
trips to write one number, times three fields, times every story.

Two rules follow, and they shape any tool that writes to a board:

- **Resolve identifiers once per run.** Project id and field list are stable for
  the duration; caching them cut the per-story cost by roughly two thirds.
- **The export is chattier still.** History needs one timeline query *per issue*,
  so a thousand-item board is a thousand queries plus paging. For anything
  regular, export on a schedule and keep the output, rather than re-querying on
  demand.

Found by running out, not by reading the code.

## The silver contract

`github_catalog.json`, in this repository, describes what the export writes — and `tests/test_export_catalog.py` fails when it stops being true, in either direction: six streams, every column
typed and nullable-or-not, `key_properties`, and the replication method per stream. It is the input a
silver→gold transform is entitled to assume, and it is checked against the real export rather than
maintained by hand alone.

**It is not `agile_catalog.json`.** That is the Gold catalog described below, it lives outside this
repository, and it describes the `agile_*` tables. The `github_` prefix is the reminder that everything
here is silver.

## Initiatives: an attribute in Gold, not a level

Silver gained a level above epic — `type:initiative`, with epics as sub-issues.
The question this forces is whether **Gold** gains one too, and the recommendation
here is **no**: an initiative should arrive as an *attribute of the issues beneath
it*, not as a fourth hierarchy level.

Three reasons, and the first is decisive:

1. **The Gold model is owned elsewhere.** `agile_catalog.json` and
   `agile_data_model.md` live outside this repository, and a new hierarchy level
   is a schema change every consumer of `agile_issues` would have to absorb. An
   attribute is additive.
2. **It answers the questions anyway.** `initiative_slug` on every issue in the
   tree — maintained by `initiative reconcile` — is what a burndown, a
   cycle-time distribution or a scope report actually needs. None of them
   traverses a hierarchy; they group.
3. **Nothing is lost.** The initiative issue is exported as an ordinary
   `github_issues` row with `type:initiative`, so if Gold later wants the level,
   the rows are already there and `parent_key` already records the edge.

| silver | gold | note |
|---|---|---|
| `initiative_slug` | an attribute on the issue | The join key. Group by it |
| `parent_key` | the parent edge, any level | A key, so it joins to `issue_key` in one column |
| `parent_type` | which level the parent is | `initiative` above an epic, `epic` above a story |
| `epic_key` | the epic a story belongs to | Empty when the parent is not an epic |
| `epic_number` | — | **Prefer `epic_key`.** A number alone is ambiguous on a board spanning repositories, and there is no `epic_repository` beside it |

That last row is the one to carry back. `agile_issues` inherits the same weakness
if it references a parent by number: GitHub numbers issues per repository, so two
repositories on one board both have a `#12`. **The Partner Gold model likely needs
the same revisit**, and that decision is not this repository's to make.

### Container progress is silver's, not Gold's

`github_issues` carries `sub_issues_done` over `sub_issues_total`, and
`github_catalog.json` states what that pair means. **Gold does not gain a
corresponding measure**, for the same reason it does not gain the level: an
initiative is an *attribute* of the issues beneath it, so "how far along is this
initiative" is a `GROUP BY` over `agile_issues` rather than a column somebody has
to keep in step.

The silver pair stays because it is what GitHub actually hands over —
`subIssuesSummary`, per level, counted at read time — and because the boards
render it directly. A Gold measure derived the same way would be a second
definition of the same number, and the two would disagree the first time an
issue was closed between two exports.

So: **read it in silver, aggregate it in Gold.** If a Gold consumer wants
progress, the honest derivation is over the issues themselves, filtered by
`initiative_slug` or joined on `parent_key` — not a copy of this pair moved up a
layer. The one thing a Gold transform must not do is treat `sub_issues_done` as
transitive: it counts direct children only, so adding an initiative's tally to
its epics' tallies produces a figure that reconciles to neither level.

## Tasks: below the boundary, and not exported

Silver gained a level *below* story — `type:task`, for a team that files
story-internal housekeeping as issues rather than as a markdown checklist.
**Nothing about it reaches Gold, because nothing about it reaches the export.**

The decision, taken on AGILE-137 before any of it was written: a task has no
metric and no KPI. It is how one person is organising their own story, and many
teams keep exactly the same thing in a checklist file. It carries no story
points, is never given a `sprint:` label, sits on no board, and is counted by
nothing that counts stories — so a row for one would change no number in any
downstream model. **A grain exists to be measured, and this one would not be.**

So `github_issues` has no task rows, and `github_events` drops their events with
them: an event referencing an issue that has no row is a foreign key into
nothing, which is worse than the absence. `github_catalog.json` states the
exclusion rather than leaving it to be inferred, because a contract silent about
what it omits reads as an oversight.

**This is a boundary, not an omission**, which is the distinction this document
exists to draw. The Gold model has no task grain and should not acquire one on
this repository's account. If breakdown analysis is ever wanted, the data is
still in GitHub and the decision reverses without rewriting anything built on
it — which is the other reason it was the cheap direction.

## Consequences for the exporter

1. **Two queries, joined on the issue node ID.** Current state from the project,
   history from the timeline. Skipping the second gives a board dump.
2. **One export per grain.** `agile_issues` is one row per item;
   `agile_events` is one row per timeline event. They are different files, not
   one denormalised sheet.
   `github_prs` is a third: one row per pull request, carrying the size and
   review-round-trip signals a flow report needs. Its review events land in
   `github_events` under `process_type: pull-requests`, beside the issue-scoped
   `change-request-opened` that `event_rows` already emitted -- both rows are
   wanted, and `process_type` is what tells the two apart. **A review is the only
   record naming a second person**: the author did the work, the reviewer
   accepted or rejected it, and no issue event distinguishes them.
3. **Snapshots are part of the design, not a workaround.** They are the only
   source of custom-field history.
4. **Case-insensitive status matching.** GitHub's stock options are `Todo`,
   `In Progress`, `Done`; a constant reading `In progress` matched nothing and
   produced null cycle times with the data sitting right there. Measured, not
   theorised.
