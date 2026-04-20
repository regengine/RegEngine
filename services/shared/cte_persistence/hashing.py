from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID


# ---------------------------------------------------------------------------
# Canonical normalization for hashing
# ---------------------------------------------------------------------------

def _normalize_for_hashing(obj: Any) -> Any:
    """
    Convert exotic JSON-incompatible Python types to deterministic string
    forms BEFORE ``json.dumps`` sees them.

    Why explicit normalization rather than ``json.dumps(..., default=str)``:
    ``str(datetime)`` / ``str(Decimal)`` formats are version- and locale-
    fragile. A silent Python upgrade could change every idempotency key or
    event hash, breaking dedup across deploys (e.g. a mid-release deploy
    that flips the format would let duplicate events slip through). Pinning
    the shape here — ISO-8601 for datetimes, fixed-point for ``Decimal``,
    plain ``str(UUID)`` — makes the serialization contract a code-owned
    invariant that survives interpreter upgrades.

    Recurses into ``dict`` values and ``list`` / ``tuple`` items so a KDE
    like ``{"batch": {"produced_at": datetime(...), ...}}`` normalizes
    consistently at every depth.

    #1313 / EPIC #1670.
    """
    if isinstance(obj, datetime):
        # ISO 8601. ``datetime.isoformat`` preserves the timezone offset
        # ("+00:00") so UTC events and offset-tagged events remain
        # distinguishable. Callers that need the "Z" suffix must
        # normalize at the edge (ingestion); hashing must be stable
        # whatever form the caller chose.
        return obj.isoformat()
    if isinstance(obj, date):
        # Must come AFTER the datetime branch — ``datetime`` is a
        # subclass of ``date``.
        return obj.isoformat()
    if isinstance(obj, Decimal):
        # ``format(..., 'f')`` renders fixed-point with no scientific
        # notation drift. ``str(Decimal("1E+2"))`` yields "1E+2"; the
        # explicit fixed-point form is unambiguous.
        return format(obj, "f")
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _normalize_for_hashing(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize_for_hashing(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Hashing Utilities
# ---------------------------------------------------------------------------

def compute_event_hash(
    event_id: str,
    event_type: str,
    tlc: str,
    product_description: str,
    quantity: float,
    unit_of_measure: str,
    location_gln: Optional[str],
    location_name: Optional[str],
    timestamp: str,
    kdes: Dict[str, Any],
) -> str:
    """
    Compute SHA-256 hash of an event using pipe-delimited canonical form.

    This is the same algorithm as the original webhook_router, now centralized.

    KDE values are normalized through ``_normalize_for_hashing`` so that
    exotic types (``datetime``, ``Decimal``, ``UUID``, ...) serialize
    deterministically and survive Python-version upgrades. See #1313.
    """
    canonical = "|".join([
        event_id,
        event_type,
        tlc,
        product_description,
        str(quantity),
        unit_of_measure,
        location_gln or "",
        location_name or "",
        timestamp,
        json.dumps(_normalize_for_hashing(kdes), sort_keys=True),
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_chain_hash(event_hash: str, previous_chain_hash: Optional[str]) -> str:
    """
    Chain this event's hash to the previous chain hash.

    Chain root uses 'GENESIS' as the seed value.
    """
    chain_input = f"{previous_chain_hash or 'GENESIS'}|{event_hash}"
    return hashlib.sha256(chain_input.encode("utf-8")).hexdigest()


def compute_idempotency_key(
    event_type: str,
    tlc: str,
    timestamp: str,
    source: str,
    kdes: Dict[str, Any],
    location_gln: Optional[str] = None,
    location_name: Optional[str] = None,
) -> str:
    """
    Compute a deduplication key from event content (LEGACY path).

    Two identical events from the same source AND location produce the same key,
    preventing double-ingestion. Location is included because FSMA 204 treats
    location as critical to event identity — the same product shipped from two
    different warehouses at the same time are distinct events.

    NOTE: This formula differs from ``TraceabilityEvent.compute_idempotency_key``
    in ``canonical_event.py``. The canonical version uses
    ``from_facility`` / ``to_facility``; this version uses
    ``location_gln`` / ``location_name``. The same real-world event
    dual-written through both paths therefore produces DIFFERENT keys
    in each table. Scope: intentional — each table dedups independently
    with its own formula; idempotency keys are scoped per-table. Cross-
    table reconciliation must use ``sha256_hash``, not idempotency_key.
    Tracked for unification with the cte_persistence retirement (#1335).

    KDE values are normalized through ``_normalize_for_hashing`` so exotic
    types (``datetime``, ``Decimal``, ``UUID``, ...) serialize
    deterministically. See ``_normalize_for_hashing`` and #1313 for why
    this is an explicit type-dispatch rather than ``json.dumps(default=str)``.
    """
    canonical = json.dumps(
        _normalize_for_hashing({
            "event_type": event_type,
            "tlc": tlc,
            "timestamp": timestamp,
            "source": source,
            "location_gln": location_gln or "",
            "location_name": location_name or "",
            "kdes": kdes,
        }),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
