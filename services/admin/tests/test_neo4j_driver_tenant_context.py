"""Regression tests for #1397 — Neo4j session wrapper binds tenant_id per
session and refuses to run Cypher that would leak across tenants.

The wrapper lives in ``services/shared/neo4j_tenant_context.py``. It is the
library-side complement to PR #1437's Cypher-pattern tenant-scope fixes: the
patterns now include ``tenant_id`` predicates, and this wrapper refuses to
run a query that forgot to.
"""

from __future__ import annotations

import uuid

import pytest

from shared.neo4j_tenant_context import (
    TenantScopedNeo4jSession,
    require_tenant_id_in_cypher,
    session_with_tenant,
)


# ---------------------------------------------------------------------------
# Fakes that mimic the neo4j Python driver contract
# ---------------------------------------------------------------------------


class _FakeNeo4jSession:
    def __init__(self):
        self.calls = []
        self.closed = False

    def run(self, query, params=None, **kwargs):
        self.calls.append((query, params, kwargs))
        return _FakeResult()

    def close(self):
        self.closed = True


class _FakeResult:
    def single(self):
        return None


class _FakeDriver:
    def __init__(self):
        self.session_instances = []

    def session(self):
        s = _FakeNeo4jSession()
        self.session_instances.append(s)
        return s


# ---------------------------------------------------------------------------
# require_tenant_id_in_cypher — static validator
# ---------------------------------------------------------------------------


def test_require_tenant_id_allows_scoped_merge():
    require_tenant_id_in_cypher(
        "MERGE (a:Facility {facility_id: $facility_id, tenant_id: $tenant_id})"
    )


def test_require_tenant_id_rejects_unscoped_merge():
    with pytest.raises(ValueError) as exc:
        require_tenant_id_in_cypher(
            "MERGE (a:Facility {facility_id: $facility_id})"
        )
    assert "tenant_id" in str(exc.value)


def test_require_tenant_id_case_insensitive():
    # "TENANT_ID" still counts — we don't want to be tripped by query style.
    require_tenant_id_in_cypher(
        "MATCH (x:Thing) WHERE x.TENANT_ID = $t RETURN x"
    )


# ---------------------------------------------------------------------------
# TenantScopedNeo4jSession — per-session binding
# ---------------------------------------------------------------------------


def test_run_injects_tenant_id_param_when_missing():
    raw = _FakeNeo4jSession()
    tenant = str(uuid.uuid4())
    wrapper = TenantScopedNeo4jSession(raw, tenant)

    wrapper.run(
        "MERGE (f:Facility {facility_id: $facility_id, tenant_id: $tenant_id})",
        {"facility_id": "f1"},
    )

    query, params, _ = raw.calls[0]
    assert params["tenant_id"] == tenant
    assert params["facility_id"] == "f1"


def test_run_accepts_matching_caller_tenant_id():
    raw = _FakeNeo4jSession()
    tenant = str(uuid.uuid4())
    wrapper = TenantScopedNeo4jSession(raw, tenant)

    wrapper.run(
        "MERGE (f:Facility {tenant_id: $tenant_id})",
        {"tenant_id": tenant},
    )
    assert raw.calls[0][1]["tenant_id"] == tenant


def test_run_rejects_mismatched_caller_tenant_id():
    raw = _FakeNeo4jSession()
    tenant = str(uuid.uuid4())
    other_tenant = str(uuid.uuid4())
    wrapper = TenantScopedNeo4jSession(raw, tenant)

    with pytest.raises(ValueError) as exc:
        wrapper.run(
            "MERGE (f:Facility {tenant_id: $tenant_id})",
            {"tenant_id": other_tenant},
        )
    assert "conflicts" in str(exc.value)
    assert raw.calls == []  # never executed


def test_run_refuses_cypher_missing_tenant_id_by_default():
    raw = _FakeNeo4jSession()
    wrapper = TenantScopedNeo4jSession(raw, str(uuid.uuid4()))

    with pytest.raises(ValueError):
        wrapper.run(
            "MERGE (f:Facility {facility_id: $facility_id})",  # no tenant_id
            {"facility_id": "f1"},
        )
    assert raw.calls == []


def test_run_allows_unscoped_only_with_explicit_opt_in():
    raw = _FakeNeo4jSession()
    wrapper = TenantScopedNeo4jSession(raw, str(uuid.uuid4()))

    # Opt-in for a genuinely global query (e.g. schema introspection).
    wrapper.run("CALL db.indexes()", {}, _allow_unscoped=True)
    assert len(raw.calls) == 1


def test_wrapper_rejects_empty_tenant_id():
    with pytest.raises(ValueError):
        TenantScopedNeo4jSession(_FakeNeo4jSession(), "")
    with pytest.raises(ValueError):
        TenantScopedNeo4jSession(_FakeNeo4jSession(), None)  # type: ignore[arg-type]


def test_session_context_manager_closes_underlying_session():
    raw = _FakeNeo4jSession()
    with TenantScopedNeo4jSession(raw, str(uuid.uuid4())) as s:
        s.run(
            "MERGE (a:X {tenant_id: $tenant_id})",
            {},
        )
    assert raw.closed is True


# ---------------------------------------------------------------------------
# session_with_tenant — factory over a driver
# ---------------------------------------------------------------------------


def test_session_with_tenant_yields_bound_wrapper():
    driver = _FakeDriver()
    tenant = str(uuid.uuid4())

    with session_with_tenant(driver, tenant) as s:
        assert isinstance(s, TenantScopedNeo4jSession)
        assert s.tenant_id == tenant
        s.run("MERGE (x:Y {tenant_id: $tenant_id})", {})

    raw = driver.session_instances[0]
    assert raw.closed is True
    assert raw.calls[0][1]["tenant_id"] == tenant


def test_session_with_tenant_rejects_missing_driver():
    with pytest.raises(ValueError):
        with session_with_tenant(None, "t"):  # type: ignore[arg-type]
            pass


def test_session_with_tenant_isolates_tenants_across_sessions():
    """Two back-to-back sessions on the same driver must not bleed tenant
    ids — each session is bound independently."""
    driver = _FakeDriver()
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())

    with session_with_tenant(driver, tenant_a) as s:
        s.run("MERGE (x:Y {tenant_id: $tenant_id})", {"id": 1})

    with session_with_tenant(driver, tenant_b) as s:
        s.run("MERGE (x:Y {tenant_id: $tenant_id})", {"id": 2})

    raw_a, raw_b = driver.session_instances
    assert raw_a.calls[0][1]["tenant_id"] == tenant_a
    assert raw_b.calls[0][1]["tenant_id"] == tenant_b
    assert raw_a.calls[0][1]["tenant_id"] != raw_b.calls[0][1]["tenant_id"]
