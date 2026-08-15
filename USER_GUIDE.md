# gh-agile user guide

Setting up a board, and the commands for a real day's work — including the one
that takes an epic from created to closed. Written so a person can follow it and
an agent can run it on a developer's behalf.

The *rules* are in [POLICY.md](POLICY.md); the *data mapping* is in
[GOLD_MODEL.md](GOLD_MODEL.md). This is the *how*.

---

## 1. The project profile

One JSON file describes the project to the tool. It is **visible, checked in,
and reviewed like any other config**:

```
.github/agile.json
```

A dotfile would be the conventional choice for tooling and the wrong one here.
`ls` does not show it, so someone cloning the repo never learns the convention
exists — and a convention nobody discovers is not a convention. `.github/` is
already where people look for repository metadata, and the file sits beside the
workflows that read it.

### Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `keys` | object | yes | Maps `owner/repo` to a short uppercase key. Produces `ZMBNI-1817` in the export's `issue_key`, the Gold model's human-readable key |
| `project.name` | string | no | Human-readable project name. Written to the project's `shortDescription` by `gh agile key --name` |
| `project.key` | string | no | The key for the main repository; a convenience copy of the matching `keys` entry |
| `config_from` | string | no | `owner/repo` of the repository holding the real profile. **Mutually exclusive with everything else** — a file with this property carries nothing else |

```json
{
  "keys": {
    "paulcaron16k/Zamboni": "ZMBNI",
    "paulcaron16k/gh-agile": "AGILE"
  },
  "project": {
    "name": "Zamboni Iceberg table maintainer",
    "key": "ZMBNI"
  }
}
```

**The key belongs to the repository, not the project.** GitHub's issue numbers
are a per-repository sequence and a project may span repositories, so a
project-level key would make `KEY-12` ambiguous the moment a second repository
joined the board.

### Where to check it in when a project spans repositories

**Put the real profile in the main repository** — the one whose name the project
carries, where most issues are filed. Supporting repositories carry a pointer
and nothing else:

```json
{ "config_from": "paulcaron16k/Zamboni" }
```

Resolved through the API, so it works for private repositories on the token `gh`
already holds, and cannot rot into a dead raw-content URL. One hop only: a
pointer to a pointer is a loop waiting to happen, so the tool ignores
`config_from` in a profile it has already followed.

Resolution order, first match wins: `.github/agile.json` → `agile.json` →
`.gh_agile.json`.

### What is *not* checked in

`.gh_agile_export.json` — the incremental-export watermark. That is state a
machine rewrites, not configuration a person writes, and deleting it to force a
full export must not lose your keys. Add it to `.gitignore`; it is deliberately
a separate file for that reason.

### Should the JSON go in the README?

**No.** Document the *properties* — as the table above does — and link to the
file. Pasting the authoritative copy into a second place is how the two drift,
and the drift is silent. A two-line example in a README is fine; the file is the
source.

---

## 2. Creating a project

```bash
# The board itself.
gh project create --owner @me --title "Zamboni Iceberg table maintainer"

# Its fields and labels. Idempotent -- run it again after editing the spec.
gh agile --project 5 setup --repo paulcaron16k/Zamboni

# The key, and the human-readable name on the project.
gh agile --project 5 key --repo paulcaron16k/Zamboni --key ZMBNI \
         --name "Zamboni Iceberg table maintainer"
```

`setup` creates five fields. `Status` already exists with three options and
gains the two the policy declares:

| Field | Type | Values |
|---|---|---|
| `Status` | single-select | `Todo`, `In Progress`, `Blocked`, `In Review`, `Done` |
| `Story Points` | number | — |
| `Priority` | single-select | `lowest`, `low`, `medium`, `high`, `highest` |
| `FR` | text | requirement id, free text |
| `Sprint` | iteration | created separately, below |

Epics, parents and sub-issue progress need no custom field: GitHub provides
them.

## 3. Creating sprints

```bash
gh agile --project 5 sprint create --start 2026-08-17 --weeks 2
gh agile --project 5 sprint create --weeks 2      # abuts the previous one
gh agile --project 5 sprint list
```
```
  Sprint 1     2026-08-17 .. 2026-08-30  (current)
  Sprint 2     2026-08-31 .. 2026-09-13
```

Without `--start`, a new sprint begins the day after the last one ends, because
overlapping sprints make "the current sprint" ambiguous.

## 4. Creating an epic and a story

