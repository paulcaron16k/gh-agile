# gh-agile v0.7.0 — one profile for a project that spans repositories

**A supporting repository's `config_from` pointer now survives every command**
(AGILE-324). A project spanning repositories keeps its profile in the main one,
and the others carry only `{"config_from": "owner/main"}`. Every command that
wrote the profile wrote the main profile it had read back over that pointer,
leaving a copy that then drifted -- the thing the pointer exists to prevent.

## What changed behaviour

**Profile edits refuse in a supporting repository** and name the main one to run
them from: `key add`, `key delete`, `project edit`, `board create --save`, and
`init` with `--key`, `--title`, `--sprint-template` or `--title-prefix`. Each
refuses before it acts, so `board create --save` no longer makes a board the
profile then fails to record. **A script that ran one of these in a supporting
repository now exits 1**; run it in the main repository instead.

**A bare `gh agile init` in a supporting clone** installs the post-merge hook and
converges the project from the main profile, and leaves the pointer
byte-identical. If the main profile lacks a default `init` would record, it says
to run `init` there.

## Documentation

**The README says why a teammate's fresh clone needs only a bare `init`**, and
has a folded *Setting up a multi-repo project*: the main repository holds the
profile with a unique key per repository, the others a pointer (AGILE-325).

**`make ci-status` reads the CI workflow only** (AGILE-322), so a failed Publish
or API-drift run no longer reports `main` as red. Development tooling; nothing
installed changes.

## What changed spelling

Nothing.

## Security review

Done before the tag, per `docs/releasing.md` §3a, against the wheel and sdist
built from `main` at c42fefa; the release commit adds only this note and
`release-next.md`, neither of which ships. **All eight pass.**

| # | Check | Result |
|---|---|---|
| 1 | No credential is handled | No read of `GH_TOKEN`, `GITHUB_TOKEN`, an `Authorization` header or a password in `gh-agile`; `gh` owns the token |
| 2 | No credential-shaped literal ships | None in the wheel or the sdist (`ghp_`, `github_pat_`, `gho_`, `AKIA`, private keys) |
| 3 | Nothing confidential ships | No internal names or hostnames; no email address; the only hosts are github.com, img.shields.io, jqlang.org and apache.org, and the only GitHub owners named are `paulcaron16k` and the fictional `acme` and `o`. The new multi-repo fold uses the fictional Widgets |
| 4 | No shell | No `shell=True`; every subprocess is an argument list |
| 5 | Destructive defaults unchanged | Live Makefile targets default to the sandbox; the sandbox, guard and iteration-write tests pass (`make test`, 2582 passed) |
| 6 | `install` writes only its own link | `tests/test_install.py` passes: refuses a checkout, a clone and somebody else's link |
| 7 | The wheel is the script | `gh-agile` and its metadata, nothing else |
| 8 | Published without a secret | `tests/test_publish_workflow.py` passes: OIDC only, `id-token` on the publish jobs, actions pinned to commits, PyPI from tags only |

**Not rehearsed on TestPyPI**: trusted publishing is registered on PyPI only, as
for v0.6.0.
