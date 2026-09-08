"""`project title-prefix --backfill`: renaming the issues that predate the setting.

The setting changes what *new* issues are called, which leaves a board adopting
it permanently mixed -- everything before it bare, everything after carrying
`KEY-<n>`. Measured on the Zamboni board the day it was taken up: 18 of 19
issues predated it.

The hand-written version is a shell loop over `gh issue list` calling
`gh issue edit --title`, and it is short enough to write twice and subtle enough
to get wrong once. Skip on "this one already has a prefix" and a re-run
double-prefixes, because the prefix it found may belong to a different issue. So
the title is **stripped and rebuilt** rather than tested, and the result depends
on the issue rather than on how many times this has run.

The stripping is the dangerous half. It must remove exactly what
`prefixed_title` writes and nothing that merely resembles it, because a title
this destroys is not recoverable from anywhere.
"""

from __future__ import annotations

import pytest


class TestStripTitlePrefix:
    @pytest.mark.parametrize("title,want", [
        ("ZMBNI-34 Retention policy", "Retention policy"),
        ("ZMBNI-34 Epic: Retention policy", "Retention policy"),
        ("ZMBNI-34 Story: Retention policy", "Retention policy"),
        ("ZMBNI-34 Bug: Retention policy", "Retention policy"),
        ("ZMBNI-7 x", "x"),
    ])
    def test_it_removes_what_prefixed_title_writes(self, tool, title, want):
        assert tool.strip_title_prefix(title, "ZMBNI") == want

    @pytest.mark.parametrize("title", [
        "Retention policy",                       # never prefixed
        "RFC-2119 keywords in requirement levels",  # another project's convention
        "CVE-2021-4034 write-up",                 # not even the right shape
        "ZMBNI-adjacent work",                    # no digits after the hyphen
        "ZMBNIX-34 something",                    # a different key that starts the same
        "OTHER-34 something",                     # somebody else's key
        "ZMBNI-34",                               # a prefix and nothing else: not a prefix
    ])
    def test_it_leaves_everything_else_alone(self, tool, title):
        """A backfill that guesses at what looks like a prefix quietly destroys
        titles nobody can recover."""
        assert tool.strip_title_prefix(title, "ZMBNI") == title

    def test_a_type_word_that_is_not_a_type_stays(self, tool):
        assert tool.strip_title_prefix("ZMBNI-34 Note: read this", "ZMBNI") == \
            "Note: read this"

    def test_another_issues_id_is_stripped_too(self, tool):
        """Wrong either way, and stripping is what lets the sweep replace it.
        Leaving it would produce `ZMBNI-34 ZMBNI-12 ...` on the next run."""
        assert tool.strip_title_prefix("ZMBNI-12 Retention policy", "ZMBNI") == \
            "Retention policy"

    def test_it_inverts_prefixed_title(self, tool):
        for mode in ("key", "key+type"):
            built = tool.prefixed_title(mode, "ZMBNI", 34, "story", "Retention policy")
            assert tool.strip_title_prefix(built, "ZMBNI") == "Retention policy"


def row(number=34, title="Retention policy", labels="type:story;key:ZMBNI",
        repo="o/r"):
    return {"number": number, "title": title, "labels": labels, "repository": repo}


@pytest.fixture
def backfill(monkeypatch, tool, capsys):
    """`backfill_titles` with the board stubbed, capturing the renames."""
    edits = []

    def fake_gh(args, **kwargs):
        if args[:2] == ["issue", "edit"]:
            edits.append((args[2], args[args.index("--title") + 1]))
        return ""

    monkeypatch.setattr(tool, "gh", fake_gh)

    def go(*rows, mode="key", dry_run=False, config=None):
        import argparse
        monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
        args = argparse.Namespace(owner="o", project=1, dry_run=dry_run)
        edits.clear()
        tool.backfill_titles(args, config or {"keys": [{"key": "ZMBNI", "repo": "o/r"}]}, mode)
        return capsys.readouterr().out

    go.edits = edits
    return go


