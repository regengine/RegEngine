"""
Tenant-scoping regression tests for services.graph.app.traceability_linker.

Covers HIGH 4: the linker matched ``(o:Obligation {id: ...})`` with no
tenant predicate, so a tenant that learned another tenant's obligation id
could link that private obligation into its own trace graph via
``link_obligation_to_traceability`` and then read its text through
``get_governing_regulations``. ``get_impacted_lots`` had the same
unscoped anchor.

These tests lock in the fix:
  - Every Obligation match carries a tenant predicate that keeps the
    shared global catalog readable (``o.tenant_id IS NULL``) while
    excluding other tenants' private obligations
    (``OR o.tenant_id = $tenant_id``).
  - ``tenant_id`` is passed as a bound parameter, never interpolated.
  - All three methods raise ValueError on an empty/None tenant_id
    (fail closed instead of running an unscoped MATCH).
  - When the tenant does not own the obligation, the call returns []
    (no match) rather than operating on another tenant's node.
"""

from __future__ import annotations

import pytest

from services.graph.app.traceability_linker import TraceabilityLinker

TENANT_A = "11111111-1111-1111-1111-111111111111"


class _FakeResult:
    """Minimal async Neo4j result double supporting single() and async for."""

    def __init__(self, rows=None, single_row=None):
        self._rows = list(rows or [])
        self._single_row = single_row

    async def single(self):
        return self._single_row

    def __aiter__(self):
        async def _gen():
            for row in self._rows:
                yield row

        return _gen()


class _FakeSession:
    def __init__(self):
        self.runs = []
        self._queued = []

    def queue(self, result):
        self._queued.append(result)

    async def run(self, query, **kwargs):
        self.runs.append((query, kwargs))
        return self._queued.pop(0)


class _FakeSessionCM:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


class _FakeDriver:
    def __init__(self, session):
        self._session = session

    def session(self):
        return _FakeSessionCM(self._session)


@pytest.fixture
def fake_session():
    return _FakeSession()


@pytest.fixture
def linker(fake_session):
    instance = TraceabilityLinker.__new__(TraceabilityLinker)
    instance.driver = _FakeDriver(fake_session)
    return instance


@pytest.mark.asyncio
async def test_link_rejects_empty_tenant_id(linker):
    """link_obligation_to_traceability must fail closed on empty tenant."""
    with pytest.raises(ValueError):
        await linker.link_obligation_to_traceability("obl-1", "")
    with pytest.raises(ValueError):
        await linker.link_obligation_to_traceability("obl-1", None)


@pytest.mark.asyncio
async def test_get_governing_regulations_rejects_empty_tenant_id(linker):
    with pytest.raises(ValueError):
        await linker.get_governing_regulations("tlc-1", "")
    with pytest.raises(ValueError):
        await linker.get_governing_regulations("tlc-1", None)


@pytest.mark.asyncio
async def test_get_impacted_lots_rejects_empty_tenant_id(linker):
    with pytest.raises(ValueError):
        await linker.get_impacted_lots("obl-1", "")
    with pytest.raises(ValueError):
        await linker.get_impacted_lots("obl-1", None)


@pytest.mark.asyncio
async def test_link_fetch_query_scopes_obligation_to_tenant(linker, fake_session):
    """The obligation fetch must not match another tenant's private node."""
    fake_session.queue(_FakeResult(single_row={"text": "Maintain sanitation records", "category": "SANITATION"}))

    links = await linker.link_obligation_to_traceability("obl-1", TENANT_A)

    assert links == []
    assert len(fake_session.runs) == 1
    cypher, kwargs = fake_session.runs[0]
    assert "o.tenant_id" in cypher
    assert "$tenant_id" in cypher
    assert kwargs["tenant_id"] == TENANT_A
    assert kwargs["id"] == "obl-1"
    # Shared global obligations stay readable; other tenants' do not.
    assert "IS NULL" in cypher
    assert TENANT_A not in cypher


@pytest.mark.asyncio
async def test_link_write_query_scopes_obligation_to_tenant(linker, fake_session):
    """The GOVERNS MERGE must only fire for global or own-tenant obligations."""
    fake_session.queue(_FakeResult(single_row={"text": "Cooling logs required daily", "category": "COOLING"}))
    fake_session.queue(_FakeResult(rows=[{"event_id": "e1", "type": "COOLING"}]))

    links = await linker.link_obligation_to_traceability("obl-9", TENANT_A)

    assert len(links) == 1
    assert len(fake_session.runs) == 2
    cypher, kwargs = fake_session.runs[1]
    assert "Obligation" in cypher
    assert "o.tenant_id" in cypher
    assert "$tenant_id" in cypher
    assert "IS NULL" in cypher
    assert kwargs["tenant_id"] == TENANT_A
    assert kwargs["obs_id"] == "obl-9"
    # Events were already scoped; the obligation anchor is what this locks in.
    assert "e.tenant_id = $tenant_id" in cypher
    assert TENANT_A not in cypher


@pytest.mark.asyncio
async def test_link_returns_empty_when_obligation_belongs_to_other_tenant(linker, fake_session):
    """Wrong-tenant obligation id must yield no match (fail closed)."""
    fake_session.queue(_FakeResult(single_row=None))

    links = await linker.link_obligation_to_traceability("obl-victim", TENANT_A)

    assert links == []
    assert len(fake_session.runs) == 1


@pytest.mark.asyncio
async def test_get_governing_regulations_scopes_obligation_to_tenant(linker, fake_session):
    """Reading governing text must exclude other tenants' private obligations."""
    fake_session.queue(_FakeResult(rows=[{"regulation": "FSMA", "requirement": "Cool it", "requirement_id": "obl-9"}]))

    regs = await linker.get_governing_regulations("tlc-1", TENANT_A)

    assert len(regs) == 1
    assert len(fake_session.runs) == 1
    cypher, kwargs = fake_session.runs[0]
    assert "o.tenant_id" in cypher
    assert "$tenant_id" in cypher
    assert "IS NULL" in cypher
    assert kwargs["tenant_id"] == TENANT_A
    assert kwargs["tlc"] == "tlc-1"
    assert TENANT_A not in cypher


@pytest.mark.asyncio
async def test_get_impacted_lots_scopes_obligation_to_tenant(linker, fake_session):
    """Impacted-lots must not resolve through another tenant's obligation."""
    fake_session.queue(_FakeResult(rows=[{"tlc": "tlc-1", "description": "Lettuce"}]))

    lots = await linker.get_impacted_lots("obl-9", TENANT_A)

    assert len(lots) == 1
    assert len(fake_session.runs) == 1
    cypher, kwargs = fake_session.runs[0]
    assert "o.tenant_id" in cypher
    assert "$tenant_id" in cypher
    assert "IS NULL" in cypher
    assert kwargs["tenant_id"] == TENANT_A
    assert kwargs["id"] == "obl-9"
    assert TENANT_A not in cypher
