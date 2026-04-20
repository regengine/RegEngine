"""Regression tests for EPIC-K admin hygiene (#1414, #1415).

Covers the pure helpers that don't require a live DB session so they run
green in any harness. Integration coverage for #1083 (SELECT FOR UPDATE),
#1405 (service-layer tenant scope), #1406 (sysadmin reactivation), and
#1407 (supplier demo RBAC) requires a postgres fixture and lives in
integration tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

# pytest.importorskip guards against test environments where FastAPI isn't
# installed (CI job matrix).
pytest.importorskip("starlette")

from app import audit  # noqa: E402
from app.audit_integrity import verify_chain  # noqa: E402
from app.audit_middleware import (  # noqa: E402
    _should_skip,
    _should_skip_request,
    _trusted_proxy_cidrs,
    _is_trusted_proxy,
    AuditContextMiddleware,
)


# ---------------------------------------------------------------------------
# #1414 — audit middleware skip list
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/health", True),
        ("/healthz", True),
        ("/health/db", True),  # /health/* subpath — #1414
        ("/health/live", True),
        ("/ready", True),
        ("/readyz", True),
        ("/docs", True),
        ("/docs/oauth2-redirect", True),
        ("/openapi.json", True),
        ("/metrics", True),
        ("/favicon.ico", True),
        ("/admin/users", False),
        ("/v1/compliance/00000000-0000-0000-0000-000000000000/alerts", False),
        # "/healthcheck" must NOT match /health skip — it's a real route name.
        ("/healthcheck", False),
    ],
)
def test_should_skip(path, expected):
    assert _should_skip(path) is expected


@pytest.mark.parametrize(
    "method,path,expected",
    [
        # OPTIONS preflight is always skipped regardless of path — #1414.
        ("OPTIONS", "/admin/users", True),
        ("OPTIONS", "/v1/compliance/alerts", True),
        ("OPTIONS", "/health", True),
        # Normal methods on real routes are NOT skipped.
        ("GET", "/admin/users", False),
        ("POST", "/v1/admin/invitations", False),
        ("PATCH", "/v1/admin/users/1/role", False),
        # Normal methods on skip-list paths ARE skipped.
        ("GET", "/health", True),
        ("GET", "/docs", True),
        ("GET", "/metrics", True),
    ],
)
def test_should_skip_request(method, path, expected):
    assert _should_skip_request(method, path) is expected


# ---------------------------------------------------------------------------
# #1414 — trusted-proxy XFF gate
# ---------------------------------------------------------------------------


def test_trusted_proxy_env_unset(monkeypatch):
    monkeypatch.delenv("AUDIT_TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    assert _trusted_proxy_cidrs() == []
    assert _is_trusted_proxy("10.0.0.1") is False


def test_trusted_proxy_shared_alias_accepted(monkeypatch):
    """``TRUSTED_PROXY_CIDRS`` is accepted as an alias for
    ``AUDIT_TRUSTED_PROXY_CIDRS`` so this config can be shared across
    services without duplicating env per service."""
    monkeypatch.delenv("AUDIT_TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    assert _is_trusted_proxy("10.0.0.5") is True


def test_trusted_proxy_audit_var_wins_over_shared(monkeypatch):
    """If both env vars are set, the explicit AUDIT_* name wins."""
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "172.16.0.0/12")
    assert _is_trusted_proxy("10.0.0.5") is True
    assert _is_trusted_proxy("172.16.0.5") is False


def test_trusted_proxy_ipv6_cidr(monkeypatch):
    """IPv6 CIDRs are honored — at minimum we don't crash on an IPv6 peer."""
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "2001:db8::/32")
    assert _is_trusted_proxy("2001:db8::1") is True
    assert _is_trusted_proxy("2001:db9::1") is False


def test_trusted_proxy_single_cidr(monkeypatch):
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    assert _is_trusted_proxy("10.5.5.5") is True
    assert _is_trusted_proxy("192.168.1.1") is False
    assert _is_trusted_proxy("not-an-ip") is False


def test_trusted_proxy_multiple_cidrs(monkeypatch):
    monkeypatch.setenv(
        "AUDIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8, 172.16.0.0/12, 127.0.0.1/32",
    )
    assert _is_trusted_proxy("10.0.0.1") is True
    assert _is_trusted_proxy("172.17.0.1") is True
    assert _is_trusted_proxy("127.0.0.1") is True
    assert _is_trusted_proxy("127.0.0.2") is False
    assert _is_trusted_proxy("8.8.8.8") is False


