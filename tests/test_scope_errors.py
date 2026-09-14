"""A missing token scope must be reported as a missing scope. #110.

`gh()` turns a non-zero `gh` into `SystemExit`, and four places catch exactly
that in order to try something else -- `project_node` asks the `user` root and
falls back to `organization`, which is only possible because a GraphQL error is
how the wrong root announces itself. That catch is correct and must stay.

It swallowed the scope refusal too. A token without `read:project` fails *both*
roots, so the loop fell out of the bottom and `views_of` reported

    no project 4 found for 'paulcaron16k' as either a user or an organization

for a project that was there all along. Measured 2026-09-14 on a freshly
installed extension; the operator went looking at the project number, the
profile and the install, none of which were wrong.

The fix is a distinct exception, so the wrong-root fallback keeps swallowing what
it should and passes this through. These tests hold both halves: the refusal
survives, and the organization fallback still works.
"""

from __future__ import annotations

import subprocess

import pytest

#: Verbatim from `gh api graphql`, 2026-09-14, on a token carrying repo but not
#: read:project. Two errors, because the query named two fields.
SCOPES_STDERR = (
    "gh: Your token has not been granted the required scopes to execute this query. "
    "The 'projectV2' field requires one of the following scopes: ['read:project'], but "
    "your token has only been granted the: ['gist', 'read:org', 'repo', 'workflow'] "
    "scopes. Please modify your token's scopes at: https://github.com/settings/tokens.\n"
    "Your token has not been granted the required scopes to execute this query. The "
    "'title' field requires one of the following scopes: ['read:project'], but your "
    "token has only been granted the: ['gist', 'read:org', 'repo', 'workflow'] scopes."
)

NOT_A_USER = "gh api graphql failed: gh: Could not resolve to a User with the login of 'acme'."
NOT_AN_ORG = ("gh api graphql failed: gh: Could not resolve to an Organization with the "
              "login of 'someone'.")


def fake_run(returncode: int, stderr: str = "", stdout: str = ""):
    def run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)
    return run


class TestGhClassifies:
    def test_a_scope_refusal_raises_missing_scope_not_system_exit(self, tool, monkeypatch):
        """`SystemExit` is what the fallback handlers eat; this must not be one."""
        monkeypatch.setattr(subprocess, "run", fake_run(1, SCOPES_STDERR))
        with pytest.raises(tool.MissingScope):
            tool.gh(["api", "graphql", "-f", "query=..."])

    def test_missing_scope_is_not_a_system_exit_subclass(self, tool):
        assert not issubclass(tool.MissingScope, SystemExit)

    def test_any_other_failure_still_exits_as_before(self, tool, monkeypatch):
        monkeypatch.setattr(subprocess, "run", fake_run(1, "HTTP 404: Not Found"))
        with pytest.raises(SystemExit) as exit_info:
            tool.gh(["api", "graphql"])
        assert "404" in str(exit_info.value)

    def test_success_is_untouched(self, tool, monkeypatch):
        monkeypatch.setattr(subprocess, "run", fake_run(0, stdout='{"ok":true}'))
        assert tool.gh(["api", "user"]) == '{"ok":true}'


class TestTheMessage:
    @pytest.fixture
    def message(self, tool):
        return tool.scope_message(SCOPES_STDERR)

    def test_it_names_the_missing_scope(self, message):
        assert "read:project" in message

    def test_it_does_not_claim_the_project_is_missing(self, message):
        """The whole defect: a scope problem reported as a lookup problem."""
        assert "no project" not in message.casefold()
        assert "as either a user or an organization" not in message

    def test_it_prints_the_fix_verbatim(self, message):
        """Including --hostname: `gh auth refresh -s project` fails without a TTY."""
        assert "gh auth refresh --hostname github.com --scopes project" in message

    def test_it_says_the_device_flow_needs_a_terminal(self, message):
        assert "terminal" in message

    def test_it_quotes_github_so_the_granted_scopes_are_visible(self, message):
        """Which scopes the token *does* carry is how you spot the wrong account."""
        assert "'gist', 'read:org', 'repo', 'workflow'" in message

    def test_an_unparseable_refusal_still_names_a_scope(self, tool):
        assert "read:project" in tool.scope_message("gh: something was refused")


