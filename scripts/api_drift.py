#!/usr/bin/env python3
"""Detect drift between GitHub's GraphQL API and the snapshot this repository keeps.

The design rested on a measured API fact -- an iteration write carried no id,
so every write cleared every Sprint value -- and GitHub changed it without this
tool noticing. `ProjectV2Iteration` gained `id`, "to preserve the iteration's
identity during replacement updates", and it was found by chance, introspecting
the schema to answer an unrelated question (#290). This finds the next change
on purpose (#291).

    snapshot   fetch the schema and write GitHub_API_spec.json, the baseline
    check      fetch it again and compare; on drift, append a timestamped
               summary to GitHub_API_changelog.md and update the snapshot

`check` exits 0 with no drift, 1 with drift (both files rewritten, ready to
commit), and 2 when the schema could not be fetched or there is no snapshot.

**Ordered, so a diff is only real change.** Introspection returns types and
members in whatever order the server keeps; every list is sorted by name and
every object's keys are sorted, and a type reference is written the way the
schema language writes it -- `[ProjectV2Iteration!]!` -- rather than as nested
`ofType` objects, which keeps the file to a third of the size and makes a
changed type one changed line.

Live, read-only, and not part of `make test` or CI, which get no token: it
calls `gh api graphql` once. The comparison and the summary are pure, and
tested offline from fixture schemas.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "GitHub_API_spec.json"
CHANGELOG = ROOT / "GitHub_API_changelog.md"
TOOL = ROOT / "gh-agile"

#: The standard introspection query. One request: GitHub rations introspection
#: per query (three uses of `__Type.inputFields` in one request is refused with
#: INTROSPECTION_LIMIT_EXCEEDED), and this shape uses each field once.
INTROSPECTION = """
query {
  __schema {
    queryType { name } mutationType { name } subscriptionType { name }
    types { ...FullType }
    directives { name description locations isRepeatable args { ...InputValue } }
  }
}
fragment FullType on __Type {
  kind name description specifiedByURL
  fields(includeDeprecated: true) {
    name description args { ...InputValue } type { ...TypeRef }
    isDeprecated deprecationReason
  }
  inputFields { ...InputValue }
  interfaces { ...TypeRef }
  enumValues(includeDeprecated: true) { name description isDeprecated deprecationReason }
  possibleTypes { ...TypeRef }
}
fragment InputValue on __InputValue { name description type { ...TypeRef } defaultValue }
fragment TypeRef on __Type {
  kind name ofType { kind name ofType { kind name ofType { kind name ofType {
    kind name ofType { kind name ofType { kind name } } } } } }
}
"""

#: The member lists a type can carry, and what each is called in a summary.
MEMBERS = {"fields": "field", "inputFields": "input field", "enumValues": "enum value"}
#: What is compared on a member, besides its arguments.
MEMBER_KEYS = ("type", "description", "isDeprecated", "deprecationReason", "defaultValue")
TYPE_KEYS = ("kind", "description", "interfaces", "possibleTypes", "specifiedByURL")


def type_ref(ref: dict | None) -> str | None:
    """`{kind: NON_NULL, ofType: {kind: LIST, ...}}` -> `[Name!]!`."""
    if ref is None:
        return None
    if ref["kind"] == "NON_NULL":
        return f"{type_ref(ref['ofType'])}!"
    if ref["kind"] == "LIST":
        return f"[{type_ref(ref['ofType'])}]"
    return ref["name"]


def _input_values(values: list[dict] | None) -> list[dict] | None:
    if values is None:
        return None
    return sorted(({**v, "type": type_ref(v["type"])} for v in values),
                  key=lambda v: v["name"])


def normalize(schema: dict) -> dict:
    """Introspection's `__schema` -> the ordered snapshot."""
    types = []
    for raw in schema["types"]:
        kind = dict(raw)
        for key in MEMBERS:
            if kind.get(key) is None:
                continue
            members = []
            for raw_member in kind[key]:
                member = dict(raw_member)
                if "type" in member:
                    member["type"] = type_ref(member["type"])
                if "args" in member:
                    member["args"] = _input_values(member["args"])
                members.append(member)
            kind[key] = sorted(members, key=lambda m: m["name"])
        for key in ("interfaces", "possibleTypes"):
            if kind.get(key) is not None:
                kind[key] = sorted(type_ref(r) for r in kind[key])
        types.append(kind)
    directives = sorted(({**d, "args": _input_values(d.get("args")),
                          "locations": sorted(d.get("locations") or [])}
                         for d in schema.get("directives") or []), key=lambda d: d["name"])
    return {
        "queryType": (schema.get("queryType") or {}).get("name"),
        "mutationType": (schema.get("mutationType") or {}).get("name"),
        "subscriptionType": (schema.get("subscriptionType") or {}).get("name"),
        "types": sorted(types, key=lambda t: t["name"]),
        "directives": directives,
    }


