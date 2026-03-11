"""Food safety platform connectors.

FoodReady, FoodDocs, and foodfluDaily are food safety management
platforms that help with HACCP plans, SOPs, and compliance documentation.
These connectors pull food safety audit/monitoring data and normalize
it into FSMA 204 CTE events.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import (
    AuthType,
    ConnectorConfig,
    ConnectionStatus,
    IntegrationConnector,
    NormalizedCTEEvent,
)

logger = logging.getLogger("connector-food-safety")


class FoodReadyConnector(IntegrationConnector):
    """FoodReady food safety management connector.

    FoodReady provides HACCP plan management, supplier verification,
    and food safety record keeping. This connector pulls:
      - Temperature monitoring logs → COOLING CTEs
      - Receiving inspection records → RECEIVING CTEs
      - Supplier verification data → KDEs
    """

    API_BASE = "https://api.foodready.ai/v1"

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        if not config.base_url:
            config.base_url = self.API_BASE

    async def test_connection(self) -> bool:
        if not self.config.api_key:
            self._status = ConnectionStatus.DISCONNECTED
            return False
        try:
            import httpx
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                timeout=self.config.timeout_seconds,
            ) as client:
                resp = await client.get(f"{self.config.base_url}/me")
                if resp.status_code == 200:
                    self._status = ConnectionStatus.CONNECTED
                    return True
        except Exception as exc:
            logger.error("foodready_connection_failed error=%s", str(exc))
        self._status = ConnectionStatus.ERROR
        return False

    async def fetch_events(
        self,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[List[NormalizedCTEEvent], Optional[str]]:
        """Fetch food safety records from FoodReady."""
        try:
            import httpx
            params: Dict[str, Any] = {"limit": limit}
            if since:
                params["since"] = since.isoformat()
            if cursor:
                params["cursor"] = cursor

            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                timeout=self.config.timeout_seconds,
            ) as client:
                resp = await client.get(
                    f"{self.config.base_url}/records",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

            events = [self.normalize_event(r) for r in data.get("records", [])]
            next_cursor = data.get("next_cursor")
            return events, next_cursor

        except Exception as exc:
            logger.error("foodready_fetch_failed error=%s", str(exc))
            return [], None

    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        record_type = raw_event.get("record_type", "").lower()
        cte_map = {
            "temperature_log": "cooling",
            "receiving_inspection": "receiving",
            "shipping_record": "shipping",
            "processing_record": "transformation",
        }
        cte_type = cte_map.get(record_type, "receiving")

        kdes: Dict[str, Any] = {
            "foodready_record_id": raw_event.get("id", ""),
            "foodready_record_type": record_type,
        }
        if raw_event.get("temperature"):
            kdes["temperature"] = raw_event["temperature"]
            kdes["temperature_unit"] = raw_event.get("temp_unit", "F")
        if raw_event.get("corrective_action"):
            kdes["corrective_action"] = raw_event["corrective_action"]

        return NormalizedCTEEvent(
            cte_type=cte_type,
            traceability_lot_code=raw_event.get("lot_code", f"FR-{raw_event.get('id', '')}"),
            product_description=raw_event.get("product", "FoodReady Record"),
            quantity=float(raw_event.get("quantity", 1)),
            unit_of_measure=raw_event.get("unit", "units"),
            timestamp=raw_event.get("created_at", datetime.now(timezone.utc).isoformat()),
            location_name=raw_event.get("location"),
            kdes=kdes,
            source_event_id=raw_event.get("id"),
        )

    def get_connector_info(self) -> Dict[str, Any]:
        return {
            "id": "foodready",
            "name": "FoodReady",
            "category": "food_safety",
            "description": (
                "Pull food safety records from FoodReady including "
                "temperature logs, receiving inspections, and HACCP "
                "monitoring data. Auto-maps to FSMA 204 CTE types."
            ),
            "supported_cte_types": ["receiving", "cooling", "shipping", "transformation"],
            "auth_type": AuthType.API_KEY.value,
            "features": [
                "Temperature monitoring sync",
                "Receiving inspection import",
                "HACCP record integration",
                "Supplier verification data",
            ],
        }


class FoodDocsConnector(IntegrationConnector):
    """FoodDocs AI food safety management connector.

    FoodDocs uses AI to generate HACCP plans and monitor food safety
    compliance. This connector pulls monitoring data and converts it
    to FSMA 204 CTE events.
    """

    API_BASE = "https://api.fooddocs.com/v2"

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        if not config.base_url:
            config.base_url = self.API_BASE

    async def test_connection(self) -> bool:
        if not self.config.api_key:
            self._status = ConnectionStatus.DISCONNECTED
            return False
        self._status = ConnectionStatus.PENDING
        return True

    async def fetch_events(
        self,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[List[NormalizedCTEEvent], Optional[str]]:
        """Fetch monitoring records from FoodDocs."""
        try:
            import httpx
            params: Dict[str, Any] = {"limit": limit}
            if since:
                params["modified_after"] = since.isoformat()
            if cursor:
                params["page"] = cursor

            async with httpx.AsyncClient(
                headers={"X-Api-Key": self.config.api_key},
                timeout=self.config.timeout_seconds,
            ) as client:
                resp = await client.get(
                    f"{self.config.base_url}/monitoring-tasks",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

            events = [self.normalize_event(t) for t in data.get("tasks", [])]
            next_page = data.get("next_page")
            return events, str(next_page) if next_page else None

        except Exception as exc:
            logger.error("fooddocs_fetch_failed error=%s", str(exc))
            return [], None

    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        task_type = raw_event.get("task_type", "").lower()
        cte_map = {
            "temperature_check": "cooling",
            "goods_receiving": "receiving",
            "dispatch": "shipping",
        }

        kdes: Dict[str, Any] = {
            "fooddocs_task_id": raw_event.get("id", ""),
            "fooddocs_task_type": task_type,
        }
        if raw_event.get("reading"):
            kdes["temperature"] = raw_event["reading"]

        return NormalizedCTEEvent(
            cte_type=cte_map.get(task_type, "receiving"),
            traceability_lot_code=raw_event.get("lot_code", f"FD-{raw_event.get('id', '')}"),
            product_description=raw_event.get("product_name", "FoodDocs Record"),
            quantity=float(raw_event.get("quantity", 1)),
            unit_of_measure=raw_event.get("unit", "units"),
            timestamp=raw_event.get("completed_at", datetime.now(timezone.utc).isoformat()),
            location_name=raw_event.get("location"),
            kdes=kdes,
            source_event_id=raw_event.get("id"),
        )

    def get_connector_info(self) -> Dict[str, Any]:
        return {
            "id": "fooddocs",
            "name": "FoodDocs",
            "category": "food_safety",
            "description": (
                "Sync AI-powered food safety monitoring data from FoodDocs. "
                "Pull temperature checks, receiving records, and HACCP "
                "monitoring tasks as FSMA 204 CTE events."
            ),
            "supported_cte_types": ["receiving", "cooling", "shipping"],
            "auth_type": AuthType.API_KEY.value,
            "features": [
                "AI monitoring task sync",
                "Temperature check import",
                "HACCP compliance data",
            ],
        }


class TiveConnector(IntegrationConnector):
    """Tive real-time shipment tracker connector.

    Tive provides GPS + temperature trackers for in-transit
    cold chain monitoring. This connector pulls tracker data
    and creates shipping/receiving CTE events with temperature KDEs.
    """

    API_BASE = "https://api.tive.com/v1"

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        if not config.base_url:
            config.base_url = self.API_BASE

    async def test_connection(self) -> bool:
        if not self.config.api_key:
            self._status = ConnectionStatus.DISCONNECTED
            return False
        try:
            import httpx
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                timeout=self.config.timeout_seconds,
            ) as client:
                resp = await client.get(f"{self.config.base_url}/trackers")
                if resp.status_code == 200:
                    self._status = ConnectionStatus.CONNECTED
                    return True
        except Exception as exc:
            logger.error("tive_connection_failed error=%s", str(exc))
        self._status = ConnectionStatus.ERROR
        return False

    async def fetch_events(
        self,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[List[NormalizedCTEEvent], Optional[str]]:
        """Fetch completed shipment tracking data from Tive."""
        try:
            import httpx
            params: Dict[str, Any] = {"limit": limit, "status": "delivered"}
            if since:
                params["since"] = since.isoformat()

            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                timeout=self.config.timeout_seconds,
            ) as client:
                resp = await client.get(
                    f"{self.config.base_url}/shipments",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

            events: List[NormalizedCTEEvent] = []
            for shipment in data.get("shipments", []):
                events.extend(self._shipment_to_ctes(shipment))
            return events[:limit], data.get("next_cursor")

        except Exception as exc:
            logger.error("tive_fetch_failed error=%s", str(exc))
            return [], None

    def _shipment_to_ctes(self, shipment: Dict) -> List[NormalizedCTEEvent]:
        """Convert a Tive shipment into shipping + receiving CTE pair."""
        events = []
        tlc = shipment.get("lot_code") or shipment.get("reference", f"TIVE-{shipment.get('id', '')}")
        product = shipment.get("product_name", "Tive Tracked Shipment")
        quantity = float(shipment.get("quantity", 1))
        unit = shipment.get("unit", "cases")

        # Temperature summary
        temp_data = shipment.get("temperature_summary", {})
        temp_kdes = {}
        if temp_data:
            temp_kdes = {
                "min_temperature": temp_data.get("min"),
                "max_temperature": temp_data.get("max"),
                "avg_temperature": temp_data.get("avg"),
                "temperature_unit": temp_data.get("unit", "F"),
                "temperature_excursions": temp_data.get("excursion_count", 0),
            }

        # Shipping CTE
        if shipment.get("ship_date"):
            events.append(NormalizedCTEEvent(
                cte_type="shipping",
                traceability_lot_code=tlc,
                product_description=product,
                quantity=quantity,
                unit_of_measure=unit,
                timestamp=shipment["ship_date"],
                location_name=shipment.get("origin", {}).get("name"),
                location_gln=shipment.get("origin", {}).get("gln"),
                kdes={
                    **temp_kdes,
                    "carrier_name": shipment.get("carrier", ""),
                    "tracking_number": shipment.get("tracking_number", ""),
                    "tive_tracker_id": shipment.get("tracker_id", ""),
                    "ship_to_location": shipment.get("destination", {}).get("name", ""),
                    "ship_to_gln": shipment.get("destination", {}).get("gln", ""),
                },
                source_event_id=f"tive-ship-{shipment.get('id', '')}",
            ))

        # Receiving CTE (when delivered)
        if shipment.get("delivery_date"):
            events.append(NormalizedCTEEvent(
                cte_type="receiving",
                traceability_lot_code=tlc,
                product_description=product,
                quantity=quantity,
                unit_of_measure=unit,
                timestamp=shipment["delivery_date"],
                location_name=shipment.get("destination", {}).get("name"),
                location_gln=shipment.get("destination", {}).get("gln"),
                kdes={
                    **temp_kdes,
                    "tive_tracker_id": shipment.get("tracker_id", ""),
                    "transit_time_hours": shipment.get("transit_hours"),
                    "receiving_location": shipment.get("destination", {}).get("name", ""),
                },
                source_event_id=f"tive-recv-{shipment.get('id', '')}",
            ))

        return events

    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        ctes = self._shipment_to_ctes(raw_event)
        return ctes[0] if ctes else NormalizedCTEEvent(
            cte_type="shipping",
            traceability_lot_code="",
            product_description="",
            quantity=1,
            unit_of_measure="cases",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def get_connector_info(self) -> Dict[str, Any]:
        return {
            "id": "tive",
            "name": "Tive Trackers",
            "category": "iot",
            "description": (
                "Import real-time GPS and temperature tracking data from "
                "Tive shipment trackers. Automatically creates shipping and "
                "receiving CTE pairs with cold chain temperature KDEs."
            ),
            "supported_cte_types": ["shipping", "receiving"],
            "auth_type": AuthType.API_KEY.value,
            "features": [
                "Real-time GPS tracking",
                "Temperature excursion alerts",
                "Shipping/receiving CTE pairs",
                "Cold chain documentation",
                "Transit time tracking",
            ],
        }
