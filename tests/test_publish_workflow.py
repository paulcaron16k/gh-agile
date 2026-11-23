"""The publish workflow keeps the properties its header promises. #316.

`.github/workflows/publish.yml` is the one workflow that holds a credential able
to publish: an OIDC token PyPI exchanges for an upload token. What it must keep
true is short, and each item is cheap to check and expensive to lose -- so it is
checked here, as text, since the standard library has no YAML parser.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "publish.yml").read_text()


def jobs() -> dict[str, str]:
    """Each job's text, by name: the two-space-indented keys under `jobs:`."""
    body = WORKFLOW.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([a-z]+):\n", body, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_the_jobs_are_these():
    assert set(jobs()) == {"build", "testpypi", "pypi"}


def test_no_stored_token():
    """Trusted publishing: no `password:`, no secret named anywhere."""
    assert "secrets." not in WORKFLOW
    assert "password:" not in WORKFLOW


def test_the_workflow_default_is_read_only():
    top = WORKFLOW.split("\njobs:\n", 1)[0]
    assert "permissions:\n  contents: read" in top


@pytest.mark.parametrize("job", ["testpypi", "pypi"])
def test_only_the_publish_jobs_get_an_identity_token(job):
    assert "id-token: write" in jobs()[job]


def test_the_build_gets_no_identity_token():
    """The build runs a build backend from PyPI; it is not handed a credential."""
    assert "id-token" not in jobs()["build"]


def test_every_action_is_pinned_to_a_commit():
    uses = re.findall(r"uses:\s*(\S+)", WORKFLOW)
    assert uses
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), ref


def test_pypi_publishes_only_from_a_tag():
    assert "if: startsWith(github.ref, 'refs/tags/v')" in jobs()["pypi"]
    assert "repository-url" not in jobs()["pypi"]


def test_a_manual_run_goes_to_testpypi_only():
    test = jobs()["testpypi"]
    assert "if: github.event_name == 'workflow_dispatch'" in test
    assert "https://test.pypi.org/legacy/" in test


def test_a_tag_build_must_be_the_tags_version():
    assert "The version is the tag" in jobs()["build"]


def test_tags_are_fetched_for_the_version():
    """hatch-vcs reads the nearest tag; a shallow clone has none and would
    build `0.1.dev1`."""
    assert "fetch-depth: 0" in jobs()["build"]
