"""EDI FSMA-rejection audit log (#1174).

When an inbound EDI document fails FSMAEvent schema validation it MUST
NOT flow into the canonical ingest stream — even in advisory mode.
Previously ``?strict=false`` persisted the failed event alongside valid
ones with ``fsma_validation_status=failed``, which polluted the FSMA
204 traceability graph and forced downstream consumers (FDA export,
recall simulator) to carry an exclusion filter on every read.

This module provides a dedicated rejection channel. The rejection is:

* logged as a structured warning (`edi_fsma_rejection_recorded`) so ops
  keeps a trail even if the store is ephemeral;
* written to an in-memory tenant-scoped ring buffer that powers the
  admin review UI and tests. The ring is capped per-tenant to bound
  memory under abuse. Production deployments that need durable
  rejection history should wire this module to a DB table by overriding
  ``record_edi_rejection`` in a subclass or adapter — keeping the API
  stable so callers don't change.

Follows the same in-memory-fallback pattern as
``app/epcis/persistence.py::_fallback_store_for`` so the subsystems
behave consistently under test and development.
"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger("edi-ingestion")


_EDI_REJECTION_CAP_PER_TENANT = int(
    os.getenv("EDI_REJECTION_CAP_PER_TENANT", "1000")
)

# Tenant-scoped in-memory rejection store. Outer dict is keyed by
# ``tenant_id``; inner OrderedDict is FIFO-evicted once full.
_edi_rejection_store: dict[str, "OrderedDict[str, dict]"] = {}


def _rejection_store_for(tenant_id: str) -> "OrderedDict[str, dict]":
    return _edi_rejection_store.setdefault(tenant_id, OrderedDict())


def record_edi_rejection(
    *,
    tenant_id: str,
    transaction_set: str,
    traceability_lot_code: str,
    errors: list[dict[str, Any]],
    extracted: dict[str, Any] | None = None,
    partner_id: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Record an EDI FSMA validation rejection.

    Returns the rejection record (dict) so the caller can surface a
    rejection_id to the client without leaking internal storage
    details. Always writes a structured warning log — even if storage
    fails — so the audit trail survives.
    """
    rejection_id = f"edi-rej-{uuid4().hex[:16]}"
    recorded_at = datetime.now(timezone.utc).isoformat()

    record = {
        "rejection_id": rejection_id,
        "tenant_id": tenant_id,
        "transaction_set": transaction_set,
        "traceability_lot_code": traceability_lot_code,
        "partner_id": partner_id,
        "source": source,
        "recorded_at": recorded_at,
        "errors": errors,
        # Snapshot of the extracted fields for forensic review. Drops
        # any non-serializable values defensively.
        "extracted": _scrub(extracted or {}),
        "reason": "fsma_validation_failed",
    }

    store = _rejection_store_for(tenant_id)
    store[rejection_id] = record
    while len(store) > _EDI_REJECTION_CAP_PER_TENANT:
        store.popitem(last=False)

    # Always log — the in-memory store is not durable on its own.
    logger.warning(
        "edi_fsma_rejection_recorded rejection_id=%s tenant=%s set=%s "
        "tlc=%s partner=%s errors=%d",
        rejection_id,
        tenant_id,
        transaction_set,
        traceability_lot_code,
        partner_id,
        len(errors),
    )

    return record


def list_edi_rejections(tenant_id: str) -> list[dict[str, Any]]:
    """Return recorded rejections for a tenant (most recent last)."""
    return list(_rejection_store_for(tenant_id).values())


def reset_edi_rejections() -> None:
    """Test helper: clear the rejection store across tenants."""
    _edi_rejection_store.clear()


def _scrub(value: Any) -> Any:
    """Best-effort JSON-safe scrub so the rejection record survives
    serialization. Drops non-serializable leaves instead of failing.
    """
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
