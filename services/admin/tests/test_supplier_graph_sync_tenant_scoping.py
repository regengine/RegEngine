"""Tenant-scoping unit tests for ``supplier_graph_sync``.

These tests assert that every Cypher MERGE/MATCH on a tenant-owned node
includes a ``tenant_id`` predicate in the match key (not just in a trailing
``SET`` clause). MERGE without a tenant predicate is a cross-tenant data-leak
vector — a second tenant reusing (or guessing) a node identifier would silently
hijack the original tenant's properties.

Companion issues: #1352, #1355, #1393, #1394, #1395, #1396.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.supplier_graph_sync import (
    CTE_EVENT_QUERY,
    FACILITY_FTL_SCOPING_QUERY,
    FACILITY_REQUIRED_CTES_QUERY,
    INVITE_ACCEPTED_QUERY,
    INVITE_CREATED_QUERY,
    SupplierGraphSync,
)


# ---------------------------------------------------------------------------
# Fake Neo4j driver/session plumbing — captures the (query, params) passed to
# session.run(...) so we can assert on the Cypher shape and its parameters
# without any real Neo4j.
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, record=None):
        self._record = record

    def single(self):
        return self._record


class _FakeSession:
    def __init__(self, sink, record=None):
        self._sink = sink
        self._record = record

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, params):
        self._sink.append((query, params))
        return _FakeResult(self._record)


class _FakeDriver:
    def __init__(self, record=None):
        self.calls: list[tuple[str, dict]] = []
        self._record = record

    def session(self):
        return _FakeSession(self.calls, self._record)


# ---------------------------------------------------------------------------
# Cypher pattern assertions (static — no driver needed).
#
# Helper: for each MERGE/MATCH pattern that targets a tenant-owned node label,
# assert the node's property map contains ``tenant_id: $tenant_id``. This is
# the belt-and-suspenders defense that closes the UUID-guess attack even if a
# later engineer forgets a WHERE clause.
# ---------------------------------------------------------------------------


_TENANT_OWNED_LABELS = {
    "SupplierFacility",
    "SupplierContact",
    "PendingSupplierInvite",
}


def _patterns_for_label(query: str, label: str) -> list[str]:
    """Return every MERGE/MATCH node pattern `(var:Label {...})` in the query."""
    # Match either MERGE or MATCH (not OPTIONAL MATCH is captured because
    # OPTIONAL MATCH ends with MATCH).
    pattern = re.compile(
        r"(?:MERGE|MATCH)\s*\(\s*\w+\s*:\s*" + re.escape(label) + r"\s*(\{[^}]*\})",
    )
    return pattern.findall(query)


def _assert_all_patterns_tenant_scoped(query: str, label: str) -> None:
    patterns = _patterns_for_label(query, label)
    assert patterns, f"No MERGE/MATCH patterns found for label {label!r}"
    for prop_block in patterns:
        assert "tenant_id" in prop_block, (
            f"{label} MERGE/MATCH missing tenant_id in pattern properties: "
            f"{prop_block!r}"
        )


# -----
# #1396
# -----


def test_invite_created_query_scopes_invite_on_tenant_id():
    """PendingSupplierInvite MERGE must be keyed on (invite_id, tenant_id)."""
    _assert_all_patterns_tenant_scoped(INVITE_CREATED_QUERY, "PendingSupplierInvite")


def test_invite_accepted_query_scopes_supplier_and_invite_on_tenant_id():
    """SupplierContact and PendingSupplierInvite patterns must include tenant_id."""
    _assert_all_patterns_tenant_scoped(INVITE_ACCEPTED_QUERY, "SupplierContact")
    _assert_all_patterns_tenant_scoped(INVITE_ACCEPTED_QUERY, "PendingSupplierInvite")


def test_record_invite_created_passes_tenant_id_to_driver():
    driver = _FakeDriver()
    sync = SupplierGraphSync(enabled=True, driver=driver)
    sync.record_invite_created(
        tenant_id="tenant-A",
        invite_id="invite-1",
        email="s@example.com",
        role_id="role-1",
        expires_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        created_by="user-1",
    )
    assert len(driver.calls) == 1
    query, params = driver.calls[0]
    assert params["tenant_id"] == "tenant-A"
    # Both pattern and the cross-tenant key are present
    assert "{invite_id: $invite_id, tenant_id: $tenant_id}" in query


def test_record_invite_accepted_passes_tenant_id_to_driver():
    driver = _FakeDriver()
    sync = SupplierGraphSync(enabled=True, driver=driver)
    sync.record_invite_accepted(
        tenant_id="tenant-A",
        invite_id="invite-1",
        user_id="user-1",
        email="s@example.com",
        role_id="role-1",
        accepted_at=datetime(2026, 3, 2, 13, 0, tzinfo=timezone.utc),
    )
    query, params = driver.calls[0]
    assert params["tenant_id"] == "tenant-A"
    assert "{user_id: $user_id, tenant_id: $tenant_id}" in query
    assert "{invite_id: $invite_id, tenant_id: $tenant_id}" in query


# -----
# #1352 and #1355 and #1393 (SupplierFacility scoping in all three queries)
# -----


def test_facility_ftl_scoping_query_keys_supplier_facility_on_tenant():
    _assert_all_patterns_tenant_scoped(
        FACILITY_FTL_SCOPING_QUERY, "SupplierFacility"
    )


def test_cte_event_query_keys_supplier_facility_on_tenant():
    _assert_all_patterns_tenant_scoped(CTE_EVENT_QUERY, "SupplierFacility")


def test_facility_required_ctes_query_keys_supplier_facility_on_tenant():
    _assert_all_patterns_tenant_scoped(
        FACILITY_REQUIRED_CTES_QUERY, "SupplierFacility"
    )


def test_get_required_ctes_for_facility_passes_tenant_id_to_driver():
    """Read-side defense-in-depth: Postgres pre-check is the primary gate,
    but the Neo4j query itself must also filter by tenant_id so a future
    refactor that skips the Postgres gate cannot leak cross-tenant categories.
    """
    driver = _FakeDriver(record={"categories": []})
    sync = SupplierGraphSync(enabled=True, driver=driver)

    sync.get_required_ctes_for_facility("facility-1", "tenant-A")

    assert len(driver.calls) == 1
    query, params = driver.calls[0]
    assert params["tenant_id"] == "tenant-A"
    assert params["facility_id"] == "facility-1"
    assert (
        "{facility_id: $facility_id, tenant_id: $tenant_id}" in query
    ), "Neo4j MATCH pattern must include tenant_id for defense-in-depth."


# -----
# #1394 (FTLCategory should be a shared read-only catalog — not mutated on MATCH)
# -----


def test_ftl_category_is_not_mutated_on_match():
    """FTLCategory nodes are shared regulatory reference data and must NOT be
    overwritten by tenant writes on MATCH. Only ``ON CREATE SET`` is allowed,
    which ensures a tenant cannot silently rewrite another tenant's view of
    required_ctes after the node is seeded.

    Every ``SET ftl.*`` clause in FACILITY_FTL_SCOPING_QUERY must be anchored
    to ``ON CREATE`` (or to ``ON MATCH`` explicitly, but the latter would be a
    bug). A bare ``SET ftl.*`` that follows a ``MERGE (ftl:FTLCategory ...)``
    mutates the shared catalog on every write — the attack described in #1394.
    """
    # Find every SET that touches ftl.*; each occurrence must be immediately
    # preceded by "ON CREATE" (allowing whitespace between).
    for match in re.finditer(r"SET\s+ftl\.", FACILITY_FTL_SCOPING_QUERY):
        prefix = FACILITY_FTL_SCOPING_QUERY[: match.start()].rstrip()
        assert prefix.endswith("ON CREATE"), (
            "FTLCategory mutation must be anchored to ON CREATE only — do not "
            "mutate ftl.* on MATCH. See issue #1394. "
            f"Found bare SET at offset {match.start()}: ...{prefix[-40:]!r}"
        )


# -----
# #1395 (Obligation shared catalog; SATISFIES edges must be reachable only
# from tenant-scoped CTEs)
# -----


def test_obligation_shared_catalog_edges_anchored_on_tenant_scoped_cte():
    """The Obligation node itself is a shared regulatory catalog, so MERGEing
    on obligation_id alone is intentional. Defense-in-depth requires every
    traversal through ``SATISFIES`` to anchor on a tenant-scoped CTE. We assert
    that the CTE side of the SATISFIES edge in CTE_EVENT_QUERY carries
    tenant_id on creation (it does — `CREATE (cte:CTEEvent {... tenant_id: $tenant_id ...})`).
    """
    # CTEEvent must carry tenant_id as a property when created.
    assert re.search(
        r"CREATE\s*\(\s*cte\s*:\s*CTEEvent\s*\{[^}]*tenant_id:\s*\$tenant_id",
        CTE_EVENT_QUERY,
    ), "CTEEvent must be created with tenant_id so downstream SATISFIES traversals can filter by tenant."


def test_every_query_with_satisfies_edge_has_tenant_scoped_cte():
    """CI-style guard for #1395: if any module-level query constant in this
    file uses the SATISFIES edge, the query MUST also carry a ``tenant_id``
    reference on the cte side (either in the MATCH pattern as
    ``{tenant_id: $tenant_id}`` or an explicit ``WHERE cte.tenant_id = ...``).

    Obligation nodes are a shared catalog and cannot enforce tenant isolation
    themselves; the guarantee is maintained on the cte side.
    """
    from app import supplier_graph_sync as module

    for attr_name in dir(module):
        if not attr_name.endswith("_QUERY"):
            continue
        query = getattr(module, attr_name)
        if not isinstance(query, str) or "SATISFIES" not in query:
            continue
        # Either (a) the cte node pattern carries tenant_id, or
        # (b) a WHERE clause filters cte.tenant_id.
        cte_has_tenant = bool(
            re.search(r"(cte|CTEEvent)[^{]*\{[^}]*tenant_id", query)
            or re.search(r"cte\.tenant_id", query)
        )
        assert cte_has_tenant, (
            f"{attr_name} contains SATISFIES but lacks a tenant_id predicate "
            f"on the cte side. See issue #1395."
        )


# -----
# Belt-and-suspenders static scan — every MERGE/MATCH on a tenant-owned label
# in any of the module-level query constants MUST include tenant_id in its
# property block.
# -----


def test_all_tenant_owned_merges_are_tenant_scoped():
    all_queries = {
        "INVITE_CREATED_QUERY": INVITE_CREATED_QUERY,
        "INVITE_ACCEPTED_QUERY": INVITE_ACCEPTED_QUERY,
        "FACILITY_FTL_SCOPING_QUERY": FACILITY_FTL_SCOPING_QUERY,
        "FACILITY_REQUIRED_CTES_QUERY": FACILITY_REQUIRED_CTES_QUERY,
        "CTE_EVENT_QUERY": CTE_EVENT_QUERY,
    }
    for query_name, query in all_queries.items():
        for label in _TENANT_OWNED_LABELS:
            # Only assert if the query references this label at all.
            if re.search(r":\s*" + re.escape(label) + r"\s*(?:\{|\))", query):
                patterns = _patterns_for_label(query, label)
                for prop_block in patterns:
                    assert "tenant_id" in prop_block, (
                        f"{query_name}: {label} MERGE/MATCH pattern missing "
                        f"tenant_id: {prop_block!r}"
                    )
