"""`initiative reconcile` sees the whole tree and every labelled issue (#309).

The tree query asked for `first: 100` at each level and never looked at
`hasNextPage`, so a 101st epic was silently missing -- with every story under
it -- and its labels were never added. The search for issues already carrying
the label stopped at `--limit 200`, so a stale label on the 201st was never
removed. Both failures are silent, which is the whole problem #309 is about.

An ordinary tree still costs one call: the first page of every level comes in
the one query, and a further page is asked for only where a level was full.
"""

from __future__ import annotations

import pytest


def node(number, *, children=None, more=None, repo="o/r"):
    """A tree node. `children` is the first page; `more` names the cursor of a
    next page, which makes the page report itself full."""
    out = {"id": f"I_{number}", "number": number, "repository": {"nameWithOwner": repo},
           "labels": {"nodes": []}}
    if children is not None:
        out["subIssues"] = {"pageInfo": {"hasNextPage": more is not None, "endCursor": more},
                            "nodes": children}
    return out


@pytest.fixture
def walk(monkeypatch, tool):
    """Run `initiative_tree` against a root and a table of further pages."""
    def go(root, pages=None):
        pages, asked = pages or {}, []

        def graphql(query, **variables):
            if "repository(owner" in query:
                asked.append("tree")
                return {"data": {"repository": {"issue": root}}}
            asked.append((variables["id"], variables["after"], variables["deep"]))
            nodes, more = pages[(variables["id"], variables["after"])]
            return {"data": {"node": {"subIssues": {
                "pageInfo": {"hasNextPage": more is not None, "endCursor": more},
                "nodes": nodes}}}}

        monkeypatch.setattr(tool, "graphql", graphql)
        found = tool.initiative_tree({"repo": "o/r", "number": 1, "slug": "big"})
        return [n["number"] for n in found], asked
    return go


class TestTheTreePages:
    def test_an_ordinary_tree_is_one_call(self, walk):
        numbers, asked = walk(node(1, children=[node(2, children=[node(3, children=[])])]))
        assert numbers == [1, 2, 3] and asked == ["tree"]

    def test_epics_past_the_first_page_are_found_with_their_stories(self, walk):
        """The 101st epic, and the story under it -- both lost before."""
        root = node(1, children=[node(2, children=[])], more="c1")
        pages = {("I_1", "c1"): ([node(102, children=[node(103, children=[])])], None)}
        numbers, asked = walk(root, pages)
        assert numbers == [1, 2, 102, 103]
        assert asked == ["tree", ("I_1", "c1", True)], "a later epic brings its stories"

    def test_stories_past_the_first_page_are_found(self, walk):
        root = node(1, children=[node(2, children=[node(3)], more="c2")])
        pages = {("I_2", "c2"): ([node(4)], "c3"), ("I_2", "c3"): ([node(5)], None)}
        numbers, asked = walk(root, pages)
        assert numbers == [1, 2, 3, 4, 5]
        assert asked == ["tree", ("I_2", "c2", False), ("I_2", "c3", False)], \
            "a story's own children are tasks, which the tree does not reach"

    def test_an_epic_from_a_later_page_pages_its_own_stories(self, walk):
        root = node(1, children=[], more="c1")
        pages = {("I_1", "c1"): ([node(102, children=[node(103)], more="c9")], None),
                 ("I_102", "c9"): ([node(104)], None)}
        numbers, _asked = walk(root, pages)
        assert numbers == [1, 102, 103, 104]

    def test_tasks_are_not_walked(self, walk):
        """Two levels below the initiative, as before: a task is off the board."""
        root = node(1, children=[node(2, children=[node(3, children=[node(4)])])])
        numbers, _asked = walk(root)
        assert numbers == [1, 2, 3]


class TestTheSearchHasNoCap:
    @pytest.fixture
    def search(self, monkeypatch, tool):
        def go(output):
            seen = []
            monkeypatch.setattr(tool, "gh", lambda args, **k: seen.append(args) or output)
            return tool.issues_labelled("o/r", "initiative:big"), seen[0]
        return go

    def test_every_page_is_read(self, search):
        numbers, args = search("".join(f"{n}\n" for n in range(1, 251)))
        assert numbers == list(range(1, 251))
        assert "--paginate" in args

    def test_it_asks_for_closed_issues_too(self, search):
        """A stale label on a closed issue still puts it on the initiative's board."""
        _numbers, args = search("")
        assert "state=all" in args and "labels=initiative:big" in args

    def test_pull_requests_are_dropped(self, search):
        """The REST endpoint lists pull requests as issues."""
        _numbers, args = search("")
        assert "select(.pull_request | not)" in args[args.index("--jq") + 1]

    def test_none_is_empty(self, search):
        assert search("")[0] == []


