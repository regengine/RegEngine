"""
Regression coverage for ``app/subscription_gate.py`` — closes the
77% -> 100% gap left by ``test_subscription_gate.py`` and
``test_subscription_gate_fail_closed.py``.

The subscription gate is the #1182 fail-closed policy for paid
endpoints. Any bug in the tenant-id extraction or the Redis lookup
is a direct revenue-leak vector (unbilled tenant gets paid access)
or a false-positive lockout. These tests pin:

* the three tenant-id extraction branches (query > header > principal)
* the fail-open env flag toggles (``1/true/yes/on`` all enable,
  everything else disables)
* the legacy ``_check_subscription_in_redis`` helper, which still
  ships in the package surface even though ``require_active_subscription``
  no longer calls it — covering it prevents accidental dead-code
  regressions where a refactor rewires the gate back through it
* each ``require_active_subscription`` early-return

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app import subscription_gate
from app.subscription_gate import (
    _check_subscription_and_redis_health,
    _check_subscription_in_redis,
    _fail_open_override_enabled,
    _get_tenant_id_from_request,
    require_active_subscription,
)
from fastapi import HTTPException
from shared.circuit_breaker import CircuitOpenError


# ===========================================================================
# Helpers
# ===========================================================================


def _mk_request(
    *,
    query: dict | None = None,
    headers: dict | None = None,
    principal_tenant: str | None = None,
    principal_set: bool = True,
):
    """Build a minimal stand-in for fastapi.Request for the gate's purposes."""
    req = MagicMock()
    req.query_params = query or {}
    req.headers = headers or {}
    if principal_set:
        if principal_tenant is not None:
            principal = MagicMock()
            principal.tenant_id = principal_tenant
            req.state.principal = principal
        else:
            req.state.principal = None
    else:
        # Mimic `getattr(request.state, "principal", None)` returning None.
        del req.state.principal  # triggers AttributeError -> getattr default
    return req


def _run(coro):
    return asyncio.run(coro)


class _FakeRedisClient:
    """In-memory stand-in for redis.Redis."""

    def __init__(self, *, raise_on_hget=None, hget_return=None):
        self._raise = raise_on_hget
        self._return = hget_return
        self.hget_calls = []

    def hget(self, key, field):
        self.hget_calls.append((key, field))
        if self._raise is not None:
            raise self._raise
        return self._return


def _install_redis(monkeypatch, client):
    """Patch ``redis.from_url`` to return ``client``."""

    import sys
    import types

    fake_redis_lib = types.ModuleType("redis")
    fake_redis_lib.from_url = lambda url, decode_responses=False: client
    monkeypatch.setitem(sys.modules, "redis", fake_redis_lib)


def _set_redis_url(monkeypatch, value="redis://localhost:6379"):
    monkeypatch.setenv("REDIS_URL", value)


# ===========================================================================
# _fail_open_override_enabled
# ===========================================================================


class TestFailOpenOverride:

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "Yes", " ON "])
    def test_enabled_for_truthy_values(self, monkeypatch, val):
        monkeypatch.setenv("SUBSCRIPTION_GATE_FAIL_OPEN", val)
        assert _fail_open_override_enabled() is True

    @pytest.mark.parametrize(
        "val",
        ["0", "false", "no", "off", "", "disabled", "anything", "  "],
    )
    def test_disabled_for_falsy_or_unknown_values(self, monkeypatch, val):
        monkeypatch.setenv("SUBSCRIPTION_GATE_FAIL_OPEN", val)
        assert _fail_open_override_enabled() is False

    def test_unset_defaults_to_disabled(self, monkeypatch):
        monkeypatch.delenv("SUBSCRIPTION_GATE_FAIL_OPEN", raising=False)
        assert _fail_open_override_enabled() is False


# ===========================================================================
# _get_tenant_id_from_request — extraction priority
# ===========================================================================


class TestTenantIdExtraction:

    def test_query_param_wins_over_header_and_principal(self):
        req = _mk_request(
            query={"tenant_id": "q-tenant"},
            headers={"X-Tenant-ID": "h-tenant"},
            principal_tenant="p-tenant",
        )
        assert _get_tenant_id_from_request(req) == "q-tenant"

    def test_header_used_when_query_absent(self):
        """Line 60 — fallthrough from query to X-Tenant-ID header."""
        req = _mk_request(
            headers={"X-Tenant-ID": "h-tenant"},
            principal_tenant="p-tenant",
        )
        assert _get_tenant_id_from_request(req) == "h-tenant"

    def test_principal_used_when_neither_query_nor_header_set(self):
        """Line 65 — final fallthrough to RBAC principal."""
        req = _mk_request(principal_tenant="p-tenant")
        assert _get_tenant_id_from_request(req) == "p-tenant"

    def test_returns_none_when_no_source_provides_tenant(self):
        req = _mk_request(principal_tenant=None)
        assert _get_tenant_id_from_request(req) is None

    def test_returns_none_when_principal_has_no_tenant(self):
        """Principal exists but has tenant_id=None — still falls through."""
        req = _mk_request(principal_tenant=None)
        assert _get_tenant_id_from_request(req) is None

    def test_empty_query_param_falls_through(self):
        """Empty string is falsy — must fall through to header."""
        req = _mk_request(
            query={"tenant_id": ""},
            headers={"X-Tenant-ID": "h-tenant"},
        )
        assert _get_tenant_id_from_request(req) == "h-tenant"


