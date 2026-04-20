"""Regression tests for #1408 — per-tenant webhook outbox + HMAC + SSRF.

Covers:
  * ``enqueue_webhook`` writes a pending row tied to the caller's txn.
  * ``WebhookOutboxDrainer`` delivers pending rows and signs the
    payload with the tenant's ``review_webhook_secret``.
  * Transient failures (timeouts, 5xx, 429) reschedule with backoff;
    terminal failures (4xx that isn't 408/429) mark the row failed
    immediately; hitting ``max_attempts`` marks failed.
  * Per-tenant URL resolution: tenant A and tenant B each get their
    own URL from ``tenant.settings.review_webhook_url``.
  * SSRF guard rejects private / loopback / metadata hosts even if a
    compromised admin sets them.
  * Missing secret → ``_notify_webhook`` refuses to dispatch (no
    silent unsigned send).
  * End-to-end: delivery failure enqueues a row; second drain attempt
    succeeds and marks the row delivered.

Uses an in-memory SQLite DB with a table shape that matches the
Postgres migration. RLS / JSONB behavior is exercised in integration
tests separately.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from datetime import datetime, timezone
from typing import Tuple
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.metrics import (
    HallucinationTracker,
    SIGNATURE_HEADER,
    WebhookTargetError,
    _validate_webhook_url,
)
from app.webhook_outbox import (
    WebhookOutboxDrainer,
    enqueue_webhook,
    reconcile_webhook_outbox,
    sign_payload,
)


# ---------------------------------------------------------------------------
# Fixtures — SQLite in-memory webhook_outbox mirroring the migration
# ---------------------------------------------------------------------------


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE webhook_outbox (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       TEXT NOT NULL,
                event_type      TEXT NOT NULL,
                target_url      TEXT NOT NULL,
                payload         TEXT NOT NULL,
                dedupe_key      TEXT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                attempts        INTEGER NOT NULL DEFAULT 0,
                max_attempts    INTEGER NOT NULL DEFAULT 10,
                last_error      TEXT NULL,
                last_status_code INTEGER NULL,
                enqueued_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                delivered_at    TEXT NULL,
                next_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = SessionLocal()
    yield s
    s.close()


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


def test_enqueue_writes_pending_row(session):
    tenant = str(uuid4())
    enqueue_webhook(
        session,
        tenant_id=tenant,
        event_type="hallucination_resolved",
        target_url="https://example.test/webhook",
        payload={"review_id": "r-1", "status": "APPROVED"},
    )
    session.commit()

    row = session.execute(text("SELECT * FROM webhook_outbox")).mappings().first()
    assert row is not None
    assert row["status"] == "pending"
    assert row["tenant_id"] == tenant
    assert row["event_type"] == "hallucination_resolved"
    assert row["target_url"] == "https://example.test/webhook"
    assert row["attempts"] == 0
    payload = json.loads(row["payload"])
    assert payload == {"review_id": "r-1", "status": "APPROVED"}


def test_enqueue_rejects_missing_tenant(session):
    with pytest.raises(ValueError):
        enqueue_webhook(
            session,
            tenant_id="",
            event_type="x",
            target_url="https://ok.test/",
            payload={},
        )


def test_enqueue_rejects_empty_event_type(session):
    with pytest.raises(ValueError):
        enqueue_webhook(
            session,
            tenant_id=str(uuid4()),
            event_type="",
            target_url="https://ok.test/",
            payload={},
        )


def test_enqueue_rolls_back_with_caller_session(session):
    """Atomicity: if the caller rolls back, the outbox insert vanishes."""
    enqueue_webhook(
        session,
        tenant_id=str(uuid4()),
        event_type="x",
        target_url="https://ok.test/",
        payload={},
    )
    session.rollback()
    count = session.execute(text("SELECT COUNT(*) FROM webhook_outbox")).scalar()
    assert count == 0


# ---------------------------------------------------------------------------
# sign_payload — HMAC matches shared/webhook_security format
# ---------------------------------------------------------------------------


def test_sign_payload_hmac_matches_expected():
    secret = "whsec_test"
    body = b'{"event":"x"}'
    ts = 1700000000
    header = sign_payload(body, secret, timestamp=ts)

    # Format: "t=<ts>,v1=<hex>"
    assert header.startswith(f"t={ts},v1=")
    _, sig_part = header.split(",")
    assert sig_part.startswith("v1=")
    sig = sig_part[3:]

    expected = hmac.new(
        secret.encode("utf-8"),
        f"{ts}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    assert sig == expected


def test_sign_payload_requires_secret():
    with pytest.raises(ValueError):
        sign_payload(b"body", "")


# ---------------------------------------------------------------------------
# Drain — happy path
# ---------------------------------------------------------------------------


def _secret_lookup_for(mapping):
    def lookup(tenant_id: str) -> Tuple[str, str]:
        return mapping.get(tenant_id, (None, None))
    return lookup


class _Poster:
    """Recording fake HTTP poster."""

    def __init__(self, responses=None, exceptions=None):
        # responses: list[int | tuple[int, str]] consumed in order
        self.responses = list(responses) if responses else []
        # exceptions: list of Exception | None; None = use a response
        self.exceptions = list(exceptions) if exceptions else []
        self.calls = []

    def __call__(self, url, body, headers):
        self.calls.append({"url": url, "body": body, "headers": dict(headers)})
        if self.exceptions:
            exc = self.exceptions.pop(0)
            if exc is not None:
                raise exc
        resp = self.responses.pop(0)
        if isinstance(resp, tuple):
            return resp
        return resp, ""


def test_drainer_delivers_and_signs_payload(session):
    tenant = str(uuid4())
    secret = "whsec_tenant_a"
    enqueue_webhook(
        session,
        tenant_id=tenant,
        event_type="hallucination_resolved",
        target_url="https://tenant-a.example.test/hook",
        payload={"review_id": "r-1", "status": "APPROVED"},
    )
    session.commit()

    poster = _Poster(responses=[200])
    drainer = WebhookOutboxDrainer(
        session,
        secret_lookup=_secret_lookup_for(
            {tenant: ("https://tenant-a.example.test/hook", secret)}
        ),
        http_poster=poster,
    )

    summary = drainer.drain_once(batch_size=10)
    assert summary["delivered"] == 1
    assert summary["failed"] == 0
    assert summary["rescheduled"] == 0

    row = session.execute(text("SELECT * FROM webhook_outbox")).mappings().first()
    assert row["status"] == "delivered"
    assert row["last_status_code"] == 200

    # Signature header present and valid.
    assert len(poster.calls) == 1
    call = poster.calls[0]
    sig_header = call["headers"][SIGNATURE_HEADER]
    assert sig_header.startswith("t=") and ",v1=" in sig_header
    ts_part, sig_part = sig_header.split(",")
    ts = int(ts_part.split("=")[1])
    sig = sig_part.split("=")[1]
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{ts}.".encode() + call["body"],
        hashlib.sha256,
    ).hexdigest()
    assert sig == expected
    assert call["headers"]["X-RegEngine-Tenant"] == tenant
    assert call["headers"]["X-RegEngine-Event"] == "hallucination_resolved"


def test_drainer_routes_per_tenant_url(session):
    """Tenant A and Tenant B each see their own URL+secret."""
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    enqueue_webhook(
        session,
        tenant_id=tenant_a,
        event_type="hallucination_resolved",
        target_url="https://a.example.test/hook",
        payload={"review_id": "ra", "status": "APPROVED"},
    )
    enqueue_webhook(
        session,
        tenant_id=tenant_b,
        event_type="hallucination_resolved",
        target_url="https://b.example.test/hook",
        payload={"review_id": "rb", "status": "APPROVED"},
    )
    session.commit()

    poster = _Poster(responses=[200, 200])
    drainer = WebhookOutboxDrainer(
        session,
        secret_lookup=_secret_lookup_for({
            tenant_a: ("https://a.example.test/hook", "secret_a"),
            tenant_b: ("https://b.example.test/hook", "secret_b"),
        }),
        http_poster=poster,
    )
    drainer.drain_once(batch_size=10)

    # Two distinct targets.
    urls = {c["url"] for c in poster.calls}
    assert urls == {"https://a.example.test/hook", "https://b.example.test/hook"}

    # Per-tenant secrets: the HMAC for call A must validate under secret_a,
    # NOT under secret_b.
    for call in poster.calls:
        sig_header = call["headers"][SIGNATURE_HEADER]
        tenant_header = call["headers"]["X-RegEngine-Tenant"]
        secret = "secret_a" if tenant_header == tenant_a else "secret_b"
        ts_part, sig_part = sig_header.split(",")
        ts = int(ts_part.split("=")[1])
        sig = sig_part.split("=")[1]
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{ts}.".encode() + call["body"],
            hashlib.sha256,
        ).hexdigest()
        assert sig == expected


# ---------------------------------------------------------------------------
# Drain — failure modes
# ---------------------------------------------------------------------------


def test_drainer_reschedules_transient_5xx(session):
    tenant = str(uuid4())
    enqueue_webhook(
        session,
        tenant_id=tenant,
        event_type="e",
        target_url="https://ok.example.test/",
        payload={},
    )
    session.commit()

    poster = _Poster(responses=[(503, "upstream boom")])
    drainer = WebhookOutboxDrainer(
        session,
        secret_lookup=_secret_lookup_for({tenant: ("https://ok.example.test/", "s")}),
        http_poster=poster,
    )

    summary = drainer.drain_once(batch_size=10)
    assert summary["rescheduled"] == 1
    assert summary["delivered"] == 0
    assert summary["failed"] == 0

    row = session.execute(text("SELECT * FROM webhook_outbox")).mappings().first()
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert row["last_status_code"] == 503
    assert "503" in row["last_error"]


def test_drainer_reschedules_transient_429(session):
    tenant = str(uuid4())
    enqueue_webhook(
        session,
        tenant_id=tenant,
        event_type="e",
        target_url="https://ok.example.test/",
        payload={},
    )
    session.commit()

    poster = _Poster(responses=[(429, "rate limited")])
    drainer = WebhookOutboxDrainer(
        session,
        secret_lookup=_secret_lookup_for({tenant: ("https://ok.example.test/", "s")}),
        http_poster=poster,
    )
    summary = drainer.drain_once(batch_size=10)
    assert summary["rescheduled"] == 1


def test_drainer_marks_failed_on_terminal_4xx(session):
    """A 400/403 is not retriable — flip straight to failed."""
    tenant = str(uuid4())
    enqueue_webhook(
        session,
        tenant_id=tenant,
        event_type="e",
        target_url="https://ok.example.test/",
        payload={},
    )
    session.commit()

    poster = _Poster(responses=[(403, "signature invalid")])
    drainer = WebhookOutboxDrainer(
        session,
        secret_lookup=_secret_lookup_for({tenant: ("https://ok.example.test/", "s")}),
        http_poster=poster,
    )
    summary = drainer.drain_once(batch_size=10)
    assert summary["failed"] == 1
    row = session.execute(text("SELECT * FROM webhook_outbox")).mappings().first()
    assert row["status"] == "failed"
    assert row["last_status_code"] == 403


def test_drainer_reschedules_on_transport_error(session):
    tenant = str(uuid4())
    enqueue_webhook(
        session,
        tenant_id=tenant,
        event_type="e",
        target_url="https://ok.example.test/",
        payload={},
    )
    session.commit()

    poster = _Poster(exceptions=[RuntimeError("connection reset")])
    drainer = WebhookOutboxDrainer(
        session,
        secret_lookup=_secret_lookup_for({tenant: ("https://ok.example.test/", "s")}),
        http_poster=poster,
    )
    summary = drainer.drain_once(batch_size=10)
    assert summary["rescheduled"] == 1
    row = session.execute(text("SELECT * FROM webhook_outbox")).mappings().first()
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert "connection reset" in row["last_error"]


def test_drainer_marks_failed_after_max_attempts(session):
    tenant = str(uuid4())
    enqueue_webhook(
        session,
        tenant_id=tenant,
        event_type="e",
        target_url="https://ok.example.test/",
        payload={},
        max_attempts=2,
    )
    session.commit()

    # First attempt fails transiently -> attempts=1, pending.
    poster1 = _Poster(responses=[(503, "boom")])
    drainer = WebhookOutboxDrainer(
        session,
        secret_lookup=_secret_lookup_for({tenant: ("https://ok.example.test/", "s")}),
        http_poster=poster1,
    )
    drainer.drain_once(batch_size=10)

    # Reset next_attempt_at so we claim it again without sleeping.
    session.execute(text("UPDATE webhook_outbox SET next_attempt_at = :now"), {
        "now": datetime.now(timezone.utc).isoformat(),
    })
    session.commit()

    # Second attempt fails transiently -> attempts=2 which hits max -> failed.
    poster2 = _Poster(responses=[(503, "boom")])
    drainer2 = WebhookOutboxDrainer(
        session,
        secret_lookup=_secret_lookup_for({tenant: ("https://ok.example.test/", "s")}),
        http_poster=poster2,
    )
    summary2 = drainer2.drain_once(batch_size=10)
    assert summary2["failed"] == 1

    row = session.execute(text("SELECT * FROM webhook_outbox")).mappings().first()
    assert row["status"] == "failed"
    # attempts counter reflects the last-persisted value before the
    # exhaustion verdict; the "exhausted N attempts" message carries
    # the arithmetic check.
    assert "exhausted 2 attempts" in row["last_error"]


def test_drainer_marks_failed_when_tenant_removes_config(session):
    """Tenant had URL+secret at enqueue; has since cleared both."""
    tenant = str(uuid4())
    enqueue_webhook(
        session,
        tenant_id=tenant,
        event_type="e",
        target_url="https://ok.example.test/",
        payload={},
    )
    session.commit()

    # Secret lookup returns (None, None) → drainer refuses to dispatch
    # and marks the row failed so ops can see the config drift.
    drainer = WebhookOutboxDrainer(
        session,
        secret_lookup=_secret_lookup_for({}),
        http_poster=_Poster(responses=[]),
    )
    summary = drainer.drain_once(batch_size=10)
    assert summary["failed"] == 1
    row = session.execute(text("SELECT * FROM webhook_outbox")).mappings().first()
    assert row["status"] == "failed"
    assert "no longer configured" in row["last_error"]


def test_drainer_retries_and_succeeds_on_second_attempt(session):
    """End-to-end: first drain fails, second drain delivers."""
    tenant = str(uuid4())
    enqueue_webhook(
        session,
        tenant_id=tenant,
        event_type="hallucination_resolved",
        target_url="https://flaky.example.test/",
        payload={"review_id": "r-1", "status": "APPROVED"},
    )
    session.commit()

    secret_map = {tenant: ("https://flaky.example.test/", "s")}

    # Attempt 1: 503 → reschedule.
    poster1 = _Poster(responses=[(503, "down")])
    d1 = WebhookOutboxDrainer(
        session,
        secret_lookup=_secret_lookup_for(secret_map),
        http_poster=poster1,
    )
    s1 = d1.drain_once(batch_size=10)
    assert s1["rescheduled"] == 1

    # Skip the backoff by resetting next_attempt_at.
    session.execute(text("UPDATE webhook_outbox SET next_attempt_at = :now"), {
        "now": datetime.now(timezone.utc).isoformat(),
    })
    session.commit()

    # Attempt 2: 200 → delivered.
    poster2 = _Poster(responses=[200])
    d2 = WebhookOutboxDrainer(
        session,
        secret_lookup=_secret_lookup_for(secret_map),
        http_poster=poster2,
    )
    s2 = d2.drain_once(batch_size=10)
    assert s2["delivered"] == 1

    row = session.execute(text("SELECT * FROM webhook_outbox")).mappings().first()
    assert row["status"] == "delivered"
    assert row["attempts"] == 1  # bumped on the rescheduled failure
    assert row["last_status_code"] == 200


# ---------------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/",                  # non-https
        "https://10.0.0.1/",                     # RFC1918
        "https://127.0.0.1/",                    # loopback
        "https://localhost/",                    # loopback name
        "https://169.254.169.254/metadata",      # AWS IMDS literal
        "https://metadata.google.internal/",     # GCP IMDS name
        "https://192.168.1.1/",                  # RFC1918
        "https://[::1]/",                        # IPv6 loopback
    ],
)
def test_ssrf_guard_rejects_unsafe(url):
    with pytest.raises(WebhookTargetError):
        _validate_webhook_url(url)


def test_ssrf_guard_rejects_non_allowlisted_host():
    with pytest.raises(WebhookTargetError):
        _validate_webhook_url(
            "https://evil.example.test/hook",
            host_allowlist=["buyer-a.example.com"],
        )


def test_ssrf_guard_accepts_allowlisted_host():
    # A public host (uses DNS). example.com is a stable IANA-reserved
    # domain that always resolves to a public IP.
    _validate_webhook_url(
        "https://example.com/webhook",
        host_allowlist=["example.com"],
    )


# ---------------------------------------------------------------------------
# HallucinationTracker._notify_webhook integration
# ---------------------------------------------------------------------------


class _FakeTenant:
    def __init__(self, settings):
        self.settings = settings


class _FakeTenantSession:
    """Session that pretends to load a tenant by id."""

    def __init__(self, tenants, engine=None):
        self._tenants = tenants
        self.bind = engine
        self.executed = []

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        return None

    def get(self, model, key):
        return self._tenants.get(str(key))

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None

    def add(self, obj):
        pass

    def flush(self):
        pass

    def refresh(self, obj):
        pass

    def query(self, model):  # pragma: no cover — not used here
        raise NotImplementedError


def _wait(threads, timeout=5.0):
    for t in threads:
        t.join(timeout)


def _drain_background_threads(timeout=2.0):
    # Best-effort wait for daemon dispatcher threads.
    main = threading.main_thread()
    for t in list(threading.enumerate()):
        if t is main or not t.daemon:
            continue
        t.join(timeout)


@pytest.fixture(autouse=True)
def _bypass_dns_resolution(monkeypatch):
    """Skip DNS in ``_validate_webhook_url`` for notify-webhook tests.

    The SSRF-guard *unit tests* exercise the real function with literal
    IPs and loopback names (which never hit the resolver). The higher-
    level ``_notify_webhook`` tests use synthetic public hostnames
    (``*.example.com``) that would otherwise fail ``getaddrinfo`` in a
    sandboxed test environment — so we replace the DNS call with a
    stub that returns a public-looking IP.
    """
    import socket as _socket

    real = _socket.getaddrinfo

    def _stub(host, *args, **kwargs):
        # If the test explicitly passed a loopback / RFC1918 literal,
        # the ipaddress short-circuit in _validate_webhook_url has
        # already run; this stub is only reached for DNS names. We
        # hand back a public IP so non-blocklisted hosts resolve.
        if host in {"example.com", "www.example.com"} or host.endswith(".example.com") or host.endswith(".example.test"):
            return [(2, 1, 6, "", ("93.184.216.34", 0))]
        return real(host, *args, **kwargs)

    monkeypatch.setattr(_socket, "getaddrinfo", _stub)


def test_notify_webhook_skips_when_tenant_has_no_config(monkeypatch):
    """No tenant-settings URL + no env fallback → quiet no-op."""
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_SECRET", raising=False)

    tenant_uuid = uuid4()
    tenants = {str(tenant_uuid): _FakeTenant({})}

    calls = []

    def dispatcher(url, body, headers):
        calls.append((url, body, headers))
        return 200, ""

    tracker = HallucinationTracker(
        session_factory=lambda: _FakeTenantSession(tenants),
        redis_client=None,
        webhook_dispatcher=dispatcher,
    )

    tracker._notify_webhook({"review_id": "r1"}, "APPROVED", tenant_uuid)
    _drain_background_threads()

    # Nothing dispatched; nothing enqueued.
    assert calls == []


def test_notify_webhook_refuses_without_secret(monkeypatch):
    """URL configured but secret missing → refuse to dispatch."""
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_SECRET", raising=False)

    tenant_uuid = uuid4()
    tenants = {
        str(tenant_uuid): _FakeTenant({
            "review_webhook_url": "https://ok.example.com/hook",
            # No review_webhook_secret.
        })
    }

    dispatched = []
    tracker = HallucinationTracker(
        session_factory=lambda: _FakeTenantSession(tenants),
        redis_client=None,
        webhook_dispatcher=lambda u, b, h: dispatched.append((u, b, h)) or (200, ""),
    )
    tracker._notify_webhook({"review_id": "r1"}, "APPROVED", tenant_uuid)
    _drain_background_threads()
    assert dispatched == []


def test_notify_webhook_rejects_private_ip(monkeypatch):
    """A compromised admin sets an internal IP → SSRF guard blocks."""
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_SECRET", raising=False)

    tenant_uuid = uuid4()
    tenants = {
        str(tenant_uuid): _FakeTenant({
            "review_webhook_url": "https://10.0.0.5/hook",
            "review_webhook_secret": "s",
        })
    }

    dispatched = []
    tracker = HallucinationTracker(
        session_factory=lambda: _FakeTenantSession(tenants),
        redis_client=None,
        webhook_dispatcher=lambda u, b, h: dispatched.append((u, b, h)) or (200, ""),
    )
    tracker._notify_webhook({"review_id": "r1"}, "APPROVED", tenant_uuid)
    _drain_background_threads()
    assert dispatched == []


def test_notify_webhook_signs_with_tenant_secret(monkeypatch):
    """Happy path: per-tenant secret produces matching HMAC header."""
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_SECRET", raising=False)

    tenant_uuid = uuid4()
    tenants = {
        str(tenant_uuid): _FakeTenant({
            "review_webhook_url": "https://buyer-a.example.com/hook",
            "review_webhook_secret": "whsec_buyer_a",
        })
    }

    captured = []

    def dispatcher(url, body, headers):
        captured.append({"url": url, "body": body, "headers": dict(headers)})
        return 200, ""

    tracker = HallucinationTracker(
        session_factory=lambda: _FakeTenantSession(tenants),
        redis_client=None,
        webhook_dispatcher=dispatcher,
    )
    tracker._notify_webhook(
        {"review_id": "r1", "text_raw": "secret-ish"},
        "APPROVED",
        tenant_uuid,
    )
    _drain_background_threads()

    assert len(captured) == 1
    call = captured[0]
    assert call["url"] == "https://buyer-a.example.com/hook"
    sig_header = call["headers"][SIGNATURE_HEADER]
    ts_part, sig_part = sig_header.split(",")
    ts = int(ts_part.split("=")[1])
    sig = sig_part.split("=")[1]
    expected = hmac.new(
        b"whsec_buyer_a",
        f"{ts}.".encode() + call["body"],
        hashlib.sha256,
    ).hexdigest()
    assert sig == expected
    assert call["headers"]["X-RegEngine-Tenant"] == str(tenant_uuid)


def test_notify_webhook_distinct_per_tenant(monkeypatch):
    """Tenant A and B each get their own URL; neither sees the other."""
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_SECRET", raising=False)

    tenant_a = uuid4()
    tenant_b = uuid4()
    tenants = {
        str(tenant_a): _FakeTenant({
            "review_webhook_url": "https://a.example.com/hook",
            "review_webhook_secret": "s_a",
        }),
        str(tenant_b): _FakeTenant({
            "review_webhook_url": "https://b.example.com/hook",
            "review_webhook_secret": "s_b",
        }),
    }

    captured = []

    def dispatcher(url, body, headers):
        captured.append(url)
        return 200, ""

    # Shared tracker but the session factory hands out a fresh fake
    # each call so both lookups see the map.
    tracker = HallucinationTracker(
        session_factory=lambda: _FakeTenantSession(tenants),
        redis_client=None,
        webhook_dispatcher=dispatcher,
    )
    tracker._notify_webhook({"review_id": "ra"}, "APPROVED", tenant_a)
    tracker._notify_webhook({"review_id": "rb"}, "APPROVED", tenant_b)
    _drain_background_threads()

    assert set(captured) == {"https://a.example.com/hook", "https://b.example.com/hook"}


def test_notify_webhook_on_failure_enqueues_to_outbox(monkeypatch):
    """Delivery failure → a webhook_outbox row is written."""
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HALLUCINATION_WEBHOOK_SECRET", raising=False)

    # Build a real in-memory DB so the enqueue actually persists.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE webhook_outbox (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       TEXT NOT NULL,
                event_type      TEXT NOT NULL,
                target_url      TEXT NOT NULL,
                payload         TEXT NOT NULL,
                dedupe_key      TEXT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                attempts        INTEGER NOT NULL DEFAULT 0,
                max_attempts    INTEGER NOT NULL DEFAULT 10,
                last_error      TEXT NULL,
                last_status_code INTEGER NULL,
                enqueued_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                delivered_at    TEXT NULL,
                next_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    tenant_uuid = uuid4()
    # Our session factory has TWO responsibilities in production: loading
    # the tenant row and writing to the outbox. We fake both with a
    # hybrid: the tenant lookup side lives on a wrapper that delegates
    # ``session.get(TenantModel, ...)`` to an in-memory dict and all
    # else to the real SQLite session.
    from app.metrics import TenantModel as _TenantModel  # noqa: F401

    tenants = {
        str(tenant_uuid): _FakeTenant({
            "review_webhook_url": "https://flaky.example.com/hook",
            "review_webhook_secret": "s",
        })
    }

    class _HybridSession:
        def __init__(self):
            self._real = SessionLocal()

        def get(self, model, key):
            if model is _TenantModel:
                return tenants.get(str(key))
            return self._real.get(model, key)

        def execute(self, *args, **kwargs):
            return self._real.execute(*args, **kwargs)

        def commit(self):
            return self._real.commit()

        def rollback(self):
            return self._real.rollback()

        def close(self):
            return self._real.close()

        def add(self, obj):
            return self._real.add(obj)

        def flush(self):
            return self._real.flush()

        def refresh(self, obj):
            return self._real.refresh(obj)

        @property
        def bind(self):
            return self._real.bind

    def dispatcher(url, body, headers):
        return 503, "down"

    tracker = HallucinationTracker(
        session_factory=_HybridSession,
        redis_client=None,
        webhook_dispatcher=dispatcher,
    )

    tracker._notify_webhook(
        {"review_id": "r-1"},
        "APPROVED",
        tenant_uuid,
    )
    _drain_background_threads(timeout=3.0)

    inspect = SessionLocal()
    try:
        row = inspect.execute(text("SELECT * FROM webhook_outbox")).mappings().first()
    finally:
        inspect.close()

    assert row is not None
    assert row["status"] == "pending"
    assert row["tenant_id"] == str(tenant_uuid)
    assert row["target_url"] == "https://flaky.example.com/hook"
    assert row["event_type"] == "hallucination_resolved"
    # Payload captured with the serialized review body.
    payload = json.loads(row["payload"])
    assert payload["event"] == "hallucination_resolved"
    assert payload["status"] == "APPROVED"
    assert payload["data"] == {"review_id": "r-1"}


# ---------------------------------------------------------------------------
# reconcile_webhook_outbox
# ---------------------------------------------------------------------------


def test_reconcile_reports_counts_and_age(session):
    tenant = str(uuid4())
    enqueue_webhook(
        session, tenant_id=tenant, event_type="e",
        target_url="https://ok.example.test/", payload={},
    )
    enqueue_webhook(
        session, tenant_id=tenant, event_type="e",
        target_url="https://ok.example.test/", payload={},
        dedupe_key="dk2",
    )
    session.commit()

    # Mark one as failed for the counter test.
    session.execute(text("UPDATE webhook_outbox SET status = 'failed' WHERE id = 2"))
    session.commit()

    health = reconcile_webhook_outbox(session)
    assert health.pending_count == 1
    assert health.failed_count == 1
    assert health.oldest_pending_age_seconds is not None
    assert health.oldest_pending_age_seconds >= 0.0
