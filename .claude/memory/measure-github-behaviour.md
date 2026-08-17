---
name: measure-github-behaviour
description: Verify GitHub API behaviour by experiment on a scratch project; docs and type names have been misleading
metadata:
  type: feedback
---

Findings this project that contradicted what the API implied: an INPUT_OBJECT literally named
`ProjectV2Iteration`; a configuration input that takes `startDate` while the readable type exposes
only `startDay` (write-only anchor); six built-in project workflows with no auto-add among them; and
`deleteProjectV2Workflow` with no create or update, so automations cannot be converged from code.

**Why:** every number in this repo's documentation came from a run. Reasoning from names produced
wrong claims more than once — including my own description of a state-file key as "legacy, never
read" when it was the live write target of a shadowed variable.

**How to apply:** when a claim needs a number, run it in the sandbox and paste the output. When the
user challenges a claim, go and check rather than defend. See [[sandbox-not-live-repos]].