def test_trusted_proxy_bad_cidr_skipped(monkeypatch):
    """Malformed CIDR entries don't crash; they just don't match."""
    monkeypatch.setenv(
        "AUDIT_TRUSTED_PROXY_CIDRS", "not-a-cidr, 10.0.0.0/8",
    )
    assert _is_trusted_proxy("10.0.0.1") is True


# ---------------------------------------------------------------------------
# #1414 — _get_client_ip respects the proxy gate
# ---------------------------------------------------------------------------


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, headers: dict, client_host: str | None):
        self.headers = headers
        self.client = _FakeClient(client_host) if client_host else None


def test_get_client_ip_untrusted_ignores_xff(monkeypatch):
    """Untrusted peer — XFF is ignored, socket IP wins."""
    monkeypatch.delenv("AUDIT_TRUSTED_PROXY_CIDRS", raising=False)
    req = _FakeRequest(
        headers={"x-forwarded-for": "1.2.3.4", "x-real-ip": "5.6.7.8"},
        client_host="192.168.1.100",
    )
    assert AuditContextMiddleware._get_client_ip(req) == "192.168.1.100"


def test_get_client_ip_trusted_uses_xff(monkeypatch):
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "192.168.0.0/16")
    req = _FakeRequest(
        headers={"x-forwarded-for": "1.2.3.4, 10.0.0.1"},
        client_host="192.168.1.100",
    )
    assert AuditContextMiddleware._get_client_ip(req) == "1.2.3.4"


def test_get_client_ip_trusted_falls_back_to_x_real_ip(monkeypatch):
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "192.168.0.0/16")
    req = _FakeRequest(
        headers={"x-real-ip": "5.6.7.8"},
        client_host="192.168.1.100",
    )
    assert AuditContextMiddleware._get_client_ip(req) == "5.6.7.8"


def test_get_client_ip_no_client():
    req = _FakeRequest(headers={}, client_host=None)
    assert AuditContextMiddleware._get_client_ip(req) == "unknown"


def test_get_client_ip_trusted_malformed_xff_falls_back(monkeypatch):
    """Trusted peer, but XFF first hop isn't a valid IP — fall back to
    the socket address rather than returning garbage into actor_ip."""
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "192.168.0.0/16")
    req = _FakeRequest(
        headers={"x-forwarded-for": "not-an-ip"},
        client_host="192.168.1.100",
    )
    assert AuditContextMiddleware._get_client_ip(req) == "192.168.1.100"


def test_get_client_ip_trusted_empty_xff_falls_back(monkeypatch):
    """Trusted peer, empty XFF header — fall back to socket address."""
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "192.168.0.0/16")
    req = _FakeRequest(
        headers={"x-forwarded-for": "   "},
        client_host="192.168.1.100",
    )
    assert AuditContextMiddleware._get_client_ip(req) == "192.168.1.100"


def test_get_client_ip_trusted_ipv6_xff(monkeypatch):
    """IPv6 hop in XFF from a trusted proxy is accepted."""
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "2001:db8::/32")
    req = _FakeRequest(
        headers={"x-forwarded-for": "2001:db8::1, 10.0.0.1"},
        client_host="2001:db8::100",
    )
    assert AuditContextMiddleware._get_client_ip(req) == "2001:db8::1"


def test_get_client_ip_trusted_ipv6_peer_ipv4_xff(monkeypatch):
    """Trusted IPv6 peer forwarding an IPv4 XFF hop — should not crash
    and should return the client-side IPv4."""
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "2001:db8::/32")
    req = _FakeRequest(
        headers={"x-forwarded-for": "203.0.113.7"},
        client_host="2001:db8::100",
    )
    assert AuditContextMiddleware._get_client_ip(req) == "203.0.113.7"


def test_get_client_ip_trusted_malformed_real_ip_falls_back(monkeypatch):
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "192.168.0.0/16")
    req = _FakeRequest(
        headers={"x-real-ip": "totally-bogus"},
        client_host="192.168.1.100",
    )
    assert AuditContextMiddleware._get_client_ip(req) == "192.168.1.100"


# ---------------------------------------------------------------------------
# #1414 — dispatch-level integration: skip list + OPTIONS short-circuits
# before audit work runs. We exercise the real middleware to prove the
# skip gate is wired at dispatch, not just a free helper.
# ---------------------------------------------------------------------------


