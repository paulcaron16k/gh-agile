# Lessons

Findings from building this tool that cost something to learn and would cost the same again. `CLAUDE.md`
carries the conventions and the architecture; this file carries the *evidence for them*, and the mistakes
that are not encoded anywhere else.

Where a claim here has a number in it, that number came from a run.

## About GitHub

**Measure GitHub, do not reason about it.** Every significant finding came from an experiment on a scratch
project, and several contradicted what the documentation and the type names implied. The iteration
behaviour, the six built-in workflows, the write-only series anchor, the `503`s — all measured. The type
name `ProjectV2Iteration` implies an identified object; it carries `startDate`, `duration` and `title` and
no id, which is the whole defect this tool is built around.

**A project's built-in workflows can be read, and reading them explains defects that look unrelated.**
Measured 2026-09-16 — `projectV2.workflows` returns each one's `name` and `enabled`:

```
project 4 (AGILE)            project 19 (sandbox)
  [off] Auto-close issue       [on ] Auto-close issue
  [off] Item closed            [on ] Item closed
```

Two defects chased from opposite ends all session turned out to be **one setting seen from two sides**.
The sandbox has everything on, so setting `Status = Done` there closed the issue before the tool could,
and `--not-planned` lost its reason. This board has almost everything off, so `Closes #n` left Status
behind and finished work sat in the In Progress column — twenty-two hours on one issue.

Neither investigation named the cause, because the documentation here said workflows could not be read
at all. **A wrong "you cannot look at that" is worse than no note**: it does not merely fail to help, it
stops the next person looking. What is genuinely impossible is *writing* them — the schema has
`deleteProjectV2Workflow` and no create or update — and reading a workflow's *filter*.

**A project workflow can close your issue before you do, and GitHub attributes it to you.** Measured
2026-09-13 on project `#19`: setting `Status` to `Done` and issuing **no close at all** left the issue
CLOSED as `COMPLETED` one second later. The `ClosedEvent` names the *project owner*, not
`github-project-automation`, so the timeline is indistinguishable from a close the tool performed — which
is how the mechanism was mis-read the first time it was seen.

Three consequences, each measured separately:

| probe | result |
|---|---|
| `Status = Done`, no close | CLOSED / `COMPLETED`, ~1s later, attributed to the caller |
| `gh issue close --reason` on an already-closed issue | no-op, `already closed` on stderr, **exit 0** |
| close with the reason *first*, then `Status = Done` | `NOT_PLANNED` survives |

So `move --status Done --not-planned --close` discarded the reason and reported success, because the
tool's close arrived second and `gh` exits 0 for a close that changed nothing. **The reason cannot be
repaired afterwards** — there is no second chance on a closed issue.

The fix is ordering, and it is not obvious from reading the code: close *before* writing `Status`. The
lesson generalises past this field — **when a project automation and this tool write the same thing, the
tool has to go first, because GitHub will not tell you it lost.** And an exit code from `gh` is not
evidence that a write happened.

**A `503` comes in bursts, so a retry loop without backoff is one attempt.** Six immediate retries of
`gh api user` all failed inside the same second, while the same call typed into a shell succeeded; one
retry twenty seconds later worked first time. Measured 2026-08-17 during a Partial System Outage.

**GitHub's errors are misleading under load.** In that same outage `gh project view --owner <login>`
returned *"unknown owner type"* — an error about the owner, for a request whose owner was correct all
along, and one that invites "fixing" the wrong thing. Retry before believing the error.

**GraphQL is charged for what you ask for, not what you get — and `gh project`'s
list commands are the expensive way to read a board.** Measured on a 25-item
board (2026-08-19), in GraphQL points:

| call | points |
|---|---|
| one `ISSUE_ITEM_QUERY` (issue-side: labels + item id + one field value) | 1 |
| `iterations()` — raw GraphQL | 2 |
| `fetch_items()` — paginated raw GraphQL, `first: 100`, every field value | 4–8 |
| `board_items()` — **was** `gh project item-list -L 200` | **106** |
| `board_items()` — now a lean GraphQL selection | **1** |
| `fields_of()` — **was** `gh project field-list -L 50` | **102** |
| `fields_of()` — now `fields(first: 50)` hand-written | **1** |

Two separate effects, and only the first is intuitive:

- **`item-list` is charged for the `-L` you ask for, not the rows you get.** `-L 200`
  against a 23-item board cost 102; `-L 25` cost 26; `-L 5` cost 6.
- **`field-list` is just flat expensive.** `-L 50` and `-L 20` both cost 102. There
  was no cheaper way to call it, only a cheaper thing to call.

