from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional


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
        json.dumps(kdes, sort_keys=True, default=str),
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
    """
    # ``default=str`` matches compute_event_hash above. Without it, a KDE
    # carrying a datetime or Decimal raises TypeError mid-insert and loses
    # the event (#1313). str() coercion is locale/version-fragile and a
    # long-term fix should normalize KDE values to JSON-safe primitives
    # before hashing — tracked for the cte_persistence retirement work.
    canonical = json.dumps(
        {
            "event_type": event_type,
            "tlc": tlc,
            "timestamp": timestamp,
            "source": source,
            "location_gln": location_gln or "",
            "location_name": location_name or "",
            "kdes": kdes,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
