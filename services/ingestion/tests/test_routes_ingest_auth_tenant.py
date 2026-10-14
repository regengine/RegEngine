"""Auth and tenant-scoping tests for the direct-ingest route.

``POST /v1/ingest`` (``app/routes_ingest.ingest_direct``) must fail closed
when the caller's API key carries no tenant: events without a tenant would
bypass every downstream tenant predicate. The guard runs before any job
record, database handle, or Kafka publish is touched.

The rate-limit wrapper keys its bucket per tenant, so a tenant-less caller
is also isolated into the ``anonymous`` bucket rather than sharing quota
with a real tenant. Both properties are exercised through HTTP with a
stubbed key; no database, Redis, or network is touched.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import shared.auth as shared_auth
from app import routes_ingest

TENANT = str(uuid.uuid4())


def _api_key(tenant_id: str | None):
    return shared_auth.APIKey(
        key_id="test-key",
        key_hash="hash",
        name="test",
        tenant_id=tenant_id,
        created_at=datetime.now(timezone.utc),
    )


def _build_client(key, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        routes_ingest, "consume_tenant_rate_limit", lambda **_kw: (True, 99)
    )
    app = FastAPI()
    app.include_router(routes_ingest.router)
    app.dependency_overrides[shared_auth.require_api_key] = lambda: key
    return TestClient(app, raise_server_exceptions=False)


def _payload():
    return {"text": "lot 7 shipped", "source_system": "probe"}


def test_ingest_direct_without_tenant_returns_403(monkeypatch):
    """A tenant-less key fails closed before any ingestion work starts."""
    db_manager_calls = []
    monkeypatch.setattr(
        routes_ingest, "get_db_manager", lambda: db_manager_calls.append(1) or None
    )
    client = _build_client(_api_key(None), monkeypatch)
    resp = client.post("/v1/ingest", json=_payload())
    assert resp.status_code == 403
    assert "tenant" in resp.json()["detail"].lower()
    assert db_manager_calls == [], "no database handle may be opened first"


def test_ingest_direct_with_tenant_passes_the_guard(monkeypatch):
    """A tenant-bound key clears the guard and the handler forwards that tenant."""
    from app.models import NormalizedEvent

    monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)
    seen = {}
    event = NormalizedEvent(
        event_id="evt-1",
        document_id="doc-1",
        document_hash="h",
        tenant_id=TENANT,
        source_system="probe",
        source_url="https://example.com/direct",
        raw_s3_path="s3://raw",
        normalized_s3_path="s3://norm",
        timestamp=datetime.now(timezone.utc),
        content_sha256="c",
    )

    def _capture(**kw):
        seen.update(kw)
        return event

    monkeypatch.setattr(routes_ingest, "_process_and_emit", _capture)
    client = _build_client(_api_key(TENANT), monkeypatch)
    resp = client.post("/v1/ingest", json=_payload())
    assert resp.status_code == 200, resp.text
    assert seen.get("tenant_id") == TENANT
    assert resp.json()["tenant_id"] == TENANT


def test_rate_limit_bucket_is_per_tenant(monkeypatch):
    """Tenant-less callers land in the ``anonymous`` bucket, never in a
    real tenant's quota."""
    seen = []

    def _consume(*, tenant_id: str, **_kw):
        seen.append(tenant_id)
        return (True, 99)

    client = _build_client(_api_key(None), monkeypatch)
    # _build_client installs a permissive stub; reinstall the spy after it
    # so the bucket choice is observed.
    monkeypatch.setattr(routes_ingest, "consume_tenant_rate_limit", _consume)
    monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)
    monkeypatch.setattr(
        routes_ingest, "_process_and_emit", MagicMock(side_effect=AssertionError("no"))
    )
    resp = client.post("/v1/ingest", json=_payload())
    assert resp.status_code == 403  # guard still fails closed
    assert seen == ["anonymous"]


def test_ingest_direct_default_source_url_uses_handler_default(monkeypatch):
    """Omitting source_url exercises the handler default through HTTP.

    The request carries no source_url, so the handler default
    (``payload.source_url or "manual://direct"``) must reach
    ``_process_and_emit`` as ``url_str``. The stub then builds the
    response through the real ``NormalizedEvent`` model, so the test
    fails if the default ever stops matching the model. The model accepts
    the ``manual://`` marker as a never-fetched provenance ref (#3274,
    #3287), so the request succeeds; it used to fail HttpUrl validation
    and the handler catch-all converted that into a 500.
    """
    from app.models import NormalizedEvent

    seen = {}

    def _through_model(**kw):
        seen["url_str"] = kw["url_str"]
        return NormalizedEvent(
            event_id="evt-1",
            document_id="doc-1",
            document_hash="h",
            tenant_id=kw["tenant_id"],
            source_system="probe",
            source_url=kw["url_str"],
            raw_s3_path="s3://raw",
            normalized_s3_path="s3://norm",
            timestamp=datetime.now(timezone.utc),
            content_sha256="c",
        )

    monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)
    monkeypatch.setattr(routes_ingest, "_process_and_emit", _through_model)
    client = _build_client(_api_key(TENANT), monkeypatch)
    payload = {"text": "lot 7 shipped", "source_system": "probe"}
    resp = client.post("/v1/ingest", json=payload)
    assert seen.get("url_str") == "manual://direct"
    assert resp.status_code == 200
    assert resp.json()["source_url"] == "manual://direct"