So the fix was not tuning `-L`. It was that **`gh project`'s list subcommands
issue far more expensive queries than the same request written by hand** — about
a hundredfold — and everything they return can be asked for directly. `sync
--dry-run` went from ~107 points to 3 on that change alone. Verified afterwards
that the old and new item sets are byte-identical, because a cheaper read that
returns a different board is not a cheaper read.

**Moving cost off GraphQL made REST the limit that bites first — and where it
went is not yet established.** At the end of the session that made the change
above, `gh api rate_limit` reported **core 0/5000** and **graphql 4928/5000**.
Three `make self-test` runs, a `check-guide` run and a lot of measurement had
exhausted the REST budget while barely touching the GraphQL one, and the failure
surfaced as `gh label create` returning 403 — labels are REST.

Do not over-read this. Those runs plausibly account for a few hundred REST calls,
not five thousand, so **something else spends REST and it has not been
identified**. What is established: the two budgets are separate, GraphQL is no
longer the one that runs out first, and `CLAUDE.md`/`GOLD_MODEL.md` both still say
the GraphQL budget is the binding constraint on this tool. That claim is now in
question rather than known-wrong. Measuring it is one instrumented run away and
should happen before either document is rewritten.

The trap to avoid on the way: the obvious-looking cure was to *cache*
`fetch_items`. It must stay uncached — `move` writes a Sprint value and then
`record_sprint_label` reads it back through `sprint_assignments`, so a cache
there silently stops the `sprint:` label being stamped, and the label is the
durable record. Saving 8 points by risking the record would have been a bad
trade even if it had worked.

This inverts the assumption the per-invocation caches were built on. `_ITEMS` and
`_FIELDS` were added because "setting one field re-fetched the whole field list",
which was right — but the comment describes `fetch_items` as the heavy query and
`board_items` as the cheap cached one, and it is the other way round by an order
of magnitude. A repair routed through `board_items` cost 105 points to write one
field; going at it from the issue instead cost 3, because an issue can hand back
its own labels, its project item id and that item's field value in one query.

The general lesson is the specific one this file keeps repeating: the cost model
was inferred from the code's shape, and the code's shape was wrong about it. Two
`gh api rate_limit` reads either side of a command is the whole experiment.

**Search indexes lag behind writes.** `gh issue list --search "in:title ..."` returned nothing for an
issue created moments earlier. **Target by issue number, never by a title search, when the next step
writes.** The recovery from that miss — `sync --adopt --state all` — swept every live issue onto a scratch
project and labelled all of them, which is a large blast radius for a lookup.

## About destructive operations

**Destroy-then-repair needs the repair budgeted first.** The GraphQL budget ran out mid-restore during
development and an assignment was lost for good — the repair is one call per item and it is not
transactional. Hence `require_graphql_budget`, which refuses the destructive write when the budget cannot
cover the restore. Refusing before the write costs nothing; refusing halfway through is not an option.

**`rm -rf` on a directory you did not create is a decision.** Two of the owner's export files went that
way. Look first.

**A guard that looks broken is a guard someone overrides.** The teardown guard reads a project's title to
decide whether it is a scratch project. When that read failed during the outage, the bare `gh` error was
all the user saw — and the obvious way past an inexplicable error is the override flag, which skips the
check instead of retrying it. A guard has to explain its own failures, and say that the override is not
the fix.

**The default is the safety mechanism.** `REPO ?= paulcaron16k/gh-agile` in the Makefile is how a
`key:TEST` label reached every real issue, how throwaway issues left permanent holes in the number
sequence, and how scratch projects accumulated. A sandbox that is not the default is a sandbox that gets
skipped.

## About the code

**Green on two branches is not green on the merge, and a red default branch is silent.** Two pull
requests, `#66` and `#67`, were cut from the same base `23caaa6`, touched different code, and passed on
their own branches — 335 and 332 tests. Merging both left `main` red at `ebd4b4d` with two failures:
`move` on `In Progress` had learned to read assignees, and the other branch's fake `gh` answered only
`--json body`. Reproduced afterwards, one commit at a time:

| checkout | result |
|---|---|
| `bd1646d` — `#66` merged | 335 passed |
| `c795832` — `#67`'s branch commit | 332 passed |
| `ebd4b4d` — both merged | **2 failed**, 350 passed |
| `c795832` with `bd1646d` merged in locally | **2 failed**, 350 passed |

**Neither pull request's CI was wrong.** Each answered a question about a base that no longer existed by
the time either merged, and nothing re-asked it. GitHub already builds the merge commit for a
`pull_request` event — the staleness is that it does so once, when the run starts.

The normal remedy is branch protection with *require branches to be up to date before merging*, which
re-runs the checks when the base moves. It is not available here:

```
$ gh api repos/paulcaron16k/gh-agile/branches/main/protection
403  Upgrade to GitHub Pro or make this repository public to enable this feature.
```

