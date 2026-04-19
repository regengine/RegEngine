"""Regression tests for #1297: canonical_persistence.get_event defaults to
OMITTING ``raw_payload``.

Before this fix, ``get_event`` always returned ``raw_payload`` — the
original supplier record. For firms with PII in their source records
(grower names, addresses, phone numbers), that flows out through any
read path that doesn't explicitly scope tenant. Combined with the
RLS-not-auto-set issue (#1265), it's a cross-tenant disclosure path.

The fix makes ``raw_payload`` opt-in via ``include_raw_payload=True``.
Existing legitimate consumers (auditor view, canonical records view)
opt in explicitly; future consumers get a safer default.

These tests lock in:
1. Default call omits ``raw_payload`` from the returned dict.
2. Explicit ``include_raw_payload=True`` returns it.
3. ``include_raw_payload`` is keyword-only (prevents positional-arg
   drift from reintroducing accidental exposure).
4. The two routed consumers both opt in (source-level check).
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make shared importable
service_dir = Path(__file__).resolve().parents[2] / "services"
sys.path.insert(0, str(service_dir))

from shared.canonical_persistence.writer import CanonicalEventStore  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_row_with_payload():
    """A fake DB row matching the 29-column SELECT in get_event.

    Positions:
    0: event_id, 1: tenant_id, 2: source_system, 3: source_record_id,
    4: event_type, 5: event_timestamp, 6: event_timezone,
    7: product_reference, 8: lot_reference, 9: traceability_lot_code,
    10: quantity, 11: unit_of_measure,
    12: from_entity_reference, 13: to_entity_reference,
    14: from_facility_reference, 15: to_facility_reference,
    16: transport_reference, 17: kdes, 18: raw_payload, 19: normalized_payload,
    20: provenance_metadata, 21: confidence_score, 22: status,
    23: supersedes_event_id, 24: schema_version,
    25: sha256_hash, 26: chain_hash, 27: created_at, 28: amended_at
    """
    from datetime import datetime, timezone
    return [
        "event-abc",                                          # 0
        "tenant-xyz",                                         # 1
        "manual",                                             # 2
        "rec-1",                                              # 3
        "shipping",                                           # 4
        datetime.now(timezone.utc),                           # 5
        "UTC",                                                # 6
        "prod-1", "lot-1", "TLC-1",                           # 7,8,9
        10.0, "LB",                                           # 10,11
        "ent-a", "ent-b", "fac-a", "fac-b",                   # 12,13,14,15
        None,                                                 # 16
        {"required_kde_1": "value"},                          # 17 kdes
        {"sensitive_grower_name": "Jane Grower",              # 18 raw_payload (PII!)
         "phone": "555-867-5309",
         "address": "123 Farm Rd"},
        {"normalized": "value"},                              # 19 normalized
        {"provenance": "v1"},                                 # 20 provenance
        0.99,                                                 # 21 confidence
        "active",                                             # 22 status
        None,                                                 # 23
        1,                                                    # 24 schema_version
        "sha1", "chain1",                                     # 25,26
        datetime.now(timezone.utc),                           # 27 created_at
        None,                                                 # 28 amended_at
    ]


def _store_with_fake_row(row):
    """Construct a CanonicalEventStore with a mocked session that
    returns a single fake row for the SELECT."""
    session = MagicMock()
    # The call chain is session.execute(...).fetchone() -> row
    session.execute.return_value.fetchone.return_value = row
    return CanonicalEventStore(session, dual_write=False)


# ── 1. Default call omits raw_payload ──────────────────────────────────────


def test_default_get_event_omits_raw_payload():
    """#1297: new consumers that don't know to opt-in must NOT get
    raw_payload back."""
    store = _store_with_fake_row(_make_row_with_payload())
    event = store.get_event("tenant-xyz", "event-abc")
    assert event is not None
    assert "raw_payload" not in event, (
        "#1297: get_event must NOT return raw_payload by default — "
        "this is a PII/GDPR vector."
    )


def test_include_raw_payload_false_omits_raw_payload():
    """Explicit False also omits — no surprise behaviour."""
    store = _store_with_fake_row(_make_row_with_payload())
    event = store.get_event("tenant-xyz", "event-abc", include_raw_payload=False)
    assert event is not None
    assert "raw_payload" not in event


# ── 2. Opt-in returns the payload ──────────────────────────────────────────


def test_include_raw_payload_true_returns_payload():
    """Legitimate consumers (auditor, record-detail) opt in and get
    the original supplier record."""
    store = _store_with_fake_row(_make_row_with_payload())
    event = store.get_event(
        "tenant-xyz", "event-abc", include_raw_payload=True
    )
    assert event is not None
    assert "raw_payload" in event
    assert event["raw_payload"]["sensitive_grower_name"] == "Jane Grower"


# ── 3. Signature invariants ────────────────────────────────────────────────


def test_include_raw_payload_is_keyword_only():
    """Keyword-only prevents positional-arg drift from accidentally
    re-enabling raw_payload in a new callsite."""
    sig = inspect.signature(CanonicalEventStore.get_event)
    param = sig.parameters.get("include_raw_payload")
    assert param is not None, (
        "#1297: get_event must accept include_raw_payload parameter"
    )
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        "#1297: include_raw_payload must be keyword-only"
    )
    # And its default must be False (the safer default)
    assert param.default is False


def test_no_row_returns_none_regardless_of_flag():
    """Edge: when no row matches, both flag values return None."""
    session = MagicMock()
    session.execute.return_value.fetchone.return_value = None
    store = CanonicalEventStore(session, dual_write=False)

    assert store.get_event("t", "e") is None
    assert store.get_event("t", "e", include_raw_payload=True) is None


def test_non_raw_payload_fields_unaffected():
    """Removing raw_payload must NOT accidentally drop other fields
    like kdes, normalized_payload, or provenance_metadata."""
    store = _store_with_fake_row(_make_row_with_payload())
    event = store.get_event("tenant-xyz", "event-abc")
    assert event is not None
    # These must still be present
    for key in ["kdes", "normalized_payload", "provenance_metadata",
                "event_id", "tenant_id", "sha256_hash", "chain_hash"]:
        assert key in event, f"#1297: regression dropped {key}"


# ── 4. Source-level assertion: routed consumers opt in ─────────────────────


def _router_source(path_parts):
    """Read a router source file relative to the repo root."""
    p = Path(__file__).resolve().parents[2] / "services" / "ingestion" / "app"
    for part in path_parts:
        p = p / part
    return p.read_text()


def test_canonical_router_opts_in():
    """canonical_router.py advertises "complete canonical event
    including raw payload" in its OpenAPI docstring — it MUST opt in
    so the endpoint keeps working."""
    src = _router_source(["canonical_router.py"])
    assert "include_raw_payload=True" in src, (
        "#1297: canonical_router.get_record must pass "
        "include_raw_payload=True to store.get_event() — its OpenAPI "
        "docstring advertises the raw payload as part of the response."
    )


def test_auditor_router_opts_in():
    """auditor_router needs raw_payload for chain-of-custody
    verification — it MUST opt in."""
    src = _router_source(["auditor_router.py"])
    assert "include_raw_payload=True" in src, (
        "#1297: auditor_router must pass include_raw_payload=True "
        "to store.get_event() — chain-of-custody view requires the "
        "original supplier record."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
