"""Tenant-scope regression tests for ``services/graph/app/overlay_resolver.py``.

Covers issues #1278, #1289, #1294, #1298 — four Cypher queries that
anchored on a tenant-scoped node but left subsequent joined nodes
(``TenantControl``, ``ControlMapping``, ``CustomerProduct``) without a
``tenant_id`` predicate. On Community Edition (where Neo4jClient is
pinned to the shared ``neo4j`` database) a cross-tenant edge — whether
from an ingestion bug, a manually-created shared template, or a
mis-scoped MERGE — would surface another tenant's controls, mappings,
and product names inside this tenant's response.

Rather than spin up a real Neo4j cluster per test, we mock the client
and assert against the Cypher strings the resolver sends. This matches
the inspection pattern used in ``test_compliance_score_tenant_scope``
and ``test_trace_path_tenant_scope``.
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app import overlay_resolver as overlay_resolver_module
from services.graph.app.overlay_resolver import OverlayResolver


TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")


# ── Helpers ────────────────────────────────────────────────────────────────


def _flatten(query: str) -> str:
    """Strip Cypher ``//`` comments and collapse whitespace.

    The fixed queries wrap the inline ``{tenant_id: $tenant_id}`` filter
    across multiple lines for readability. Flatten so substring matches
    like ``"TenantControl {tenant_id: $tenant_id}"`` work regardless of
    whitespace/comment formatting in the source.
    """
    no_comments = re.sub(r"//[^\n]*", "", query)
    return " ".join(no_comments.split())


class _SingleResult:
    """Async-context-manager-free stand-in for a Neo4j `Result`.

    The resolver uses two access patterns on the result:
      * ``await result.single()`` for single-record queries
      * ``async for record in result:`` for streaming multi-record queries
    We provide both so the same fixture serves all four methods.
    """

    def __init__(self, records):
        self._records = list(records)

    async def single(self):
        return self._records[0] if self._records else None

    def __aiter__(self):
        async def _gen():
            for r in self._records:
                yield r

        return _gen()


def _make_session(records):
    """Construct a mock async session whose ``run`` returns records.

    Also records every ``run`` call on ``session.run.call_args_list`` so
    tests can inspect the Cypher and parameters.
    """
    session = AsyncMock()
    # run() returns a _SingleResult synchronously (awaiting the
    # AsyncMock returns the mock's return_value).
    result = _SingleResult(records)
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _make_client(*per_call_records):
    """Make a Neo4jClient mock with scripted per-call record sets.

    Each call to ``client.session()`` yields a fresh mock session whose
    ``run(...)`` returns the next record set. The real resolver opens a
    new session per query, so scripting per-call keeps the fixture
    aligned with production control flow.
    """
    client = MagicMock()
    # Each session() call returns the same async-ctx-manager session so
    # call_args_list accumulates across all queries on this client. A
    # shared session is simpler and still lets us assert on the Cypher.
    session = _make_session([])
    session.run = AsyncMock(side_effect=[_SingleResult(r) for r in per_call_records])
    client.session = MagicMock(return_value=session)
    client.close = AsyncMock()
    return client, session


def _install_client_mocks(tenant_records, global_records):
    """Patch Neo4jClient so tenant vs global construction yields scripted mocks.

    The resolver instantiates ``Neo4jClient(database=self.tenant_db)`` for
    the tenant database and ``Neo4jClient(database=self.global_db)`` for
    the global one. We route via the ``database`` kwarg to return the
    right mock.
    """
    tenant_client, tenant_session = _make_client(*tenant_records)
    global_client, global_session = _make_client(*global_records)

    def _factory(database=None, **kwargs):
        # The OverlayResolver constructor computes both db names via
        # Neo4jClient.get_*_database_name; we compare against those.
        if database and database.startswith("reg_tenant_"):
            return tenant_client
        return global_client

    return _factory, tenant_session, global_session


# ── #1298 — get_regulatory_requirements mapping_query ──────────────────────


@pytest.mark.asyncio
async def test_get_regulatory_requirements_mapping_query_scopes_control_and_mapping():
    """#1298: both TenantControl and ControlMapping must be tenant-scoped,
    and ``$tenant_id`` must be bound on every invocation of the mapping
    query inside the per-control loop."""
    # Tenant session needs two scripted results:
    #   1) product_controls_query → one product with one control
    #   2) mapping_query → a single mapping record
    product_record = {
        "product": {"id": "prod-1", "tenant_id": str(TENANT_A)},
        "controls": [{"id": "ctrl-1", "tenant_id": str(TENANT_A)}],
    }
    mapping_record = {
        "mapping": {
            "provision_hash": "abc123",
            "tenant_id": str(TENANT_A),
        }
    }
    factory, tenant_session, _ = _install_client_mocks(
        tenant_records=[[product_record], [mapping_record]],
        global_records=[[]],
    )

    with patch.object(overlay_resolver_module, "Neo4jClient") as mock_cls:
        mock_cls.side_effect = factory
        mock_cls.get_global_database_name = MagicMock(return_value="neo4j")
        mock_cls.get_tenant_database_name = MagicMock(
            return_value=f"reg_tenant_{TENANT_A}"
        )

        resolver = OverlayResolver(tenant_id=TENANT_A)
        await resolver.get_regulatory_requirements(
            product_id=uuid.UUID("22222222-2222-2222-2222-222222222222")
        )

    # Second run() call is the mapping_query (first is product_controls_query).
    assert tenant_session.run.call_count >= 2
    mapping_cypher = _flatten(tenant_session.run.call_args_list[1].args[0])
    mapping_kwargs = tenant_session.run.call_args_list[1].args[1]

    assert "TenantControl {id: $control_id, tenant_id: $tenant_id}" in mapping_cypher, (
        f"#1298: mapping_query must scope TenantControl by tenant_id. Cypher:\n{mapping_cypher}"
    )
    assert "ControlMapping {tenant_id: $tenant_id}" in mapping_cypher, (
        f"#1298: mapping_query must scope ControlMapping by tenant_id. Cypher:\n{mapping_cypher}"
    )
    # Params dict must thread tenant_id — production bug was that the loop
    # only passed {"control_id": control_id}.
    assert mapping_kwargs.get("tenant_id") == str(TENANT_A), (
        f"#1298: mapping_query must bind $tenant_id to caller's tenant; got {mapping_kwargs!r}"
    )


# ── #1278 — get_provision_with_overlays tenant_query ───────────────────────


@pytest.mark.asyncio
async def test_get_provision_with_overlays_scopes_control_and_product():
    """#1278: TenantControl and CustomerProduct in the overlay tenant
    query must both filter by tenant_id — the mapping node was scoped
    but the joined nodes leaked."""
    # Global session: one provision record; tenant session: zero overlays.
    provision_record = {
        "prov": {"hash": "hash-1"},
        "doc": None,
        "concepts": [],
        "jurisdictions": [],
    }
    factory, tenant_session, _ = _install_client_mocks(
        tenant_records=[[]],
        global_records=[[provision_record]],
    )

    with patch.object(overlay_resolver_module, "Neo4jClient") as mock_cls:
        mock_cls.side_effect = factory
        mock_cls.get_global_database_name = MagicMock(return_value="neo4j")
        mock_cls.get_tenant_database_name = MagicMock(
            return_value=f"reg_tenant_{TENANT_A}"
        )

        resolver = OverlayResolver(tenant_id=TENANT_A)
        await resolver.get_provision_with_overlays(provision_hash="hash-1")

    # Tenant session ran exactly once (the overlay lookup).
    assert tenant_session.run.call_count == 1
    overlay_cypher = _flatten(tenant_session.run.call_args.args[0])
    overlay_kwargs = tenant_session.run.call_args.args[1]

    assert "TenantControl {tenant_id: $tenant_id}" in overlay_cypher, (
        f"#1278: overlay query must scope TenantControl by tenant_id. Cypher:\n{overlay_cypher}"
    )
    assert "CustomerProduct {tenant_id: $tenant_id}" in overlay_cypher, (
        f"#1278: overlay query must scope CustomerProduct by tenant_id. Cypher:\n{overlay_cypher}"
    )
    assert overlay_kwargs.get("tenant_id") == str(TENANT_A)


# ── #1289 — get_control_details OPTIONAL MATCH ─────────────────────────────


@pytest.mark.asyncio
async def test_get_control_details_scopes_optional_matches():
    """#1289: OPTIONAL MATCH clauses for ControlMapping and CustomerProduct
    must both filter by tenant_id. Anchor TenantControl was already scoped;
    the OPTIONAL joins were not."""
    control_record = {
        "control": {"id": "ctrl-1", "tenant_id": str(TENANT_A)},
        "mappings": [],
        "products": [],
    }
    factory, tenant_session, _ = _install_client_mocks(
        tenant_records=[[control_record]],
        global_records=[[]],
    )

    with patch.object(overlay_resolver_module, "Neo4jClient") as mock_cls:
        mock_cls.side_effect = factory
        mock_cls.get_global_database_name = MagicMock(return_value="neo4j")
        mock_cls.get_tenant_database_name = MagicMock(
            return_value=f"reg_tenant_{TENANT_A}"
        )

        resolver = OverlayResolver(tenant_id=TENANT_A)
        await resolver.get_control_details(
            control_id=uuid.UUID("33333333-3333-3333-3333-333333333333")
        )

    cypher = _flatten(tenant_session.run.call_args.args[0])
    kwargs = tenant_session.run.call_args.args[1]

    assert "ControlMapping {tenant_id: $tenant_id}" in cypher, (
        f"#1289: OPTIONAL MATCH on ControlMapping must scope by tenant_id. Cypher:\n{cypher}"
    )
    assert "CustomerProduct {tenant_id: $tenant_id}" in cypher, (
        f"#1289: OPTIONAL MATCH on CustomerProduct must scope by tenant_id. Cypher:\n{cypher}"
    )
    # Anchor must still be tenant-scoped (defense in depth).
    assert "TenantControl {id: $control_id, tenant_id: $tenant_id}" in cypher
    assert kwargs.get("tenant_id") == str(TENANT_A)


# ── #1294 — get_compliance_gaps tenant_query ───────────────────────────────


@pytest.mark.asyncio
async def test_get_compliance_gaps_scopes_control_and_mapping():
    """#1294: TenantControl and ControlMapping on the compliance-gap
    lookup must both filter by tenant_id. Missing filters under-report
    genuine gaps — a cross-tenant MAPS_TO makes us believe provisions
    are already addressed when they're not."""
    gap_record = {"mapped_hashes": []}
    factory, tenant_session, _ = _install_client_mocks(
        tenant_records=[[gap_record]],
        global_records=[[]],
    )

    with patch.object(overlay_resolver_module, "Neo4jClient") as mock_cls:
        mock_cls.side_effect = factory
        mock_cls.get_global_database_name = MagicMock(return_value="neo4j")
        mock_cls.get_tenant_database_name = MagicMock(
            return_value=f"reg_tenant_{TENANT_A}"
        )

        resolver = OverlayResolver(tenant_id=TENANT_A)
        await resolver.get_compliance_gaps(
            product_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
            jurisdiction="US",
        )

    cypher = _flatten(tenant_session.run.call_args.args[0])
    kwargs = tenant_session.run.call_args.args[1]

    assert "TenantControl {tenant_id: $tenant_id}" in cypher, (
        f"#1294: compliance-gap query must scope TenantControl by tenant_id. Cypher:\n{cypher}"
    )
    assert "ControlMapping {tenant_id: $tenant_id}" in cypher, (
        f"#1294: compliance-gap query must scope ControlMapping by tenant_id. Cypher:\n{cypher}"
    )
    # Anchor product still scoped.
    assert "CustomerProduct {id: $product_id, tenant_id: $tenant_id}" in cypher
    assert kwargs.get("tenant_id") == str(TENANT_A)


