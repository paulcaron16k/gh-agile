"""`--json`, `--jq` and `--template` on every list, view and status. AGILE-219.

`gh` scripts reach for `--json fields -q expr` on every list and view;
`gh agile issue list --json number,title` failed with "unrecognized arguments",
and each command had its own `--format` choice. This runs all three flags
through every read command, on stubbed reads, so a command added without them
-- or whose JSON grows a field its help does not list -- fails here.
"""

from __future__ import annotations

import json
import shutil

import pytest

SPRINT = {"id": "IT1", "title": "0006 W42-2026", "startDate": "2026-10-12", "duration": 14}
VIEW = {"id": "V1", "number": 3, "name": "Backlog", "layout": "TABLE_LAYOUT",
        "filter": "no:sprint"}


def board_item(number=7, labels=("type:story", "key:AGILE")):
    return {
        "isArchived": False,
        "fieldValues": {"nodes": [{"name": "Todo", "field": {"name": "Status"}}]},
        "content": {
            "__typename": "Issue", "number": number, "state": "OPEN",
            "title": f"AGILE-{number} work", "url": f"https://github.com/o/r/issues/{number}",
            "repository": {"nameWithOwner": "o/r"},
            "labels": {"nodes": [{"name": n} for n in labels]},
            "assignees": {"nodes": [{"login": "me"}]},
            "author": {"login": "me"}, "milestone": None,
        },
    }


ISSUE_NODE = {
    "number": 7, "title": "AGILE-7 work", "url": "https://github.com/o/r/issues/7",
    "state": "OPEN", "stateReason": None, "body": "## Intent\nx\n",
    "labels": {"nodes": [{"name": "type:story"}]},
    "assignees": {"nodes": []}, "repository": {"nameWithOwner": "o/r"},
    "projectItems": {"nodes": []}, "subIssues": {"nodes": []},
}

#: Every read command, and how to point it at something: `(argv, list?)`.
COMMANDS = [
    (["issue", "list"], True), (["epic", "list"], True), (["story", "list"], True),
    (["initiative", "list"], True), (["task", "list"], True),
    (["issue", "status"], False), (["issue", "view", "7"], False),
    (["story", "view", "7"], False), (["board", "list"], True),
    (["board", "view", "Backlog"], False), (["sprint", "list"], True),
    (["sprint", "view"], False), (["key", "list"], True), (["project", "view"], False),
]


@pytest.fixture
def run(tool, monkeypatch, capsys):
    monkeypatch.setattr(tool, "iterations", lambda *a: ([SPRINT], []))
    monkeypatch.setattr(tool, "fetch_items", lambda *a: ("t", [
        board_item(7), board_item(8, labels=("type:epic", "key:AGILE")),
        board_item(9, labels=("type:initiative", "key:AGILE"))]))
    monkeypatch.setattr(tool, "views_of", lambda *a: [VIEW])
    monkeypatch.setattr(tool, "current_repo", lambda: None)
    monkeypatch.setattr(tool, "caller_login", lambda: "me")
    monkeypatch.setattr(tool, "stdout_is_terminal", lambda: False)
    monkeypatch.setattr(tool, "parse_issue_ref", lambda ref, cfg, repo: ("o/r", 7))
    monkeypatch.setattr(tool, "issue_checks", lambda *a: None)

    def graphql(query, **variables):
        if "search(" in query:
            return {"data": {"search": {"nodes": [{
                "number": 9, "state": "OPEN", "title": "a task", "url": "u",
                "repository": {"nameWithOwner": "o/r"}, "parent": None}]}}}
        return {"data": {"repository": {"issue": ISSUE_NODE}}}
    monkeypatch.setattr(tool, "graphql", graphql)

    def go(argv, *flags):
        args = tool.build_parser().parse_args([*argv, *flags])
        args.owner, args.project = "o", 4
        args.repo = getattr(args, "repo", None) or "o/r"
        args._config = {"keys": [{"key": "AGILE", "repo": "o/r", "name": "A"}],
                        "project": {"name": "Board", "issue_title_prefix": "key"}}
        code = args.func(args)
        return code, capsys.readouterr()
    return go


def fields_of(tool, argv):
    parser = tool.build_parser()
    for word in argv:
        if word.isdigit() or word[:1].isupper():
            break
        parser = {n: p for n, _t, p in parser.subcommands()}[word]
    return parser.json_fields


@pytest.mark.parametrize("argv,is_list", COMMANDS, ids=lambda v: " ".join(v)
                         if isinstance(v, list) else "")