**And CI did catch it.** The `push: branches: [main]` run fired and failed. `main` then sat red while the
next branch was cut from it, a pull request was opened, reviewed and merged; it was found by running
`make test` for an unrelated reason. A signal nobody is shown is the same as no signal — which is the
same lesson as *"Stop reporting permission failures as success"*, arriving from the other direction.

So, two habits with a target each: `make merge-check` before merging, which merges `origin/main` into a
throwaway worktree and runs the suite — the fourth row of that table is exactly what it does — and
`make hooks`, whose `post-merge` hook reports a red `main` the next time you pull, because that is the
moment somebody is already looking at the terminal.

**A target nobody runs is a target that does not work.** `make scratch` created a project, had its `setup`
refused because `--project 20` disagreed with `project.number 4` in the profile, and **still exited 0** —
handing back a scratch project with no fields and no labels while reporting success. Broken since
`project.number` first entered the profile. `self-test` never hit it because `apply_defaults` exempts that
command by name, so the *tested* path and the *documented* path had diverged silently.

**The tests and the tool can run on different interpreters, and only one of them
is the user's.** Raising ruff's `target-version` to `py312` let UP017 rewrite
`dt.timezone.utc` to `dt.UTC`, which arrived in 3.11. Every check stayed green —
`make lint`, 227 tests — because pytest runs inside `.venv` (3.12). The tool
itself has `#!/usr/bin/env python3`, which on this machine is 3.10, so the first
real invocation died:

    AttributeError: module 'datetime' has no attribute 'UTC'

`gh extension install` clones a file and provisions no interpreter, so a `gh`
extension runs on whatever the user happens to have. The dev floor and the
runtime floor are different numbers and the second one is not ours to choose.
Two `# noqa: UP017` keep the compatible spelling, and `require_interpreter()`
turns a genuinely too-old interpreter into a sentence rather than an exception
from the middle of a command.

The general shape: a green suite proves the code works *under the interpreter the
suite used*. Whenever the shipped entry point picks its own runtime — a shebang,
a container base image, a Lambda runtime — that is a second environment nothing
has tested.

**The fix is not a comment, it is a job that runs the floor.** `ruff`'s
`target-version` now sits at the floor rather than at the development default, so
pyupgrade cannot suggest syntax the floor will not run, and CI builds the venv at
3.10 as well as 3.12 and 3.13. Within seconds of first running the suite at 3.10,
it found the *same* autofix still sitting in `tests/test_time.py` — two more
`dt.UTC` calls that lint and 286 green tests had both waved through, because both
ran on 3.12. One bug had been fixed and its twin was still there.

So: three settings have to agree — the runtime guard, the lint target, and the
matrix — and the matrix is the only one of the three that can actually catch a
disagreement. A floor no job tests is a promise nothing keeps.

**A flaky test is worst where it is the only test.** `make self-test` was the sole
cover for `history()` — the function that turns a timeline into `started_at`,
`done_at` and `added_to_board_at`, and therefore the source of every cycle time
in the export. It asserts against a real GitHub timeline, which lags creation by
a minute or more, so it fails for reasons unrelated to the code. Twice in one
afternoon on 2026-08-21: once on `added_to_board_at`, once on the status
transitions, both green on an immediate re-run of identical code.

Two separate defects, and the second is the interesting one:

1. The wait loop polled for two of the three facts the assertions require, so an
   unpropagated `AddedToProjectV2Event` read as a regression. Wait for what you
   assert on.
2. **The parsing had no offline test at all.** So a genuine break and GitHub being
   slow produced the same output, and the only way to tell them apart was to run
   it again and see. `tests/test_history.py` now pins the parsing against fixture
   timelines — including the case-insensitivity that the original null-cycle-time
   bug turned on — and the live test keeps the one job only it can do: catching
   GitHub changing what it emits.

The general form: when a slow, non-deterministic test is the only thing covering
a piece of logic, its flakiness is not a test-quality problem, it is a coverage
problem wearing a disguise. Every failure becomes an investigation.

**Swallowed errors cost hours.** `restore_assignments` caught `SystemExit` and printed "could not restore"
without the reason. The reason was a rate limit, and finding that out took a full reproduction.

**A test that scans source text will fail on a comment.** The unit-suffix test first scanned the module and
tripped over a comment about another system's schema. Assert on emitted column names, not on the source
that produces them.

**Shadowed variables hide in the branch you did not run.** The export watermark was read under one
`state_key` and written under another, so incremental file export never advanced — and appeared to work
only because stdout runs happened to move the read key. Two names for one thing is a defect waiting for a
branch to be exercised.

## About writing things down

