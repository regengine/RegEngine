"""QA deep pass: ``shared.tenant_context`` resolution and GUC helpers.

``tests/security/test_tenant_isolation.py`` covers the path-param /
query / header / body mismatch matrix through one funnel. This file
covers the rest of the module contract:

1. ``resolve_tenant_context`` principal branches (api_key, test_bypass
   kind, JWT user, RBAC principal) and failure codes.
2. ``assert_tenant_claim_matches`` edge handling (None, empty, match).
3. Claim collectors: camelCase body keys, override headers,
   non-JSON and GET bodies skipped.
4. ``set_tenant_guc`` / ``set_tenant_guc_if_uuid`` validation.
5. ``tenant_scope`` / ``set_rls_tenant_id`` contextvar semantics.
6. ``_apply_rls_gucs_on_begin`` non-Postgres no-op and baseline GUCs.

Pure Python, no DB, no network.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from shared import tenant_context as tc_mod
from shared.tenant_context import (
    TenantContext,
    TenantContextError,
    _apply_rls_gucs_on_begin,
    apply_tenant_context,
    assert_tenant_claim_matches,
    get_rls_tenant_id,
    reset_rls_tenant_id,
    resolve_tenant_context,
    set_rls_tenant_id,
    set_tenant_guc,
    set_tenant_guc_if_uuid,
    tenant_scope,
)

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def _clean_rls_context():
    token = set_rls_tenant_id(None)
    yield
    try:
        reset_rls_tenant_id(token)
    except ValueError:
        set_rls_tenant_id(None)


def _request(*, api_key=None, user=None, principal=None, path_params=None,
             query=None, headers=None, method="POST", json_body: Any = None,
             has_principal_attr: bool = True) -> Request:
    """Build a Starlette Request with controllable auth state."""
    scope = {
        "type": "http",
        "method": method,
        "path": "/items",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": "&".join(f"{k}={v}" for k, v in (query or {}).items()).encode(),
        "path_params": path_params or {},
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(scope, receive)
    if api_key is not None:
        request.state.api_key = api_key
    if user is not None:
        request.state.user = user
    if principal is not None:
        request.state.principal = principal
    elif not has_principal_attr and not hasattr(request.state, "principal"):
        pass
    if json_body is not None:
        import json as _json

        async def _json_override():
            return json_body

        request.json = _json_override  # type: ignore[method-assign]
    return request


def _api_key(tenant_id=TENANT_A, key_id="rge_test"):
    return SimpleNamespace(key_id=key_id, tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# 1. resolve_tenant_context principal branches
# ---------------------------------------------------------------------------


class TestResolvePrincipalBranches:
    async def test_api_key_principal_resolves(self):
        ctx = await resolve_tenant_context(_request(api_key=_api_key()))
        assert ctx == TenantContext(tenant_id=TENANT_A, principal_kind="api_key",
                                    principal_id="rge_test", actor_email=None)

    async def test_test_bypass_key_reports_bypass_kind(self):
        ctx = await resolve_tenant_context(_request(api_key=_api_key(key_id="test")))
        assert ctx.principal_kind == "test_bypass"
        assert ctx.tenant_id == TENANT_A

    async def test_jwt_user_principal_resolves(self):
        user = SimpleNamespace(id="user-1", tenant_id=TENANT_A, email="a@example.com")
        ctx = await resolve_tenant_context(_request(user=user))
        assert ctx.principal_kind == "jwt"
        assert ctx.principal_id == "user-1"
        assert ctx.actor_email == "a@example.com"

    async def test_rbac_principal_resolves(self):
        principal = SimpleNamespace(tenant_id=TENANT_A, auth_mode="rbac", key_id="k-9")
        ctx = await resolve_tenant_context(_request(principal=principal))
        assert ctx.principal_kind == "rbac"
        assert ctx.principal_id == "k-9"

    async def test_no_principal_is_401_no_principal(self):
        with pytest.raises(TenantContextError) as exc_info:
            await resolve_tenant_context(_request())
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == "E_NO_PRINCIPAL"

    async def test_principal_without_tenant_is_401_no_tenant(self):
        with pytest.raises(TenantContextError) as exc_info:
            await resolve_tenant_context(_request(api_key=_api_key(tenant_id=None)))
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == "E_NO_TENANT"

    async def test_empty_string_tenant_is_no_tenant(self):
        with pytest.raises(TenantContextError) as exc_info:
            await resolve_tenant_context(_request(api_key=_api_key(tenant_id="")))
        assert exc_info.value.detail["code"] == "E_NO_TENANT"

    async def test_api_key_beats_jwt_user_when_both_present(self):
        user = SimpleNamespace(id="user-1", tenant_id=TENANT_B, email="b@example.com")
        ctx = await resolve_tenant_context(_request(api_key=_api_key(), user=user))
        assert ctx.tenant_id == TENANT_A
        assert ctx.principal_kind == "api_key"

    async def test_resolution_seeds_rls_contextvar(self):
        await resolve_tenant_context(_request(api_key=_api_key()))
        assert get_rls_tenant_id() == TENANT_A


# ---------------------------------------------------------------------------
# 2. assert_tenant_claim_matches edges
# ---------------------------------------------------------------------------


class TestAssertClaimMatches:
    def _ctx(self):
        return TenantContext(tenant_id=TENANT_A, principal_kind="api_key", principal_id="k")

    def test_none_and_empty_claims_pass(self):
        assert_tenant_claim_matches(self._ctx(), None, source="query")
        assert_tenant_claim_matches(self._ctx(), "", source="query")

    def test_matching_claim_passes(self):
        assert_tenant_claim_matches(self._ctx(), TENANT_A, source="path")

    def test_mismatch_raises_409(self):
        with pytest.raises(TenantContextError) as exc_info:
            assert_tenant_claim_matches(self._ctx(), TENANT_B, source="path", path="/x")
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "E_TENANT_MISMATCH"


# ---------------------------------------------------------------------------
# 3. Claim collectors
# ---------------------------------------------------------------------------


class TestClaimCollectors:
    async def test_matching_claims_pass_through(self):
        req = _request(
            api_key=_api_key(),
            path_params={"tenant_id": TENANT_A},
            query={"tenant_id": TENANT_A},
            headers={"X-Tenant-ID": TENANT_A, "content-type": "application/json"},
            json_body={"tenant_id": TENANT_A},
        )
        ctx = await resolve_tenant_context(req)
        assert ctx.tenant_id == TENANT_A

    async def test_camelcase_body_claim_conflicts(self):
        req = _request(api_key=_api_key(), json_body={"tenantId": TENANT_B},
                       headers={"content-type": "application/json"})
        with pytest.raises(TenantContextError) as exc_info:
            await resolve_tenant_context(req)
        assert exc_info.value.detail["code"] == "E_TENANT_MISMATCH"

    async def test_override_header_claim_conflicts(self):
        req = _request(api_key=_api_key(), headers={"X-Tenant-ID-Override": TENANT_B})
        with pytest.raises(TenantContextError):
            await resolve_tenant_context(req)

    async def test_regengine_tenant_header_claim_conflicts(self):
        req = _request(api_key=_api_key(), headers={"X-RegEngine-Tenant-ID": TENANT_B})
        with pytest.raises(TenantContextError):
            await resolve_tenant_context(req)

    async def test_get_ignores_body_claims(self):
        req = _request(api_key=_api_key(), method="GET", json_body={"tenant_id": TENANT_B},
                       headers={"content-type": "application/json"})
        ctx = await resolve_tenant_context(req)
        assert ctx.tenant_id == TENANT_A

    async def test_non_json_body_skipped(self):
        scope = {"type": "http", "method": "POST", "path": "/x", "headers": [],
                 "query_string": b"", "path_params": {}}

        async def receive():
            return {"type": "http.request", "body": b"tenant_id=x", "more_body": False}

        req = Request(scope, receive)
        req.state.api_key = _api_key()
        ctx = await resolve_tenant_context(req)
        assert ctx.tenant_id == TENANT_A

    async def test_non_dict_json_body_skipped(self):
        req = _request(api_key=_api_key(), json_body=["tenant_id", TENANT_B])
        ctx = await resolve_tenant_context(req)
        assert ctx.tenant_id == TENANT_A

    async def test_unparseable_json_body_skipped(self):
        req = _request(api_key=_api_key())

        async def _boom():
            raise ValueError("not json")

        req.json = _boom  # type: ignore[method-assign]
        req.headers  # touch
        scope_headers = [(b"content-type", b"application/json")]
        req.scope["headers"] = scope_headers
        ctx = await resolve_tenant_context(req)
        assert ctx.tenant_id == TENANT_A


# ---------------------------------------------------------------------------
# 4. set_tenant_guc validation
# ---------------------------------------------------------------------------


class TestSetTenantGuc:
    def test_rejects_empty_and_non_uuid(self):
        session = MagicMock()
        for bad in ("", "not-a-uuid", "tenant-slug", None, 123):
            with pytest.raises(ValueError):
                set_tenant_guc(session, bad)
        session.execute.assert_not_called()

    def test_valid_uuid_binds_parameterized(self):
        session = MagicMock()
        set_tenant_guc(session, TENANT_A)
        (stmt, params), _ = session.execute.call_args
        assert params == {"tid": TENANT_A}
        assert ":tid" in str(stmt)

    def test_if_uuid_skips_slugs_without_raising(self):
        session = MagicMock()
        assert set_tenant_guc_if_uuid(session, "some-slug") is None
        assert set_tenant_guc_if_uuid(session, None) is None
        session.execute.assert_not_called()

    def test_if_uuid_sets_for_uuid_and_uuid_objects(self):
        import uuid as _uuid

        session = MagicMock()
        set_tenant_guc_if_uuid(session, TENANT_A)
        assert session.execute.called
        session.reset_mock()
        set_tenant_guc_if_uuid(session, _uuid.UUID(TENANT_A))
        (_, params), _ = session.execute.call_args
        assert params == {"tid": TENANT_A}

    def test_apply_tenant_context_delegates(self):
        session = MagicMock()
        ctx = TenantContext(tenant_id=TENANT_A, principal_kind="api_key", principal_id="k")
        apply_tenant_context(session, ctx)
        (_, params), _ = session.execute.call_args
        assert params == {"tid": TENANT_A}


# ---------------------------------------------------------------------------
# 5. ContextVar semantics
# ---------------------------------------------------------------------------


class TestRlsContextVar:
    def test_set_and_clear(self):
        token = set_rls_tenant_id(TENANT_A)
        assert get_rls_tenant_id() == TENANT_A
        reset_rls_tenant_id(token)
        assert get_rls_tenant_id() is None

    def test_none_clears(self):
        set_rls_tenant_id(TENANT_A)
        set_rls_tenant_id(None)
        assert get_rls_tenant_id() is None

    def test_uuid_coerced_to_str(self):
        import uuid as _uuid

        set_rls_tenant_id(_uuid.UUID(TENANT_A))
        assert get_rls_tenant_id() == TENANT_A

    def test_tenant_scope_restores(self):
        set_rls_tenant_id(TENANT_B)
        with tenant_scope(TENANT_A):
            assert get_rls_tenant_id() == TENANT_A
        assert get_rls_tenant_id() == TENANT_B

    def test_tenant_scope_restores_on_exception(self):
        with pytest.raises(RuntimeError):
            with tenant_scope(TENANT_A):
                raise RuntimeError("boom")
        assert get_rls_tenant_id() is None


# ---------------------------------------------------------------------------
# 6. begin hook
# ---------------------------------------------------------------------------


class TestBeginHook:
    def _conn(self, dialect_name: str):
        conn = MagicMock()
        conn.dialect.name = dialect_name
        return conn

    def test_non_postgres_dialect_noop(self):
        conn = self._conn("sqlite")
        _apply_rls_gucs_on_begin(conn)
        conn.execute.assert_not_called()

    def test_postgres_baseline_without_tenant(self):
        conn = self._conn("postgresql")
        _apply_rls_gucs_on_begin(conn)
        assert conn.execute.call_count == 1
        (stmt,), _ = conn.execute.call_args
        text = str(stmt)
        assert "app.tenant_id" in text
        assert "regengine.is_sysadmin" in text

    def test_postgres_applies_seeded_tenant(self):
        set_rls_tenant_id(TENANT_A)
        conn = self._conn("postgresql")
        _apply_rls_gucs_on_begin(conn)
        assert conn.execute.call_count == 2
        (_, params), _ = conn.execute.call_args
        assert params == {"tid": TENANT_A}

    def test_postgres_skips_non_uuid_slug(self):
        set_rls_tenant_id("some-slug")
        conn = self._conn("postgresql")
        _apply_rls_gucs_on_begin(conn)
        assert conn.execute.call_count == 1

    def test_install_hook_idempotent(self):
        before = tc_mod._HOOK_INSTALLED
        tc_mod.install_rls_guc_hook()
        assert tc_mod._HOOK_INSTALLED is True
        assert before is True
