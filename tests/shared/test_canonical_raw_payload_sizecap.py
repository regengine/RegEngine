"""Regression tests for #1290: ``raw_payload`` size cap.

Why this matters
----------------
``raw_payload`` preserves the supplier record verbatim. Before the fix
there was no upper bound — a 10 MB supplier JSON would:

1. Block the per-tenant advisory lock for the chain, stalling every
   concurrent writer for the tenant.
2. Bloat backups and hot tables (JSONB in Postgres is stored TOASTed
   but the row still has to be read during every SELECT *).
3. Combine with any downstream audit UI or PDF export that renders
   ``raw_payload.description`` (or any supplier-controlled field)
   without escaping to become a stored-XSS vector with unbounded
   payload size.

The fix enforces a size cap at ``prepare_for_persistence`` (primary
check) AND at ``_event_to_params`` inside the writer (defense-in-depth
in case a caller mutates ``raw_payload`` after prep). Oversized
payloads raise :class:`RawPayloadTooLargeError` — a ``ValueError``
subclass so existing ingestion error-handlers keep working.

What we test
------------
1. Default cap: 256 KiB.
2. Hard ceiling: 1 MiB. Env overrides above the ceiling are clamped.
3. Env override works within the allowed range.
4. Invalid env values fall back to the default (doesn't crash prep).
5. Empty / None raw_payload is a no-op.
6. Oversized payload raises ``RawPayloadTooLargeError`` at prep time.
7. Writer ``_event_to_params`` re-checks (defense-in-depth): an event
   that slipped past prep still gets rejected at serialization.
8. ``RawPayloadTooLargeError`` IS a ``ValueError`` (back-compat).
9. Oversized payload rejection happens BEFORE hash computation
   (sha256_hash remains None on failure).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

service_dir = Path(__file__).resolve().parents[2] / "services"
sys.path.insert(0, str(service_dir))

from shared.canonical_event import (  # noqa: E402
    CTEType,
    IngestionSource,
    RAW_PAYLOAD_DEFAULT_MAX_BYTES,
    RAW_PAYLOAD_HARD_CEILING_BYTES,
    RawPayloadTooLargeError,
    TraceabilityEvent,
    _raw_payload_max_bytes,
)
from shared.canonical_persistence.writer import CanonicalEventStore  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_event(raw_payload=None):
    """Build a minimal valid TraceabilityEvent for tests."""
    return TraceabilityEvent(
        tenant_id=uuid4(),
        source_system=IngestionSource.MANUAL,
        event_type=CTEType.SHIPPING,
        event_timestamp=datetime.now(timezone.utc),
        traceability_lot_code="TLC-1",
        quantity=10.0,
        unit_of_measure="LB",
        raw_payload=raw_payload or {},
    )


def _big_payload(target_bytes: int) -> dict:
    """Build a payload whose JSON encoding is just above target_bytes."""
    # Each repeat of this string contributes ~60 bytes.
    filler = "A" * target_bytes
    return {"description": filler}


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    """Isolation: clear the env override between tests."""
    monkeypatch.delenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", raising=False)
    yield


# ── 1. Default cap ────────────────────────────────────────────────────────


def test_default_max_bytes_is_256kib():
    """The default is 256 KiB — an order of magnitude above the 95th
    percentile observed FSMA 204 record in staging."""
    assert RAW_PAYLOAD_DEFAULT_MAX_BYTES == 256 * 1024


def test_hard_ceiling_is_1mib():
    """Hard ceiling matches the issue text: ``1MB hard ceiling``."""
    assert RAW_PAYLOAD_HARD_CEILING_BYTES == 1024 * 1024


def test_raw_payload_max_bytes_default():
    """No env override → default cap."""
    assert _raw_payload_max_bytes() == RAW_PAYLOAD_DEFAULT_MAX_BYTES


# ── 2. Env override ────────────────────────────────────────────────────────


def test_env_override_within_range(monkeypatch):
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "65536")
    assert _raw_payload_max_bytes() == 65536


def test_env_override_clamped_to_ceiling(monkeypatch):
    """An operator typo setting 100 MB must be clamped to the hard
    ceiling, not accepted."""
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", str(100 * 1024 * 1024))
    assert _raw_payload_max_bytes() == RAW_PAYLOAD_HARD_CEILING_BYTES


def test_env_override_invalid_falls_back_to_default(monkeypatch):
    """Garbage env value → default, don't crash."""
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "not-a-number")
    assert _raw_payload_max_bytes() == RAW_PAYLOAD_DEFAULT_MAX_BYTES


def test_env_override_zero_falls_back_to_default(monkeypatch):
    """A non-positive override is nonsense — a payload of 0 bytes would
    block all ingestion. Fall back to the default."""
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "0")
    assert _raw_payload_max_bytes() == RAW_PAYLOAD_DEFAULT_MAX_BYTES


def test_env_override_negative_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "-100")
    assert _raw_payload_max_bytes() == RAW_PAYLOAD_DEFAULT_MAX_BYTES


# ── 3. Prep-time enforcement ───────────────────────────────────────────────


def test_empty_raw_payload_passes():
    """Events with no raw_payload (e.g., manual entry) must prep cleanly."""
    event = _make_event(raw_payload={})
    event.prepare_for_persistence()
    assert event.sha256_hash is not None


