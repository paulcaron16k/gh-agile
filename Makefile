# Targets that touch a live GitHub account, because that is the only place this
# tool can be tested. The case-sensitivity bug that made every cycle time null
# was invisible to any fixture: the transitions were in the timeline and the
# comparison silently missed them.

OWNER ?= paulcaron16k
REPO  ?= paulcaron16k/gh-agile
PROJECT ?= 1

VENV  ?= .venv
PY    := $(VENV)/bin/python

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

venv:
	python3 -m venv $(VENV)
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
	./gh-agile --owner $(OWNER) self-test --repo $(REPO)

# Same setup, left standing. For when the self-test fails and you need to look
# at the board rather than at its assertions. Prints the number to tear down.
scratch:
	@num=$$(gh project create --owner $(OWNER) --title "gh-agile scratch $$(date -u +%H%M%S)" \
	          --format json -q .number); \
	 ./gh-agile --owner $(OWNER) --project $$num setup --repo $(REPO); \
	 echo; \
	 echo "  scratch project #$$num  https://github.com/users/$(OWNER)/projects/$$num"; \
	 echo "  tear down with: make teardown NUM=$$num"

teardown:
	@test -n "$(NUM)" || { echo "usage: make teardown NUM=<project number>"; exit 2; }
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
