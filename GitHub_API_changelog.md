# GitHub API changelog

Changes to GitHub's GraphQL schema, found by `make api-drift`, which compares the
live schema against `GitHub_API_spec.json`. Each entry is when the drift was
seen, not when GitHub made the change. *Touches what gh-agile uses* lists the
changes to a type, or a root query or mutation, that the extension names; a
change marked *not in GitHub's changelog* was not announced. *GitHub's changelog
since* quotes GitHub's own dated record (`github/docs`, `changelog.json`), and
*Announced removals touching gh-agile* lists what GitHub has said it will remove
from what the extension uses (`upcoming-changes.json`), overdue and due within
90 days first.

## 2026-10-27T21:40:05Z

Baseline snapshot: 1839 types, 5 directives.
