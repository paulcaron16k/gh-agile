#!/usr/bin/env python3
"""The README's sample output, produced by the real commands from a fixed project.

The README shows what `board view`, `issue status` and `initiative view` print.
Typed by hand, those blocks drift the first time a column moves, and nothing
notices: a front page showing output the tool no longer produces is worse than
showing none. So they are rendered here, by the commands themselves, against a
fictional *Widgets* project -- only GitHub's answers are faked, at the functions
that ask it, and everything from argument parsing to the last column is the code
a user runs.

    python scripts/readme_samples.py            # print every sample
    python scripts/readme_samples.py --write    # rewrite README.md's blocks in place
    python scripts/readme_samples.py --check    # exit 1 if README.md is out of date

A README block is the fenced block that follows a `<!-- sample: NAME -->` marker.
`tests/test_readme_samples.py` runs `--check`'s comparison offline, so a change
to a renderer that moves the README's output fails until `--write` is run.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.machinery
import importlib.util
import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

OWNER, NUMBER, REPO, KEY = "acme", 7, "acme/widgets", "WIDG"
ME = "alice"
TODAY = dt.date(2026, 11, 25)

PROFILE = {
    "project": {"number": NUMBER, "owner": OWNER, "key": KEY, "name": "Widgets"},
    "keys": [{"key": KEY, "name": "Widgets", "repo": REPO}],
    "boards": [{"name": "Sprint board", "type": "scrum"},
               {"name": "Backlog", "type": "backlog"},
               {"name": "Roadmap", "type": "roadmap"}],
    "sprint": {"template": "2-week", "cadence_days": 14, "start_day": "monday",
               "ahead": 1, "autocreate": True,
               "name_template": "{n:04d} W{iso_week}-{year}"},
}

#: Two weeks each. `iterations` hands back the active ones -- current first,
#: then the future -- and the completed ones separately, as GitHub does.
CURRENT = {"id": "it5", "title": "0005 W48-2026", "startDate": "2026-11-23", "duration": 14}
NEXT = {"id": "it6", "title": "0006 W50-2026", "startDate": "2026-12-07", "duration": 14}
PREVIOUS = {"id": "it4", "title": "0004 W46-2026", "startDate": "2026-11-09", "duration": 14}

VIEWS = [
    {"number": 1, "name": "Sprint board", "layout": "BOARD_LAYOUT", "filter": "sprint:@current"},
    {"number": 2, "name": "Backlog", "layout": "TABLE_LAYOUT", "filter": "no:sprint -status:Done"},
    {"number": 3, "name": "Roadmap", "layout": "ROADMAP_LAYOUT", "filter": "label:type:epic"},
]

#: The worked example: one initiative, two epics, their stories, and a bug.
#: (number, type, title, status, sprint, points, priority, assignee, parent)
WORK = [
    (40, "initiative", "Offline sync", "In Progress", None, None, "high", None, None),
    (41, "epic", "Conflict resolution", "In Progress", None, None, "high", None, 40),
    (42, "epic", "Local cache", "Todo", None, None, "medium", None, 40),
    (43, "story", "Detect concurrent edits", "Done", PREVIOUS, 3, "high", "alice", 41),
    (44, "story", "Keep both versions on conflict", "In Review", CURRENT, 5, "high", "bob", 41),
    (45, "story", "Show a conflict banner", "In Progress", CURRENT, 2, "medium", "alice", 41),
    (46, "story", "Merge edits that do not overlap", "Todo", CURRENT, 3, "medium", None, 41),
    (47, "story", "Version-stamp every record", "Done", CURRENT, 1, "medium", "bob", 41),
    (48, "story", "Cache records on the device", "Todo", None, 5, "medium", None, 42),
    (49, "story", "Evict the cache by age", "Todo", None, 2, "low", None, 42),
    (50, "bug", "Edits made offline are lost on reconnect", "In Progress", CURRENT, None,
     "highest", "alice", 41),
]

BODIES = {
    40: ("## Intent\nWidgets must work without a connection and reconcile when it\n"
         "returns, without losing an edit made on either side.\n\n"
         "## Acceptance\nAn edit made offline on two devices survives reconnecting\n"
         "both, and a conflict is shown rather than resolved silently.\n"),
}


def load_tool():
    spec = importlib.util.spec_from_loader(
        "gh_agile", importlib.machinery.SourceFileLoader("gh_agile", str(ROOT / "gh-agile")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def labels_of(number, kind, sprint):
    labels = [f"type:{kind}", f"key:{KEY}", "initiative:offline-sync"]
    if sprint:
        labels.append(f"sprint:{sprint['startDate']}")
    return labels


def by_number():
    return {row[0]: row for row in WORK}


def parent_node(number):
    if number is None:
        return None
    _n, kind, title, *_rest = by_number()[number]
    return {"number": number, "title": title, "repository": {"nameWithOwner": REPO},
            "labels": {"nodes": [{"name": f"type:{kind}"}]}}


def children_of(number):
    return [row for row in WORK if row[8] == number]


def board_item(row):
    """A `fetch_items` node."""
    number, kind, title, status, sprint, points, priority, who, parent = row
    fields = [{"__typename": "ProjectV2ItemFieldSingleSelectValue", "name": status,
               "field": {"name": "Status"}},
              {"__typename": "ProjectV2ItemFieldSingleSelectValue", "name": priority,
               "field": {"name": "Priority"}}]
    if sprint:
        fields.append({"__typename": "ProjectV2ItemFieldIterationValue",
                       "title": sprint["title"], "startDate": sprint["startDate"],
                       "duration": sprint["duration"], "field": {"name": "Sprint"}})
    if points is not None:
        fields.append({"__typename": "ProjectV2ItemFieldNumberValue", "number": points,
                       "field": {"name": "Story Points"}})
    kids = children_of(number)
    return {
        "id": f"PVTI_{number}", "isArchived": False, "fieldValues": {"nodes": fields},
        "content": {
            "__typename": "Issue", "id": f"I_{number}", "number": number, "title": title,
            "url": f"https://github.com/{REPO}/issues/{number}",
            "state": "CLOSED" if status == "Done" else "OPEN",
            "repository": {"nameWithOwner": REPO},
            "labels": {"nodes": [{"name": n} for n in labels_of(number, kind, sprint)]},
            "assignees": {"nodes": [{"login": who}] if who else []},
            "parent": parent_node(parent),
            "subIssuesSummary": {"total": len(kids),
                                 "completed": sum(k[3] == "Done" for k in kids)},
            "createdAt": "2026-11-02T09:00:00Z", "updatedAt": "2026-11-24T16:00:00Z",
            "closedAt": "2026-11-24T16:00:00Z" if status == "Done" else None,
        },
    }


def view_node(number):
    """An issue as `ISSUE_VIEW_QUERY` returns it."""
    _n, kind, title, status, sprint, points, priority, who, parent = by_number()[number]
    kids = children_of(number)
    return {
        "number": number, "title": title, "url": f"https://github.com/{REPO}/issues/{number}",
        "state": "OPEN", "stateReason": None, "body": BODIES.get(number, ""),
        "repository": {"nameWithOwner": REPO},
        "labels": {"nodes": [{"name": n} for n in labels_of(number, kind, sprint)]},
        "assignees": {"nodes": [{"login": who}] if who else []},
        "parent": parent_node(parent),
        "subIssuesSummary": {"total": len(kids),
                             "completed": sum(k[3] == "Done" for k in kids)},
        "subIssues": {"nodes": [
            {"number": k[0], "title": k[2], "state": "CLOSED" if k[3] == "Done" else "OPEN",
             "repository": {"nameWithOwner": REPO},
             "labels": {"nodes": [{"name": f"type:{k[1]}"}]},
             "projectItems": {"nodes": [{"project": {"number": NUMBER},
                                         "status": {"name": k[3]},
                                         "points": None}]}}
            for k in kids]},
        "projectItems": {"nodes": [{"project": {"number": NUMBER},
                                    "status": {"name": status},
                                    "sprint": None, "points": None,
                                    "priority": {"name": priority},
                                    "start": {"date": "2026-11-09"},
                                    "target": {"date": "2026-12-18"}}]},
    }


def offline(tool):
    """Answer every question the commands ask GitHub from the fixture above.

    Anything not answered here raises, so a renderer that starts asking for
    something new fails loudly instead of printing a sample built on nothing.
    """
    items = [board_item(row) for row in WORK]

    def graphql(query, **variables):
        if query is tool.ISSUE_VIEW_QUERY:
            return {"data": {"repository": {"issue": view_node(variables["number"])}}}
        raise RuntimeError(f"readme_samples: unanswered GraphQL query:\n{query[:200]}")

    def gh(argv, *_a, **_k):
        if argv[:2] == ["issue", "list"] and "initiative:offline-sync" in " ".join(argv):
            return json.dumps([{"number": 40}])
        raise RuntimeError(f"readme_samples: unanswered gh call: {argv}")

    tool.graphql = graphql
    tool.gh = gh
    tool.read_config = lambda *_a, **_k: json.loads(json.dumps(PROFILE))
    tool.current_repo = lambda: REPO
    tool.caller_login = lambda: ME
    tool.today_utc = lambda: TODAY
    tool.views_of = lambda _login, _number: VIEWS
    tool.iterations = lambda _login, _number: ([CURRENT, NEXT], [PREVIOUS])
    tool.fetch_items = lambda _login, _number: ("Widgets", items)
    tool.stdout_is_terminal = lambda: True
    tool.display_width = lambda stream=None: tool.BOARD_WIDTH
    # `validate`'s project-settings advice asks the API which workflows are on;
    # the sample is about the issue, not the project's settings.
    if hasattr(tool, "project_workflows"):
        tool.project_workflows = lambda *_a, **_k: None
    return tool


#: The samples, by marker name, and the command line each one runs.
SAMPLES = {
    "sprint-board": ["board", "view", "sprint"],
    "backlog": ["board", "view", "backlog"],
    "roadmap": ["board", "view", "roadmap"],
    "issue-status": ["issue", "status"],
    "initiative-view": ["initiative", "view", "offline-sync"],
}


def run(tool, argv):
    args = tool.build_parser().parse_args(argv)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        tool.apply_defaults(args)
        status = args.func(args)
    if status:
        raise RuntimeError(f"readme_samples: {' '.join(argv)} exited {status}")
    # A block in markdown has no use for trailing blank lines or trailing spaces.
    return "\n".join(line.rstrip() for line in out.getvalue().strip("\n").splitlines())


def samples() -> dict[str, str]:
    tool = offline(load_tool())
    return {name: run(tool, argv) for name, argv in SAMPLES.items()}


#: A marker, then the fenced block after it. The body may not contain a fence, so
#: an empty block cannot run on into the next one; the closing newline is
#: optional for the same reason.
BLOCK = re.compile(
    r"(<!-- sample: (?P<name>[a-z-]+) -->\n```text\n)(?P<body>(?:(?!```).)*?)\n?```", re.S)


def readme_blocks(text: str) -> dict[str, str]:
    return {m["name"]: m["body"] for m in BLOCK.finditer(text)}


def rewrite(text: str, rendered: dict[str, str]) -> str:
    def swap(m):
        return f"{m.group(1)}{rendered[m['name']]}\n```"
    return BLOCK.sub(swap, text)


def main(argv: list[str]) -> int:
    rendered = samples()
    if "--write" in argv:
        README.write_text(rewrite(README.read_text(), rendered))
        return 0
    if "--check" in argv:
        found = readme_blocks(README.read_text())
        stale = sorted(n for n in rendered if found.get(n) != rendered[n])
        missing = sorted(set(found) - set(rendered))
        for name in stale:
            print(f"README.md: sample {name!r} differs from what the command prints",
                  file=sys.stderr)
        for name in missing:
            print(f"README.md: sample {name!r} has no command here", file=sys.stderr)
        if stale or missing:
            print("  python scripts/readme_samples.py --write", file=sys.stderr)
            return 1
        return 0
    for name, text in rendered.items():
        print(f"<!-- sample: {name} -->  $ gh agile {' '.join(SAMPLES[name])}\n{text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
