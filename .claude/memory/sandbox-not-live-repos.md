---
name: sandbox-not-live-repos
description: Live-path testing goes in paulcaron16k/agile-test, never gh-agile or Zamboni
metadata:
  type: feedback
---

The user asked for a sandbox after live testing damaged real repos: a `key:TEST` label on all 26
gh-agile issues, ~13 throwaway issues created and deleted leaving permanent holes in the number
sequence, 11 scratch projects, and two export files deleted by `rm -rf`.

**Why:** gh-agile is near alpha with issue tracking load-bearing, and Zamboni is heading for
production. Neither is a test fixture. The user's words: "issues need to be treated as such not as
test fixtures".

**How to apply:** offline tests → agile-test → gh-agile → Zamboni, in that order. `~/checkout/prj_mgmt/agile-test`
is the sandbox. Most work needs no live repo at all: 123 offline tests cover the pure logic.
