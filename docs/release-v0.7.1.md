# gh-agile v0.7.1 — the PyPI page explains what a board shows

**Documentation only.** The `gh-agile` script is byte-identical to v0.7.0; this
tag republishes the README, which is the package's page on PyPI.

## Documentation

**A board shows only the issues added to its project** (AGILE-331). The README's
*See the work* now starts with `gh agile sync`, and says why it is needed: a Jira
board is a query over every issue, a GitHub Project is a collection, so an issue
filed in the web UI, with `gh issue create`, or in another repository of the
profile is on no board until something adds it.

**`docs/releasing.md`: the `pypi` environment has no required reviewer, on
purpose** (AGILE-329). With one developer the reviewer is whoever pushed the tag,
and a token of theirs can approve through the API, so the gate stops only a stray
tag push, which a yank recovers from. What guards a release instead is named.
Not in the package.

## What changed spelling

Nothing.

## What changed behaviour

Nothing.

## Security review

Done before the tag, per `docs/releasing.md` §3a, against the wheel and sdist
built from `main` at 3fdcd62; the release commit adds only this note and
`release-next.md`, neither of which ships. **All eight pass.**

| # | Check | Result |
|---|---|---|
| 1 | No credential is handled | No read of `GH_TOKEN`, `GITHUB_TOKEN`, an `Authorization` header or a password in `gh-agile`; `gh` owns the token |
| 2 | No credential-shaped literal ships | None in the wheel or the sdist (`ghp_`, `github_pat_`, `gho_`, `AKIA`, private keys) |
| 3 | Nothing confidential ships | No internal names or hostnames; no email address; the only hosts are github.com, img.shields.io, jqlang.org and apache.org, and the only GitHub owners named are `paulcaron16k` and the fictional `acme` and `o` |
| 4 | No shell | No `shell=True`; every subprocess is an argument list |
| 5 | Destructive defaults unchanged | The script is unchanged since v0.7.0; the sandbox, guard and iteration-write tests pass |
| 6 | `install` writes only its own link | `tests/test_install.py` passes: refuses a checkout, a clone and somebody else's link |
| 7 | The wheel is the script | `gh-agile` and its metadata, nothing else |
| 8 | Published without a secret | `tests/test_publish_workflow.py` passes: OIDC only, `id-token` on the publish jobs, actions pinned to commits, PyPI from tags only |

**Not rehearsed on TestPyPI**: trusted publishing is registered on PyPI only.
