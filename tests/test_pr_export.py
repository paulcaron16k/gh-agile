"""Pull requests, reviews and merges as export rows.

`github_events` stopped at the boundary where most of the engineering signal
starts. A pull request's life -- opened, reviewed, changes requested,
re-reviewed, merged -- was not exported at all, and **reviews name a second
person**: the author did the work, the reviewer approved or rejected it. No issue
event distinguishes them.

Two properties these tests exist to hold.

**Incremental, not full-table.** `since` goes to GitHub as `updated:>=` inside
the search query, not applied to the rows afterwards. The projects API has no
server-side `updatedAt` filter, so `rows()` fetches the board and discards;
search does the filtering on GitHub's side, and an incremental run never
transfers a pull request nobody has touched.

**No code content.** These rows make events and metrics. Not a diff hunk, not a
patch, not a review or comment body -- and the query is where that is enforced,
so it is asserted against the query text itself.
"""

from __future__ import annotations

import pytest

KEYS = {"o/r": "AGILE"}


def review(state="APPROVED", at="2026-09-08T10:00:00Z", who="reviewer",
           ident="RV_1", comments=()):
    return {"id": ident, "state": state, "submittedAt": at, "author": {"login": who},
            "comments": {"nodes": list(comments)}}


def comment(at="2026-09-08T10:00:05Z", who="reviewer", ident="RC_1"):
    return {"id": ident, "createdAt": at, "author": {"login": who}}


def pull(**overrides):
    data = {
        "id": "PR_1", "number": 7, "title": "a change", "url": "u",
        "state": "MERGED", "isDraft": False,
        "createdAt": "2026-09-08T09:00:00Z", "updatedAt": "2026-09-08T11:00:00Z",
        "closedAt": "2026-09-08T11:00:00Z", "mergedAt": "2026-09-08T11:00:00Z",
        "author": {"login": "dev"}, "repository": {"nameWithOwner": "o/r"},
        "baseRefName": "main", "headRefName": "feature",
        "additions": 40, "deletions": 5, "changedFiles": 3,
        "commits": {"totalCount": 2}, "reviewDecision": "APPROVED",
        "mergedBy": {"login": "dev"},
        "closingIssuesReferences": {"nodes": []},
        "reviews": {"totalCount": 0, "nodes": []},
    }
    data.update(overrides)
    return data


def issue_ref(number=12, repo="o/r", labels=()):
    return {"number": number, "repository": {"nameWithOwner": repo},
            "labels": {"nodes": [{"name": n} for n in labels]}}


class TestTheQueryCarriesNoCodeContent:
    """The exclusion is a property of the query, so it is asserted there."""

    @pytest.mark.parametrize("forbidden", ["body", "bodyText", "diff", "patch", "hunk"])
    def test_nothing_that_would_carry_source(self, tool, forbidden):
        assert forbidden not in tool.PR_SEARCH_QUERY

    def test_but_it_does_carry_the_size_signals(self, tool):
        for wanted in ("additions", "deletions", "changedFiles", "reviewDecision"):
            assert wanted in tool.PR_SEARCH_QUERY


class TestIncremental:
    @pytest.fixture
    def fetch(self, monkeypatch, tool):
        seen = []

        def fake_graphql(query, **variables):
            seen.append(variables)
            return {"data": {"search": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": [pull()]}}}

        monkeypatch.setattr(tool, "graphql", fake_graphql)

        def go(since, config=None):
            seen.clear()
            return tool.pull_requests(
                config or {"keys": [{"key": "AGILE", "repo": "o/r"}]}, since), seen
        return go

    def test_since_goes_to_github_as_a_search_term(self, tool, fetch):
        """Server-side. Applying it to the rows afterwards would transfer every
        pull request in the repository on every run and call it incremental."""
        _, seen = fetch("2026-09-08T00:00:00Z")
        assert "updated:>=2026-09-08T00:00:00Z" in seen[0]["q"]

    def test_no_since_is_a_full_export(self, tool, fetch):
        _, seen = fetch(None)
        assert "updated:" not in seen[0]["q"]
        assert seen[0]["q"] == "repo:o/r is:pr"

    def test_one_search_per_repository(self, tool, fetch):
        config = {"keys": [{"key": "A", "repo": "o/one"}, {"key": "B", "repo": "o/two"}]}
        _, seen = fetch(None, config)
        assert sorted(v["q"] for v in seen) == ["repo:o/one is:pr", "repo:o/two is:pr"]

    def test_a_repo_named_twice_is_searched_once(self, tool, fetch):
        """A mono-repo carries several keys against one repository."""
        config = {"keys": [{"key": "A", "repo": "o/r"}, {"key": "B", "repo": "o/r"}]}
        _, seen = fetch(None, config)
        assert len(seen) == 1

    def test_no_cursor_is_sent_on_the_first_page(self, tool, fetch):
        """`-F after=` would send an empty string where the schema wants null."""
        _, seen = fetch(None)
        assert "after" not in seen[0]

    def test_it_follows_pagination(self, tool, monkeypatch):
        pages = [
            {"data": {"search": {"pageInfo": {"hasNextPage": True, "endCursor": "C1"},
                                 "nodes": [pull(number=1, id="PR_1")]}}},
            {"data": {"search": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                                 "nodes": [pull(number=2, id="PR_2")]}}},
        ]
        seen = []

        def fake_graphql(query, **variables):
            seen.append(variables)
            return pages[len(seen) - 1]

        monkeypatch.setattr(tool, "graphql", fake_graphql)
        out = tool.pull_requests({"keys": [{"key": "A", "repo": "o/r"}]}, None)
        assert [p["number"] for p in out] == [1, 2]
        assert seen[1]["after"] == "C1"

    def test_issues_in_the_search_result_are_dropped(self, tool, monkeypatch):
        """`search(type: ISSUE)` returns issues too, and they arrive as empty
        objects because the whole selection is inside the PullRequest fragment."""
        monkeypatch.setattr(tool, "graphql", lambda query, **variables: {"data": {"search": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{}, pull(), {}]}}})
        assert len(tool.pull_requests({"keys": [{"key": "A", "repo": "o/r"}]}, None)) == 1