class _FakeURL:
    def __init__(self, path: str):
        self.path = path


class _DispatchFakeRequest:
    """Minimal Request stand-in for dispatch. We never call call_next's
    result, so Response mocking is unnecessary."""

    def __init__(
        self,
        method: str,
        path: str,
        headers: dict | None = None,
        client_host: str | None = "192.168.1.100",
    ):
        self.method = method
        self.url = _FakeURL(path)
        self.headers = headers or {}
        self.client = _FakeClient(client_host) if client_host else None

        class _State:
            pass

        self.state = _State()


@pytest.mark.asyncio
async def test_dispatch_skips_health_no_audit_context():
    """/health GET must NOT attach audit_context."""
    mw = AuditContextMiddleware(app=None)

    async def call_next(_req):
        return "response_sentinel"

    req = _DispatchFakeRequest("GET", "/health")
    resp = await mw.dispatch(req, call_next)
    assert resp == "response_sentinel"
    assert not hasattr(req.state, "audit_context")


@pytest.mark.asyncio
async def test_dispatch_skips_docs_no_audit_context():
    mw = AuditContextMiddleware(app=None)

    async def call_next(_req):
        return "response_sentinel"

    req = _DispatchFakeRequest("GET", "/docs")
    resp = await mw.dispatch(req, call_next)
    assert resp == "response_sentinel"
    assert not hasattr(req.state, "audit_context")


@pytest.mark.asyncio
async def test_dispatch_skips_options_preflight_no_audit_context():
    """OPTIONS preflight on a real route must NOT attach audit_context."""
    mw = AuditContextMiddleware(app=None)

    async def call_next(_req):
        return "response_sentinel"

    req = _DispatchFakeRequest("OPTIONS", "/v1/admin/users")
    resp = await mw.dispatch(req, call_next)
    assert resp == "response_sentinel"
    assert not hasattr(req.state, "audit_context")


