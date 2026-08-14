# Mapping GitHub to the Gold Agile data model

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

## `agile_issues` field mapping

| Gold field | GitHub source | Notes |
|---|---|---|
| `ext_process_id` | `Issue.id` (node ID) | Stable across renames and transfers |
| `issue_key` | `owner/repo#number` | GitHub has no project-prefixed key; the number is per repository |
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
| `lead_time_hours` | `AddedToProjectV2Event` → done | **Not** created→done: an issue open a year and boarded yesterday has one day of lead time by this definition. State it |
| `cycle_time_hours` | first `In Progress` → `Done` | From the timeline |
| `blocked_hours`, `review_hours`, `qa_hours` | Sum of intervals in each status | Derivable from the status events, since each carries its previous value |
| `status_change_count`, `reopen_count`, `was_blocked` | Count of status events | |
| `data` | Everything unmapped | Where the extra assignees and any custom field goes |

**Unfillable from GitHub, and better left null than faked:** `business_value`,
`severity_id`, `released_date` and the release-linked features — GitHub has no
release object tied to an issue the way Jira's `fixVersion` is. `team_id` needs
the org synthesis rules; GitHub has no team edge on an issue.

---

## Consequences for the exporter

1. **Two queries, joined on the issue node ID.** Current state from the project,
   history from the timeline. Skipping the second gives a board dump.
2. **One export per grain.** `agile_issues` is one row per item;
   `agile_events` is one row per timeline event. They are different files, not
   one denormalised sheet.
3. **Snapshots are part of the design, not a workaround.** They are the only
   source of custom-field history.
4. **Case-insensitive status matching.** GitHub's stock options are `Todo`,
   `In Progress`, `Done`; a constant reading `In progress` matched nothing and
   produced null cycle times with the data sitting right there. Measured, not
   theorised.