# ── Defense-in-depth: every tenant-database query binds $tenant_id ─────────


@pytest.mark.asyncio
async def test_every_tenant_query_binds_tenant_id_parameter():
    """Sanity check: no query sent to the tenant database should omit the
    ``tenant_id`` parameter. If a future refactor drops the binding from
    even one query, the tenant filters become silently inert."""
    product_record = {
        "product": {"id": "prod-1", "tenant_id": str(TENANT_A)},
        "controls": [{"id": "ctrl-1", "tenant_id": str(TENANT_A)}],
    }
    mapping_record = {
        "mapping": {"provision_hash": "h", "tenant_id": str(TENANT_A)}
    }
    factory, tenant_session, _ = _install_client_mocks(
        tenant_records=[[product_record], [mapping_record]],
        global_records=[[]],
    )

    with patch.object(overlay_resolver_module, "Neo4jClient") as mock_cls:
        mock_cls.side_effect = factory
        mock_cls.get_global_database_name = MagicMock(return_value="neo4j")
        mock_cls.get_tenant_database_name = MagicMock(
            return_value=f"reg_tenant_{TENANT_A}"
        )

        resolver = OverlayResolver(tenant_id=TENANT_A)
        await resolver.get_regulatory_requirements(
            product_id=uuid.UUID("22222222-2222-2222-2222-222222222222")
        )

    # Every call to the tenant session must bind tenant_id.
    for i, call in enumerate(tenant_session.run.call_args_list):
        params = call.args[1] if len(call.args) > 1 else call.kwargs
        assert params.get("tenant_id") == str(TENANT_A), (
            f"tenant-database query #{i} missing $tenant_id binding; "
            f"params were {params!r}; Cypher:\n{call.args[0]}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