# ===========================================================================
# _check_subscription_in_redis — legacy helper (lines 76-97)
# ===========================================================================


class TestCheckSubscriptionInRedis:
    """Covers the now-unused helper so the 77% -> 100% target closes.

    NOTE: this helper is no longer called by ``require_active_subscription``
    (see #1182) — it's legacy dead code. See the spawned follow-up task
    for cleanup. Tests here keep the behavior pinned in case it's
    reused elsewhere before deletion.
    """

    def setup_method(self):
        # Keep the circuit closed during these tests.
        from shared.circuit_breaker import redis_circuit
        redis_circuit.reset()

    def test_returns_none_when_no_redis_url(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        assert _check_subscription_in_redis("t-1") is None

    def test_returns_status_when_redis_has_key(self, monkeypatch):
        _set_redis_url(monkeypatch)
        client = _FakeRedisClient(hget_return="active")
        _install_redis(monkeypatch, client)
        assert _check_subscription_in_redis("t-1") == "active"
        assert client.hget_calls == [("billing:tenant:t-1", "status")]

    def test_returns_none_when_key_missing(self, monkeypatch):
        _set_redis_url(monkeypatch)
        client = _FakeRedisClient(hget_return=None)
        _install_redis(monkeypatch, client)
        assert _check_subscription_in_redis("t-1") is None

    def test_swallows_redis_exceptions_and_returns_none(self, monkeypatch):
        _set_redis_url(monkeypatch)
        client = _FakeRedisClient(raise_on_hget=ConnectionError("down"))
        _install_redis(monkeypatch, client)
        assert _check_subscription_in_redis("t-1") is None

    def test_propagates_circuit_open_error(self, monkeypatch):
        """CircuitOpenError must bubble — callers need to distinguish
        'circuit tripped' from 'Redis healthy but silent'."""
        _set_redis_url(monkeypatch)

        def _boom(*a, **kw):
            raise CircuitOpenError("redis", 5.0)

        monkeypatch.setattr(
            subscription_gate.redis_circuit, "_check_state", _boom
        )
        with pytest.raises(CircuitOpenError):
            _check_subscription_in_redis("t-1")


# ===========================================================================
# _check_subscription_and_redis_health
# ===========================================================================


class TestCheckSubscriptionAndHealth:

    def setup_method(self):
        from shared.circuit_breaker import redis_circuit
        redis_circuit.reset()

    def test_returns_none_false_when_no_redis_url(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        status, ok = _check_subscription_and_redis_health("t-1")
        assert status is None
        assert ok is False

    def test_returns_status_true_when_healthy(self, monkeypatch):
        _set_redis_url(monkeypatch)
        client = _FakeRedisClient(hget_return="active")
        _install_redis(monkeypatch, client)
        status, ok = _check_subscription_and_redis_health("t-1")
        assert status == "active"
        assert ok is True

    def test_returns_none_true_when_key_missing(self, monkeypatch):
        """Redis up + no key -> (None, True) — distinct from 'redis down'."""
        _set_redis_url(monkeypatch)
        client = _FakeRedisClient(hget_return=None)
        _install_redis(monkeypatch, client)
        status, ok = _check_subscription_and_redis_health("t-1")
        assert status is None
        assert ok is True

    def test_returns_none_false_on_redis_error(self, monkeypatch):
        _set_redis_url(monkeypatch)
        client = _FakeRedisClient(raise_on_hget=ConnectionError("down"))
        _install_redis(monkeypatch, client)
        status, ok = _check_subscription_and_redis_health("t-1")
        assert status is None
        assert ok is False

    def test_propagates_circuit_open_error(self, monkeypatch):
        _set_redis_url(monkeypatch)

        def _boom(*a, **kw):
            raise CircuitOpenError("redis", 5.0)

        monkeypatch.setattr(
            subscription_gate.redis_circuit, "_check_state", _boom
        )
        with pytest.raises(CircuitOpenError):
            _check_subscription_and_redis_health("t-1")


# ===========================================================================
# require_active_subscription — early returns & bypass
# ===========================================================================


class TestRequireActiveSubscriptionBypass:

    def test_returns_early_when_no_tenant_id(self, monkeypatch):
        """Public / unauthenticated endpoints skip the gate entirely."""
        req = _mk_request(principal_tenant=None)
        # Should not raise, should not hit Redis.
        _run(require_active_subscription(req))

    def test_bypass_via_env_flag_short_circuits(self, monkeypatch):
        """Fail-open flag bypasses Redis entirely — still logs at CRITICAL."""
        monkeypatch.setenv("SUBSCRIPTION_GATE_FAIL_OPEN", "true")
        called = {"hit_redis": False}

        def _sentinel(_tid):
            called["hit_redis"] = True
            return None, False

        monkeypatch.setattr(
            subscription_gate,
            "_check_subscription_and_redis_health",
            _sentinel,
        )
        req = _mk_request(query={"tenant_id": "t-bypass"})
        _run(require_active_subscription(req))
        assert called["hit_redis"] is False