class TestPrRow:
    def test_the_size_signals(self, tool):
        row = tool.pr_row(pull(), KEYS)
        assert (row["additions"], row["deletions"], row["changed_files"],
                row["commits"]) == (40, 5, 3, 2)

    def test_durations_are_integer_seconds(self, tool):
        row = tool.pr_row(pull(reviews={"totalCount": 1, "nodes": [
            review(at="2026-09-08T09:10:00Z")]}), KEYS)
        assert row["time_to_first_review"] == 600
        assert row["time_to_merge"] == 7200
        assert row["review_latency"] == 6600
        assert not any(k.endswith(("_days", "_hours")) for k in row)

    def test_a_pull_request_with_no_review_has_no_review_times(self, tool):
        row = tool.pr_row(pull(), KEYS)
        assert row["first_review_at"] == "" and row["time_to_first_review"] is None

    def test_an_unmerged_pull_request_has_no_merge_time(self, tool):
        row = tool.pr_row(pull(state="OPEN", mergedAt=None, mergedBy=None), KEYS)
        assert row["time_to_merge"] is None and row["merged_by"] == ""

    def test_round_trips_are_counted(self, tool):
        """How often it came back is a flow problem teams act on, and it needs no
        line of source."""
        row = tool.pr_row(pull(reviews={"totalCount": 3, "nodes": [
            review(state="CHANGES_REQUESTED", ident="RV_1"),
            review(state="CHANGES_REQUESTED", ident="RV_2"),
            review(state="APPROVED", ident="RV_3"),
        ]}), KEYS)
        assert row["changes_requested_total"] == 2 and row["reviews_total"] == 3

    def test_reviewers_are_distinct_and_sorted(self, tool):
        row = tool.pr_row(pull(reviews={"totalCount": 3, "nodes": [
            review(who="bea", ident="RV_1"), review(who="ann", ident="RV_2"),
            review(who="bea", ident="RV_3")]}), KEYS)
        assert row["reviewers"] == "ann;bea" and row["reviewer_count"] == 2

    def test_first_and_last_review_are_by_time_not_by_order(self, tool):
        row = tool.pr_row(pull(reviews={"totalCount": 2, "nodes": [
            review(at="2026-09-08T10:30:00Z", ident="RV_1"),
            review(at="2026-09-08T09:30:00Z", ident="RV_2")]}), KEYS)
        assert row["first_review_at"] == "2026-09-08T09:30:00Z"
        assert row["last_review_at"] == "2026-09-08T10:30:00Z"

    def test_the_issues_it_closes(self, tool):
        row = tool.pr_row(pull(closingIssuesReferences={"nodes": [
            issue_ref(12), issue_ref(13)]}), KEYS)
        assert row["closes_issues"] == "AGILE-12;AGILE-13"

    def test_an_issues_own_key_label_wins(self, tool):
        """Explicit beats assumed, the same rule `rows()` follows -- so a pull
        request and the issue it closes cannot disagree about its name."""
        row = tool.pr_row(pull(closingIssuesReferences={"nodes": [
            issue_ref(12, labels=["key:ZMBNI"])]}), KEYS)
        assert row["closes_issues"] == "ZMBNI-12"

    def test_no_content_columns(self, tool):
        row = tool.pr_row(pull(), KEYS)
        assert not {"body", "diff", "patch"} & set(row)


