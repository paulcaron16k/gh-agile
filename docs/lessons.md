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

**A target nobody runs is a target that does not work.** `make scratch` created a project, had its `setup`
refused because `--project 20` disagreed with `project.number 4` in the profile, and **still exited 0** —
handing back a scratch project with no fields and no labels while reporting success. Broken since
`project.number` first entered the profile. `self-test` never hit it because `apply_defaults` exempts that
command by name, so the *tested* path and the *documented* path had diverged silently.

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
