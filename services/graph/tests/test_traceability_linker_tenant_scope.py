"""
Tenant-scoping regression tests for services.graph.app.traceability_linker.

Covers HIGH 4: the linker matched ``(o:Obligation {id: ...})`` with no
tenant predicate, so a tenant that learned another tenant's obligation id
could link that private obligation into its own trace graph via
``link_obligation_to_traceability`` and then read its text through
``get_governing_regulations``. ``get_impacted_lots`` had the same
unscoped anchor.

These tests lock in the fix:
  - Every Obligation match carries a quarantine predicate that keeps
    explicitly marked catalog rows readable (``o.catalog = true``)
    while excluding other tenants' private obligations and unmarked
    null-tenant rows (only ``o.tenant_id = $tenant_id`` otherwise).
  - ``tenant_id`` is passed as a bound parameter, never interpolated.
  - All three methods raise ValueError on an empty/None tenant_id
    (fail closed instead of running an unscoped MATCH).
  - When the tenant does not own the obligation, the call returns []
    (no match) rather than operating on another tenant's node.
"""

from __future__ import annotations

import re

import pytest

from services.graph.app.traceability_linker import (
    _OBLIGATION_TENANT_PREDICATE,
    TraceabilityLinker,
)

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"

# Independent expectation: quarantine predicate. Literal on purpose,
# importing the product constant below would mirror the implementation.
# No ``IS NULL`` arm: an unmarked null-tenant row must match no tenant.
_EXPECTED_QUARANTINE_PREDICATE = "(o.tenant_id = $tenant_id OR o.catalog = true)"


def _quarantine_visible(node: dict, tenant_id: str) -> bool:
    """Whether a node passes the quarantine rule, with Cypher NULL semantics.

    A missing tenant_id is NULL, and ``NULL = $tenant_id`` is not true,
    so the row is visible only through the catalog marker. This mirrors
    the exact predicate pinned by
    ``test_obligation_predicate_is_quarantine_shaped`` below.
    """
    assert _OBLIGATION_TENANT_PREDICATE == _EXPECTED_QUARANTINE_PREDICATE
    own_tenant = node.get("tenant_id") is not None and node.get("tenant_id") == tenant_id
    return bool(own_tenant or node.get("catalog") is True)

# Independent expectation, written as a literal on purpose: importing the
# product constant would mirror the implementation and let a weakened
# predicate pass. Every Obligation MATCH must carry this exact WHERE clause:
# the #3344 quarantine predicate, not the pre-quarantine IS NULL shim.
_EXPECTED_OBLIGATION_PREDICATE = "(o.tenant_id = $tenant_id OR o.catalog = true)"
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
    assert "o.tenant_id" in cypher
    assert "$tenant_id" in cypher
    assert kwargs["tenant_id"] == TENANT_A
    assert kwargs["id"] == "obl-1"
    # Marked catalog obligations stay readable; unmarked null-tenant rows
    # and other tenants' rows do not.
    assert _EXPECTED_QUARANTINE_PREDICATE in cypher
    assert "IS NULL" not in cypher
    assert TENANT_A not in cypher


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
    assert "o.tenant_id" in cypher
    assert "$tenant_id" in cypher
    assert _EXPECTED_QUARANTINE_PREDICATE in cypher
    assert "IS NULL" not in cypher
    assert kwargs["tenant_id"] == TENANT_A
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
        "(o.tenant_id = $tenant_id OR o.catalog = true OR true)",
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
    assert "o.tenant_id" in cypher
    assert "$tenant_id" in cypher
    assert _EXPECTED_QUARANTINE_PREDICATE in cypher
    # The old Obligation shim stays banned. The joined Section is mixed
    # shared-or-own catalog with no catalog marker, so it carries the
    # null-or-own predicate the tenant-scope proof requires (#3332). That
    # one Section arm is the only IS NULL allowed anywhere in the query.
    section_predicate = "(s.tenant_id IS NULL OR s.tenant_id = $tenant_id)"
    assert cypher.count(section_predicate) == 1
    assert "IS NULL" not in cypher.replace(section_predicate, "")
    assert kwargs["tenant_id"] == TENANT_A
    assert kwargs["tlc"] == "tlc-1"


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
    assert _EXPECTED_QUARANTINE_PREDICATE in cypher
    assert "IS NULL" not in cypher
    assert kwargs["tenant_id"] == TENANT_A
    assert kwargs["id"] == "obl-9"
    assert TENANT_A not in cypher


def test_obligation_predicate_is_quarantine_shaped():
    """The product predicate must be the quarantine shape, not the old shim.

    Fails against the pre-quarantine predicate
    ``(o.tenant_id IS NULL OR o.tenant_id = $tenant_id)``, which showed
    every unmarked null-tenant obligation to every tenant.
    """
    assert _OBLIGATION_TENANT_PREDICATE == _EXPECTED_QUARANTINE_PREDICATE
    assert "IS NULL" not in _OBLIGATION_TENANT_PREDICATE


def test_unmarked_null_tenant_obligation_hidden_from_every_tenant():
    """An unmarked null-tenant row matches no tenant (Decision 3 quarantine)."""
    row = {"id": "obl-stray"}
    assert _quarantine_visible(row, TENANT_A) is False
    assert _quarantine_visible(row, TENANT_B) is False


def test_marked_catalog_obligation_visible_to_every_tenant():
    """A row stamped ``catalog = true`` by a catalog writer is shared."""
    row = {"id": "obl-catalog", "catalog": True}
    assert _quarantine_visible(row, TENANT_A) is True
    assert _quarantine_visible(row, TENANT_B) is True


def test_private_obligation_visible_only_to_own_tenant():
    """A tenant-stamped row stays confined to its tenant."""
    row = {"id": "obl-private", "tenant_id": TENANT_B}
    assert _quarantine_visible(row, TENANT_A) is False
    assert _quarantine_visible(row, TENANT_B) is True