```bash
gh agile --project 5 epic "Snapshot expiry and orphan removal" \
  --repo paulcaron16k/Zamboni \
  --intent "Nothing reclaims storage; 120 files on disk and 1 live after five days." \
  --acceptance "expire and remove-orphans delete only unreferenced files, and abort otherwise."

gh agile --project 5 story "Compute the reachable file set" \
  --repo paulcaron16k/Zamboni --epic 31 \
  --points 5 --priority highest \
  --intent "Both operations depend on it; an omission here deletes live data." \
  --acceptance "Every referenced file across all six metadata categories is returned."
```

The story is created, attached to its epic as a sub-issue, added to the board and
given its fields **in one call**. That matters: an issue created now and attached
to its epic later is an orphan in every roll-up run in between, and nothing
complains.

---

## 5. The workflow, end to end

A story from creation to closed, then its epic. Every command here is
non-interactive, so an agent can run the same sequence.

**1 — the epic exists**

```bash
gh agile --project 5 epic "Snapshot expiry and orphan removal" --repo OWNER/REPO \
  --intent "..." --acceptance "..."
#   epic #31: Snapshot expiry and orphan removal
```

**2 — a story under it**

```bash
gh agile --project 5 story "Compute the reachable file set" --repo OWNER/REPO \
  --epic 31 --points 5 --priority highest --intent "..." --acceptance "..."
#   story #32 under epic #31
```

**3 — into the sprint**

```bash
gh agile --project 5 set --issue 32 --field Sprint --value @current
```

**4 — start work**

```bash
gh agile --project 5 move 32 --status "In Progress"
```

No evidence required to start. Requiring it here would be ceremony; requiring it
to finish is the point.

**5 — fixed, with evidence**

```bash
gh agile --project 5 move 32 --status Done --evidence-file evidence.md --close
```

where `evidence.md` is:

```markdown
## Evidence
Reference set validated read-only against the demo table: 421 referenced,
426 on disk, 0 referenced-but-absent. Each of the six categories asserted
non-empty, so a silently dropped category fails the test.
```

Three ways to supply it, and one that only works for a human:

| Form | Use |
|---|---|
| `--evidence-file notes.md` | An agent, CI, or anyone who wrote it down first |
| `--evidence "text"` | A one-liner |
| `--evidence-file -` or `--evidence -` | A pipe: `git log -1 \| gh agile move …` |
| *(nothing, at a terminal)* | Prompts section by section |

**The body is validated, not merely templated.** `Done` requires `## Evidence`,
and the transition is refused if the section is missing, empty, or still `_TBD_`:

```
the body is not complete:
  - ## Evidence is still _TBD_
```

`--close` closes the issue as completed; `--not-planned` closes it as not
planned, so work that stopped for another reason stays distinguishable in the
export.

**6 — close the epic**

```bash
gh agile --project 5 move 31 --status Done --evidence-file epic-evidence.md --close
```

Close it when its stories are closed. `gh agile validate` reports an epic marked
`Done` with open children.

**7 — check and export**

```bash
gh agile --project 5 validate
gh agile --project 5 export --csv --out-dir exports/
```

---

## 6. For an agent working on a developer's behalf

Everything above is non-interactive when given explicit input, which is the
property that makes it drivable. A working sequence:

```bash
PROJECT=5; REPO=OWNER/REPO

# Pick up the work, and say so on the board.
gh agile --project $PROJECT move "$ISSUE" --status "In Progress"

# ... make the change, run the tests ...

# Record what was actually established, from a file the agent wrote.
cat > /tmp/evidence.md <<'EOF'
## Evidence
491 tests pass on the branch. The regression reproduces on 0.12.0rc1 and not
after the fix, verified by running the 25-line case against both.
EOF

gh agile --project $PROJECT move "$ISSUE" --status Done \
         --evidence-file /tmp/evidence.md --close
```

Two rules worth encoding in whatever drives it:

- **Never pass `_TBD_` to get past the validator.** The check exists because a
  closed issue saying "done" has thrown away the reasoning. An agent that
  defeats it has removed the only durable record of why the change was right.
- **Evidence is what was measured**, not what was intended — that is
  `## Intent`, written at creation. If nothing was measured, the honest evidence
  says so.

---

## 7. Command reference

Every command lists its own fields with type, obligation and description:

```bash
gh agile setup --help
gh agile story --help
gh agile move --help
```

| Command | Does |
|---|---|
| `setup` | Create fields and labels; converge on re-run |
| `key` | Record a repository's key; list what is recorded |
| `sprint list` / `sprint create` | Show or append iterations |
| `epic` / `story` | Create work items with their parent, labels and fields |
| `set` | Set one field on an item already on the board |
| `move` | Change status, with the evidence that status requires |
| `validate` | Check the conventions a machine can check |
| `export` | Items joined to status history, full or incremental |
| `self-test` | Stand up a scratch project, exercise everything, tear it down |
