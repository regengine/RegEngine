from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from services.shared.canonical_event import normalize_webhook_event


def test_normalize_webhook_event_preserves_inbound_source() -> None:
    event = SimpleNamespace(
        cte_type="shipping",
        traceability_lot_code="LOT-001",
        product_description="Romaine Lettuce",
        quantity=48,
        unit_of_measure="cases",
        timestamp=datetime(2026, 4, 27, 18, 30, tzinfo=timezone.utc),
        location_gln=None,
        location_name="Inflow Lab Demo DC",
        kdes={},
    )

    canonical = normalize_webhook_event(
        event,
        "00000000-0000-0000-0000-000000000001",
        source="inflow-lab",
    )

    assert canonical.raw_payload["source"] == "inflow-lab"
    assert canonical.kdes["ingest_source"] == "inflow-lab"
