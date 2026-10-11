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

import pytest
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
    """A tenant-bound key clears the guard and the event keeps its tenant."""
    from app.models import NormalizedEvent

    monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)
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
    monkeypatch.setattr(routes_ingest, "_process_and_emit", lambda **_kw: event)
    client = _build_client(_api_key(TENANT), monkeypatch)
    resp = client.post("/v1/ingest", json=_payload())
    assert resp.status_code == 200, resp.text
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


@pytest.mark.xfail(
    strict=True,
    reason="BUG routes_ingest default source_url: ingest_direct falls back to "
    "'manual://direct' but NormalizedEvent.source_url is HttpUrl (http/https "
    "only), so _process_and_emit cannot build the response for a default "
    "direct ingest",
)
def test_ingest_direct_default_source_url_validates():
    """Mirrors the NormalizedEvent construction in _process_and_emit using
    the handler's own default ``url_str`` (``payload.source_url or
    "manual://direct"``). Today this raises ValidationError, which the
    handler's catch-all converts into a 500."""
    from app.models import NormalizedEvent

    NormalizedEvent(
        event_id="evt-1",
        document_id="doc-1",
        document_hash="h",
        tenant_id=TENANT,
        source_system="probe",
        source_url="manual://direct",
        raw_s3_path="s3://raw",
        normalized_s3_path="s3://norm",
        timestamp=datetime.now(timezone.utc),
        content_sha256="c",
    )
