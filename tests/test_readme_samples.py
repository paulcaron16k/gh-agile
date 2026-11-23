"""The README's sample output is what the commands print. #315.

The front page shows a sprint board, the backlog, the roadmap, a stand-up and an
initiative. Typed by hand, each would drift the first time a column moved, and a
front page showing output the tool no longer produces is worse than none. So
`scripts/readme_samples.py` renders them with the real commands against a
fictional Widgets project, faking only GitHub's answers, and this holds the
README to it.

When this fails after a change to a renderer: `python scripts/readme_samples.py
--write`, then read the diff -- it is the change a user will see.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def generator():
    spec = importlib.util.spec_from_file_location(
        "readme_samples", ROOT / "scripts" / "readme_samples.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rendered(generator):
    return generator.samples()


@pytest.fixture(scope="module")
def blocks(generator):
    return generator.readme_blocks((ROOT / "README.md").read_text())


def test_every_sample_is_in_the_readme(generator, blocks):
    assert set(blocks) == set(generator.SAMPLES)


@pytest.mark.parametrize("name", ["sprint-board", "backlog", "roadmap", "issue-status",
                                  "initiative-view"])
def test_the_readme_shows_what_the_command_prints(rendered, blocks, name):
    assert blocks[name] == rendered[name], (
        f"README.md's {name!r} sample is stale: python scripts/readme_samples.py --write")


def test_the_samples_are_not_empty(rendered):
    """A renderer that printed nothing would match an empty block."""
    for name, text in rendered.items():
        assert len(text.splitlines()) > 3, name


def test_rewriting_is_idempotent(generator, rendered):
    text = (ROOT / "README.md").read_text()
    assert generator.rewrite(text, rendered) == text


def test_an_empty_block_does_not_swallow_the_next(generator):
    """The first `--write` matched from an empty block to the next block's
    closing fence and deleted everything between them. A body may not contain
    a fence now."""
    text = ("<!-- sample: a -->\n```text\n```\n\nkept\n\n"
            "<!-- sample: b -->\n```text\nold\n```\n")
    assert generator.rewrite(text, {"a": "A", "b": "B"}) == (
        "<!-- sample: a -->\n```text\nA\n```\n\nkept\n\n"
        "<!-- sample: b -->\n```text\nB\n```\n")
