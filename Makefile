# Targets that touch a live GitHub account, because that is the only place this
# tool can be tested. The case-sensitivity bug that made every cycle time null
# was invisible to any fixture: the transitions were in the timeline and the
# comparison silently missed them.

OWNER ?= paulcaron16k
REPO  ?= paulcaron16k/gh-agile
PROJECT ?= 1

.PHONY: self-test scratch teardown lint help

help:
	@echo "make self-test           stand a scratch project up, exercise it, tear it down"
	@echo "make scratch             leave a scratch project standing, for poking at by hand"
	@echo "make teardown NUM=<n>    delete a scratch project left by 'make scratch'"
	@echo "make lint                syntax and style"
	@echo
	@echo "OWNER=$(OWNER)  REPO=$(REPO)"

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

lint:
	python3 -c "import ast,sys; ast.parse(open('gh-agile').read()); print('gh-agile parses')"
	@command -v ruff >/dev/null && ruff check gh-agile || echo "(ruff not installed; skipped)"
