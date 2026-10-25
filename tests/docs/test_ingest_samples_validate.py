"""The ingest docs must match the real ingest checks.

The docs no longer ship example payload files: #3544 removed every
``frontend/src/lib/api-samples/ingest-*.json`` sample because a printed lot code,
supplier or quantity reads as real data. The docs now render a skeleton from
``frontend/src/lib/api-samples/ingest-samples.ts`` whose values are ``<...>``
descriptions, plus ``required-kdes.json``, the per-event-type table the API
reference prints.

This test keeps the docs honest against ``POST /api/v1/webhooks/ingest``:

* ``required-kdes.json`` is diffed against ``REQUIRED_KDES_BY_CTE``;
* the skeleton's field names are diffed against ``IngestEvent`` and the
  receiving KDEs the backend requires;
* the skeleton keeps ``{{EVENT_TIMESTAMP}}`` / ``{{EVENT_DATE}}`` placeholders,
  never a fixed date;
* the event-timestamp window the docs describe (90 days back, 24 hours ahead)
  and the ``X-Webhook-Signature`` check (HMAC-SHA256 of the exact body bytes)
  behave as documented. Events for these checks are built at runtime from the
  backend's own required-KDE table; no sample record is stored.

Run with an interpreter that has ``requirements.lock`` installed: importing
``webhook_router_v2`` needs ``typesafe-sdk``.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from services.ingestion.app.webhook_models import (
    REQUIRED_KDES_BY_CTE,
    IngestEvent,
    WebhookCTEType,
    WebhookPayload,
)
from services.ingestion.app.webhook_router_v2 import (
    _validate_event_kdes,
    _validate_event_timestamp_window,
    _verify_webhook_signature,
)

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "api-samples"
REQUIRED_KDES_PATH = SAMPLE_DIR / "required-kdes.json"
SKELETON_PATH = SAMPLE_DIR / "ingest-samples.ts"

# Event fields that every CTE needs and that sit on the event itself, not in kdes.
_UNIVERSAL_FIELDS = {"traceability_lot_code", "product_description", "quantity", "unit_of_measure"}

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Test-only value for the HMAC check below. It is not a credential.
_TEST_SIGNING_SECRET = "docs-sample-signing-secret"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _default_replay_window(monkeypatch):
    # The docs say 90 days back / 24 hours ahead. Pin the defaults so a stray
    # WEBHOOK_MAX_EVENT_* in the developer's shell cannot change the verdict.
    monkeypatch.delenv("WEBHOOK_MAX_EVENT_AGE_DAYS", raising=False)
    monkeypatch.delenv("WEBHOOK_MAX_EVENT_FUTURE_HOURS", raising=False)


def _skeleton_block() -> str:
    text = SKELETON_PATH.read_text(encoding="utf-8")
    start = text.index("const INGEST_BODY_SKELETON")
    return text[start : text.index("\n};", start)]


def _skeleton_keys(block: str) -> set[str]:
    return set(re.findall(r"^\s*([a-z_]+):", block, flags=re.MULTILINE))


def _runtime_payload(when: datetime) -> dict:
    """A receiving event built from the backend's required-KDE table, values generated at runtime."""
    token = uuid.uuid4().hex
    kdes: dict[str, object] = {}
    event: dict[str, object] = {
        "cte_type": WebhookCTEType.RECEIVING.value,
        "traceability_lot_code": f"TEST-{token}",
        "product_description": f"product-{token}",
        "quantity": 1,
        "unit_of_measure": "cases",
        "location_name": f"location-{token}",
        "timestamp": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kdes": kdes,
    }
    for kde in REQUIRED_KDES_BY_CTE[WebhookCTEType.RECEIVING]:
        if kde in event:
            continue
        kdes[kde] = when.strftime("%Y-%m-%d") if kde.endswith("_date") else f"{kde}-{token}"
    return {"source": f"source-{token}", "events": [event]}


def test_no_example_payload_files_are_shipped():
    # #3544 removed the ingest-*.json samples on purpose; they must not come back.
    assert sorted(p.name for p in SAMPLE_DIR.glob("ingest-*.json")) == []


def test_skeleton_keeps_placeholders_and_no_fixed_date():
    block = _skeleton_block()
    assert "{{EVENT_TIMESTAMP}}" in block and "{{EVENT_DATE}}" in block
    assert not _ISO_DATE.search(block), "the docs skeleton must keep placeholders, never a fixed date"


