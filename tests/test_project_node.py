"""Reaching a project whether its owner is a user or an organization. S8.

`gh api graphql` exits non-zero when GraphQL returns an `errors` block, and asking
the wrong root does exactly that -- HTTP 200, a null owner, and a NOT_FOUND error.
Measured 2026-08-23 against public logins, no organization required:

    user(login: "github")               exit 1, "Could not resolve to a User"
    organization(login: "paulcaron16k")  exit 1, "Could not resolve to an Organization"

`gh()` turns a non-zero exit into `SystemExit`, so a loop over both roots that
does not catch it dies on the first one. `fetch_items` caught it and
`project_id`/`sprint_field` did not, which is why reading an organization's board
worked and almost every write did not -- and the error blamed the login:

    Could not resolve to a User with the login of 'acme'

for a login that was correct. Three call sites ran that loop and two were wrong,
so it is one function now.

These tests stub `graphql` rather than calling GitHub, so the organization branch
is exercised without anyone owning an organization.
"""

from __future__ import annotations

import pytest

NOT_A_USER = "gh api graphql failed: gh: Could not resolve to a User with the login of 'acme'."
NOT_AN_ORG = ("gh api graphql failed: gh: Could not resolve to an Organization with the "
              "login of 'someone'.")


@pytest.fixture
def roots(monkeypatch, tool):
    """Answer per root: a dict to return, or an exception to raise."""
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


class TestProjectNode:
    def test_a_user_owned_project_is_found_on_the_first_root(self, tool, roots):
        seen = roots({"user": {"projectV2": {"id": "PVT_1"}}, "organization": None})
        assert tool.project_node("someone", 4, "id") == {"id": "PVT_1"}
        assert seen == ["user"], "the organization root should not have been needed"

    def test_an_org_owned_project_is_found_after_the_user_root_errors(self, tool, roots):
        """The S8 defect. Without the catch, the SystemExit below ended the command."""
        seen = roots({
            "user": SystemExit(NOT_A_USER),
            "organization": {"projectV2": {"id": "PVT_2"}},
        })
        assert tool.project_node("acme", 4, "id") == {"id": "PVT_2"}
        assert seen == ["user", "organization"]

    def test_a_null_owner_also_falls_through(self, tool, roots):
        """Not every wrong root errors; some just answer null."""
        roots({"user": None, "organization": {"projectV2": {"id": "PVT_3"}}})
        assert tool.project_node("acme", 4, "id") == {"id": "PVT_3"}

    def test_an_owner_without_that_project_falls_through(self, tool, roots):
        roots({"user": {"projectV2": None}, "organization": {"projectV2": {"id": "PVT_4"}}})
        assert tool.project_node("acme", 4, "id") == {"id": "PVT_4"}

    def test_neither_root_returns_none_rather_than_raising(self, tool, roots):
        """The caller writes the message, because it knows what it was looking for."""
        roots({"user": SystemExit(NOT_A_USER), "organization": SystemExit(NOT_AN_ORG)})
        assert tool.project_node("nobody", 4, "id") is None


class TestCallersReachTheOrganisation:
    """Each of the three now says "not found", never "not a User"."""

    def test_project_id_finds_an_org_project(self, tool, roots, monkeypatch):
        monkeypatch.setattr(tool, "_PROJECT_IDS", {})
        roots({"user": SystemExit(NOT_A_USER),
               "organization": {"projectV2": {"id": "PVT_org"}}})
        assert tool.project_id("acme", 4) == "PVT_org"

    def test_sprint_field_finds_an_org_project(self, tool, roots):
        roots({"user": SystemExit(NOT_A_USER),
               "organization": {"projectV2": {"field": {"id": "PVTIF_org"}}}})
        assert tool.sprint_field("acme", 4)["id"] == "PVTIF_org"

    def test_project_fields_finds_an_org_project(self, tool, roots):
        roots({"user": SystemExit(NOT_A_USER), "organization": {"projectV2": {"fields": {
            "nodes": [{"id": "F1", "name": "Story Points", "dataType": "NUMBER"}]}}}})
        got = tool.project_fields("acme", 4)
        assert got == [{"id": "F1", "name": "Story Points", "data_type": "NUMBER"}]

    @pytest.mark.parametrize("call", ["project_id", "sprint_field", "project_fields"])
    def test_a_genuinely_absent_project_blames_the_project_not_the_login(
        self, tool, roots, monkeypatch, call,
    ):
        """The old message sent people to check a login that was spelled correctly."""
        monkeypatch.setattr(tool, "_PROJECT_IDS", {})
        roots({"user": SystemExit(NOT_A_USER), "organization": SystemExit(NOT_AN_ORG)})
        with pytest.raises(SystemExit) as exit_info:
            getattr(tool, call)("acme", 99)
        message = str(exit_info.value)
        assert "as either a user or an organization" in message
        assert "Could not resolve to a User" not in message

    def test_sprint_field_still_distinguishes_a_project_with_no_sprint_field(self, tool, roots):
        """A found project missing the field is a `setup` problem, not a lookup one."""
        roots({"user": {"projectV2": {"field": None}}, "organization": None})
        with pytest.raises(SystemExit) as exit_info:
            tool.sprint_field("someone", 4)
        assert "gh agile init" in str(exit_info.value)
