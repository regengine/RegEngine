"""Inflow Lab developer connector.

Inflow Lab is a RegEngine-owned simulator that pushes FSMA 204 webhook
payloads into the ingestion API. It is intentionally push-only: there is no
external vendor account to poll and no production credential exchange.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import (
    AuthType,
    ConnectorConfig,
    ConnectionStatus,
    IntegrationConnector,
    NormalizedCTEEvent,
)


SUPPORTED_CTE_TYPES = [
    "harvesting",
    "cooling",
    "initial_packing",
    "first_land_based_receiving",
    "shipping",
    "receiving",
    "transformation",
]


class InflowLabConnector(IntegrationConnector):
    """RegEngine-owned simulator connector for demos and contract testing."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._source_label = config.extra.get("source_label", "inflow-lab")

    async def test_connection(self) -> bool:
        """Mark configured Inflow Lab as available.

        The simulator submits data to RegEngine's webhook endpoint, so there is
        no upstream credential or health endpoint required for normal use.
        """
        self._status = ConnectionStatus.CONNECTED
        return True

    async def fetch_events(
        self,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[List[NormalizedCTEEvent], Optional[str]]:
        """Inflow Lab is push-only; scheduled pulls are a no-op."""
        return [], None

    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        """Normalize a RegEngine-shaped simulator event."""
        kdes = dict(raw_event.get("kdes") or {})
        kdes.setdefault("integration_source", self._source_label)

        source_event_id = raw_event.get("source_event_id") or raw_event.get("id")
        if source_event_id:
            kdes.setdefault("source_event_id", source_event_id)

        timestamp = raw_event.get("timestamp")
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        return NormalizedCTEEvent(
            cte_type=str(raw_event.get("cte_type", "shipping")),
            traceability_lot_code=str(raw_event.get("traceability_lot_code", "")),
            product_description=str(raw_event.get("product_description", "")),
            quantity=float(raw_event.get("quantity", 0)),
            unit_of_measure=str(raw_event.get("unit_of_measure", "each")),
            timestamp=str(timestamp),
            location_gln=raw_event.get("location_gln"),
            location_name=raw_event.get("location_name"),
            kdes=kdes,
            source_event_id=source_event_id,
        )

    def get_connector_info(self) -> Dict[str, Any]:
        return {
            "id": "inflow_lab",
            "slug": "inflow-lab",
            "aliases": ["inflow-lab"],
            "name": "Inflow Lab",
            "category": "developer",
            "description": (
                "RegEngine-owned FSMA 204 simulator for webhook contract tests, "
                "demo traceability flows, and developer validation."
            ),
            "logo_url": None,
            "supported_cte_types": SUPPORTED_CTE_TYPES,
            "auth_type": AuthType.NONE.value,
            "docs_url": "/docs/connectors/inflow-lab",
            "delivery_mode": "webhook_push",
            "features": [
                "Pushes RegEngine webhook payloads",
                "Covers the FSMA 204 CTE lifecycle",
                "Supports contract CI and demo data generation",
                "Tags inbound events with source=inflow-lab",
            ],
        }