def dump(spec: dict) -> str:
    return json.dumps(spec, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def fetch() -> dict:
    """The live schema, normalized. Exits 2 when `gh` cannot fetch it."""
    try:
        result = subprocess.run(["gh", "api", "graphql", "-f", f"query={INTROSPECTION}"],
                                capture_output=True, text=True)
    except FileNotFoundError:
        sys.exit("`gh` is not on PATH; it is what fetches the schema.")
    if result.returncode:
        print(f"could not fetch the schema: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return normalize(json.loads(result.stdout)["data"]["__schema"])


def _short(text: str | None, limit: int = 140) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _by_name(items: list[dict] | None) -> dict[str, dict]:
    return {item["name"]: item for item in items or []}


def _compare_member(path: str, what: str, old: dict, new: dict) -> list[dict]:
    changes = []
    for key in MEMBER_KEYS:
        if old.get(key) != new.get(key):
            if key == "description":
                detail = f"description now: \"{_short(new.get(key))}\""
            else:
                detail = f"{key}: {old.get(key)!r} -> {new.get(key)!r}"
            changes.append({"change": "changed", "path": path, "what": what,
                            "detail": detail})
    old_args, new_args = _by_name(old.get("args")), _by_name(new.get("args"))
    for name in sorted(old_args.keys() | new_args.keys()):
        arg_path = f"{path}({name})"
        if name not in old_args:
            changes.append({"change": "added", "path": arg_path, "what": "argument",
                            "detail": new_args[name]["type"]})
        elif name not in new_args:
            changes.append({"change": "removed", "path": arg_path, "what": "argument",
                            "detail": old_args[name]["type"]})
        else:
            changes += _compare_member(arg_path, "argument", old_args[name], new_args[name])
    return changes


def diff(old: dict, new: dict) -> list[dict]:
    """Every difference, as `{change, path, what, detail}`, in path order."""
    changes: list[dict] = []
    for key in ("queryType", "mutationType", "subscriptionType"):
        if old.get(key) != new.get(key):
            changes.append({"change": "changed", "path": key, "what": "root",
                            "detail": f"{old.get(key)!r} -> {new.get(key)!r}"})
    old_types, new_types = _by_name(old["types"]), _by_name(new["types"])
    for name in sorted(old_types.keys() | new_types.keys()):
        if name not in old_types:
            kind = new_types[name]
            changes.append({"change": "added", "path": name, "what": kind["kind"].lower(),
                            "detail": _short(kind.get("description"))})
            continue
        if name not in new_types:
            changes.append({"change": "removed", "path": name,
                            "what": old_types[name]["kind"].lower(), "detail": ""})
            continue
        before, after = old_types[name], new_types[name]
        for key in TYPE_KEYS:
            if before.get(key) != after.get(key):
                detail = (f"description now: \"{_short(after.get(key))}\""
                          if key == "description"
                          else f"{key}: {before.get(key)!r} -> {after.get(key)!r}")
                changes.append({"change": "changed", "path": name, "what": "type",
                                "detail": detail})
        for key, what in MEMBERS.items():
            was, now = _by_name(before.get(key)), _by_name(after.get(key))
            for member in sorted(was.keys() | now.keys()):
                path = f"{name}.{member}"
                if member not in was:
                    item = now[member]
                    detail = " ".join(part for part in (
                        item.get("type") or "",
                        f"-- \"{_short(item.get('description'))}\""
                        if item.get("description") else "") if part)
                    changes.append({"change": "added", "path": path, "what": what,
                                    "detail": detail})
                elif member not in now:
                    changes.append({"change": "removed", "path": path, "what": what,
                                    "detail": was[member].get("type") or ""})
                else:
                    changes += _compare_member(path, what, was[member], now[member])
    old_dirs, new_dirs = _by_name(old.get("directives")), _by_name(new.get("directives"))
    for name in sorted(old_dirs.keys() | new_dirs.keys()):
        if (old_dirs.get(name) or {}) != (new_dirs.get(name) or {}):
            change = ("added" if name not in old_dirs
                      else "removed" if name not in new_dirs else "changed")
            changes.append({"change": change, "path": f"@{name}", "what": "directive",
                            "detail": ""})
    return changes


def names_used(source: str) -> set[str]:
    """Every identifier in the extension's source: its queries, mutations,
    selections and the comments that explain them."""
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", source))


def touches_us(change: dict, used: set[str], roots: set[str]) -> bool:
    """Whether a change is to something gh-agile names.

    A type counts when its name appears in the source -- `ProjectV2Iteration`,
    `AddSubIssueInput`. On the root types every field is an entry point, so a
    `Query` or `Mutation` field counts by its own name -- `updateProjectV2Field`
    -- rather than because the source says `mutation`.
    """
    head = change["path"].split("(")[0]
    type_name, _, member = head.partition(".")
    if type_name in roots:
        return bool(member) and member in used
    return type_name in used


def render(changes: list[dict], when: str, used: set[str], roots: set[str]) -> str:
    """One changelog entry: a heading with the time, a count, and the changes
    that touch this tool first."""
    ours = [c for c in changes if touches_us(c, used, roots)]
    rest = [c for c in changes if not touches_us(c, used, roots)]
    counts = {kind: sum(c["change"] == kind for c in changes)
              for kind in ("added", "removed", "changed")}

    def line(c: dict) -> str:
        detail = f" -- {c['detail']}" if c["detail"] else ""
        return f"- {c['change']} {c['what']} `{c['path']}`{detail}"

    out = [f"## {when}", "",
           f"{len(changes)} change(s): {counts['added']} added, {counts['removed']} removed, "
           f"{counts['changed']} changed. {len(ours)} touch what gh-agile uses.", ""]
    if ours:
        out += ["### Touches what gh-agile uses", "", *map(line, ours), ""]
    if rest:
        out += ["### Elsewhere in the schema", "", *map(line, rest), ""]
    return "\n".join(out)


CHANGELOG_HEADER = """# GitHub API changelog

Changes to GitHub's GraphQL schema, found by `make api-drift`, which compares the
live schema against `GitHub_API_spec.json`. Each entry is when the drift was
seen, not when GitHub made the change. *Touches what gh-agile uses* lists the
changes to a type, or a root query or mutation, that the extension names.

"""


def append_changelog(entry: str, path: Path = CHANGELOG) -> None:
    text = path.read_text() if path.exists() else CHANGELOG_HEADER
    path.write_text(text.rstrip("\n") + "\n\n" + entry.rstrip("\n") + "\n")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_snapshot(spec_path: Path = SPEC, changelog: Path = CHANGELOG) -> int:
    spec = fetch()
    spec_path.write_text(dump(spec))
    append_changelog(f"## {now_utc()}\n\nBaseline snapshot: {len(spec['types'])} types, "
                     f"{len(spec['directives'])} directives.\n", changelog)
    print(f"  {spec_path.name}: {len(spec['types'])} types")
    return 0


def cmd_check(spec_path: Path = SPEC, changelog: Path = CHANGELOG, *,
              write: bool = True) -> int:
    if not spec_path.exists():
        print(f"no {spec_path.name} to compare against; run `make api-spec` first",
              file=sys.stderr)
        return 2
    old = json.loads(spec_path.read_text())
    new = fetch()
    changes = diff(old, new)
    if not changes:
        print(f"  no drift: the live schema matches {spec_path.name}")
        return 0
    used = names_used(TOOL.read_text())
    roots = {r for r in (new.get("queryType"), new.get("mutationType"),
                         new.get("subscriptionType")) if r}
    entry = render(changes, now_utc(), used, roots)
    print(entry)
    if write:
        append_changelog(entry, changelog)
        spec_path.write_text(dump(new))
        print(f"  {changelog.name} and {spec_path.name} updated; review and commit them")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot", help="fetch the schema and write the baseline")
    check = sub.add_parser("check", help="compare the live schema with the baseline")
    check.add_argument("--no-write", action="store_true",
                       help="report drift without touching either file")
    args = parser.parse_args(argv)
    if args.command == "snapshot":
        return cmd_snapshot()
    return cmd_check(write=not args.no_write)


if __name__ == "__main__":
    sys.exit(main())
