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
