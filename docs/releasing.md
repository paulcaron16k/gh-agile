# Releasing gh-agile

How a build is tagged and published to PyPI (#316). The policy a consumer reads
-- the extension tracks `main`, the package is a tagged release -- is in
REFERENCE.md under *Versions, and what installing gets you*. This file is the
procedure, for whoever cuts the tag.

**The tag is the publication.** Pushing `vX.Y.Z` runs
`.github/workflows/publish.yml`, which builds the wheel from that tag and uploads
it. PyPI never re-issues a version number, so a mistake is fixed by the next
version, never by replacing this one. Everything below happens *before* the tag.

## 1. Once per project: trusted publishing

No token is stored anywhere. PyPI exchanges the workflow's OIDC identity for a
short-lived upload token, and is told in advance which workflow to trust.

1. **GitHub environments.** Repository → Settings → Environments: create `pypi`
   and `testpypi`. Give `pypi` a required reviewer (yourself), so a pushed tag
   waits for one click before anything uploads -- a second gate that costs
   nothing.
2. **PyPI pending publisher.** pypi.org → Account → Publishing → *Add a pending
   publisher*: project `gh-agile`, owner `paulcaron16k`, repository `gh-agile`,
   workflow `publish.yml`, environment `pypi`. "Pending" because the project does
   not exist on PyPI until the first upload creates it.
3. **The same on TestPyPI** (test.pypi.org, a separate account), with environment
   `testpypi`.

## 2. Rehearse on TestPyPI

```bash
make dist                                   # build and check locally first
gh workflow run publish.yml --ref main      # builds main, uploads to TestPyPI only
```

A run from a commit the tag does not point at builds a dev version
(`0.5.1.dev12`), which TestPyPI accepts and PyPI would too -- which is why the
`pypi` job runs on tags only. Then, in a clean environment:

```bash
pipx install --index-url https://test.pypi.org/simple/ gh-agile
gh-agile --version                          # "(package)", and the dev version
```

and read the page at <https://test.pypi.org/p/gh-agile>: the README renders, the
contents links jump, the folded sections open, the samples are monospaced.

## 3. Before the tag

### 3a. Security review -- first, and written down

Every item is here because a release can get it wrong. **If one fails, the
release stops.** Record the outcome in the release note: a review with no written
result is indistinguishable from one that was skipped.

1. **No credential is handled.** The tool never reads, stores or passes a token;
   `gh` owns it. `grep -n 'GH_TOKEN\|GITHUB_TOKEN\|Authorization\|password' gh-agile`
   finds nothing that reads one.
2. **No credential-shaped literal ships.** Over the built files:
   `unzip -p dist/*.whl | grep -E 'ghp_|github_pat_|gho_|AKIA|BEGIN .*PRIVATE KEY'`
   and the same over the sdist find nothing.
3. **Nothing confidential ships.** The repository is public and so is the
   package: no internal hostnames, no other organisation's names, issues or data
   in the script, the README or the examples. The README's sample project is the
   fictional *Widgets*, by design.
4. **No shell.** Every subprocess is an argument list: `grep -n 'shell=True'
   gh-agile` finds nothing, so no issue title, label or branch name is ever
   interpreted by a shell.
5. **Destructive defaults unchanged.** The live Makefile targets still default to
   the sandbox and refuse anything else without `ALLOW_LIVE=1`; `teardown` still
   deletes only the titles the live targets create; every iteration write still
   sends the ids and checks them after. `make test` covers all three.
6. **`install` writes only its own link.** It creates `gh-agile-package/gh-agile`
   under the data directory and asks `gh` to install that; it refuses a checkout,
   an `agile` installed from a repository, and somebody else's local link.
7. **The wheel is the script.** `make dist` lists it: `gh-agile` and its
   metadata, nothing else. The workflow refuses anything else too.
8. **The workflow still publishes without a secret.** `tests/test_publish_workflow.py`
   holds it: no `secrets.`, `id-token: write` on the publish jobs only, every
   action pinned to a commit, PyPI from tags only.

### 3b. The rest

- `main` is green: `make ci-status`.
- `docs/release-next.md` becomes `docs/release-vX.Y.Z.md`, with the security
  review's result in it, and a fresh `release-next.md` is started.
- The version is a counter: minor for anything a user notices, patch for fixes.
  The deprecation policy in REFERENCE.md says what a rename needs first.

## 4. Tag and publish

```bash
git tag -a vX.Y.Z -F docs/release-vX.Y.Z.md
git push origin vX.Y.Z
```

The workflow builds, checks the wheel holds only the script, checks the wheel's
version *is* the tag, then waits on the `pypi` environment's reviewer. Approve it
in the run. Then, in a clean environment: `pipx install gh-agile`,
`gh-agile --version`, `gh-agile install`, `gh agile --version`.
