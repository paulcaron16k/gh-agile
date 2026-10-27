"""`validate --json`, for a scheduled job or CI to read. AGILE-284.

POLICY.md §7 puts `validate` in a scheduled workflow, and its exit status is the
signal. Its findings were prose only, so a job that wanted to post them or count
them over time had to scrape the text. `--json` gives the same findings as data,
and changes nothing about the exit status.
"""

from __future__ import annotations

import argparse
import json

import pytest


def row(number, *, kind="story", title=None, state="OPEN", status="Todo",
        epic=None, sub_total=0, sub_done=0):
    return {
        "number": number, "issue_key": f"A-{number}", "title": title or f"issue {number}",
        "repository": "o/r", "state": state,
        "state_reason": "COMPLETED" if state == "CLOSED" else "",
        # An epic is in no sprint; giving it one is a finding of its own.
        "labels": f"type:{kind};key:A" + ("" if kind == "epic" else ";sprint:2026-08-31"),
        "field_status": status, "field_sprint": "" if kind == "epic" else "S2",
        "epic_number": epic, "parent_key": "", "parent_type": "",
        "assignees": "dev", "sub_issues_total": sub_total, "sub_issues_done": sub_done,
        "started_at": "", "done_at": "",
    }


@pytest.fixture
def validate(monkeypatch, tool, capsys):
    def go(*rows, json_fields=None, jq=None, template=None, sprints=None):
        monkeypatch.setattr(tool, "rows", lambda *a, **k: list(rows))
        monkeypatch.setattr(tool, "iterations", lambda *a, **k: (
            sprints or [{"title": "S2", "startDate": "2026-08-31", "duration": 14}], []))
        args = argparse.Namespace(owner="o", project=1, _config={}, id=None,
                                  json=json_fields, jq=jq, template=template)
        code = tool.cmd_validate(args)
        return code, capsys.readouterr().out
    return go


def as_json(validate, *rows, **kwargs):
    code, out = validate(*rows, **kwargs)
    return code, json.loads(out)


class TestTheRecord:
    def test_a_clean_board(self, validate):
        code, data = as_json(validate, row(1, epic=5),
                             json_fields="ok,item_count,problem_count,note_count,"
                                         "problems,notes")
        assert code == 0
        assert data == {"ok": True, "item_count": 1, "problem_count": 0, "note_count": 0,
                        "problems": [], "notes": []}

    def test_a_problem_names_its_rule_count_and_issue(self, validate):
        code, data = as_json(validate, row(7, kind="epic", title="An epic"),
                             json_fields="problems,ok")
        assert code == 1 and data["ok"] is False
        (finding,) = data["problems"]
        assert finding == {"rule": "epic has no stories", "count": 1, "issues": [
            {"key": "A-7", "number": 7, "repository": "o/r", "title": "An epic",
             "detail": None}]}

    def test_the_detail_after_the_issue_is_kept_apart(self, validate):
        _code, data = as_json(validate, row(8, state="CLOSED", status="In Review"),
                              json_fields="problems")
        issue = next(f for f in data["problems"]
                     if f["rule"].startswith("closed but status"))["issues"][0]
        assert issue["number"] == 8 and issue["detail"] == "'In Review'"

    def test_a_title_holding_a_colon_is_not_split_on_it(self, validate):
        """The issue is found by its prefix, not by parsing the line."""
        title = "Export: the catalog: every column"
        _code, data = as_json(validate, row(9, kind="epic", title=title),
                              json_fields="problems")
        issue = data["problems"][0]["issues"][0]
        assert issue["title"] == title and issue["detail"] is None

    def test_notes_are_records_too(self, validate):
        code, data = as_json(validate, row(3), json_fields="notes,note_count,ok")
        assert code == 0 and data["ok"] is True and data["note_count"] == 1
        assert data["notes"][0]["rule"] == "story has no epic"
        assert data["notes"][0]["issues"][0]["key"] == "A-3"

    def test_a_board_finding_has_only_detail(self, validate):
        """Overlapping sprints are about the series, not an issue."""
        sprints = [{"title": "S1", "startDate": "2026-08-31", "duration": 14},
                   {"title": "S2", "startDate": "2026-09-07", "duration": 14}]
        _code, data = as_json(validate, row(1, epic=5), json_fields="problems",
                              sprints=sprints)
        (issue,) = next(f for f in data["problems"]
                        if f["rule"].startswith("sprints overlap"))["issues"]
        assert issue["number"] is None and "overlaps" in issue["detail"]


class TestTheExitStatusIsUnchanged:
    @pytest.mark.parametrize("rows,code", [((row(1, epic=5),), 0),
                                           ((row(7, kind="epic"),), 1)])
    def test_same_as_text(self, validate, rows, code):
        assert validate(*rows)[0] == code
        assert validate(*rows, json_fields="ok")[0] == code

    def test_notes_alone_still_exit_zero(self, validate):
        assert validate(row(3), json_fields="ok")[0] == 0


def test_template_reads_it(validate):
    _code, out = validate(row(7, kind="epic"),
                          template="{{range .problems}}{{.rule}}={{.count}}{{end}}")
    assert out == "epic has no stories=1"


def test_no_text_is_printed_with_json(validate):
    _code, out = validate(row(7, kind="epic"), json_fields="ok")
    assert "problem(s) across" not in out and json.loads(out) == {"ok": False}


def test_help_lists_the_fields(tool, capsys):
    with pytest.raises(SystemExit):
        tool.build_parser().parse_args(["validate", "--help"])
    text = capsys.readouterr().out
    fields = text.split("JSON FIELDS\n", 1)[1].split("\n\n", 1)[0]
    for field in tool.VALIDATE_FIELDS:
        assert field in fields
