"""RLS-ordering regression tests for API-key tenant auth (PR #3238 repair).

``get_current_tenant`` must bind the VALIDATED API-key tenant via the
canonical ``TenantContext.set_tenant_context`` BEFORE reading the tenant
row: ``tenants`` is FORCE RLS, so PostgreSQL denies the status lookup
until ``app.tenant_id`` is bound. The pre-repair order (``db.get`` first,
bind after) fails closed on real PostgreSQL for every API-key request.

The existing ``TestApiKeySuspendedTenant`` tests use a permissive
``MagicMock`` session whose ``db.get`` succeeds with no context bound, so
they cannot see the ordering. This file uses an RLS-enforcing fake
session that raises unless the requested tenant is currently bound
through the REAL ``TenantContext`` helper (no monkeypatching of the
helper itself), plus negative-path coverage:

* active/trial tenants allowed; suspended/archived/missing denied (403)
* context-bind failure and status-read failure deny (503)
* missing/invalid/unassociated keys never bind any tenant
* deny paths attempt to clear the binding; cleanup errors retain the denial

Hermetic: direct async-function invocation, no network, no live database.
This is an order regression only — it is not PostgreSQL integration proof.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_TENANT_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


class RlsOrderViolation(AssertionError):
    """Tenant row read before TenantContext bound it (FORCE RLS would deny)."""


class RlsEnforcingFakeSession:
    """Minimal Session stand-in enforcing FORCE-RLS ordering.

    Drives the REAL ``TenantContext`` helper down its PostgreSQL branch
    (``bind`` is None, so ``_uses_sqlite`` is False): ``set_tenant_context``
    and ``clear_tenant_context`` arrive here as ``execute`` calls whose SQL
    text this fake interprets to track the bound tenant. ``get`` serves a
    ``TenantModel`` row only when the requested tenant is currently bound —
    any unbound or cross-tenant read raises ``RlsOrderViolation``, mirroring
    the PostgreSQL denial.
    """

    def __init__(self, tenant_status="active", fail_context=False, fail_read=None):
        self._tenant_status = tenant_status  # None => tenant row missing
        self._fail_context = fail_context
        self._fail_read = fail_read  # exception instance => get() raises it
        self._bound_tenant: str | None = None
        self.bind = None
        self.info: dict = {}
        self.set_calls: list[str] = []
        self.clear_calls = 0
        self.get_calls: list[str] = []

    @property
    def bound_tenant(self) -> str | None:
        return self._bound_tenant

    def execute(self, statement, params=None):
        sql = str(statement)
        if "set_tenant_context" in sql:
            if self._fail_context:
                raise RuntimeError("simulated context bind failure")
            tid = str((params or {}).get("tid"))
            self._bound_tenant = tid
            self.set_calls.append(tid)
        elif "set_config" in sql and "app.tenant_id" in sql:
            self._bound_tenant = None
            self.clear_calls += 1
        return MagicMock()

    def get(self, model, ident, populate_existing=False):
        self.get_calls.append(str(ident))
        if getattr(model, "__name__", "") != "TenantModel":
            raise AssertionError(f"unexpected model read: {model!r}")
        if self._bound_tenant is None or str(ident) != self._bound_tenant:
            raise RlsOrderViolation(
                f"RLS_ORDER_VIOLATION: TenantModel {ident} read with bound tenant "
                f"{self._bound_tenant!r} — context must be bound before lookup"
            )
        if self._fail_read is not None:
            raise self._fail_read
        if self._tenant_status is None:
            return None
        return SimpleNamespace(status=self._tenant_status)


def _stub_key_store(monkeypatch, tenant_id):
    """Stub ``get_db_key_store`` to validate any key as ``tenant_id``.

    ``tenant_id`` of None simulates a key with no tenant association;
    the sentinel ``"invalid"`` simulates key rejection.
    """
    from services.admin.app import dependencies as deps_mod

    async def _fake_get_store():
        store = MagicMock()

        async def _validate_key(_key):
            if tenant_id == "invalid":
                return None
            return SimpleNamespace(tenant_id=tenant_id)

        store.validate_key = _validate_key
        return store

    monkeypatch.setattr(deps_mod, "get_db_key_store", _fake_get_store)
    return deps_mod


class TestApiKeyTenantRlsOrdering:
    @pytest.mark.parametrize("tenant_status", ["active", "trial"])
    def test_valid_key_binds_before_read_and_allows(self, monkeypatch, tenant_status):
        deps_mod = _stub_key_store(monkeypatch, str(TENANT_ID))
        db = RlsEnforcingFakeSession(tenant_status=tenant_status)
        assert asyncio.run(deps_mod.get_current_tenant(key="valid-key", db=db)) == TENANT_ID
        # Bound exactly once, to the validated key tenant only.
        assert db.set_calls == [str(TENANT_ID)]
        assert db.get_calls == [str(TENANT_ID)]
        # Success path keeps the binding for downstream route work.
        assert db.bound_tenant == str(TENANT_ID)

    def test_binding_follows_validated_key_tenant(self, monkeypatch):
        deps_mod = _stub_key_store(monkeypatch, str(OTHER_TENANT_ID))
        db = RlsEnforcingFakeSession(tenant_status="active")
        assert asyncio.run(deps_mod.get_current_tenant(key="valid-key", db=db)) == OTHER_TENANT_ID
        assert db.set_calls == [str(OTHER_TENANT_ID)]

    @pytest.mark.parametrize("tenant_status", ["suspended", "archived", None])
    def test_non_active_tenant_rejected_and_state_cleared(self, monkeypatch, tenant_status):
        deps_mod = _stub_key_store(monkeypatch, str(TENANT_ID))
        db = RlsEnforcingFakeSession(tenant_status=tenant_status)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps_mod.get_current_tenant(key="valid-key", db=db))
        assert exc.value.status_code == 403
        # Deny path must not leave the rejected tenant bound on the
        # pooled connection.
        assert db.bound_tenant is None
        assert db.clear_calls >= 1

    def test_status_read_failure_denies_503_and_clears(self, monkeypatch):
        deps_mod = _stub_key_store(monkeypatch, str(TENANT_ID))
        db = RlsEnforcingFakeSession(tenant_status="active", fail_read=ConnectionError("db down"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps_mod.get_current_tenant(key="valid-key", db=db))
        assert exc.value.status_code == 503
        assert db.bound_tenant is None
        assert db.clear_calls >= 1

    def test_context_bind_failure_denies_503_without_read(self, monkeypatch):
        deps_mod = _stub_key_store(monkeypatch, str(TENANT_ID))
        db = RlsEnforcingFakeSession(tenant_status="active", fail_context=True)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps_mod.get_current_tenant(key="valid-key", db=db))
        assert exc.value.status_code == 503
        assert db.bound_tenant is None
        assert db.get_calls == []

    @pytest.mark.parametrize(
        "tenant_status, fail_read, expected_status",
        [("suspended", None, 403), ("active", ConnectionError("db down"), 503)],
    )
    def test_cleanup_failure_does_not_replace_denial(self, monkeypatch, tenant_status, fail_read, expected_status):
        deps_mod = _stub_key_store(monkeypatch, str(TENANT_ID))
        db = RlsEnforcingFakeSession(tenant_status=tenant_status, fail_read=fail_read)
        execute = db.execute

        def execute_with_failed_clear(statement, params=None):
            if "set_config" in str(statement):
                raise RuntimeError("simulated aborted transaction")
            return execute(statement, params)

        db.execute = execute_with_failed_clear
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps_mod.get_current_tenant(key="valid-key", db=db))
        assert exc.value.status_code == expected_status

    @pytest.mark.parametrize("key", ["", None])
    def test_missing_key_denies_401_without_binding(self, monkeypatch, key):
        deps_mod = _stub_key_store(monkeypatch, str(TENANT_ID))
        db = RlsEnforcingFakeSession(tenant_status="active")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps_mod.get_current_tenant(key=key, db=db))
        assert exc.value.status_code == 401
        assert db.set_calls == []
        assert db.bound_tenant is None

    def test_invalid_key_denies_403_without_binding(self, monkeypatch):
        deps_mod = _stub_key_store(monkeypatch, "invalid")
        db = RlsEnforcingFakeSession(tenant_status="active")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps_mod.get_current_tenant(key="bad-key", db=db))
        assert exc.value.status_code == 403
        assert db.set_calls == []
        assert db.bound_tenant is None

    def test_key_without_tenant_denies_403_without_binding(self, monkeypatch):
        deps_mod = _stub_key_store(monkeypatch, None)
        db = RlsEnforcingFakeSession(tenant_status="active")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps_mod.get_current_tenant(key="orphan-key", db=db))
        assert exc.value.status_code == 403
        assert db.set_calls == []
        assert db.bound_tenant is None
