#!/usr/bin/env python3
"""Check that USER_GUIDE.md's commands are real, and that the safe ones run.

Three defects reached the published guide before this existed, every one of
them found by hand-running a command that had already been written down: a raw
traceback when `gh` was off PATH, a cron `PATH` with no `/snap/bin`, and a log
redirect into `/var/log` that a user crontab cannot write. A guide whose
examples nobody executes is a guide that drifts, and the drift is invisible.

Two levels, because they catch different things:

1. **Every documented invocation is checked against the CLI's own help** --
   subcommand exists, every long flag exists. This catches a guide that
   documents `--foo` after `--foo` was renamed, which no amount of running the
   *other* examples would reveal.
2. **The read-only ones are executed**, in a stripped environment resembling
   cron's, so a command that only works because of an interactive shell's PATH
   fails here rather than at 07:00.

Mutating examples -- epic, story, issue move, init -- are checked but not
run; `make self-test` covers those against a scratch project.
"""

from __future__ import annotations

import functools
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "USER_GUIDE.md"
TOOL = ROOT / "gh-agile"

#: Executed for real. Everything else is checked for existence only.
#:
#: The work-item lists are here and their views are not: a list reads whatever
#: board the profile names, and a view names one issue, which on another board
#: is somebody else's issue or none -- the reason `board view` is absent too.
SAFE = {
    ("key", "list"), ("board", "list"), ("sprint", "list"), ("sprint", "view"),
    ("project", "view"),
    ("validate",), ("sync",), ("export",),
    ("initiative", "list"), ("epic", "list"), ("story", "list"), ("issue", "list"),
    ("issue", "status"),
}

#: Flags on the root parser rather than on a subcommand, so they are legal
#: *before* the subcommand and appear in no subcommand's help. The value is
#: whether the flag takes one, because `gh agile --owner some-org init`
#: otherwise reads `some-org` as the subcommand.
#:
#: This replaced a blacklist of one value -- `@me` was filtered out by name --
#: which worked until the guide documented an owner that was not `@me`. Skipping
#: the token after a known value-taking flag is the same fix without the
#: guesswork.
GLOBAL_FLAGS = {"--owner": True, "--project": True, "--config": True, "--help": False}

#: Never executed, whatever SAFE says. Learned by running this script the first
#: time: `key --key SPARK` (now `key add SPARK`) wrote a third key into the profile and
#: `export --out-dir exports/` created a directory. A checker with side effects
#: is worse than no checker -- it makes the thing it checks wrong.
#:
#: `--web` and `-w` open a browser, which is a side effect on whoever runs this.
#:
#: `--adopt` is listed even though `run_safe` appends `--dry-run` to every sync,
#: which already suppresses it. Relying on that interaction means a label is
#: written to a live repository the day the two are decoupled.
NEVER_RUN = ("--key ", "--out-dir", "--save", "--evidence", "--close", "--force",
             "--adopt", "--yes", "--web", " -w")

#: Placeholders. A guide has to name a repository somewhere, and owner/repo is
#: not one; running it is a guaranteed failure that says nothing.
PLACEHOLDERS = ("owner/", "OWNER/", "/srv/", "USERNAME", "YOUR_", "<", "...")

#: A cron-like environment: no interactive shell's PATH, no inherited niceties.
#: `/snap/bin` is included because `gh` is a snap on some machines and its
#: absence is one of the defects this script exists to prevent.
CRON_ENV = {
    "HOME": os.environ["HOME"],
    "PATH": "/usr/local/bin:/usr/bin:/bin:/snap/bin",
}


