"""Every Mermaid label survives GitHub's renderer. AGILE-260.

The README's sprint diagram failed with "Unable to render rich display" for
two months: `class SprintField["ProjectV2IterationField &quot;Sprint&quot;"]`.
GitHub decodes `&quot;` to `"` before Mermaid parses the block, so Mermaid saw
quotes nested inside a quoted label. Nothing checked. This is the offline half;
rendering every block is the other, done before merging.
"""

from __future__ import annotations

import html
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ["README.md", "USER_GUIDE.md"]


def blocks():
    for doc in DOCS:
        text = (ROOT / doc).read_text()
        for match in re.finditer(r"```mermaid\n(.*?)```", text, re.S):
            yield doc, text[:match.start()].count("\n") + 1, match.group(1)


#: A bracketed, quoted label: `Name["..."]`, as classDiagram and flowchart write them.
LABEL = re.compile(r'\["(.*?)"\]')


def test_there_are_diagrams_to_check():
    assert len(list(blocks())) >= 4


@pytest.mark.parametrize("doc,line,body", list(blocks()),
                         ids=[f"{d}:{n}" for d, n, _ in blocks()])
def test_no_label_carries_a_quote_once_github_decodes_it(doc, line, body):
    """Decoded as GitHub decodes it, a label may hold no `"` of its own."""
    decoded = html.unescape(body)
    for row in decoded.splitlines():
        for match in re.finditer(r'\["', row):
            rest = row[match.end():]
            inner = rest[:rest.find('"]')] if '"]' in rest else rest
            assert '"' not in inner, f"{doc}:{line}: nested quote in label: {row.strip()}"


def test_the_sprint_diagram_names_its_field_without_quotes():
    readme = (ROOT / "README.md").read_text()
    assert 'class SprintField["ProjectV2IterationField (Sprint)"]' in readme
