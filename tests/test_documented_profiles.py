"""The profile examples in the documentation are shapes the tool accepts. #161.

`README.md` documented `keys` as `{"owner/repo": "ZMBNI"}` long after it became a
list. The documented shape does not merely differ -- it **raises**, because
iterating a dict yields its keys as strings and every consumer does `k["key"]`
or `k.get("repo")`. A reader copying the first example in *Getting started* got
`AttributeError: 'str' object has no attribute 'get'` and no way to tell which
of the two was wrong.

**Documentation that is confidently wrong costs more than documentation that is
absent**, because the reader trusts it and blames themselves. So this asserts by
*running* rather than by reading: every JSON block in the README and the guide
that looks like a profile is parsed out and pushed through the tool's own
accessors. A future shape change fails here rather than rotting in prose.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ["README.md", "USER_GUIDE.md", "POLICY.md", "GOLD_MODEL.md"]

#: A block is a profile if it carries one of these. `keys` alone is too loose --
#: the export catalog talks about keys too.
MARKERS = ("keys", "project", "config_from", "sprint", "boards")


def profiles() -> list[tuple[str, int, dict]]:
    """Every fenced ```json block in the docs that parses as a profile."""
    found = []
    for name in DOCS:
        text = (ROOT / name).read_text()
        for match in re.finditer(r"```json\n(.*?)```", text, re.S):
            line = text[:match.start()].count("\n") + 1
            try:
                parsed = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue          # a fragment or an ellipsis; not a claim
            if isinstance(parsed, dict) and any(m in parsed for m in MARKERS):
                found.append((name, line, parsed))
    return found


def test_the_docs_contain_profile_examples_at_all():
    """If the extraction stops matching, every test below passes vacuously --
    the failure #158 was written about, one file over."""
    assert len(profiles()) >= 3


@pytest.mark.parametrize("name,line,profile",
                         profiles(), ids=lambda v: v if isinstance(v, str) else "")
class TestEveryDocumentedProfile:
    def test_the_keys_accessor_accepts_it(self, tool, name, line, profile):
        """`profile_keys` is where every read goes through, and where the
        documented mapping raised."""
        assert isinstance(tool.profile_keys(profile), list), f"{name}:{line}"

    def test_a_repository_can_be_looked_up_in_it(self, tool, name, line, profile):
        for entry in tool.profile_keys(profile):
            repo = entry.get("repo")
            if repo:
                assert tool.keys_for_repo(profile, repo), f"{name}:{line}"

    def test_a_key_resolves_back_to_its_repository(self, tool, name, line, profile):
        for entry in tool.profile_keys(profile):
            if entry.get("key") and entry.get("repo"):
                assert tool.repo_for_key(profile, entry["key"]) == entry["repo"]

    def test_the_title_prefix_is_legal(self, tool, name, line, profile):
        """An illegal value stops every command, so a documented one must not be."""
        assert tool.title_prefix_mode(profile) in tool.TITLE_PREFIX_MODES

    def test_the_sprint_settings_are_readable(self, tool, name, line, profile):
        settings = tool.sprint_settings(profile)
        assert isinstance(settings.get("cadence_days"), int), f"{name}:{line}"


class TestTheShapeThatUsedToCrash:
    def test_a_mapping_is_refused_not_crashed_on(self, tool):
        with pytest.raises(SystemExit) as exit_info:
            tool.profile_keys({"keys": {"owner/repo": "ZMBNI"}})
        assert "must be a list" in str(exit_info.value)

    def test_the_refusal_says_why_the_order_matters(self, tool):
        """A mapping cannot express the ordering the default depends on."""
        with pytest.raises(SystemExit) as exit_info:
            tool.profile_keys({"keys": {"owner/repo": "ZMBNI"}})
        assert "order is the default" in str(exit_info.value)

    def test_it_shows_the_shape_to_write_instead(self, tool):
        with pytest.raises(SystemExit) as exit_info:
            tool.profile_keys({"keys": {"owner/repo": "ZMBNI"}})
        assert '"keys": [' in str(exit_info.value)

    def test_the_list_form_still_works(self, tool):
        profile = {"keys": [{"key": "ZMBNI", "repo": "o/r"}]}
        assert tool.profile_keys(profile) == [{"key": "ZMBNI", "repo": "o/r"}]

    def test_an_absent_keys_is_empty_not_an_error(self, tool):
        """A profile need not list any: `project create` writes one later."""
        assert tool.profile_keys({}) == []


class TestTheReadmeSpecifically:
    @staticmethod
    def readme_profiles():
        return [p for name, _line, p in profiles() if name == "README.md"]

    def test_the_readme_has_a_profile_example(self):
        assert self.readme_profiles()

    def test_its_keys_are_a_list(self, tool):
        for profile in self.readme_profiles():
            assert isinstance(profile.get("keys", []), list)

    def test_it_records_the_project_owner(self, tool):
        """A number alone means "project N belonging to whoever typed this" --
        invisibly correct for one person and wrong for everyone else. The guide
        spends four paragraphs on it; the README's example omitted it."""
        for profile in self.readme_profiles():
            if "project" in profile and "number" in profile["project"]:
                assert profile["project"].get("owner"), "project.number without owner"
