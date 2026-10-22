"""`create` and `issue edit` take `gh issue`'s flags. AGILE-207, under #200.

Every work item is an issue, and `gh issue create` and `gh issue edit` already
define what a `gh` user will type. Before this, `epic`/`story`/`task` took
`--intent` and `--acceptance` and nothing else, and `set` took `--field` with
`--value` or `--number` -- a `gh` user met an unknown flag on nearly every
reflex, and `story create --points 5` and `set --field "Story Points" --number 5`
were two spellings of one write.

Offline: every `gh` call and field write is captured.
"""

from __future__ import annotations

import json

import pytest

CREATES = [["initiative", "create"], ["epic", "create"],
           ["story", "create", "--epic", "none"], ["task", "create", "--story", "9"]]


def parse(tool, *argv):
    return tool.build_parser().parse_args(list(argv))


class TestEveryCreateTakesGhIssueCreatesFlags:
    @pytest.mark.parametrize("verb", CREATES, ids=lambda v: v[0])
    def test_the_flags_parse_with_gh_short_forms(self, tool, verb):
        args = parse(tool, *verb, "-t", "T", "-b", "words", "-a", "@me", "-a", "x",
                     "-l", "bug", "-m", "v1")
        assert (args.title, args.body, args.assignee, args.label, args.milestone) == \
            ("T", "words", ["@me", "x"], ["bug"], "v1")

    @pytest.mark.parametrize("verb", CREATES, ids=lambda v: v[0])
    def test_body_file_parses(self, tool, verb):
        assert parse(tool, *verb, "-t", "T", "-F", "-").body_file == "-"

    @pytest.mark.parametrize("flag,why", [("-e", "does not prompt"),
                                          ("--editor", "does not prompt"),
                                          ("-w", "never sees")])
    @pytest.mark.parametrize("verb", CREATES, ids=lambda v: v[0])
    def test_editor_and_web_are_refused_saying_why(self, tool, capsys, verb, flag, why):
        with pytest.raises(SystemExit):
            parse(tool, *verb, "-t", "T", flag)
        assert why in capsys.readouterr().err

    @pytest.mark.parametrize("verb", CREATES, ids=lambda v: v[0])
    def test_the_title_is_still_required(self, tool, verb):
        with pytest.raises(SystemExit):
            parse(tool, *verb, "-b", "words")


class TestTheBody:
    def body(self, tool, *flags):
        return tool.create_body(parse(tool, "epic", "create", "-t", "T", *flags))

    def test_sections_from_a_file_match_the_section_flags(self, tool, tmp_path):
        path = tmp_path / "body.md"
        path.write_text("## Intent\nWhy it matters.\n\n## Acceptance\nIt works.\n")
        assert self.body(tool, "-F", str(path)) == self.body(
            tool, "--intent", "Why it matters.", "--acceptance", "It works.")

    def test_an_unheaded_body_is_the_intent(self, tool):
        assert self.body(tool, "-b", "Just words.") == self.body(tool, "--intent",
                                                                  "Just words.")

    def test_stdin_is_read_for_a_dash(self, tool, monkeypatch):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO("## Acceptance\nDone when.\n"))
        body = self.body(tool, "-F", "-")
        assert "## Acceptance\nDone when." in body
        assert "## Intent\n_TBD_" in body

    def test_an_absent_section_is_the_placeholder(self, tool):
        body = self.body(tool, "-b", "## Intent\nWhy.")
        assert "## Acceptance\n_TBD_" in body

    def test_every_body_keeps_its_evidence_heading(self, tool):
        assert "## Evidence" in self.body(tool, "-b", "words")

    def test_another_heading_is_kept_after_evidence(self, tool):
        body = self.body(tool, "-b", "## Intent\nWhy.\n\n## Notes\nSee #3.")
        assert body.index("## Evidence") < body.index("## Notes\nSee #3.")

    def test_a_section_given_twice_is_refused(self, tool):
        with pytest.raises(SystemExit) as caught:
            self.body(tool, "-b", "## Intent\nOne.", "--intent", "Two.")
        assert "--intent" in str(caught.value)

    def test_body_and_body_file_together_are_refused(self, tool):
        with pytest.raises(SystemExit) as caught:
            self.body(tool, "-b", "x", "-F", "y")
        assert "pass one" in str(caught.value)


class TestTheToolsOwnLabelsAreRefused:
    @pytest.mark.parametrize("label", ["type:epic", "key:X", "sprint:2026-10-12",
                                       "initiative:big", "Type:Story"])
    def test_refused(self, tool, label):
        with pytest.raises(SystemExit) as caught:
            tool.extra_labels([label])
        assert label in str(caught.value)

    def test_another_label_passes(self, tool):
        assert tool.extra_labels(["bug", "needs-design"]) == ["bug", "needs-design"]

    def test_refused_before_the_issue_exists(self, tool, monkeypatch):
        """An issue number is never reused, so a refusal afterwards costs one."""
        created = []
        monkeypatch.setattr(tool, "require_sprint_config", lambda *a, **k: None)
        monkeypatch.setattr(tool, "require_key_for_prefix", lambda *a, **k: None)
        monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
        monkeypatch.setattr(tool, "create_issue", lambda *a, **k: created.append(a))
        args = parse(tool, "epic", "create", "-t", "T", "-l", "type:story")
        args._config, args.repo, args.key = {}, "o/r", "AGILE"
        with pytest.raises(SystemExit):
            tool.cmd_epic(args)
        assert created == []