class TestTheSweep:
    def test_a_bare_title_is_prefixed(self, tool, backfill):
        backfill(row())
        assert backfill.edits == [("34", "ZMBNI-34 Retention policy")]

    def test_key_plus_type_uses_the_type_label(self, tool, backfill):
        backfill(row(), mode="key+type")
        assert backfill.edits == [("34", "ZMBNI-34 Story: Retention policy")]

    def test_an_untyped_issue_falls_back_to_the_key_form(self, tool, backfill):
        """A machine may not infer a type. Better a correct short prefix than an
        invented one -- the same rule `sync --adopt` follows."""
        backfill(row(labels="key:ZMBNI"), mode="key+type")
        assert backfill.edits == [("34", "ZMBNI-34 Retention policy")]

    def test_off_strips_the_prefix(self, tool, backfill):
        backfill(row(title="ZMBNI-34 Epic: Retention policy"), mode="off")
        assert backfill.edits == [("34", "Retention policy")]

    def test_off_leaves_a_title_that_only_looks_prefixed(self, tool, backfill):
        out = backfill(row(title="RFC-2119 keywords"), mode="off")
        assert backfill.edits == []
        assert "already correct 1" in out


class TestItIsIdempotent:
    def test_a_second_run_changes_nothing(self, tool, backfill):
        out = backfill(row(title="ZMBNI-34 Retention policy"), mode="key")
        assert backfill.edits == []
        assert "already correct 1" in out

    def test_and_so_does_a_second_run_of_key_plus_type(self, tool, backfill):
        backfill(row(title="ZMBNI-34 Story: Retention policy"), mode="key+type")
        assert backfill.edits == []

    def test_another_issues_id_is_corrected_not_stacked(self, tool, backfill):
        """The trap the hand-written shell loop fell into: skipping on "looks
        prefixed" leaves the wrong id, and re-running stacks a second one."""
        backfill(row(number=34, title="ZMBNI-12 Retention policy"))
        assert backfill.edits == [("34", "ZMBNI-34 Retention policy")]

    def test_running_it_twice_over_is_stable(self, tool, backfill):
        backfill(row())
        once = backfill.edits[0][1]
        backfill(row(title=once))
        assert backfill.edits == []


class TestKeys:
    def test_the_issues_own_key_label_wins_over_the_repo_default(self, tool, backfill):
        """A mono-repo carries several keys against one repository, and the label
        is which one this issue answers to."""
        config = {"keys": [{"key": "SPARK", "repo": "o/r"}, {"key": "TRINO", "repo": "o/r"}]}
        backfill(row(labels="type:story;key:TRINO"), config=config)
        assert backfill.edits == [("34", "TRINO-34 Retention policy")]

    def test_the_repo_default_is_used_when_there_is_no_label(self, tool, backfill):
        config = {"keys": [{"key": "SPARK", "repo": "o/r"}, {"key": "TRINO", "repo": "o/r"}]}
        backfill(row(labels="type:story"), config=config)
        assert backfill.edits == [("34", "SPARK-34 Retention policy")]

    def test_an_issue_with_no_key_at_all_is_reported_and_left(self, tool, backfill):
        """Without a key, `strip_title_prefix` cannot tell this tool's prefix from
        the issue's own words, so there is nothing safe to do."""
        out = backfill(row(labels="type:story", repo="o/other"), config={"keys": []})
        assert backfill.edits == []
        assert "no key applies" in out


class TestDryRun:
    def test_it_writes_nothing(self, tool, backfill):
        out = backfill(row(), dry_run=True)
        assert backfill.edits == []
        assert "would rename o/r#34: ZMBNI-34 Retention policy" in out

    def test_and_counts_the_same_way(self, tool, backfill):
        out = backfill(row(), row(number=35, title="ZMBNI-35 Already"), dry_run=True)
        assert "would rename 1, already correct 1, across 2 item(s)" in out
