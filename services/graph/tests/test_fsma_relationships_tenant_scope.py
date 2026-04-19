"""Regression tests for ``FSMARelationships`` cross-tenant edge bug (#1284).

Previously, all 10 relationship templates MATCHed nodes by identifier
only (``tlc``, ``event_id``, ``gln``, etc.). Because uniqueness
constraints are ``(identifier, tenant_id)`` — not the identifier alone
— two tenants CAN share the same TLC or event_id. The MATCH picked
whichever node the planner found first, and the resulting MERGE
created a cross-tenant edge between tenant A's event and tenant B's
lot.

That corrupts tenant B's graph, and when tenant A later runs a
variable-length trace query, the walker slides across the foreign
edge and leaks B's nodes into A's response — a data-disclosure
attack, not just a consistency bug.

These tests lock in:

1. Every template contains ``tenant_id: $tenant_id`` on BOTH MATCH
   nodes (not just one).
2. Every call site passes ``tenant_id`` as a kwarg — a refactor that
   drops the kwarg would silently make the scoped MATCH match no
   rows, turning the MERGE into a no-op. Better than a cross-tenant
   edge, but still a regression worth catching.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.models.fsma_nodes import FSMARelationships


TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


def _flatten(cypher: str) -> str:
    """Collapse Cypher whitespace for substring assertions."""
    return " ".join(cypher.split())


# ── Template inspection ────────────────────────────────────────────────────

ALL_TEMPLATES = [
    ("LOT_UNDERWENT_EVENT", FSMARelationships.LOT_UNDERWENT_EVENT),
    ("EVENT_PRODUCED_LOT", FSMARelationships.EVENT_PRODUCED_LOT),
    ("EVENT_CONSUMED_LOT", FSMARelationships.EVENT_CONSUMED_LOT),
    ("EVENT_OCCURRED_AT", FSMARelationships.EVENT_OCCURRED_AT),
    ("SHIPPED_FROM", FSMARelationships.SHIPPED_FROM),
    ("SHIPPED_TO", FSMARelationships.SHIPPED_TO),
    ("LOT_IS_PRODUCT", FSMARelationships.LOT_IS_PRODUCT),
    ("DOCUMENT_EVIDENCES", FSMARelationships.DOCUMENT_EVIDENCES),
    ("LOT_ASSIGNED_BY_GLN", FSMARelationships.LOT_ASSIGNED_BY_GLN),
    ("LOT_ASSIGNED_BY_FDA_REG", FSMARelationships.LOT_ASSIGNED_BY_FDA_REG),
]


@pytest.mark.parametrize("name,cypher", ALL_TEMPLATES)
def test_every_template_scopes_both_match_nodes(name, cypher):
    """#1284: each template has exactly two MATCH clauses; both must
    carry ``tenant_id: $tenant_id`` inside the map literal.

    Using the inline-map syntax (not a separate WHERE) means Neo4j can
    use the composite (identifier, tenant_id) uniqueness index for
    constant-time lookup *and* makes the tenant predicate impossible
    to forget when editing the template.
    """
    flat = _flatten(cypher)

    # There are exactly 2 MATCH clauses per template.
    match_count = flat.count("MATCH (")
    assert match_count == 2, (
        f"#1284: {name} expected 2 MATCH clauses, found {match_count}"
    )

    # Both MATCHes must include tenant_id in the map.
    tenant_occurrences = flat.count("tenant_id: $tenant_id")
    assert tenant_occurrences >= 2, (
        f"#1284: {name} must scope BOTH MATCH nodes by tenant_id "
        f"(found {tenant_occurrences}). Cypher:\n{cypher}"
    )


@pytest.mark.parametrize("name,cypher", ALL_TEMPLATES)
def test_no_identifier_only_match_remains(name, cypher):
    """Catch future refactors that accidentally drop the tenant_id
    predicate from a MATCH. The pattern to reject is
    ``MATCH (x:Label {key: $key})`` with no ``tenant_id`` in the map."""
    # Remove whitespace/newlines so we can eyeball MATCH maps.
    flat = _flatten(cypher)

    # Every MATCH (...:Label { ... }) block must contain tenant_id.
    # Strategy: find each "MATCH (...)" segment, verify tenant_id in it.
    match_blocks = re.findall(r"MATCH\s*\([^)]+\)", flat)
    assert len(match_blocks) == 2, (
        f"#1284: {name} expected 2 MATCH blocks, got {len(match_blocks)}"
    )
    for block in match_blocks:
        assert "tenant_id" in block, (
            f"#1284: {name} has a MATCH block without tenant_id: {block}"
        )


# ── Call-site inspection (router) ──────────────────────────────────────────


def test_traceability_router_source_passes_tenant_id_to_relationships():
    """#1284: every ``session.run(FSMARelationships.*)`` call in
    ``routers/fsma/traceability.py`` must include ``tenant_id=`` as a
    kwarg on the same call expression.

    Static source inspection (not runtime) because the mobile ``/event``
    handler does heavy validation / canonical bridging before it reaches
    the relationship calls, and booting all of that in a unit test is
    fragile. The failure mode we care about — a reviewer deleting the
    ``tenant_id=...`` kwarg — is structural, not behavioural.
    """
    src_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routers"
        / "fsma"
        / "traceability.py"
    )
    source = src_path.read_text()

    # Find every call like `session.run(FSMARelationships.NAME, ...)`.
    # The regex captures the full kwargs body up to the matching close-paren.
    pattern = re.compile(
        r"session\.run\(\s*FSMARelationships\.[A-Z_]+\s*,(.*?)\)",
        re.DOTALL,
    )
    matches = pattern.findall(source)
    assert matches, (
        "expected at least one session.run(FSMARelationships.*) call in "
        "traceability.py; did the router change shape?"
    )
    for body in matches:
        assert "tenant_id" in body, (
            f"#1284: relationship call in traceability.py missing tenant_id "
            f"kwarg. Call body:\n{body}"
        )


# ── Call-site inspection (consumer) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_fsma_consumer_passes_tenant_id_to_relationships():
    """#1284: ingest_fsma_event (the Kafka consumer path) must also
    pass tenant_id to every relationship template. The consumer is the
    high-volume write path — a miss here would let Avro-consumer-level
    producers (with weaker auth than HTTP) forge cross-tenant edges."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.run = AsyncMock(return_value=MagicMock())

    client = MagicMock()
    client.session = MagicMock(return_value=session)

    event = {
        "document_id": "doc-1284-test",
        "document_type": "INVOICE",
        "timestamp": "2026-04-18T00:00:00Z",
        "tenant_id": TENANT_A,
        "ctes": [
            {
                "type": "SHIPPING",
                "confidence": 0.99,
                "kdes": {
                    "traceability_lot_code": "LOT-1284",
                    "event_date": "2026-04-18",
                    "product_description": "Test product",
                    "quantity": 10.0,
                    "unit_of_measure": "kg",
                    "location_identifier": "urn:gln:0614141999996",
                },
            }
        ],
    }

    from services.graph.app.consumers.fsma_consumer import ingest_fsma_event

    await ingest_fsma_event(client, event)

    # Collect relationship-template calls.
    relationship_calls = []
    for call in session.run.call_args_list:
        args = call.args
        if args and isinstance(args[0], str):
            cypher = args[0]
            if (
                ":UNDERWENT]" in cypher
                or ":OCCURRED_AT]" in cypher
                or ":EVIDENCES]" in cypher
            ):
                relationship_calls.append(call)

    assert len(relationship_calls) >= 2, (
        f"expected ≥2 relationship calls, got {len(relationship_calls)}: "
        f"{[c.args[0][:60] for c in relationship_calls]}"
    )
    for call in relationship_calls:
        kwargs = call.kwargs
        assert kwargs.get("tenant_id") == TENANT_A, (
            f"#1284: consumer relationship call missing/wrong tenant_id; "
            f"cypher={call.args[0][:80]!r} kwargs={kwargs!r}"
        )


# ── Cross-tenant isolation property ────────────────────────────────────────


def test_templates_never_accept_implicit_cross_tenant_match():
    """Final belt-and-braces check: no template relies on an implicit
    'match first Lot with this TLC' semantic. Every MATCH on a
    tenant-scoped label must carry tenant_id in the map.

    Labels that ARE tenant-scoped (per the uniqueness constraints in
    FSMA_CONSTRAINTS): Lot, Facility, TraceEvent, Document.
    """
    tenant_scoped_labels = {"Lot", "Facility", "TraceEvent", "Document", "FoodItem"}
    for name, cypher in ALL_TEMPLATES:
        flat = _flatten(cypher)
        # For each label, wherever it appears as a MATCH target, the
        # map must contain tenant_id.
        for label in tenant_scoped_labels:
            # e.g. match "MATCH (l:Lot { ... })" — look inside the map.
            pattern = re.compile(rf"MATCH\s*\([^)]*:{label}\s*\{{([^}}]+)\}}")
            for map_body in pattern.findall(flat):
                assert "tenant_id" in map_body, (
                    f"#1284: {name} MATCHes :{label} without tenant_id in map; "
                    f"map_body={map_body!r}"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
