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

import re

import pytest

from services.graph.app.traceability_linker import TraceabilityLinker

TENANT_A = "11111111-1111-1111-1111-111111111111"

# Independent expectation, written as a literal on purpose: importing the
# product constant would mirror the implementation and let a weakened
# predicate pass. Every Obligation MATCH must carry this exact WHERE clause.
_EXPECTED_OBLIGATION_PREDICATE = "(o.tenant_id IS NULL OR o.tenant_id = $tenant_id)"
_OBLIGATION_WHERE_RE = re.compile(r"WHERE\s*" + re.escape(_EXPECTED_OBLIGATION_PREDICATE) + r"\s*(MATCH|RETURN|MERGE)")


def _assert_obligation_scoped(source: str, cypher: str, kwargs: dict) -> None:
    """The exact shared-catalog WHERE predicate is present, bound, not interpolated."""
    assert _OBLIGATION_WHERE_RE.search(" ".join(cypher.split())), (
        f"{source}: missing exact shared-catalog WHERE {_EXPECTED_OBLIGATION_PREDICATE!r} "
        f"before MATCH/RETURN/MERGE:\n{cypher}"
    )
    assert kwargs.get("tenant_id") == TENANT_A, f"{source}: $tenant_id not bound: {kwargs!r}"
    assert TENANT_A not in cypher, f"{source}: tenant value interpolated into Cypher:\n{cypher}"


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
    # Shared global obligations stay readable; other tenants' do not.
    _assert_obligation_scoped("link fetch", cypher, kwargs)
    assert kwargs["id"] == "obl-1"


@pytest.mark.asyncio
async def test_link_write_query_scopes_obligation_to_tenant(linker, fake_session):
    """The GOVERNS MERGE must only fire for global or own-tenant obligations."""
    fake_session.queue(_FakeResult(single_row={"text": "Cooling logs required daily", "category": "COOLING"}))
    fake_session.queue(_FakeResult(rows=[{"event_id": "e1", "type": "COOLING"}]))

    links = await linker.link_obligation_to_traceability("obl-9", TENANT_A)

    assert len(links) == 1
    assert len(fake_session.runs) == 2
    fetch_cypher, fetch_kwargs = fake_session.runs[0]
    _assert_obligation_scoped("link fetch", fetch_cypher, fetch_kwargs)
    cypher, kwargs = fake_session.runs[1]
    assert "Obligation" in cypher
    _assert_obligation_scoped("link write", cypher, kwargs)
    assert kwargs["obs_id"] == "obl-9"
    # Events were already scoped; the obligation anchor is what this locks in.
    assert "e.tenant_id = $tenant_id" in cypher


@pytest.mark.asyncio
async def test_link_returns_empty_when_obligation_belongs_to_other_tenant(linker, fake_session):
    """Wrong-tenant obligation id must yield no match (fail closed).

    The empty row models Neo4j returning no node because the exact tenant
    predicate below excluded the other tenant's obligation. The proof is the
    captured Cypher: without that WHERE clause the victim node would match
    and the link would proceed, so the query assertion is what makes this
    test sensitive to a predicate revert.
    """
    fake_session.queue(_FakeResult(single_row=None))

    links = await linker.link_obligation_to_traceability("obl-victim", TENANT_A)

    assert links == []
    assert len(fake_session.runs) == 1
    cypher, kwargs = fake_session.runs[0]
    _assert_obligation_scoped("cross-tenant fetch", cypher, kwargs)
    assert kwargs["id"] == "obl-victim"


@pytest.mark.asyncio
async def test_obligation_predicate_rejects_or_true_mutation(linker, fake_session, monkeypatch):
    """A weakened predicate such as OR true must fail the exact-clause check.

    Guards against boolean mutations that keep every substring token while
    letting other tenants' obligations match.
    """
    import services.graph.app.traceability_linker as linker_module

    monkeypatch.setattr(
        linker_module,
        "_OBLIGATION_TENANT_PREDICATE",
        "(o.tenant_id IS NULL OR o.tenant_id = $tenant_id OR true)",
    )
    fake_session.queue(_FakeResult(single_row={"text": "Cooling logs", "category": "COOLING"}))
    fake_session.queue(_FakeResult(rows=[{"event_id": "e1", "type": "COOLING"}]))

    await linker.link_obligation_to_traceability("obl-9", TENANT_A)

    cypher, kwargs = fake_session.runs[0]
    with pytest.raises(AssertionError):
        _assert_obligation_scoped("weakened predicate", cypher, kwargs)


@pytest.mark.asyncio
async def test_get_governing_regulations_scopes_obligation_to_tenant(linker, fake_session):
    """Reading governing text must exclude other tenants' private obligations."""
    fake_session.queue(_FakeResult(rows=[{"regulation": "FSMA", "requirement": "Cool it", "requirement_id": "obl-9"}]))

    regs = await linker.get_governing_regulations("tlc-1", TENANT_A)

    assert len(regs) == 1
    assert len(fake_session.runs) == 1
    cypher, kwargs = fake_session.runs[0]
    _assert_obligation_scoped("governing regulations", cypher, kwargs)
    assert kwargs["tlc"] == "tlc-1"


@pytest.mark.asyncio
async def test_get_impacted_lots_scopes_obligation_to_tenant(linker, fake_session):
    """Impacted-lots must not resolve through another tenant's obligation."""
    fake_session.queue(_FakeResult(rows=[{"tlc": "tlc-1", "description": "Lettuce"}]))

    lots = await linker.get_impacted_lots("obl-9", TENANT_A)

    assert len(lots) == 1
    assert len(fake_session.runs) == 1
    cypher, kwargs = fake_session.runs[0]
    _assert_obligation_scoped("impacted lots", cypher, kwargs)
    assert kwargs["id"] == "obl-9"
