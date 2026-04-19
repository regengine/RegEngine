"""Tenant-scope regression tests for ``chain_integrity.find_broken_chains`` (#1301).

The three broken-chain queries (missing_origin, temporal_paradox,
crypto_gap) previously scoped only ``l.tenant_id`` — the joined
``shipping``, ``origin``, and NOT EXISTS / EXISTS sub-query nodes had no
``tenant_id`` predicate. Combined with the cross-tenant MERGE bug in
``FSMARelationships`` (#1284), this meant:

* **missing_origin**: a cross-tenant CREATION would falsely satisfy the
  NOT EXISTS existence check and **suppress** a genuine broken-chain
  violation for tenant A.
* **temporal_paradox**: a cross-tenant origin event whose date is later
  than tenant A's shipping would create a **spurious** paradox — false
  positive wasting reviewer time.
* **crypto_gap**: a cross-tenant origin whose merkle_hash happens to
  match could **mask** a genuine hash-chain break.

Tests mock the Neo4j client and assert on the Cypher strings the
function sends. Same inspection pattern as the prior tenant-scoping PRs.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma.chain_integrity import find_broken_chains


TENANT_A = "11111111-1111-1111-1111-111111111111"


def _flatten(q: str) -> str:
    """Strip Cypher `//` comments and collapse whitespace for substring match."""
    return " ".join(re.sub(r"//[^\n]*", "", q).split())


def _make_client_with_empty_results():
    """Return a client mock whose session.run() yields zero records.

    We only need to capture the Cypher — the function short-circuits on
    empty results so no post-processing code runs.
    """
    client = MagicMock()
    session = AsyncMock()

    async def _empty_aiter(self):  # pragma: no cover - async iter protocol
        if False:
            yield None

    empty_result = MagicMock()
    empty_result.__aiter__ = _empty_aiter
    session.run = AsyncMock(return_value=empty_result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    client.session = MagicMock(return_value=session)
    return client, session


# ── Cypher inspection ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_origin_query_scopes_shipping_and_origin():
    """#1301: Query 1 must tenant-scope Lot, shipping, and the origin inside
    the NOT EXISTS sub-query (that's the one that suppresses false
    positives — unscoped, a cross-tenant origin hides real violations)."""
    client, session = _make_client_with_empty_results()
    await find_broken_chains(client, tenant_id=TENANT_A)

    # First run() call is the missing_origin_query.
    cypher = _flatten(session.run.call_args_list[0].args[0])

    assert "l.tenant_id = $tenant_id" in cypher
    assert "shipping.tenant_id = $tenant_id" in cypher, (
        f"#1301: missing_origin_query must scope shipping event. Cypher:\n{cypher}"
    )
    assert "origin.tenant_id = $tenant_id" in cypher, (
        f"#1301: missing_origin_query must scope origin event inside NOT EXISTS. "
        f"Cypher:\n{cypher}"
    )
    # Defense in depth: the "$tenant_id IS NULL OR" shim must be gone.
    assert "$tenant_id IS NULL" not in cypher, (
        "#1301: null-tenant shim must be removed — caller must pass tenant_id"
    )


@pytest.mark.asyncio
async def test_temporal_paradox_query_scopes_all_three_event_nodes():
    """#1301: Query 2 has two event nodes (shipping and origin via a
    separate MATCH). Both must be tenant-scoped or cross-tenant origins
    create spurious paradox violations."""
    client, session = _make_client_with_empty_results()
    await find_broken_chains(client, tenant_id=TENANT_A)

    cypher = _flatten(session.run.call_args_list[1].args[0])

    assert "l.tenant_id = $tenant_id" in cypher
    assert "shipping.tenant_id = $tenant_id" in cypher
    assert "origin.tenant_id = $tenant_id" in cypher, (
        f"#1301: temporal_paradox_query must scope origin event. Cypher:\n{cypher}"
    )
    assert "$tenant_id IS NULL" not in cypher


@pytest.mark.asyncio
async def test_crypto_gap_query_scopes_every_origin_match():
    """#1301: Query 3 has TWO origin MATCHes — one in the EXISTS sub-query
    and one at top-level that collects merkle_hashes. **Both** must carry
    the tenant filter or a cross-tenant hash collision can mask a real
    chain break."""
    client, session = _make_client_with_empty_results()
    await find_broken_chains(client, tenant_id=TENANT_A)

    cypher = session.run.call_args_list[2].args[0]  # raw, to count occurrences
    flat = _flatten(cypher)

    assert "l.tenant_id = $tenant_id" in flat
    assert "shipping.tenant_id = $tenant_id" in flat
    # Expect ≥ 2 occurrences of "origin.tenant_id = $tenant_id": one
    # inside EXISTS, one at the outer MATCH. A refactor that drops either
    # must fail this assertion.
    occurrences = flat.count("origin.tenant_id = $tenant_id")
    assert occurrences >= 2, (
        f"#1301: crypto_gap_query must scope BOTH origin MATCHes "
        f"(EXISTS + outer). Found {occurrences}. Cypher:\n{cypher}"
    )
    assert "$tenant_id IS NULL" not in flat


@pytest.mark.asyncio
async def test_every_query_binds_tenant_id_parameter():
    """Every session.run() invocation must bind $tenant_id as a kwarg.
    If a refactor drops the binding, the scoped predicates become
    silently inert (match nothing)."""
    client, session = _make_client_with_empty_results()
    await find_broken_chains(client, tenant_id=TENANT_A)

    # Three queries → three run() calls, all with tenant_id kwarg.
    assert session.run.call_count == 3
    for i, call in enumerate(session.run.call_args_list):
        kwargs = call.kwargs
        assert kwargs.get("tenant_id") == TENANT_A, (
            f"Query #{i} missing $tenant_id binding; kwargs={kwargs!r}"
        )


# ── Fail-fast on null-tenant callers ───────────────────────────────────────


@pytest.mark.asyncio
async def test_none_tenant_id_raises():
    """#1301: the `$tenant_id IS NULL` shim was a production info-disclosure.
    Callers that previously passed None must now get a loud error so the
    mistake is caught in CI / smoke rather than silently leaking all
    tenants' chain data."""
    client, _ = _make_client_with_empty_results()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_broken_chains(client, tenant_id=None)


@pytest.mark.asyncio
async def test_empty_string_tenant_id_raises():
    """Empty string counts as absent — same failure mode as None."""
    client, _ = _make_client_with_empty_results()
    with pytest.raises(ValueError, match="tenant_id"):
        await find_broken_chains(client, tenant_id="")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
