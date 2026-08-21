# Targets that touch a live GitHub account, because that is the only place this
# tool can be tested. The case-sensitivity bug that made every cycle time null
# was invisible to any fixture: the transitions were in the timeline and the
# comparison silently missed them.

# The sandbox, and the reason the live targets below have a guard at all.
#
# `REPO ?= paulcaron16k/gh-agile` was the default here, and that default is how
# a `key:TEST` label reached every real gh-agile issue, how throwaway issues
# left permanent holes in the issue-number sequence, and how scratch projects
# accumulated on the account. The sandbox exists so that a forgotten or mistyped
# target costs nothing; defaulting to the repository it is meant to protect gave
# that back. `paulcaron16k/agile-test` holds nothing of value and is meant to be
# broken -- see its plan.txt.
#
# There was also a `PROJECT ?= 1` here, referenced by no target and naming no
# project that has ever existed. It is gone rather than corrected: a variable
# that looks authoritative and is never read is the kind of thing someone copies
# into a command.
SANDBOX_OWNER   := paulcaron16k
SANDBOX_REPO    := paulcaron16k/agile-test
SANDBOX_PROJECT := 19

OWNER ?= $(SANDBOX_OWNER)
REPO  ?= $(SANDBOX_REPO)

VENV  ?= .venv
PY    := $(VENV)/bin/python

# Named explicitly rather than taking whatever `python3` happens to be. On this
# machine `python3` is 3.10, which is end of life -- so `make venv` would have
# quietly built an environment below the floor the CI matrix tests, and the two
# would drift without anything failing. Override for a one-off: make venv
# PYTHON=python3.13
PYTHON ?= python3.12

.PHONY: venv test test-watch coverage self-test scratch teardown lint check-guide metrics help

# Every Python target runs through $(PY) and checks the venv exists first.
# Nothing here may fall back to the system interpreter: a suite that silently
# runs against whatever is installed globally is testing a different
# environment on every machine it lands on. tests/conftest.py asserts the same
# thing from the inside, for anyone invoking pytest directly.
define require_venv
@test -x $(PY) || { \
  echo "no virtualenv at $(VENV) -- run 'make venv' first"; exit 2; }
@$(PY) -c "import sys, pathlib; \
  want = pathlib.Path('$(VENV)').resolve(); got = pathlib.Path(sys.prefix).resolve(); \
  sys.exit(0) if want == got else (print(f'wrong interpreter: {got} != {want}'), sys.exit(2))"
endef

# The same shape as require_venv, for the same reason: that guard caught a real
# mistake within minutes of existing, and this one guards something that cannot
# be undone at all. A live target creates issues, labels and a project on a real
# account -- issue numbers are never reused, so a throwaway issue in the wrong
# repository is a permanent gap in that repository's sequence.
#
# `ALLOW_LIVE=1` is the override, and it deliberately does not stand alone: the
# repository has to be named on the same command line. Aiming at the real board
# is then two explicit acts rather than one forgotten default.
define require_sandbox
@{ test "$(REPO)" = "$(SANDBOX_REPO)" && test "$(OWNER)" = "$(SANDBOX_OWNER)"; } \
  || test -n "$(ALLOW_LIVE)" || { \
  echo "refusing '$@': OWNER=$(OWNER) REPO=$(REPO) is not the sandbox."; \
  echo "  This target creates issues, labels and a project on a live account,"; \
  echo "  and issue numbers are never reused."; \
  echo "  The sandbox is $(SANDBOX_REPO) (project #$(SANDBOX_PROJECT)), and it is the default."; \
  echo; \
  echo "  To run it against $(REPO) anyway:"; \
  echo "      make $@ OWNER=$(OWNER) REPO=$(REPO) ALLOW_LIVE=1"; \
  exit 2; }
endef

# `make teardown NUM=4` deletes the live AGILE board. Status, Story Points and
# Sprint live on the project item and not on the issue, so 25 items' worth of
# them would go with it and none of it comes back -- the sprint labels are the
# only part that would survive.
#
# So the title is read before the delete, and only the projects the live targets
# create may be deleted: `make scratch` titles them "gh-agile scratch <time>"
# and `self-test` titles them "gh-agile self-test". Checking the title rather
# than the number means this keeps working when the numbers move, and project
# numbers do move -- the sandbox landed on #19 because earlier scratch projects
# had consumed the ones before it.
#
# A title that cannot be read refuses too, and says so in its own words. During
# a GitHub outage `gh project view` failed here with a bare "unknown owner type"
# -- an error about the owner, for a request that was fine -- and a message like
# that invites reaching for ALLOW_LIVE=1 to get past it, which skips the check
# rather than retrying it. The one thing this guard must never do is look broken.
define require_scratch_project
@title=$$(gh project view $(NUM) --owner $(OWNER) --format json -q .title) || { \
  echo "refusing to delete project #$(NUM): its title could not be read, so there"; \
  echo "  is no way to tell a scratch project from a real one. The error above came"; \
  echo "  from 'gh' -- during an outage it can be misleading. Retry rather than"; \
  echo "  overriding: ALLOW_LIVE=1 skips this check, it does not fix the read."; \
  exit 2; }; \
 test -n "$(ALLOW_LIVE)" || case "$$title" in \
   "gh-agile scratch "*|"gh-agile self-test"*) ;; \
   *) echo "refusing to delete project #$(NUM), titled \"$$title\"."; \
      echo "  teardown deletes the projects 'make scratch' and 'self-test' create."; \
      echo "  That title is neither, so this is a project someone means to keep:"; \
      echo "  deleting it discards every item's Status, Story Points and Sprint."; \
      echo; \
      echo "  If you are certain:  make teardown NUM=$(NUM) OWNER=$(OWNER) ALLOW_LIVE=1"; \
      exit 2;; \
 esac
