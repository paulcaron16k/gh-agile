---
name: labels-are-additive
description: gh issue edit --add-label appends without read-modify-write; titles replace and iteration configs replace wholesale
metadata:
  type: reference
---

Three write models in one API, verified on the live board:

- **Labels** — additive. `--add-label` maps to `addLabelsToLabelable`; other labels untouched.
  Batchable: `gh issue edit 9 10 11 --add-label x`.
- **Title / body** — whole-value replace, scoped to that one issue.
- **Iteration configuration** — replace-wholesale *and* re-mints every id, destroying references
  board-wide. See [[github-iterations-destroy-assignments]].

**How to apply:** labels are the only primitive with no read-modify-write and no collateral damage,
which is why `type:`, `key:` and `sprint:` all live on labels rather than in project fields.