def documented_commands() -> list[tuple[int, str]]:
    """`gh agile ...` lines from fenced blocks, joined across backslashes."""
    out, lineno, buffer, start = [], 0, "", 0
    in_block = False
    for lineno, raw in enumerate(GUIDE.read_text().splitlines(), 1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_block = not in_block
            continue
        if not in_block:
            continue
        if buffer:
            buffer += " " + stripped.rstrip("\\").strip()
        elif stripped.startswith(("gh agile", "gh-agile")):
            buffer, start = stripped.rstrip("\\").strip(), lineno
        else:
            continue
        if raw.rstrip().endswith("\\"):
            continue
        out.append((start, buffer))
        buffer = ""
    return out


@functools.cache
def help_for(words: tuple[str, ...]) -> str:
    """`--help` for one subcommand, once.

    Cached because the guide documents many invocations of the same handful of
    subcommands, and this spawns an interpreter each time. Uncached it crossed
    two minutes as the guide grew, which is slow enough that people stop running
    it -- and a check nobody runs is the thing this script exists to prevent.
    """
    result = subprocess.run(
        [sys.executable, str(TOOL), *words, "--help"],
        capture_output=True, text=True, env={**os.environ, "COLUMNS": "200"},
    )
    return result.stdout + result.stderr


def check(command: str) -> list[str]:
    """Subcommand and flags must exist. Returns problems."""
    tokens = command.split()[2:]  # drop `gh agile` / `gh-agile <sub>`
    if command.startswith("gh-agile"):
        tokens = command.split()[1:]
    words, flags = [], []
    skip = False
    for token in tokens:
        if skip:
            # The value of a global flag, not a subcommand.
            skip = False
            continue
        if token.startswith("--"):
            flag = token.split("=")[0]
            flags.append(flag)
            skip = GLOBAL_FLAGS.get(flag, False) and "=" not in token
        elif not words or (words and not flags and not token.startswith("-")
                           and len(words) < 2
                           and token.replace("-", "").isalpha()):
            # Hyphens allowed: `isalpha()` rejected `sprint-template`, so a
            # two-word subcommand was checked against its parent's help and its
            # flags reported as nonexistent. Found by documenting one.
            words.append(token)
    if not words:
        return []
    text = help_for(tuple(words[:1]))
    if "invalid choice" in text or "unrecognized" in text:
        return [f"subcommand {words[0]!r} does not exist"]
    # A two-word subcommand, e.g. `board list`.
    if len(words) > 1 and words[1] in text:
        text = help_for(tuple(words[:2]))
    return [f"{words[0]}: no such flag {flag}" for flag in flags
            if flag not in text and flag not in GLOBAL_FLAGS]


#: Commands the guide is not required to document, and why each one is here.
#:
#: **A reason per entry, not a silent skip.** An exemption with no justification
#: is indistinguishable from an oversight, which is the failure this whole check
#: exists to catch -- so anything added later has to argue for itself in this
#: dict, where a reviewer will see it.
UNDOCUMENTED_OK = {
    ("task", "create"):
        "filing tasks as GitHub issues is deliberately not promoted -- POLICY.md "
        "§2 still recommends a markdown checklist inside the story, and the "
        "command exists so a team doing it anyway is not punished by `validate`. "
        "Documenting it in the guide would read as a recommendation. Revisit when "
        "the task model is settled",
    ("task", "list"):
        "the same reason as `task create`: documenting how to list tasks reads as "
        "recommending them",
}


def load_parser():
    """The CLI's own parser, built in-process from the file `gh` would run."""
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("gh_agile_cli", str(TOOL))
    spec = importlib.util.spec_from_loader("gh_agile_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.build_parser()


def parser_leaves(parser=None) -> set[tuple[str, ...]]:
    """Every subcommand a user can actually invoke, leaves only.

    Read from the CLI's own parser rather than from a list kept beside it, for
    the reason this direction exists at all: a list maintained by hand drifts
    from the thing it describes, and then the check is checking the list.

    **Walked, not scraped from `--help`.** It read the `{a,b,c}` line under
    `positional arguments:`, which matched an option's choices the same way
    (`sync all`), then matched nothing at all once the commands took a
    `<command>` metavar and `--help` grew `gh`'s sections (#203, #204). A
    command with no `help=` is hidden from `--help` -- `self-test`,
    `unfinished` -- and so is not one the guide owes a reader.

    Leaves, because a guide showing `board list` and never `board view` has not
    documented `board view`. Reporting the parent as covered would be the false
    assurance the whole script exists to remove.
    """
    import argparse

    def walk(node, path):
        for action in node._actions:
            if not isinstance(action, argparse._SubParsersAction):
                continue
            # `_choices_actions` holds only the subcommands given a `help=`:
            # exactly the ones `--help` shows.
            for shown in action._choices_actions:
                child = action.choices[shown.dest]
                deeper = list(walk(child, (*path, shown.dest)))
                yield from deeper or [(*path, shown.dest)]

    leaves = set(walk(parser or load_parser(), ()))
    if not leaves:
        # **A check that can pass by finding nothing is not a check.** An
        # extraction that stops matching would otherwise make every command
        # exempt and the check green -- which happened once.
        sys.exit("check_guide: no subcommands found in the CLI's parser; "
                 "the extraction stopped matching")
    return leaves


def documented_leaves(commands: list[tuple[int, str]]) -> set[tuple[str, ...]]:
    """The leaves the guide actually invokes.

    A command is not documented because its name appears in a sentence -- it is
    documented when an invocation of it appears, which is the same evidence the
    other direction of this script already works from.
    """
    seen = set()
    for _line, command in commands:
        tokens = command.split()[1:] if command.startswith("gh-agile") \
            else command.split()[2:]
        words, skip = [], False
        for token in tokens:
            if skip:
                skip = False
                continue
            if token.startswith("--"):
                if len(words) >= 1:
                    break
                skip = GLOBAL_FLAGS.get(token.split("=")[0], False) and "=" not in token
            elif token.replace("-", "").isalpha() and len(words) < 2:
                words.append(token)
            else:
                break
        if words:
            seen.add(tuple(words[:2]))
            seen.add((words[0],))
    return seen


def coverage_problems(commands: list[tuple[int, str]]) -> list[str]:
    """Leaves the parser exposes and the guide never invokes.

    **The direction this script was missing.** It checked every documented
    invocation against the CLI and never the CLI against the guide, so a command
    documented nowhere passed everything: `gh agile task` shipped, `make
    check-guide` reported "no problems found", CI stayed green, and the omission
    was found months later by a person asking whether the docs were current.

    The same shape as a grouping that collapses to one bucket: the check ran,
    passed, and conveyed nothing. A guard that looks one way reports the absence
    of what it cannot see.
    """
    missing = sorted(parser_leaves() - documented_leaves(commands)
                     - set(UNDOCUMENTED_OK))
    return [
        f"`gh agile {' '.join(leaf)}` exists and USER_GUIDE.md never invokes it.\n"
        f"      Document it there, or add it to UNDOCUMENTED_OK in "
        f"scripts/check_guide.py with a reason."
        for leaf in missing
    ]


def run_safe(command: str) -> tuple[bool, str]:
    words = tuple(w for w in command.split()[2:] if not w.startswith("-"))[:2]
    if not any(words[: len(s)] == s for s in SAFE):
        return True, "not run (mutating)"
    if any(token in command for token in NEVER_RUN):
        return True, "not run (writes)"
    if any(token in command for token in PLACEHOLDERS):
        return True, "not run (placeholder)"
    argv = command.replace("gh-agile", str(TOOL), 1).replace("gh agile", str(TOOL), 1)
    # **The trailing comment goes before anything is appended.** These run through
    # `sh -c`, so a documented line ending in `# every repo in the profile keys`
    # swallowed the safety flag added after it -- `gh agile sync  # ... --dry-run`
    # is a real sync -- and the check that exists to prove the guide is honest
    # wrote 35 issues onto a live board. Measured 2026-09-12, and harmless only
    # for as long as `sync` happened to be looking at one repository.
    argv = strip_comment(argv)
    # Read-only variants only: never write state or a file during a check.
    for flag, addition in (("export", " --no-history --no-state"), ("sync", " --dry-run")):
        if f" {flag}" in argv and addition.strip().split()[0] not in argv:
            argv += addition
    result = subprocess.run(
        ["sh", "-c", f"cd {ROOT} && {argv}"],
        capture_output=True, text=True, env=CRON_ENV,
    )
    note = (result.stderr or result.stdout).strip()
    note = note.splitlines()[-1] if note else "no output"
    ok = result.returncode == 0
    # `validate` exits 1 when it finds something, and that is a report rather
    # than a failure: the command ran and did its job. Without this, the
    # documentation check is really a test of how tidy the board happens to be
    # today, and it goes red the moment a real epic is left open over closed
    # children -- which is what happened the first time the roll-up check ran.
    #
    # Matched on the summary line, not on the exit code alone, because
    # `sys.exit("message")` also exits 1: a project that cannot be reached must
    # still fail here.
    if not ok and " validate" in argv and "problem(s) across" in result.stdout:
        ok = True
    return ok, note


def strip_comment(command: str) -> str:
    """`cmd  # why` -> `cmd`. Quote-aware, because a `#` can be an argument.

    Only a `#` that begins a word outside quotes starts a comment, which is the
    shell's own rule: `--title "fixes #12"` and `--query "a#b"` keep theirs.
    """
    quote = None
    for i, char in enumerate(command):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (i == 0 or command[i - 1].isspace()):
            return command[:i].rstrip()
    return command.rstrip()


def main() -> int:
    commands = documented_commands()
    if not commands:
        sys.exit("no commands found in USER_GUIDE.md; the extraction stopped matching")

    problems, ran, skipped = coverage_problems(commands), 0, {}
    for line, command in commands:
        issues = check(command)
        for issue in issues:
            problems.append(f"USER_GUIDE.md:{line}: {issue}")
        if issues:
            continue
        ok, note = run_safe(command)
        if note.startswith("not run"):
            # Reported, not silently passed: a command nobody ran is not a
            # command anybody verified, and saying "ok" for it would be the
            # false assurance this script exists to remove.
            skipped.setdefault(note, []).append(command[:60])
            continue
        ran += 1
        status = "ok" if ok else "FAIL"
        # A finding is shown even though the command passed. Reporting `[ok]` and
        # nothing else for a board with a real problem would be the false
        # assurance this script exists to remove.
        finding = f"  -- {note}" if ok and "problem(s) across" in note else ""
        print(f"  [{status}] {command[:72]}{finding}")
        if not ok:
            problems.append(f"USER_GUIDE.md:{line}: {command[:60]} -> {note}")

    covered = len(parser_leaves()) - len(UNDOCUMENTED_OK)
    print(f"\n  {len(commands)} documented command(s): {ran} executed in a cron-like "
          f"environment, {sum(len(v) for v in skipped.values())} checked but not run")
    print(f"  {covered} command(s) require documenting; "
          f"{len(UNDOCUMENTED_OK)} exempt, with a reason each")
    for reason, items in sorted(skipped.items()):
        print(f"    {reason}: {len(items)}")
    if problems:
        print("\nproblems:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("  no problems found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