class TestCreatePassesAssigneeAndMilestoneToGh:
    def test_they_reach_gh_issue_create(self, tool, monkeypatch):
        seen = []

        def fake_gh(argv, **kwargs):
            seen.append(argv)
            if argv[:2] == ["issue", "create"]:
                return "https://github.com/o/r/issues/40\n"
            return json.dumps({"id": "I_40"})
        monkeypatch.setattr(tool, "gh", fake_gh)
        monkeypatch.setattr(tool, "require_sprint_config", lambda *a, **k: None)
        monkeypatch.setattr(tool, "require_key_for_prefix", lambda *a, **k: None)
        monkeypatch.setattr(tool, "ensure_labels", lambda *a, **k: None)
        monkeypatch.setattr(tool, "add_to_project", lambda *a, **k: "PVTI")
        monkeypatch.setattr(tool, "set_field", lambda *a, **k: None)
        args = parse(tool, "epic", "create", "-t", "T", "-a", "@me", "-m", "v1",
                     "-l", "bug")
        args._config, args.repo, args.key = {}, "o/r", "AGILE"
        args.owner, args.project = "o", 1
        tool.cmd_epic(args)
        create = next(c for c in seen if c[:2] == ["issue", "create"])
        assert create[create.index("--assignee") + 1] == "@me"
        assert create[create.index("--milestone") + 1] == "v1"
        assert "bug" in create and "type:epic" in create


@pytest.fixture
def edit(monkeypatch, tool, capsys, edit_args):
    """Drive `issue edit`, capturing `gh` and the field writes."""
    def go(*argv, labels=None, config=None):
        labels = labels or {}
        calls = {"gh": [], "fields": []}
        monkeypatch.setattr(tool, "parse_issue_ref",
                            lambda ref, cfg, repo: ("o/r", int(ref.rsplit("-", 1)[-1])))
        monkeypatch.setattr(tool, "issue_labels",
                            lambda repo, n: labels.get(n, ["type:story", "key:AGILE"]))
        monkeypatch.setattr(tool, "board_item_for",
                            lambda login, project, repo, n: {"id": f"PVTI_{n}"})
        monkeypatch.setattr(tool, "gh", lambda a, **k: calls["gh"].append(a) or "")
        monkeypatch.setattr(tool, "set_field",
                            lambda login, project, item, name, v:
                            calls["fields"].append((item, name, v)))
        go.calls = calls
        tool.cmd_edit(edit_args(*argv, config=config))
        return calls, capsys.readouterr().out
    return go


KEYED = {"project": {"issue_title_prefix": "key"}}
TYPED = {"project": {"issue_title_prefix": "key+type"}}


class TestEditKeepsThePrefix:
    def test_the_key_is_rebuilt(self, edit):
        calls, _out = edit("12", "-t", "New words", config=KEYED)
        assert calls["gh"] == [["issue", "edit", "12", "--repo", "o/r",
                                "--title", "AGILE-12 New words"]]

    def test_the_type_too_when_the_profile_says_so(self, edit):
        calls, _out = edit("12", "-t", "New words", config=TYPED)
        assert "AGILE-12 Story: New words" in calls["gh"][0]

    def test_a_typed_prefix_is_not_doubled(self, edit):
        calls, _out = edit("12", "-t", "AGILE-12 New words", config=KEYED)
        assert "AGILE-12 New words" in calls["gh"][0]

    def test_with_no_prefix_the_words_are_the_title(self, edit):
        calls, _out = edit("12", "-t", "New words")
        assert "New words" in calls["gh"][0]

    def test_no_key_label_is_refused_rather_than_unprefixed(self, edit):
        with pytest.raises(SystemExit) as caught:
            edit("12", "-t", "New words", labels={12: ["type:story"]}, config=KEYED)
        assert "no key: label" in str(caught.value)
        assert edit.calls["gh"] == []