**Counts in prose rot; measurements do not.** The previous handoff said the tool was 2958 lines. It was
3288 by the time anyone checked. Where the number is the point — a dated measurement, a row count from a
specific run — keep it and date it. Where it is incidental, state the durable fact instead: "every profile
write is a read-modify-write", not "five call sites are".

**My own confident wording has been wrong more than once.** The `AGILE` state-file key was described as
"legacy from an older keying scheme, never read". It was the live *write* target of a shadowed variable.
Check before characterising something as dead, and prefer "I have not found a reader" to "there is none".

**Non-obvious workarounds need a comment saying why.** Several of them look like removable dead code —
`heal_sprint_fields` after a restore, re-sending byte-identical iterations, the budget check before a
mutation. Each carries the measurement that justifies it, because the next person to read it will
otherwise delete it and be right to, on the evidence in front of them.

**The owner caught things this tool's author missed** — a cron writing to `/var/log` that a user crontab
cannot, a recommendation to enable a built-in workflow that does not exist on user-owned projects, and the
sandbox question itself. Take a challenge as a signal to go and check, not to defend.

**A set named for the first rule that needed it will be read by six.** `SPANNING_TYPES` / `spans_sprints`
named epic-and-initiative after the rule that introduced them: a container must never be pinned to one
sprint. Five rules later — the `closed/total` tally, the status promotion, the assignee exemption, two
validator checks — only three were still about sprints, and `spans_sprints(labels)` was being read at sites
where no sprint was involved, sending the reader looking for one. Renamed to `CONTAINER_TYPES` /
`container_level`, after what the set *is*: the levels that contain work rather than being it. Every rule
follows from that sentence; the sprint reasoning moved down to the sprint call sites, where it is the point
rather than a name everything else reads past. **Name a set for its membership, not for its first
consumer** — and when the second rule reads it, that is the moment to check the name still describes the
set.

**A rule that removes a field from a level degrades every view grouped on it, silently.** #115 stopped
putting epics and initiatives in sprints — correct, and not in question. `ROADMAP_LAYOUT` had been grouping
by sprint as "the nearest text analogue of a timeline", chosen when an epic could carry one. Afterwards nine
of the ten epics on this board sat in a single `(no sprint)` bucket: the view still rendered, still
validated, still passed every test, and conveyed nothing. Nothing failed, because a grouping that collapses
to one bucket is indistinguishable from a board that genuinely has one. Found by reviewing the initiative
against its own acceptance months later, not by anyone hitting it. **When a change makes a field
unreachable for some level, grep for what groups, sorts or filters on it** — those are the places that
degrade rather than break. The replacement here derives the axis from work that happened (`sprint:` labels
on descendants) rather than from a field the rows can never hold, which is also why it cannot degrade the
same way again.

**A comment explaining why something is *not* selected is a claim about the future, and nothing checks
it.** `PROJECT_FIELDS_SELECTION` asked GraphQL for `__typename` and deliberately not `dataType`, with four
lines saying why: the two callers compared against `ProjectV2IterationField` and `ProjectV2Field`, and
selecting both would invite confusing them. True when written, and it separated exactly three kinds of
field — because everything that is not an iteration or a single-select is `ProjectV2Field`. TEXT, NUMBER and
DATE are one typename, 14 of the 17 fields on this board. So `#175` added two DATE fields and the premise
was gone that moment, silently, with the comment still standing there reading as authoritative. Every date
`gh agile epic --start` wrote went out as `--text`, and GitHub answered *did not receive a date value to
update a field of type date*. **When a change adds a case to a set, re-read the comments that justified
narrowing that set** — a rationale is dated evidence, not a standing fact, and the one place it will not be
questioned is the place it is written down.

**Something must test the thing everything else stubs.** Roughly thirty tests monkeypatch `set_field` away,
correctly: they are about what a command decides to write, not how. The consequence is that nothing had
ever looked at the argv it builds, so the defect above lived one layer below the entire suite — 1334
offline tests, `lint`, CI on four interpreters, all green, on a feature that had never once worked. It was
found by a question about a different part of it. **Count the stubs**: a seam mocked in thirty tests is
load-bearing, and it needs one test of its own that asserts on the real thing. Here that is
`tests/test_set_field_types.py`, which builds the command and reads the flags back — and whose fixtures
carry both `__typename` and `dataType`, so that against the unfixed tool it fails on the defect rather than
on a `KeyError`.

**And the write side is not covered by anything green.** CI gets no token and calls no `gh`; `check-guide`
runs read commands only; the offline suite is pure by design. So a green board says the logic is sound and
says nothing whatever about whether a write reaches GitHub. The date fields did not yet exist on the
author's own board, so the first real attempt to write one was the bug report. **Run it once against a real
project before calling it shipped** — that is the step whose absence let this go out, and the sandbox
(`paulcaron16k/agile-test`, project `19`) exists so it costs nothing.
