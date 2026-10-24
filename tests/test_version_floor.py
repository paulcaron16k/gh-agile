"""The three settings that must name the same release, and the date to look again.

CLAUDE.md states the rule -- *a floor no job tests is a promise nothing keeps* --
and until now nothing verified it. It was broken once and cost real time:
`target-version = py312` let UP017 rewrite `dt.timezone.utc` to `dt.UTC`, which
arrived in 3.11; `make lint` and the whole suite stayed green because both run in
the 3.12 venv; and the tool crashed on first use under the system 3.10. The
convention was written down afterwards and left unenforced, so the next
disagreement would have been found the same way.

Three places have to agree:

    gh-agile     RUNTIME_FLOOR = (3, 10)
    ruff.toml    target-version = "py310"
    ci.yml       matrix: '3.10' … '3.13'

and a fourth says so to a reader: the README's Python badge (#246), which is
static and so drifts unless something holds it.

**These parse the files as text, on purpose.** `tomllib` arrived in 3.11, there is
no YAML parser in the standard library, and this suite runs under the floor
interpreter in CI -- so a test *of* the floor may not use a parser that postdates
it. The constraint being checked, applied to the check.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import warnings

ROOT = pathlib.Path(__file__).resolve().parent.parent


def spell(version: tuple[int, int]) -> str:
    return ".".join(str(part) for part in version)


def ruff_target_version() -> tuple[int, int]:
    """`target-version = "py310"` -> `(3, 10)`.

    The `py<major><minor>` spelling packs the major into one character, which is
    true of every Python release there has ever been and is why this is safe to
    split positionally.
    """
    for line in (ROOT / "ruff.toml").read_text().splitlines():
        if line.strip().startswith("target-version"):
            value = line.split("=", 1)[1].strip().strip("\"'")
            digits = value.removeprefix("py")
            return int(digits[0]), int(digits[1:])
    raise AssertionError("ruff.toml declares no target-version")


def ci_matrix_versions() -> list[tuple[int, int]]:
    """The interpreter list from the CI matrix, in the order it declares them."""
    for line in (ROOT / ".github" / "workflows" / "ci.yml").read_text().splitlines():
        stripped = line.strip()
        # The other `python-version:` is the setup-python step, which reads the
        # matrix rather than declaring it.
        if stripped.startswith("python-version:") and "[" in stripped:
            inside = stripped[stripped.index("[") + 1:stripped.rindex("]")]
            out = []
            for part in inside.split(","):
                major, minor = part.strip().strip("\"'").split(".")
                out.append((int(major), int(minor)))
            return out
    raise AssertionError("ci.yml declares no python-version matrix")


class TestTheThreeAgree:
    def test_ruff_targets_the_floor(self, tool):
        """The one that broke. Raising `target-version` above the floor lets ruff
        rewrite code into syntax the floor cannot run, and every check stays
        green because they all run in the venv."""
        floor, target = tool.RUNTIME_FLOOR, ruff_target_version()
        assert target == floor, (
            f"ruff.toml target-version is py{target[0]}{target[1]} and "
            f"RUNTIME_FLOOR is {spell(floor)}; CI's lowest is "
            f"{spell(min(ci_matrix_versions()))}. All three must name one release."
        )

    def test_the_matrix_runs_the_floor(self, tool):
        """A floor no job tests is a promise nothing keeps."""
        floor, matrix = tool.RUNTIME_FLOOR, ci_matrix_versions()
        assert floor in matrix, (
            f"the CI matrix is {[spell(v) for v in matrix]} and does not include "
            f"RUNTIME_FLOOR {spell(floor)}; ruff.toml targets "
            f"py{ruff_target_version()[0]}{ruff_target_version()[1]}."
        )

    def test_the_floor_is_the_lowest_the_matrix_runs(self, tool):
        """Lower than the floor would test a promise nobody made; higher would
        leave the floor untested while claiming to support it."""
        floor, matrix = tool.RUNTIME_FLOOR, ci_matrix_versions()
        assert min(matrix) == floor, (
            f"CI's lowest is {spell(min(matrix))} and RUNTIME_FLOOR is "
            f"{spell(floor)}; ruff.toml targets "
            f"py{ruff_target_version()[0]}{ruff_target_version()[1]}."
        )

    def test_the_matrix_has_no_gaps(self):
        """`ci.yml` says every version the README claims, with no gaps -- the list
        skipped 3.11 once, for the reason that floor-and-newest felt like enough,
        which is the same reasoning that let a 3.11+ idiom through."""
        matrix = sorted(ci_matrix_versions())
        expected = [(matrix[0][0], minor)
                    for minor in range(matrix[0][1], matrix[-1][1] + 1)]
        assert matrix == expected, (
            f"the CI matrix {[spell(v) for v in matrix]} skips a release between "
            f"{spell(matrix[0])} and {spell(matrix[-1])}."
        )


def readme_badge_versions() -> list[tuple[int, int]]:
    """The versions the README's Python badge names: `python-3.10%20%7C%203.11...`."""
    for line in (ROOT / "README.md").read_text().splitlines():
        if line.startswith("[![Python]("):
            label = line.split("/badge/python-", 1)[1].rsplit("-", 1)[0]
            out = []
            for part in label.split("%20%7C%20"):
                major, minor = part.split(".")
                out.append((int(major), int(minor)))
            return out
    raise AssertionError("README.md carries no Python badge")


class TestTheBadgeSaysTheSame:
    """A static badge is a fourth copy of the matrix, and a copy nothing checks is
    the one that goes stale (#246)."""

    def test_the_badge_names_exactly_the_matrix(self):
        badge, matrix = readme_badge_versions(), ci_matrix_versions()
        assert badge == matrix, (
            f"the README's Python badge says {[spell(v) for v in badge]} and the CI "
            f"matrix runs {[spell(v) for v in matrix]}.")

    def test_its_lowest_is_the_floor(self, tool):
        assert min(readme_badge_versions()) == tool.RUNTIME_FLOOR


class TestWhenToLookAgain:
    def test_the_review_date_is_a_date(self, tool):
        """Hand-maintained, so it can rot into something unparseable."""
        assert dt.date.fromisoformat(tool.RUNTIME_FLOOR_REVIEW)

    def test_the_floor_is_not_yet_due_for_review(self, tool):
        """**Warns rather than fails.** A floor being worth another look is not a
        reason to break the build, and the date is deliberately the one the
        distributions move on rather than upstream end of life -- the comment
        beside `RUNTIME_FLOOR` settles that: EOL stops python.org patches and
        removes 3.10 from nobody's machine."""
        due = dt.date.fromisoformat(tool.RUNTIME_FLOOR_REVIEW)
        if tool.today_utc() >= due:
            warnings.warn(
                f"RUNTIME_FLOOR {spell(tool.RUNTIME_FLOOR)} was due for review on "
                f"{due}: the distributions carrying it have moved on. Raise it in "
                f"gh-agile, ruff.toml and the CI matrix together, and move "
                f"RUNTIME_FLOOR_REVIEW with it.",
                stacklevel=2,
            )
