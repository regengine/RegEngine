"""Focused unit tests for ``services/admin/app/dependencies.py``.

Covers the module's main public behavior with mocks only (no DB, no
network, no clock dependence): bearer token parsing, session-store
backend selection and singleton wiring, Supabase exception
classifiers, exception factories, path-tenant verification,
``PermissionChecker`` fail-closed verdicts, the ``get_current_tenant``
missing-key edge, and best-effort tenant-context cleanup.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request


def _request_with_auth_header(value: bytes | None) -> Request:
    headers = [(b"authorization", value)] if value is not None else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


# ---------------------------------------------------------------------------
# _optional_bearer_token
# ---------------------------------------------------------------------------


class TestOptionalBearerToken:
    def test_missing_header_returns_none(self):
        from services.admin.app.dependencies import _optional_bearer_token

        assert _optional_bearer_token(_request_with_auth_header(None)) is None

    def test_non_bearer_scheme_returns_none(self):
        from services.admin.app.dependencies import _optional_bearer_token

        assert _optional_bearer_token(_request_with_auth_header(b"Basic dXNlcjpwYXNz")) is None

    def test_bearer_scheme_is_case_insensitive(self):
        from services.admin.app.dependencies import _optional_bearer_token

        assert _optional_bearer_token(_request_with_auth_header(b"BeArEr abc123")) == "abc123"

    def test_bearer_with_empty_token_returns_none(self):
        from services.admin.app.dependencies import _optional_bearer_token

        assert _optional_bearer_token(_request_with_auth_header(b"Bearer ")) is None


# ---------------------------------------------------------------------------
# _parse_token_version
# ---------------------------------------------------------------------------


class TestParseTokenVersion:
    def test_int_passes_through(self):
        from services.admin.app.dependencies import _parse_token_version

        assert _parse_token_version(3) == 3

    def test_numeric_string_is_coerced(self):
        from services.admin.app.dependencies import _parse_token_version

        assert _parse_token_version("7") == 7

    def test_booleans_none_and_garbage_return_none(self):
        from services.admin.app.dependencies import _parse_token_version

        assert _parse_token_version(None) is None
        assert _parse_token_version(True) is None
        assert _parse_token_version("v3") is None
        assert _parse_token_version("   ") is None
        assert _parse_token_version(3.0) is None


# ---------------------------------------------------------------------------
# _should_use_in_memory_session_store
# ---------------------------------------------------------------------------


def _non_strict(monkeypatch):
    from services.admin.app import dependencies as deps

    monkeypatch.setattr(deps, "requires_strict_auth_runtime", lambda: False)
    return deps


class TestShouldUseInMemorySessionStore:
    def test_explicit_memory_backend_wins(self, monkeypatch):
        deps = _non_strict(monkeypatch)
        monkeypatch.setenv("SESSION_STORE_BACKEND", "memory")
        monkeypatch.delenv("ALLOW_INMEMORY_SESSION_STORE", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        assert deps._should_use_in_memory_session_store() is True

    def test_allow_flag_wins_without_redis(self, monkeypatch):
        deps = _non_strict(monkeypatch)
        monkeypatch.delenv("SESSION_STORE_BACKEND", raising=False)
        monkeypatch.setenv("ALLOW_INMEMORY_SESSION_STORE", "true")
        monkeypatch.delenv("REDIS_URL", raising=False)
        assert deps._should_use_in_memory_session_store() is True

    def test_redis_url_selects_redis(self, monkeypatch):
        deps = _non_strict(monkeypatch)
        monkeypatch.delenv("SESSION_STORE_BACKEND", raising=False)
        monkeypatch.delenv("ALLOW_INMEMORY_SESSION_STORE", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        assert deps._should_use_in_memory_session_store() is False

    def test_no_redis_url_falls_back_to_memory(self, monkeypatch):
        deps = _non_strict(monkeypatch)
        monkeypatch.delenv("SESSION_STORE_BACKEND", raising=False)
        monkeypatch.delenv("ALLOW_INMEMORY_SESSION_STORE", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        assert deps._should_use_in_memory_session_store() is True

    def test_strict_runtime_never_uses_memory(self, monkeypatch):
        from services.admin.app import auth_runtime, dependencies as deps

        monkeypatch.setattr(deps, "requires_strict_auth_runtime", lambda: True)
        monkeypatch.setattr(auth_runtime, "load_auth_runtime_config", lambda: SimpleNamespace())
        monkeypatch.setenv("SESSION_STORE_BACKEND", "memory")
        assert deps._should_use_in_memory_session_store() is False


# ---------------------------------------------------------------------------
# Supabase exception classifiers
# ---------------------------------------------------------------------------


def _exc_with_identity(name: str, module: str, message: str = "boom") -> Exception:
    cls = type(name, (Exception,), {"__module__": module})
    return cls(message)


class TestSupabaseExceptionClassifiers:
    def test_gotrue_rejection_is_recognized(self):
        from services.admin.app.dependencies import _is_supabase_token_rejection

        assert _is_supabase_token_rejection(_exc_with_identity("AuthApiError", "gotrue.errors")) is True
        assert (
            _is_supabase_token_rejection(_exc_with_identity("AuthInvalidCredentialsError", "supabase_auth.errors"))
            is True
        )

    def test_unrelated_error_is_not_a_rejection(self):
        from services.admin.app.dependencies import _is_supabase_token_rejection

        assert _is_supabase_token_rejection(ValueError("bad")) is False
        assert _is_supabase_token_rejection(_exc_with_identity("AuthApiError", "myapp.errors")) is False

    def test_retryable_error_is_transient(self):
        from services.admin.app.dependencies import _is_supabase_transient_exception

        assert _is_supabase_transient_exception(_exc_with_identity("AuthRetryableError", "gotrue.errors")) is True

    def test_non_retryable_error_is_not_transient(self):
        from services.admin.app.dependencies import _is_supabase_transient_exception

        assert _is_supabase_transient_exception(_exc_with_identity("AuthApiError", "gotrue.errors")) is False
        assert _is_supabase_transient_exception(ConnectionError("down")) is False


# ---------------------------------------------------------------------------
# Exception factories
# ---------------------------------------------------------------------------


class TestExceptionFactories:
    def test_credentials_exception_is_bearer_401(self):
        from services.admin.app.dependencies import _credentials_exception

        exc = _credentials_exception()
        assert exc.status_code == 401
        assert exc.headers == {"WWW-Authenticate": "Bearer"}

    def test_session_store_exception_is_503(self):
        from services.admin.app.dependencies import _session_store_exception

        exc = _session_store_exception()
        assert exc.status_code == 503


# ---------------------------------------------------------------------------
# get_session_store singleton wiring
# ---------------------------------------------------------------------------


class TestGetSessionStore:
    def test_memory_backend_returns_in_memory_singleton(self, monkeypatch):
        from services.admin.app import dependencies as deps

        monkeypatch.setattr(deps, "_session_store", None)
        monkeypatch.setattr(deps, "requires_strict_auth_runtime", lambda: False)
        monkeypatch.setenv("SESSION_STORE_BACKEND", "memory")
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("ALLOW_INMEMORY_SESSION_STORE", raising=False)

        first = deps.get_session_store()
        assert isinstance(first, deps.InMemorySessionStore)
        assert deps.get_session_store() is first

    def test_redis_url_returns_redis_store_without_connecting(self, monkeypatch):
        from services.admin.app import dependencies as deps

        monkeypatch.setattr(deps, "_session_store", None)
        monkeypatch.setattr(deps, "requires_strict_auth_runtime", lambda: False)
        monkeypatch.delenv("SESSION_STORE_BACKEND", raising=False)
        monkeypatch.delenv("ALLOW_INMEMORY_SESSION_STORE", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

        store = deps.get_session_store()
        assert isinstance(store, deps.RedisSessionStore)
        assert not isinstance(store, deps.InMemorySessionStore)
        assert store._client is None


# ---------------------------------------------------------------------------
# verify_path_tenant_matches
# ---------------------------------------------------------------------------


class TestVerifyPathTenantMatches:
    def test_malformed_uuid_is_400(self, monkeypatch):
        from services.admin.app import dependencies as deps

        with pytest.raises(HTTPException) as exc:
            deps.verify_path_tenant_matches(
                tenant_id="not-a-uuid", user=SimpleNamespace(id=uuid.uuid4()), db=MagicMock()
            )
        assert exc.value.status_code == 400

    def test_missing_auth_context_is_403(self, monkeypatch):
        from services.admin.app import dependencies as deps

        monkeypatch.setattr(deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: None))
        with pytest.raises(HTTPException) as exc:
            deps.verify_path_tenant_matches(
                tenant_id=str(uuid.uuid4()), user=SimpleNamespace(id=uuid.uuid4()), db=MagicMock()
            )
        assert exc.value.status_code == 403

    def test_cross_tenant_path_is_403(self, monkeypatch):
        from services.admin.app import dependencies as deps

        monkeypatch.setattr(
            deps.TenantContext,
            "get_tenant_context",
            staticmethod(lambda _db: uuid.UUID("11111111-1111-1111-1111-111111111111")),
        )
        with pytest.raises(HTTPException) as exc:
            deps.verify_path_tenant_matches(
                tenant_id="22222222-2222-2222-2222-222222222222",
                user=SimpleNamespace(id=uuid.uuid4()),
                db=MagicMock(),
            )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Tenant mismatch"

    def test_matching_path_returns_uuid(self, monkeypatch):
        from services.admin.app import dependencies as deps

        tenant_id = uuid.uuid4()
        monkeypatch.setattr(deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: tenant_id))
        assert (
            deps.verify_path_tenant_matches(
                tenant_id=str(tenant_id), user=SimpleNamespace(id=uuid.uuid4()), db=MagicMock()
            )
            == tenant_id
        )


# ---------------------------------------------------------------------------
# PermissionChecker fail-closed verdicts
# ---------------------------------------------------------------------------


class TestPermissionChecker:
    def test_missing_tenant_context_is_403(self, monkeypatch):
        from services.admin.app import dependencies as deps

        monkeypatch.setattr(deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: None))
        with pytest.raises(HTTPException) as exc:
            deps.PermissionChecker("users.read")(user=SimpleNamespace(id=uuid.uuid4()), db=MagicMock())
        assert exc.value.status_code == 403
        assert "E_NO_TENANT_CONTEXT" in exc.value.detail

    def test_granted_permission_passes(self, monkeypatch):
        from services.admin.app import dependencies as deps

        tenant_id = uuid.uuid4()
        monkeypatch.setattr(deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: tenant_id))
        monkeypatch.setattr(deps, "has_permission", lambda perms, required: True)
        result = MagicMock()
        result.scalar_one_or_none.return_value = SimpleNamespace(permissions=["users.read"])
        db = MagicMock()
        db.execute.return_value = result
        assert deps.PermissionChecker("users.read")(user=SimpleNamespace(id=uuid.uuid4()), db=db) is True

    def test_missing_role_is_403(self, monkeypatch):
        from services.admin.app import dependencies as deps

        monkeypatch.setattr(deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: uuid.uuid4()))
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db = MagicMock()
        db.execute.return_value = result
        with pytest.raises(HTTPException) as exc:
            deps.PermissionChecker("users.read")(user=SimpleNamespace(id=uuid.uuid4()), db=db)
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# get_current_tenant missing-key edge and cleanup helper
# ---------------------------------------------------------------------------


class TestGetCurrentTenant:
    def test_missing_key_is_401_without_touching_store(self, monkeypatch):
        from services.admin.app import dependencies as deps

        async def _fail_store():  # pragma: no cover - must not be called
            raise AssertionError("key store must not be consulted without a key")

        monkeypatch.setattr(deps, "get_db_key_store", _fail_store)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps.get_current_tenant(key=None, db=MagicMock()))
        assert exc.value.status_code == 401

    def test_clear_helper_swallows_cleanup_errors(self, monkeypatch):
        from services.admin.app import dependencies as deps

        monkeypatch.setattr(
            deps.TenantContext,
            "clear_tenant_context",
            staticmethod(lambda _db: (_ for _ in ()).throw(RuntimeError("connection aborted"))),
        )
        deps._clear_tenant_context_best_effort(MagicMock())