class TestEveryReadCommand:
    def test_json_alone_lists_the_fields(self, tool, run, argv, is_list):
        code, out = run(argv, "--json")
        assert code == 1
        assert out.err.split("\n")[1:-1] == [f"  {f}" for f in fields_of(tool, argv)]

    def test_json_with_a_field_selects_it(self, tool, run, argv, is_list):
        field = fields_of(tool, argv)[0]
        code, out = run(argv, "--json", field)
        data = json.loads(out.out)
        assert code == 0
        records = data if is_list else [data]
        assert isinstance(data, list) == is_list
        assert records and all(list(r) == [field] for r in records)

    def test_json_with_no_field_named_is_every_field(self, tool, run, argv, is_list):
        """`--jq` implies `--json` with every field."""
        code, out = run(argv, "-t", "{{len .}}")
        assert code == 0

    def test_template(self, tool, run, argv, is_list):
        field = fields_of(tool, argv)[0]
        template = ("{{range .}}[{{." + field + "}}]{{end}}" if is_list
                    else "[{{." + field + "}}]")
        code, out = run(argv, "--json", field, "-t", template)
        assert code == 0 and out.out.startswith("[")

    @pytest.mark.skipif(shutil.which("jq") is None, reason="needs jq")
    def test_jq(self, tool, run, argv, is_list):
        code, out = run(argv, "-q", "type")
        assert code == 0
        assert out.out.strip() == ("array" if is_list else "object")

    def test_an_unknown_field_is_refused_listing_them(self, tool, run, argv, is_list):
        with pytest.raises(SystemExit) as caught:
            run(argv, "--json", "nope")
        assert "unknown JSON field: 'nope'" in str(caught.value)

    def test_the_help_lists_the_fields(self, tool, argv, is_list):
        parser = tool.build_parser()
        for word in argv:
            if word.isdigit() or word[:1].isupper():
                break
            parser = {n: p for n, _t, p in parser.subcommands()}[word]
        text = parser.format_help()
        assert "JSON FIELDS" in text
        assert all(f in text for f in parser.json_fields)


class TestTheFieldListsMatchTheBuilders:
    def test_a_list_row(self, tool):
        assert tuple(tool.board_row(board_item(), {})) == tool.ROW_FIELDS

    def test_a_view(self, tool):
        assert (*tool.view_facts(ISSUE_NODE, 4, {}), "checks") == tool.VIEW_FIELDS

    def test_every_json_field_is_present_in_full_output(self, tool, run):
        for argv, is_list in COMMANDS:
            _code, out = run(argv, "--json", ",".join(fields_of(tool, argv)))
            data = json.loads(out.out)
            record = data[0] if is_list else data
            assert set(record) == set(fields_of(tool, argv)), argv


class TestJq:
    def test_without_jq_it_refuses_naming_the_install(self, tool, run, monkeypatch):
        monkeypatch.setattr(tool.shutil, "which", lambda name: None)
        with pytest.raises(SystemExit) as caught:
            run(["key", "list"], "-q", ".")
        assert "jq" in str(caught.value) and "jqlang.org" in str(caught.value)

    @pytest.mark.skipif(shutil.which("jq") is None, reason="needs jq")
    def test_strings_come_out_raw_as_gh_prints_them(self, tool, run):
        _code, out = run(["key", "list"], "--json", "key", "-q", ".[].key")
        assert out.out == "AGILE\n"

    def test_jq_and_template_together_are_refused(self, tool, run):
        with pytest.raises(SystemExit):
            run(["key", "list"], "-q", ".", "-t", "x")


class TestTemplate:
    DATA = [{"key": "A-1", "status": "Todo", "labels": ["bug", "ui"], "n": 3.0},
            {"key": "A-22", "status": "In Progress", "labels": [], "n": None}]

    def render(self, tool, template, data=None):
        return tool.render_template(template, self.DATA if data is None else data)

    def test_fields_and_range(self, tool):
        assert self.render(tool, "{{range .}}{{.key}};{{end}}") == "A-1;A-22;"

    def test_tablerow_aligns_columns(self, tool):
        out = self.render(tool, "{{range .}}{{tablerow .key .status}}{{end}}")
        assert out == "A-1   Todo\nA-22  In Progress\n"

    def test_if_else(self, tool):
        out = self.render(tool, "{{range .}}{{if .labels}}L{{else}}-{{end}}{{end}}")
        assert out == "L-"

    def test_join_and_pipes(self, tool):
        assert self.render(tool, '{{range .}}{{.labels | join ","}}|{{end}}') == "bug,ui||"

    def test_len_pluck_printf_truncate(self, tool):
        assert self.render(tool, "{{len .}}") == "2"
        assert self.render(tool, '{{pluck "key" . | join " "}}') == "A-1 A-22"
        assert self.render(tool, '{{range .}}{{printf "%s=%v " .key .n}}{{end}}') == \
            "A-1=3 A-22=<no value> "
        assert self.render(tool, '{{range .}}{{truncate 4 .status}} {{end}}') == "Todo I... "

    def test_trim_markers(self, tool):
        assert self.render(tool, "{{range .}}  {{- .key -}}  ,{{end}}") == "A-1,A-22,"

    @pytest.mark.parametrize("bad", ["{{range .}}x", "{{end}}", "{{template \"x\"}}",
                                     "{{.key", "{{$x := 1}}"])
    def test_outside_the_subset_is_refused_naming_it(self, tool, bad):
        with pytest.raises(SystemExit) as caught:
            self.render(tool, bad)
        assert "Supported:" in str(caught.value)


class TestFormatJson:
    def test_it_is_retired_with_a_hint(self, tool):
        assert "--json" in tool.retired_spelling(["issue", "view", "12", "--format", "json"])

    def test_export_keeps_it(self, tool):
        assert tool.retired_spelling(["export", "--format", "json"]) is None

    def test_jsonl_stays(self, tool):
        assert tool.retired_spelling(["story", "list", "--format", "jsonl"]) is None

    def test_format_and_json_together_are_refused(self, tool, run):
        with pytest.raises(SystemExit):
            run(["story", "list"], "--format", "jsonl", "--json", "key")
