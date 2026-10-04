"""The ingest sample shown in the developer docs must pass the real ingest checks.

``frontend/src/lib/api-samples/ingest-receiving.json`` is the one payload behind
the quickstart, docs index, developers page and API reference. Its timestamps
are placeholders so a page can render them as shell/Python/JS time expressions.
This test fills them with "now minus 1 hour" and runs the sample through the
same checks ``POST /api/v1/webhooks/ingest`` runs:

* the Pydantic model in ``services/ingestion/app/webhook_models.py``;
* the required-KDE check in ``webhook_router_v2/validation.py``;
* the event-timestamp window in ``webhook_router_v2/security.py`` (90 days back,
  24 hours ahead; a stale event comes back ``rejected`` inside a 200);
* the ``X-Webhook-Signature`` check (HMAC-SHA256 of the exact body bytes).

A fixed date in the sample would silently start failing 90 days later, which is
how the old docs samples broke. The negative tests prove the checks that guard
against that actually fire.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from services.ingestion.app.webhook_models import (
    REQUIRED_KDES_BY_CTE,
    WebhookCTEType,
    WebhookPayload,
)
from services.ingestion.app.webhook_router_v2 import (
    _validate_event_kdes,
    _validate_event_timestamp_window,
    _verify_webhook_signature,
)

SAMPLE_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "api-samples" / "ingest-receiving.json"

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Test-only value for the HMAC check below. It is not a credential.
_TEST_SIGNING_SECRET = "docs-sample-signing-secret"  # pragma: allowlist secret


def _render(when: datetime) -> dict:
    """Fill the sample's placeholders the way the docs pages do."""
    text = SAMPLE_PATH.read_text(encoding="utf-8")
    text = text.replace("{{EVENT_TIMESTAMP}}", when.strftime("%Y-%m-%dT%H:%M:%SZ"))
    text = text.replace("{{EVENT_DATE}}", when.strftime("%Y-%m-%d"))
    assert "{{" not in text, "sample has a placeholder this test does not fill"
    return json.loads(text)


def _one_hour_ago() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=1)


@pytest.fixture(autouse=True)
def _default_replay_window(monkeypatch):
    # The docs say 90 days back / 24 hours ahead. Pin the defaults so a stray
    # WEBHOOK_MAX_EVENT_* in the developer's shell cannot change the verdict.
    monkeypatch.delenv("WEBHOOK_MAX_EVENT_AGE_DAYS", raising=False)
    monkeypatch.delenv("WEBHOOK_MAX_EVENT_FUTURE_HOURS", raising=False)


def test_sample_file_has_no_fixed_date_and_uses_test_lot_prefix():
    raw = SAMPLE_PATH.read_text(encoding="utf-8")
    assert not _ISO_DATE.search(raw), "the shared sample must keep placeholders, never a fixed date"
    payload = _render(_one_hour_ago())
    for event in payload["events"]:
        assert event["traceability_lot_code"].startswith("TEST-"), "writes are permanent: samples use a TEST- lot"


def test_sample_passes_model_kde_and_timestamp_checks():
    payload = WebhookPayload.model_validate(_render(_one_hour_ago()))

    assert payload.events, "sample must contain at least one event"
    for event in payload.events:
        assert event.cte_type is WebhookCTEType.RECEIVING
        assert _validate_event_timestamp_window(event.timestamp) is None
        assert _validate_event_kdes(event) == []


def test_stale_timestamp_is_rejected_by_the_replay_window():
    stale = datetime.now(timezone.utc) - timedelta(days=91)
    payload = WebhookPayload.model_validate(_render(stale))

    # The Pydantic model accepts old dates (backfill); the route rejects the event.
    errors = [_validate_event_timestamp_window(e.timestamp) for e in payload.events]
    assert all(errors), "a sample dated more than 90 days ago must fail the replay window"
    assert "WEBHOOK_MAX_EVENT_AGE_DAYS=90" in errors[0]


@pytest.mark.parametrize(
    "kde",
    ["receive_date", "receiving_location", "immediate_previous_source", "reference_document", "tlc_source_reference"],
)
def test_missing_receiving_kde_is_rejected(kde):
    assert kde in REQUIRED_KDES_BY_CTE[WebhookCTEType.RECEIVING], "docs list a KDE the backend no longer requires"
    broken = copy.deepcopy(_render(_one_hour_ago()))
    del broken["events"][0]["kdes"][kde]

    event = WebhookPayload.model_validate(broken).events[0]
    assert _validate_event_kdes(event) == [f"Missing required KDE '{kde}' for receiving CTE"]


def _request_with_body(body: bytes) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/api/v1/webhooks/ingest", "headers": []}, receive)


def _signature_check(monkeypatch, secret: str, body: bytes, signature: str | None) -> None:
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", secret)
    asyncio.run(_verify_webhook_signature(_request_with_body(body), signature))


def test_signature_is_hmac_sha256_of_the_exact_body_bytes(monkeypatch):
    secret = _TEST_SIGNING_SECRET
    body = json.dumps(_render(_one_hour_ago())).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    _signature_check(monkeypatch, secret, body, signature)  # no exception == accepted


def test_signature_over_different_bytes_or_missing_is_rejected(monkeypatch):
    secret = _TEST_SIGNING_SECRET
    body = json.dumps(_render(_one_hour_ago())).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    with pytest.raises(HTTPException) as tampered:
        _signature_check(monkeypatch, secret, body + b" ", signature)  # one extra byte
    assert tampered.value.status_code == 401

    with pytest.raises(HTTPException) as missing:
        _signature_check(monkeypatch, secret, body, None)
    assert missing.value.status_code == 401