class TestEditPassesGhIssueEditsFlagsThrough:
    def test_labels_assignees_milestone_and_body(self, edit):
        calls, _out = edit("12", "--add-label", "bug", "--remove-label", "wontfix",
                           "--add-assignee", "@me", "--remove-assignee", "x",
                           "-m", "v1", "-b", "new body")
        argv = calls["gh"][0]
        for flag, value in [("--add-label", "bug"), ("--remove-label", "wontfix"),
                            ("--add-assignee", "@me"), ("--remove-assignee", "x"),
                            ("--milestone", "v1"), ("--body", "new body")]:
            assert argv[argv.index(flag) + 1] == value

    def test_remove_milestone_takes_no_value(self, edit):
        calls, _out = edit("12", "--remove-milestone")
        assert calls["gh"][0][-1] == "--remove-milestone"

    def test_a_body_file_is_read_once_for_every_issue(self, edit, tmp_path):
        path = tmp_path / "b.md"
        path.write_text("## Intent\nx\n")
        calls, _out = edit("12", "13", "-F", str(path))
        assert [c[c.index("--body") + 1] for c in calls["gh"]] == ["## Intent\nx\n"] * 2

    def test_a_field_only_edit_calls_no_gh_issue_edit(self, edit):
        calls, _out = edit("12", "--points", "3")
        assert calls["gh"] == []


class TestEditSeveralIssues:
    def test_points_on_two_issues_edits_both(self, edit):
        calls, _out = edit("12", "13", "--points", "3")
        assert calls["fields"] == [("PVTI_12", "Story Points", 3.0),
                                   ("PVTI_13", "Story Points", 3.0)]

    def test_one_refusal_writes_to_none_of_them(self, edit):
        """A task carries no estimate, and the story before it is not half-edited."""
        with pytest.raises(SystemExit):
            edit("12", "13", "--points", "3", labels={13: ["type:task", "key:AGILE"]})
        assert edit.calls["fields"] == [] and edit.calls["gh"] == []

    def test_keyed_references_mix_with_numbers(self, edit):
        calls, _out = edit("AGILE-12", "13", "--priority", "High")
        assert [f[0] for f in calls["fields"]] == ["PVTI_12", "PVTI_13"]


class TestPointsAreOneWrite:
    def test_create_and_edit_parse_the_same_value(self, tool):
        created = parse(tool, "story", "create", "-t", "T", "--epic", "none",
                        "--points", "5")
        edited = parse(tool, "issue", "edit", "12", "--points", "5")
        assert created.points == edited.points == 5.0

    def test_number_is_gone(self, tool):
        with pytest.raises(SystemExit):
            parse(tool, "issue", "edit", "12", "--field", "Story Points", "--number", "3")

    def test_a_value_is_written_as_the_fields_type_says(self, tool, monkeypatch):
        """`--value 3` on a NUMBER field goes out as `--number 3`, not as text."""
        seen = []
        monkeypatch.setattr(tool, "fields_of", lambda *a: {
            "Story Points": {"id": "F", "data_type": "NUMBER"}})
        monkeypatch.setattr(tool, "project_id", lambda *a: "P")
        monkeypatch.setattr(tool, "gh", lambda a, **k: seen.append(a))
        tool.set_field("o", 1, "I", "Story Points", "3")
        tool.set_field("o", 1, "I", "Story Points", 3.0)
        assert [c[-2:] for c in seen] == [["--number", "3"], ["--number", "3"]]

    def test_a_non_number_is_refused_naming_the_field(self, tool, monkeypatch):
        monkeypatch.setattr(tool, "fields_of", lambda *a: {
            "Story Points": {"id": "F", "data_type": "NUMBER"}})
        monkeypatch.setattr(tool, "project_id", lambda *a: "P")
        with pytest.raises(SystemExit) as caught:
            tool.set_field("o", 1, "I", "Story Points", "lots")
        assert "Story Points" in str(caught.value)


class TestEditRefuses:
    def test_nothing_to_change(self, edit):
        with pytest.raises(SystemExit) as caught:
            edit("12")
        assert "nothing to change" in str(caught.value)

    def test_a_field_with_no_value(self, edit):
        with pytest.raises(SystemExit):
            edit("12", "--field", "FR")

    def test_status_names_move(self, edit):
        with pytest.raises(SystemExit) as caught:
            edit("12", "--field", "Status", "--value", "Done")
        assert "issue move" in str(caught.value)

    def test_there_is_no_status_flag(self, tool):
        with pytest.raises(SystemExit):
            parse(tool, "issue", "edit", "12", "--status", "Done")


class TestEditAbsorbsPlan:
    def test_start_and_for_on_an_epic(self, edit, monkeypatch, tool):
        monkeypatch.setattr(tool, "item_date", lambda *a, **k: None)
        calls, out = edit("12", "--start", "2026-11-02", "--for", "6w",
                          labels={12: ["type:epic", "key:AGILE"]})
        assert calls["fields"] == [("PVTI_12", "Start date", "2026-11-02"),
                                   ("PVTI_12", "Target date", "2026-12-13")]
        assert "(6w from 2026-11-02)" in out

    def test_a_story_is_refused_as_plan_refused_it(self, edit):
        with pytest.raises(SystemExit) as caught:
            edit("12", "--start", "2026-11-02", "--for", "6w")
        assert "not an epic or an initiative" in str(caught.value)
        assert edit.calls["fields"] == []

    def test_plan_fails_at_argument_parsing(self, tool):
        with pytest.raises(SystemExit):
            parse(tool, "plan", "12", "--start", "2026-11-02")
