---
name: github-iterations-destroy-assignments
description: Any write to a ProjectV2 iteration configuration clears every item's Sprint value, board-wide and retroactively
metadata:
  type: project
---

Measured on a live project on 2026-08-16: renaming **one unused future sprint** re-minted all six
iteration ids and unassigned four items staged across a completed, a current and a future sprint —
including a closed issue in the completed sprint. A pure append, every existing entry re-sent
byte-identical plus one new, does the same. That append is the routine fortnightly act.

`ProjectV2Iteration` — the input object the mutation accepts — carries `startDate`, `duration` and
`title` and no id, so the configuration is replaced wholesale and every reference dies.

**Why:** there is no safe write. The field cannot hold history.

**How to apply:** field for the present, labels for the past. `sprint:YYYY-MM-DD` on the issue is the
record; the field is re-derivable UI state. Never rename or re-date a sprint to "tidy up". See
[[labels-are-additive]] and the six workarounds in CLAUDE.md.