class TestItSurvivesTheFallbackHandlers:
    @pytest.fixture
    def roots(self, monkeypatch, tool):
        def install(answers):
            seen = []

            def fake_graphql(query, **variables):
                root = "organization" if "organization(login:" in query else "user"
                seen.append(root)
                answer = answers[root]
                if isinstance(answer, BaseException):
                    raise answer
                return {"data": {root: answer}}

            monkeypatch.setattr(tool, "graphql", fake_graphql)
            return seen
        return install

    def test_project_node_does_not_swallow_it(self, tool, roots):
        roots({"user": tool.MissingScope("missing read:project"),
               "organization": {"projectV2": {"id": "PVT_1"}}})
        with pytest.raises(tool.MissingScope):
            tool.project_node("someone", 4, "id")

    def test_the_second_root_is_not_asked_a_doomed_question(self, tool, roots):
        """No root has a scope the token lacks, so the retry is pure waste."""
        seen = roots({"user": tool.MissingScope("missing read:project"),
                      "organization": {"projectV2": {"id": "PVT_1"}}})
        with pytest.raises(tool.MissingScope):
            tool.project_node("someone", 4, "id")
        assert seen == ["user"]

    def test_the_wrong_root_fallback_still_works(self, tool, roots):
        """The regression this fix must not cause: NOT_FOUND is still swallowed."""
        seen = roots({"user": SystemExit(NOT_A_USER),
                      "organization": {"projectV2": {"id": "PVT_2"}}})
        assert tool.project_node("acme", 4, "id") == {"id": "PVT_2"}
        assert seen == ["user", "organization"]

    def test_a_genuinely_absent_project_still_says_so(self, tool, roots):
        roots({"user": SystemExit(NOT_A_USER), "organization": SystemExit(NOT_AN_ORG)})
        assert tool.project_node("nobody", 4, "id") is None

    @pytest.mark.parametrize("call", ["views_of", "sprint_field", "project_id"])
    def test_every_caller_reports_the_scope_not_a_missing_project(
        self, tool, roots, monkeypatch, call,
    ):
        """All five sites shared one sentence; none of them should print it here."""
        monkeypatch.setattr(tool, "_PROJECT_IDS", {})
        roots({"user": tool.MissingScope("missing read:project"),
               "organization": tool.MissingScope("missing read:project")})
        with pytest.raises(tool.MissingScope):
            getattr(tool, call)("someone", 4)


class TestMainConvertsItToAnExit:
    def test_main_turns_it_into_a_message_not_a_traceback(self, tool, monkeypatch):
        def raiser(_args):
            raise tool.MissingScope(tool.scope_message(SCOPES_STDERR))

        monkeypatch.setattr(tool, "apply_defaults", raiser)
        monkeypatch.setattr("sys.argv", ["gh agile", "validate"])
        with pytest.raises(SystemExit) as exit_info:
            tool.main()
        message = str(exit_info.value)
        assert "read:project" in message
        assert "gh auth refresh --hostname github.com --scopes project" in message


class TestConfigDoesNotReportAnEmptyBoardAsSprintless:
    def test_unreadable_sprints_are_said_out_loud(self, tool, monkeypatch, capsys):
        """An empty sprints table and an unreadable one render identically."""
        monkeypatch.setattr(tool, "views_of", lambda *a, **k: [])
        monkeypatch.setattr(
            tool, "iterations",
            lambda *a, **k: (_ for _ in ()).throw(SystemExit("no Sprint iteration field")),
        )
        rows = tool.master_rows("someone", 4, {}, "2026-09-14T00:00:00Z")
        assert rows["sprints"] == []
        assert "sprints could not be read" in capsys.readouterr().err