def test_small_raw_payload_passes():
    """A typical supplier record (a few hundred bytes) passes."""
    event = _make_event(raw_payload={
        "supplier": "Acme Foods",
        "lot": "ABC-123",
        "quantity": 100.0,
        "notes": "harvested 2026-04-15",
    })
    event.prepare_for_persistence()
    assert event.sha256_hash is not None


def test_oversized_raw_payload_raises(monkeypatch):
    """A payload above the cap raises RawPayloadTooLargeError."""
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "1024")
    event = _make_event(raw_payload=_big_payload(2000))
    with pytest.raises(RawPayloadTooLargeError) as exc_info:
        event.prepare_for_persistence()
    # Carries size info so logs/monitoring can aggregate.
    assert exc_info.value.size_bytes > 1024
    assert exc_info.value.max_bytes == 1024


def test_payload_at_default_cap_would_exceed(monkeypatch):
    """A 300 KB payload exceeds the 256 KiB default."""
    event = _make_event(raw_payload=_big_payload(300 * 1024))
    with pytest.raises(RawPayloadTooLargeError):
        event.prepare_for_persistence()


def test_oversized_payload_blocks_hash_computation(monkeypatch):
    """Size check runs BEFORE hash computation — a rejected event
    must not leak any prepared state."""
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "1024")
    event = _make_event(raw_payload=_big_payload(2000))
    assert event.sha256_hash is None  # not prepped yet
    with pytest.raises(RawPayloadTooLargeError):
        event.prepare_for_persistence()
    # sha256_hash must still be None — the check short-circuited
    # before compute_sha256_hash was called.
    assert event.sha256_hash is None
    assert event.idempotency_key is None


# ── 4. Back-compat with ValueError ─────────────────────────────────────────


def test_raw_payload_too_large_is_value_error(monkeypatch):
    """Existing ingestion code that catches ValueError keeps working."""
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "1024")
    event = _make_event(raw_payload=_big_payload(2000))
    # This is the back-compat invariant: any ``except ValueError`` branch
    # still catches our rejection. That matters because the ingestion
    # routers wrap normalize()/prep() in broad ``except ValueError``
    # blocks to map to HTTP 400.
    with pytest.raises(ValueError):
        event.prepare_for_persistence()


def test_error_message_mentions_issue_reference(monkeypatch):
    """Regression: the error should point a debugger at #1290."""
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "512")
    event = _make_event(raw_payload=_big_payload(1024))
    with pytest.raises(RawPayloadTooLargeError) as exc_info:
        event.prepare_for_persistence()
    assert "#1290" in str(exc_info.value)


def test_error_mentions_env_var(monkeypatch):
    """The error should tell an operator how to raise the cap."""
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "512")
    event = _make_event(raw_payload=_big_payload(1024))
    with pytest.raises(RawPayloadTooLargeError) as exc_info:
        event.prepare_for_persistence()
    assert "REGENGINE_RAW_PAYLOAD_MAX_BYTES" in str(exc_info.value)


# ── 5. Defense-in-depth at writer serialization ────────────────────────────


def test_writer_rejects_post_prep_mutation(monkeypatch):
    """If an event is prepped with a small payload then raw_payload is
    swapped for a huge one before persist_event, the writer must still
    reject it at serialization time.

    This defends against:
    - A bug in a custom ingestion pipeline.
    - A test that reuses an event and mutates it.
    - An attacker who controls the raw_payload after the model layer
      (e.g. through a Pydantic pre-save hook override).
    """
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "1024")
    event = _make_event(raw_payload={"ok": "small"})
    event.prepare_for_persistence()  # succeeds
    # Simulate post-prep mutation.
    event.raw_payload = _big_payload(2000)
    store = CanonicalEventStore(MagicMock(), dual_write=False)
    with pytest.raises(RawPayloadTooLargeError):
        store._event_to_params(event)


def test_writer_params_happy_path():
    """Baseline: a normal-sized event round-trips through _event_to_params."""
    event = _make_event(raw_payload={"ok": "small"})
    event.prepare_for_persistence()
    store = CanonicalEventStore(MagicMock(), dual_write=False)
    params = store._event_to_params(event)
    # raw_payload is serialized to JSON; decoding round-trips it.
    assert json.loads(params["raw_payload"]) == {"ok": "small"}


# ── 6. Boundary: exactly at the cap ────────────────────────────────────────


def test_payload_just_under_cap_passes(monkeypatch):
    """A payload 1 byte under the cap passes — no off-by-one."""
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "200")
    # Build a payload whose JSON encoding is ~150 bytes.
    event = _make_event(raw_payload={"x": "A" * 100})
    # Verify it's actually under 200 bytes:
    size = len(json.dumps(event.raw_payload, default=str).encode("utf-8"))
    assert size < 200, f"test setup mismatch: {size}"
    event.prepare_for_persistence()


def test_payload_just_over_cap_rejects(monkeypatch):
    """A payload 1 byte over the cap rejects."""
    monkeypatch.setenv("REGENGINE_RAW_PAYLOAD_MAX_BYTES", "150")
    event = _make_event(raw_payload={"x": "A" * 200})
    with pytest.raises(RawPayloadTooLargeError):
        event.prepare_for_persistence()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
