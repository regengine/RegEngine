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
        ("/docs", True),
        ("/docs/oauth2-redirect", True),
        ("/openapi.json", True),
        ("/metrics", True),
        ("/favicon.ico", True),
        ("/admin/users", False),
        ("/v1/compliance/00000000-0000-0000-0000-000000000000/alerts", False),
    ],
)
def test_should_skip(path, expected):
    assert _should_skip(path) is expected


# ---------------------------------------------------------------------------
# #1414 — trusted-proxy XFF gate
# ---------------------------------------------------------------------------


def test_trusted_proxy_env_unset(monkeypatch):
    monkeypatch.delenv("AUDIT_TRUSTED_PROXY_CIDRS", raising=False)
    assert _trusted_proxy_cidrs() == []
    assert _is_trusted_proxy("10.0.0.1") is False


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