def test_skeleton_fields_match_the_backend_receiving_event():
    keys = _skeleton_keys(_skeleton_block())
    required = set(REQUIRED_KDES_BY_CTE[WebhookCTEType.RECEIVING])
    event_fields = set(IngestEvent.model_fields)

    documented_kdes = keys - event_fields - {"source", "events"}
    assert documented_kdes == required - event_fields, "skeleton kdes differ from the receiving KDEs the backend requires"
    assert (keys & event_fields) >= _UNIVERSAL_FIELDS


def test_runtime_event_passes_model_kde_and_timestamp_checks():
    payload = WebhookPayload.model_validate(_runtime_payload(datetime.now(timezone.utc) - timedelta(hours=1)))
    for event in payload.events:
        assert _validate_event_timestamp_window(event.timestamp) is None
        assert _validate_event_kdes(event) == []


def test_stale_timestamp_is_rejected_by_the_replay_window():
    payload = WebhookPayload.model_validate(_runtime_payload(datetime.now(timezone.utc) - timedelta(days=91)))
    error = _validate_event_timestamp_window(payload.events[0].timestamp)
    assert error and "WEBHOOK_MAX_EVENT_AGE_DAYS=90" in error


def test_future_timestamp_fails_the_whole_request_not_one_event():
    with pytest.raises(ValidationError) as excinfo:
        WebhookPayload.model_validate(_runtime_payload(datetime.now(timezone.utc) + timedelta(hours=25)))
    assert ("events", 0, "timestamp") in [error["loc"] for error in excinfo.value.errors()]
    assert "more than 24 hours in the future" in str(excinfo.value)


def test_timestamp_just_inside_the_future_window_is_accepted():
    payload = WebhookPayload.model_validate(_runtime_payload(datetime.now(timezone.utc) + timedelta(hours=23)))
    assert _validate_event_timestamp_window(payload.events[0].timestamp) is None


def test_required_kdes_table_matches_the_backend():
    documented = json.loads(REQUIRED_KDES_PATH.read_text(encoding="utf-8"))

    # The docs list the 7 FDA-defined CTEs. GROWING is accepted for backwards
    # compatibility only and has no required-KDE row.
    assert set(WebhookCTEType) - set(REQUIRED_KDES_BY_CTE) == {WebhookCTEType.GROWING}
    assert set(documented) == {cte.value for cte in REQUIRED_KDES_BY_CTE}, (
        "a CTE type is missing from, or extra in, the docs table"
    )
    event_fields = set(IngestEvent.model_fields)
    for cte in REQUIRED_KDES_BY_CTE:
        row = documented[cte.value]
        top_level, in_kdes = set(row["top_level"]), set(row["kdes"])

        assert not top_level & in_kdes, f"{cte.value}: a KDE is listed twice"
        assert top_level <= event_fields, f"{cte.value}: top_level names a field IngestEvent does not have"
        assert not in_kdes & event_fields, f"{cte.value}: a top-level event field is listed under kdes"
        assert top_level | in_kdes | _UNIVERSAL_FIELDS == set(REQUIRED_KDES_BY_CTE[cte]), (
            f"{cte.value}: the docs table differs from REQUIRED_KDES_BY_CTE"
        )


def _request_with_body(body: bytes) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/api/v1/webhooks/ingest", "headers": []}, receive)


def _signature_check(monkeypatch, secret: str, body: bytes, signature: str | None) -> None:
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", secret)
    asyncio.run(_verify_webhook_signature(_request_with_body(body), signature))


def _signed_body() -> tuple[bytes, str]:
    body = json.dumps(_runtime_payload(datetime.now(timezone.utc) - timedelta(hours=1))).encode()
    return body, "sha256=" + hmac.new(_TEST_SIGNING_SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_signature_is_hmac_sha256_of_the_exact_body_bytes(monkeypatch):
    body, signature = _signed_body()
    _signature_check(monkeypatch, _TEST_SIGNING_SECRET, body, signature)  # no exception == accepted


def test_signature_over_different_bytes_or_missing_is_rejected(monkeypatch):
    body, signature = _signed_body()

    with pytest.raises(HTTPException) as tampered:
        _signature_check(monkeypatch, _TEST_SIGNING_SECRET, body + b" ", signature)  # one extra byte
    assert tampered.value.status_code == 401

    with pytest.raises(HTTPException) as missing:
        _signature_check(monkeypatch, _TEST_SIGNING_SECRET, body, None)
    assert missing.value.status_code == 401
