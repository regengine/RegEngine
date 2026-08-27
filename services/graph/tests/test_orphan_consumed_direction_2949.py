"""#2949: orphan detection's outbound-consumption guard points the wrong way.

``find_orphaned_lots`` excludes lots that show outbound activity. One of those
guards is "was consumed by a transformation", written as::

    AND NOT EXISTS { MATCH (l)-[:CONSUMED]->(trans:TraceEvent) }

but ``FSMARelationships.EVENT_CONSUMED_LOT`` persists the edge the other way::

    MERGE (e)-[:CONSUMED]->(l)          # TraceEvent -> Lot

so the ``NOT EXISTS`` is unconditionally true and the guard is dead code. The
inbound branch of the *same* query gets the direction right
(``(trans:TraceEvent)-[:PRODUCED]->(l)``), which is what makes this an
inversion rather than a deliberate reversed convention.

These tests derive the expected direction **from the writer template itself**
rather than hardcoding an arrow, so they stay correct if the schema is ever
deliberately reversed — the reader would simply have to follow. They are
structural rather than data-level: ``find_orphaned_lots`` is a single query
built from nested ``EXISTS`` sub-queries, an ``OPTIONAL MATCH``, a ``collect``
and a date cutoff, and standing up a fake evaluator for exactly that query
would amount to re-implementing it in the test — the assertion would then only
prove the test agrees with itself. Cross-checking reader against writer proves
something the code cannot fake.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma.data_quality import find_orphaned_lots  # noqa: E402
from services.graph.app.models.fsma_nodes import FSMARelationships  # noqa: E402

TENANT = "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_orphan_query() -> str:
    """Run ``find_orphaned_lots`` against a mock and return the Cypher it sent."""
    mock_client = MagicMock()
    mock_session = AsyncMock()

    mock_result = AsyncMock()
    mock_result.__aiter__ = lambda self: self
    mock_result.__anext__ = AsyncMock(side_effect=StopAsyncIteration)
    mock_session.run = AsyncMock(return_value=mock_result)

    mock_client.session = MagicMock(return_value=mock_session)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    asyncio.run(find_orphaned_lots(mock_client, tenant_id=TENANT, days_stagnant=30))
    return mock_session.run.call_args.args[0]


def _flatten(query: str) -> str:
    return " ".join(re.sub(r"//[^\n]*", "", query).split())


def _writer_direction(template: str, rel_type: str) -> Tuple[str, str]:
    """Return ``(source_label, target_label)`` for ``rel_type`` in a writer template.

    Reads the arrow out of the repository's own MERGE template, so the
    expectation below is the schema's, not the test author's.
    """
    labels: Dict[str, str] = dict(re.findall(r"MATCH\s*\(\s*(\w+):(\w+)", template))
    merge = re.search(rf"MERGE\s*\(\s*(\w+)\s*\)-\[:{rel_type}\]->\(\s*(\w+)\s*\)", template)
    assert merge is not None, f"{rel_type} writer template is not a simple `MERGE (a)-[:{rel_type}]->(b)`"
    return labels[merge.group(1)], labels[merge.group(2)]


_REL_USE_RE_TMPL = r"\(\s*(?P<left>[^()]*?)\s*\)\s*(?P<lhs><-|-)\[\s*:{rel}\s*\]\s*(?P<rhs>->|-)\s*\(\s*(?P<right>[^()]*?)\s*\)"


def _relationship_uses(query: str, rel_type: str) -> List[Tuple[str, str]]:
    """Every ``rel_type`` traversal in ``query`` as ``(source_token, target_token)``."""
    uses: List[Tuple[str, str]] = []
    for m in re.finditer(_REL_USE_RE_TMPL.format(rel=rel_type), _flatten(query)):
        left, right = m.group("left"), m.group("right")
        if m.group("lhs") == "<-":
            uses.append((right, left))
        else:
            uses.append((left, right))
    return uses


def _role(token: str, lot_var: str = "l") -> str:
    """Classify a node token as ``'Lot'``, ``'TraceEvent'`` or its literal text."""
    label = re.search(r":(\w+)", token)
    if label:
        return label.group(1)
    var = token.split()[0] if token.split() else token
    return "Lot" if var == lot_var else var


# ---------------------------------------------------------------------------
# Direction: reader must agree with writer
# ---------------------------------------------------------------------------


def test_consumed_guard_matches_the_direction_the_writer_persists():
    """AC #1: a lot reached by ``(e:TraceEvent)-[:CONSUMED]->(lot)`` is not an orphan."""
    source_label, target_label = _writer_direction(FSMARelationships.EVENT_CONSUMED_LOT, "CONSUMED")
    assert (source_label, target_label) == ("TraceEvent", "Lot")

    uses = _relationship_uses(_capture_orphan_query(), "CONSUMED")
    assert uses, "expected find_orphaned_lots to still guard on a CONSUMED edge"

    for src, dst in uses:
        assert (_role(src), _role(dst)) == (source_label, target_label), (
            f"#2949: find_orphaned_lots traverses CONSUMED as ({src})->({dst}), but "
            f"FSMARelationships.EVENT_CONSUMED_LOT persists it "
            f"{source_label} -> {target_label}. The NOT EXISTS is therefore "
            "unconditionally true and the outbound-consumption guard never fires."
        )


def test_consumed_guard_is_not_written_lot_to_event():
    """The specific inverted shape must be gone."""
    compact = _flatten(_capture_orphan_query())
    assert not re.search(r"\(\s*l\s*\)\s*-\[\s*:CONSUMED\s*\]->", compact), (
        f"#2949: the inverted `(l)-[:CONSUMED]->(trans:TraceEvent)` guard is still present:\n{compact}"
    )


def test_produced_branch_direction_is_unchanged():
    """Control: the inbound branch already agreed with the writer — keep it that way."""
    source_label, target_label = _writer_direction(FSMARelationships.EVENT_PRODUCED_LOT, "PRODUCED")
    uses = _relationship_uses(_capture_orphan_query(), "PRODUCED")
    assert uses
    for src, dst in uses:
        assert (_role(src), _role(dst)) == (source_label, target_label)


# ---------------------------------------------------------------------------
# AC #3 — every sub-query node is tenant-scoped
# ---------------------------------------------------------------------------


def _exists_blocks(query: str) -> List[str]:
    """Return the body of every ``EXISTS { ... }`` sub-query."""
    compact = _flatten(query)
    blocks: List[str] = []
    for m in re.finditer(r"EXISTS\s*\{", compact):
        depth = 0
        for idx in range(m.end() - 1, len(compact)):
            if compact[idx] == "{":
                depth += 1
            elif compact[idx] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(compact[m.end() : idx])
                    break
    return blocks


def test_every_subquery_node_is_tenant_scoped():
    """AC #3: a cross-tenant event must not suppress or create an orphan classification."""
    query = _capture_orphan_query()
    blocks = _exists_blocks(query)
    assert blocks, "expected find_orphaned_lots to use EXISTS sub-queries"

    for block in blocks:
        # Variables introduced inside the sub-query (i.e. carrying a label).
        introduced = {var for var, _label in re.findall(r"\(\s*(\w+):(\w+)", block)}
        for var in introduced:
            scoped = re.search(rf"\b{var}\.tenant_id\s*=\s*\$tenant_id", block) or re.search(
                rf"\(\s*{var}:\w+\s*\{{[^}}]*tenant_id\s*:\s*\$tenant_id", block
            )
            assert scoped, (
                f"#2949: sub-query variable `{var}` is not tenant-scoped, so a "
                f"cross-tenant event can flip an orphan classification. Block: {block!r}"
            )