endef

help:
	@echo "make venv                create $(VENV) and install the test dependencies"
	@echo "make test                unit tests -- no network, no GitHub account"
	@echo "make coverage            unit tests with a coverage report"
	@echo "make self-test           stand a scratch project up, exercise it, tear it down"
	@echo "make scratch             leave a scratch project standing, for poking at by hand"
	@echo "make teardown NUM=<n>    delete a scratch project left by 'make scratch'"
	@echo "make check-guide         every command in USER_GUIDE.md exists; the safe ones run"
	@echo "make metrics DIR=<path>  compact an export directory and report Agile metrics"
	@echo "make lint                syntax and style"
	@echo
	@echo "OWNER=$(OWNER)  REPO=$(REPO)"
	@echo
	@echo "self-test, scratch and teardown write to a live GitHub account and run"
	@echo "against the sandbox $(SANDBOX_REPO) (project #$(SANDBOX_PROJECT))."
	@echo "They refuse any other repository unless ALLOW_LIVE=1 names it explicitly."
	@echo "check-guide is read-only but not offline: it runs the guide's read commands"
	@echo "against whichever board this clone's profile names."

venv:
	@command -v $(PYTHON) >/dev/null || { \
	  echo "$(PYTHON) is not on PATH. Python 3.12 is the floor -- 3.9, 3.10 and 3.11"; \
	  echo "  are all past or near end of life. Install it, or name another:"; \
	  echo "      make venv PYTHON=python3.13"; exit 2; }
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet --requirement requirements-dev.txt
	@echo "  $(VENV) ready: $$($(PY) -m pytest --version)"

# The fast one. No network, no GitHub account, no live project -- so it runs on
# every save and in CI. `make self-test` covers one happy path against real
# GitHub; these cover the pure logic, which is where every defect found in
# review actually lived.
test:
	$(require_venv)
	$(PY) -m pytest tests/ -q

coverage:
	$(require_venv)
	$(PY) -m pytest tests/ -q --cov=. --cov-report=term-missing

# The one to run before committing a change to the export or the write side.
# Creates everything it needs and deletes it again, including after a failure.
self-test:
	$(require_sandbox)
	./gh-agile --owner $(OWNER) self-test --repo $(REPO)

# Same setup, left standing. For when the self-test fails and you need to look
# at the board rather than at its assertions. Prints the number to tear down.
#
# The throwaway profile is not ceremony. `setup` resolves --project through
# apply_defaults, which refuses a number that disagrees with `project.number` in
# whatever profile it finds -- and the profile in this clone names the live board.
# So this target created a project, had its setup refused for that reason, and
# still exited 0: the scratch project came out with no fields and no labels and
# said nothing about it. `self-test` never hit this because apply_defaults
# exempts it by name; `scratch` is not exempt, so it brings a profile that agrees
# with the project it just created.
#
# The cadence is written out here rather than read from the sandbox clone: a
# target in this repository that only works when a checkout of another repository
# happens to be beside it is a worse failure than a duplicated 14.
#
# No `boards` in it, so a scratch project gets fields and labels only. Add one by
# hand when the thing under test is a board:
#     ./gh-agile --config <profile> --project <n> board create --name X --type scrum
scratch:
	$(require_sandbox)
	@set -e; \
	 num=$$(gh project create --owner $(OWNER) --title "gh-agile scratch $$(date -u +%H%M%S)" \
	          --format json -q .number); \
	 echo "  scratch project #$$num created"; \
	 prof=$$(mktemp); \
	 trap 'rm -f "$$prof"' EXIT; \
	 printf '{"project": {"number": %s}, "sprint": {"template": "2-week", ' "$$num" > "$$prof"; \
	 printf '"cadence_days": 14, "start_day": "monday", "ahead": 2}}\n' >> "$$prof"; \
	 if ./gh-agile --config "$$prof" --owner $(OWNER) --project $$num setup --repo $(REPO); then \
	   echo; \
	   echo "  scratch project #$$num  https://github.com/users/$(OWNER)/projects/$$num"; \
	   echo "  tear down with: make teardown NUM=$$num"; \
	 else \
	   echo; \
	   echo "  setup FAILED on scratch project #$$num, which is now incomplete."; \
	   echo "  tear down with: make teardown NUM=$$num"; \
	   exit 2; \
	 fi

teardown:
	@test -n "$(NUM)" || { echo "usage: make teardown NUM=<project number>"; exit 2; }
	$(require_scratch_project)
	gh project delete $(NUM) --owner $(OWNER)

# Every documented command is checked against the CLI's own help, and the
# read-only ones are executed in a stripped, cron-like environment. Three
# defects reached the published guide before this existed -- a traceback when
# `gh` was off PATH, a cron PATH missing /snap/bin, and a log redirect into
# /var/log that a user crontab cannot write -- and every one was found by
# hand-running a command that had already been written down.
check-guide:
	$(require_venv)
	$(PY) scripts/check_guide.py

# Needs uv: the analytics script declares duckdb with PEP 723 inline metadata,
# because `gh extension install` installs no dependencies and the extension
# itself must stay standard library only.
metrics:
	@test -n "$(DIR)" || { echo "usage: make metrics DIR=exports/KEY"; exit 2; }
	uv run scripts/agile_analytics.py --dir $(DIR) compact --keep
	uv run scripts/agile_analytics.py --dir $(DIR) metrics

lint:
	$(require_venv)
	$(PY) -c "import ast; ast.parse(open('gh-agile').read()); print('gh-agile parses')"
	$(VENV)/bin/ruff check gh-agile tests/ scripts/