class TestPrEventRows:
    def names(self, tool, data):
        return [r["event_name"] for r in tool.pr_event_rows(data, "AGILE", KEYS)]

    def test_a_bare_pull_request_opens_and_merges(self, tool):
        assert self.names(tool, pull()) == ["change-request-opened", "change-request-merged"]

    def test_an_open_one_has_no_merge_event(self, tool):
        assert self.names(tool, pull(state="OPEN", mergedAt=None)) == \
            ["change-request-opened"]

    def test_a_review_and_its_comments(self, tool):
        data = pull(mergedAt=None, reviews={"totalCount": 1, "nodes": [
            review(comments=[comment(ident="RC_1"), comment(ident="RC_2")])]})
        assert self.names(tool, data) == [
            "change-request-opened", "change-request-reviewed",
            "change-request-commented", "change-request-commented"]

    def test_the_review_state_rides_in_the_state_column(self, tool):
        """`APPROVED` and `CHANGES_REQUESTED` are the whole point: they say
        whether the second person accepted the first person's work."""
        for state in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"):
            rows = tool.pr_event_rows(
                pull(reviews={"totalCount": 1, "nodes": [review(state=state)]}),
                "AGILE", KEYS)
            reviewed = next(r for r in rows if r["event_name"] == "change-request-reviewed")
            assert reviewed["state"] == state

    def test_the_reviewer_is_the_actor_not_the_author(self, tool):
        rows = tool.pr_event_rows(
            pull(author={"login": "dev"},
                 reviews={"totalCount": 1, "nodes": [review(who="bea")]}), "AGILE", KEYS)
        by = {r["event_name"]: r["actor_name"] for r in rows}
        assert by["change-request-opened"] == "dev"
        assert by["change-request-reviewed"] == "bea"

    def test_a_pending_review_is_not_an_event(self, tool):
        """No `submittedAt` means nobody has submitted it yet."""
        data = pull(mergedAt=None, reviews={"totalCount": 1, "nodes": [review(at=None)]})
        assert "change-request-reviewed" not in self.names(tool, data)

    def test_they_are_scoped_to_the_pull_request(self, tool):
        rows = tool.pr_event_rows(pull(), "AGILE", KEYS)
        assert all(r["process_type"] == "pull-requests" for r in rows)
        assert all(r["process_id"] == 7 for r in rows)

    def test_the_issue_it_closes_rides_along(self, tool):
        rows = tool.pr_event_rows(
            pull(closingIssuesReferences={"nodes": [issue_ref(12)]}), "AGILE", KEYS)
        assert all(r["issue_key"] == "AGILE-12" for r in rows)


class TestEventHashUniqueness:
    def test_a_batch_of_comments_in_one_second_does_not_collide(self, tool):
        """GitHub timestamps to the second and a batch review submits every one
        of its comments at once, so `pr|kind|occurred|actor` collides for exactly
        the rows a reviewer left in one pass. The node id is what separates them
        -- the same defect measured on the issue side, where 187 rows collapsed
        to 181 distinct hashes."""
        same_second = [comment(at="2026-09-08T10:00:05Z", ident=f"RC_{n}") for n in range(5)]
        rows = tool.pr_event_rows(
            pull(reviews={"totalCount": 1, "nodes": [review(comments=same_second)]}),
            "AGILE", KEYS)
        assert len({r["event_hash"] for r in rows}) == len(rows)

    def test_two_reviews_in_one_second_do_not_collide(self, tool):
        rows = tool.pr_event_rows(pull(reviews={"totalCount": 2, "nodes": [
            review(at="2026-09-08T10:00:00Z", ident="RV_1"),
            review(at="2026-09-08T10:00:00Z", ident="RV_2")]}), "AGILE", KEYS)
        assert len({r["event_hash"] for r in rows}) == len(rows)

    def test_the_same_export_run_twice_hashes_the_same(self, tool):
        """An overlapping incremental run re-exports rows by design; the target
        resolves them latest-wins on the hash, so they must be stable."""
        data = pull(reviews={"totalCount": 1, "nodes": [review(comments=[comment()])]})
        first = [r["event_hash"] for r in tool.pr_event_rows(data, "AGILE", KEYS)]
        second = [r["event_hash"] for r in tool.pr_event_rows(data, "AGILE", KEYS)]
        assert first == second

    def test_it_does_not_collide_with_the_issue_side_row(self, tool):
        """`event_rows` emits its own `change-request-opened` for the issue a
        pull request closes. Both rows are wanted and they must not be one row."""
        issue = {"id": "I_1", "number": 12, "issue_key": "AGILE-12"}
        closing = [{"number": 7, "createdAt": "2026-09-08T09:00:00Z",
                    "author": {"login": "dev"}}]
        issue_side = tool.event_rows(issue, [], "AGILE", closing_prs=closing)
        pr_side = tool.pr_event_rows(pull(), "AGILE", KEYS)
        assert issue_side[0]["event_hash"] != pr_side[0]["event_hash"]
        assert issue_side[0]["process_type"] != pr_side[0]["process_type"]


class TestKeyForIssue:
    def test_the_label_wins(self, tool):
        assert tool.key_for_issue(12, "o/r", ["key:ZMBNI"], KEYS) == "ZMBNI-12"

    def test_then_the_repository_default(self, tool):
        assert tool.key_for_issue(12, "o/r", [], KEYS) == "AGILE-12"

    def test_and_a_repo_with_no_key_falls_back_to_the_github_reference(self, tool):
        assert tool.key_for_issue(12, "o/other", [], KEYS) == "o/other#12"
