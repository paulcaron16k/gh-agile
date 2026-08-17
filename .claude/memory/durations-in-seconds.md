---
name: durations-in-seconds
description: Every emitted duration is an integer count of seconds and no column name carries a unit suffix
metadata:
  type: feedback
---

The user's instruction: "All time measurements - all - to be in seconds, no exceptions, never a
`_days` or `_hours` suffix in metric name".

**Why:** in days, cycle times reported `0.0` and a median of `0.0` was published as if it were a
measurement. The same work reads 165, 181, 17, 76, 561 seconds. A unit in the name also rots the
moment the unit changes, while every consumer keeps dividing by the old one.

**How to apply:** `seconds_between`, never a `days_between`. Presentation is the consumer's problem.
`cadence_days` survives as the profile's hand-authored spelling (a person writes 14) — the one
exception, and the user may yet want it renamed. The Gold catalog's `*_hours` columns live outside
this repo and still need changing.