@pytest.mark.asyncio
async def test_dispatch_attaches_context_on_real_route(monkeypatch):
    """Regular /v1/admin GET — middleware DOES attach audit context, and
    actor_ip is the socket IP (no trusted proxy configured)."""
    monkeypatch.delenv("AUDIT_TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    mw = AuditContextMiddleware(app=None)

    async def call_next(_req):
        return "response_sentinel"

    req = _DispatchFakeRequest(
        "GET",
        "/v1/admin/users",
        headers={"x-forwarded-for": "1.2.3.4", "user-agent": "pytest/1.0"},
        client_host="203.0.113.9",
    )
    resp = await mw.dispatch(req, call_next)
    assert resp == "response_sentinel"
    ctx = req.state.audit_context
    # Untrusted peer — XFF ignored, socket IP used.
    assert ctx["actor_ip"] == "203.0.113.9"
    assert ctx["actor_ua"] == "pytest/1.0"
    assert ctx["endpoint"] == "GET /v1/admin/users"
    assert ctx["request_id"]  # non-empty uuid


# ---------------------------------------------------------------------------
# #1415 — audit hash includes actor fields
# ---------------------------------------------------------------------------


def _base_hash_kwargs():
    return dict(
        prev_hash="deadbeef",
        tenant_id="tenant-a",
        timestamp="2026-04-18T12:00:00+00:00",
        event_type="membership.role_change",
        action="membership.role_change",
        resource_id="user-1",
        metadata={"old_role": "Owner", "new_role": "Member"},
    )


def test_hash_v2_changes_when_actor_id_changes():
    """SQL-rewriting actor_id MUST break the chain (#1415)."""
    h1 = audit.compute_integrity_hash(
        **_base_hash_kwargs(),
        actor_id="actor-1", actor_email="a@x.com", severity="info", endpoint="PATCH /admin/users/1/role",
    )
    h2 = audit.compute_integrity_hash(
        **_base_hash_kwargs(),
        actor_id="actor-2", actor_email="a@x.com", severity="info", endpoint="PATCH /admin/users/1/role",
    )
    assert h1 != h2


def test_hash_v2_changes_when_actor_email_changes():
    h1 = audit.compute_integrity_hash(
        **_base_hash_kwargs(),
        actor_id="actor-1", actor_email="alice@x.com", severity="info", endpoint="PATCH /x",
    )
    h2 = audit.compute_integrity_hash(
        **_base_hash_kwargs(),
        actor_id="actor-1", actor_email="bob@x.com", severity="info", endpoint="PATCH /x",
    )
    assert h1 != h2


def test_hash_v2_changes_when_severity_changes():
    h1 = audit.compute_integrity_hash(
        **_base_hash_kwargs(),
        actor_id="a", actor_email=None, severity="info", endpoint="/x",
    )
    h2 = audit.compute_integrity_hash(
        **_base_hash_kwargs(),
        actor_id="a", actor_email=None, severity="warning", endpoint="/x",
    )
    assert h1 != h2


def test_hash_v2_changes_when_endpoint_changes():
    h1 = audit.compute_integrity_hash(
        **_base_hash_kwargs(),
        actor_id="a", actor_email=None, severity="info", endpoint="/x",
    )
    h2 = audit.compute_integrity_hash(
        **_base_hash_kwargs(),
        actor_id="a", actor_email=None, severity="info", endpoint="/y",
    )
    assert h1 != h2


def test_hash_v2_differs_from_v1_for_same_core_fields():
    """v2 must produce a distinct hash from v1 for the same tenant/event/
    metadata — otherwise the hash schema is ambiguous."""
    v1 = audit.compute_integrity_hash(**_base_hash_kwargs(), version=1)
    v2 = audit.compute_integrity_hash(
        **_base_hash_kwargs(),
        actor_id=None, actor_email=None, severity=None, endpoint=None,
    )
    assert v1 != v2


def test_verify_chain_accepts_v1_and_v2_rows():
    """Legacy v1 rows remain verifiable after the schema migration to v2."""
    # Build a two-row chain: one v1 (legacy), one v2 (new).
    ts1 = "2026-04-01T00:00:00+00:00"
    ts2 = "2026-04-02T00:00:00+00:00"
    row1_hash = audit.compute_integrity_hash(
        prev_hash=None,
        tenant_id="t1",
        timestamp=ts1,
        event_type="login",
        action="login",
        resource_id=None,
        metadata={},
        version=1,
    )
    row2_hash = audit.compute_integrity_hash(
        prev_hash=row1_hash,
        tenant_id="t1",
        timestamp=ts2,
        event_type="role_change",
        action="role_change",
        resource_id="u1",
        metadata={"n": 1},
        actor_id="actor-1",
        actor_email="a@x.com",
        severity="info",
        endpoint="PATCH /x",
    )
    entries = [
        {
            "id": 1,
            "tenant_id": "t1",
            "timestamp": ts1,
            "event": {"type": "login", "action": "login"},
            "resource": {"id": None},
            "metadata": {},
            "integrity": {"prev_hash": None, "hash": row1_hash},
        },
        {
            "id": 2,
            "tenant_id": "t1",
            "timestamp": ts2,
            "event": {"type": "role_change", "action": "role_change"},
            "resource": {"id": "u1"},
            "metadata": {"n": 1},
            "actor": {"id": "actor-1", "email": "a@x.com"},
            "severity": "info",
            "endpoint": "PATCH /x",
            "integrity": {"prev_hash": row1_hash, "hash": row2_hash},
        },
    ]
    result = verify_chain(entries)
    assert result["valid"] is True, result
    assert result["verified"] == 2


def test_verify_chain_detects_actor_tampering():
    """An attacker rewrites actor_email in a v2 row — chain MUST break."""
    ts = "2026-04-02T00:00:00+00:00"
    real_hash = audit.compute_integrity_hash(
        prev_hash=None,
        tenant_id="t1",
        timestamp=ts,
        event_type="role_change",
        action="role_change",
        resource_id="u1",
        metadata={},
        actor_id="actor-1",
        actor_email="alice@x.com",
        severity="info",
        endpoint="PATCH /x",
    )
    # Tampered row — same hash stored, but actor_email rewritten.
    entries = [
        {
            "id": 1,
            "tenant_id": "t1",
            "timestamp": ts,
            "event": {"type": "role_change", "action": "role_change"},
            "resource": {"id": "u1"},
            "metadata": {},
            "actor": {"id": "actor-1", "email": "bob@x.com"},  # ← rewritten
            "severity": "info",
            "endpoint": "PATCH /x",
            "integrity": {"prev_hash": None, "hash": real_hash},
        },
    ]
    result = verify_chain(entries)
    assert result["valid"] is False
    assert any(e["error"] == "integrity_hash_mismatch" for e in result["errors"])