def item(number, *labels, parent=None, repo="o/r", parent_repo=None):
    """A `fetch_items` item. `parent` is `(number, labels)`, in `parent_repo`,
    which defaults to the item's own."""
    if parent is not None:
        parent = {"number": parent[0], "repository": {"nameWithOwner": parent_repo or repo},
                  "labels": {"nodes": [{"name": n} for n in parent[1]]}}
    return {"id": f"PVTI_{number}", "content": {
        "__typename": "Issue", "number": number, "repository": {"nameWithOwner": repo},
        "labels": {"nodes": [{"name": n} for n in labels]}, "parent": parent}}


INITIATIVE = ("type:initiative", "initiative:big")


class TestSyncStampsMissingLabels:
    """`sync` adds the label the tree says is missing, and never removes one.

    Without it the label was kept only by `initiative reconcile`, run by hand, so
    issues made before stories inherited the label -- and parents set in the web
    UI -- stayed unlabelled: 29 of them on one board.
    """

    @pytest.fixture
    def stamp(self, monkeypatch, tool, capsys):
        def go(items, *, repos=("o/r",), dry_run=False):
            edits, ensured = [], []
            monkeypatch.setattr(tool, "fetch_items", lambda *a, **k: ("t", items))
            monkeypatch.setattr(tool, "ensure_labels", lambda repo, labels: ensured.append(repo))
            monkeypatch.setattr(tool, "gh", lambda args, **k: edits.append(args) or "")
            tool.stamp_initiative_labels("o", 1, list(repos), dry_run=dry_run)
            added = [(a[2], a[a.index("--repo") + 1], a[a.index("--add-label") + 1])
                     for a in edits if a[:2] == ["issue", "edit"]]
            assert not any("--remove-label" in a for a in edits)
            return added, ensured, capsys.readouterr().out
        return go

    def test_a_tree_member_without_the_label_gets_it(self, stamp):
        added, _ensured, out = stamp([
            item(1, *INITIATIVE),
            item(2, "type:epic", parent=(1, INITIATIVE)),
            item(3, "type:story", parent=(2, ["type:epic"]))])
        assert added == [("2", "o/r", "initiative:big"), ("3", "o/r", "initiative:big")]
        assert "labelled 2 issue(s)" in out

    def test_nothing_missing_is_silent(self, stamp):
        added, _ensured, out = stamp([
            item(1, *INITIATIVE),
            item(2, "type:epic", "initiative:big", parent=(1, INITIATIVE))])
        assert added == [] and out == ""

    def test_a_stale_label_is_left_for_reconcile(self, stamp):
        """Removing is a correction, and `sync` promises to be additive."""
        added, _ensured, _out = stamp([item(1, *INITIATIVE),
                                       item(4, "type:story", "initiative:big")])
        assert added == []

    def test_an_undetermined_chain_adds_nothing(self, stamp):
        added, _ensured, _out = stamp([item(3, "type:story", parent=(2, ["type:epic"]))])
        assert added == []

    def test_a_task_is_skipped(self, stamp):
        added, _ensured, _out = stamp([
            item(1, *INITIATIVE),
            item(2, "type:story", "initiative:big", parent=(1, INITIATIVE)),
            item(9, "type:task", parent=(2, ["type:story", "initiative:big"]))])
        assert added == []

    def test_only_the_repositories_this_run_covers(self, stamp):
        """`sync --repo` narrows the writes as it narrows the adds."""
        items = [item(1, *INITIATIVE),
                 item(2, "type:epic", parent=(1, INITIATIVE)),
                 item(5, "type:epic", repo="o/other", parent=(1, INITIATIVE), parent_repo="o/r")]
        added, _ensured, _out = stamp(items, repos=("o/r",))
        assert added == [("2", "o/r", "initiative:big")]

    def test_a_dry_run_writes_nothing(self, stamp):
        added, ensured, out = stamp([item(1, *INITIATIVE),
                                     item(2, "type:epic", parent=(1, INITIATIVE))],
                                    dry_run=True)
        assert added == [] and ensured == []
        assert "would label o/r#2  +initiative:big" in out

    def test_the_label_is_ensured_once_per_repository(self, stamp):
        _added, ensured, _out = stamp([
            item(1, *INITIATIVE),
            item(2, "type:epic", parent=(1, INITIATIVE)),
            item(3, "type:epic", parent=(1, INITIATIVE))])
        assert ensured == ["o/r"]
