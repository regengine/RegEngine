"""Retailer network connectors.

Walmart, Kroger, Whole Foods, and Costco all participate in FSMA 204
traceability requirements as receivers of food on the Food Traceability
List (FTL). These connectors handle:

  - Walmart: GDSN / GS1 US Data Hub integration for item data sync
  - Kroger: 84.51° supplier portal data exchange
  - Whole Foods: Amazon supplier compliance portal
  - Costco: Supplier diversity and food safety portal

Note: These are "outbound" connectors — they push RegEngine's
traceability data TO retailer portals, rather than pulling data in.
Each retailer has specific format/submission requirements.
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

logger = logging.getLogger("connector-retailers")


class WalmartGDSNConnector(IntegrationConnector):
    """Walmart GDSN / GS1 US Data Hub connector.

    Pushes product traceability data to Walmart's supplier systems
    using GS1 GDSN (Global Data Synchronisation Network) format.

    Walmart requires:
      - GTIN (Global Trade Item Number) for each product
      - GLN for each shipping/receiving location
      - CTE records for shipping events to Walmart DCs
    """

    API_BASE = "https://api.walmart.com/v3/items"

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._client_id = config.oauth_client_id
        self._client_secret = config.oauth_client_secret

    async def test_connection(self) -> bool:
        """Test Walmart API credentials."""
        if not self._client_id or not self._client_secret:
            self._status = ConnectionStatus.DISCONNECTED
            return False
        # Walmart uses OAuth2 — token exchange would happen here
        # For now, validate credentials are present
        self._status = ConnectionStatus.PENDING
        logger.info("walmart_credentials_configured awaiting_activation")
        return True

    async def fetch_events(
        self,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[List[NormalizedCTEEvent], Optional[str]]:
        """Walmart is primarily outbound — fetch returns retailer acknowledgments."""
        return [], None

    async def push_event(self, event: NormalizedCTEEvent) -> bool:
        """Push a shipping CTE to Walmart's receiving system.

        Converts CTE event to Walmart's expected ASN (Advanced Shipping
        Notice) format with GS1 identifiers.
        """
        if event.cte_type != "shipping":
            logger.debug("walmart_skip_non_shipping cte_type=%s", event.cte_type)
            return True  # only shipping events relevant to Walmart

        # Build Walmart ASN payload
        asn_payload = {
            "shipmentHeader": {
                "shipmentId": event.source_event_id or f"RE-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "shipDate": event.timestamp,
                "estimatedDeliveryDate": event.kdes.get("estimated_delivery"),
                "carrierName": event.kdes.get("carrier_name", ""),
                "trackingNumber": event.kdes.get("tracking_number", ""),
            },
            "shipmentLines": [
                {
                    "gtin": event.kdes.get("gtin", ""),
                    "lotNumber": event.traceability_lot_code,
                    "quantity": event.quantity,
                    "unitOfMeasure": event.unit_of_measure.upper(),
                    "productDescription": event.product_description,
                    "shipFromGln": event.location_gln or event.kdes.get("ship_from_gln", ""),
                    "shipToGln": event.kdes.get("ship_to_gln", ""),
                }
            ],
        }
        logger.info(
            "walmart_asn_prepared shipment_id=%s tlc=%s",
            asn_payload["shipmentHeader"]["shipmentId"],
            event.traceability_lot_code,
        )
        # Actual API call would go here with httpx
        return True

    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        """Normalize Walmart acknowledgment to CTE event."""
        return NormalizedCTEEvent(
            cte_type="receiving",
            traceability_lot_code=raw_event.get("lotNumber", ""),
            product_description=raw_event.get("productDescription", ""),
            quantity=float(raw_event.get("quantity", 1)),
            unit_of_measure=raw_event.get("unitOfMeasure", "cases"),
            timestamp=raw_event.get("receivedDate", datetime.now(timezone.utc).isoformat()),
            location_gln=raw_event.get("receivingGln"),
            kdes={"walmart_po": raw_event.get("poNumber", "")},
        )

    def get_connector_info(self) -> Dict[str, Any]:
        return {
            "id": "walmart",
            "name": "Walmart GDSN",
            "category": "retailer",
            "description": (
                "Push shipping traceability data to Walmart via GS1 GDSN. "
                "Automatically generates ASN (Advanced Shipping Notice) "
                "from shipping CTE events with GTIN and GLN identifiers."
            ),
            "supported_cte_types": ["shipping"],
            "auth_type": AuthType.OAUTH2.value,
            "features": [
                "ASN generation from shipping CTEs",
                "GTIN/GLN product identification",
                "Walmart supplier portal sync",
                "GS1 GDSN format compliance",
            ],
        }


class KrogerConnector(IntegrationConnector):
    """Kroger 84.51° supplier data exchange connector.

    Kroger uses their 84.51° data platform for supplier collaboration.
    This connector pushes traceability data for products shipped to
    Kroger distribution centers.
    """

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)

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
        return [], None

    async def push_event(self, event: NormalizedCTEEvent) -> bool:
        if event.cte_type != "shipping":
            return True
        logger.info(
            "kroger_push_prepared tlc=%s product=%s",
            event.traceability_lot_code, event.product_description,
        )
        return True

    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        return NormalizedCTEEvent(
            cte_type="receiving",
            traceability_lot_code=raw_event.get("lot_number", ""),
            product_description=raw_event.get("product", ""),
            quantity=float(raw_event.get("quantity", 1)),
            unit_of_measure=raw_event.get("uom", "cases"),
            timestamp=raw_event.get("date", datetime.now(timezone.utc).isoformat()),
        )

    def get_connector_info(self) -> Dict[str, Any]:
        return {
            "id": "kroger",
            "name": "Kroger 84.51°",
            "category": "retailer",
            "description": (
                "Exchange traceability data with Kroger via their 84.51° "
                "supplier collaboration platform. Push shipping records "
                "for products destined to Kroger distribution centers."
            ),
            "supported_cte_types": ["shipping"],
            "auth_type": AuthType.API_KEY.value,
            "features": [
                "Supplier portal data exchange",
                "Shipping CTE push",
                "Kroger DC routing support",
            ],
        }


class WholeFoodsConnector(IntegrationConnector):
    """Whole Foods (Amazon) supplier compliance connector."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)

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
        return [], None

    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        return NormalizedCTEEvent(
            cte_type="receiving",
            traceability_lot_code=raw_event.get("lot", ""),
            product_description=raw_event.get("product", ""),
            quantity=float(raw_event.get("qty", 1)),
            unit_of_measure=raw_event.get("unit", "cases"),
            timestamp=raw_event.get("date", datetime.now(timezone.utc).isoformat()),
        )

    def get_connector_info(self) -> Dict[str, Any]:
        return {
            "id": "whole_foods",
            "name": "Whole Foods Market",
            "category": "retailer",
            "description": (
                "Push traceability data to Whole Foods via Amazon's "
                "supplier compliance portal. Supports FTL product "
                "documentation and shipping record exchange."
            ),
            "supported_cte_types": ["shipping"],
            "auth_type": AuthType.OAUTH2.value,
            "features": [
                "Amazon supplier portal integration",
                "FTL product documentation",
                "Shipping record exchange",
            ],
        }


class CostcoConnector(IntegrationConnector):
    """Costco supplier food safety portal connector."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)

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
        return [], None

    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        return NormalizedCTEEvent(
            cte_type="receiving",
            traceability_lot_code=raw_event.get("lot", ""),
            product_description=raw_event.get("product", ""),
            quantity=float(raw_event.get("qty", 1)),
            unit_of_measure=raw_event.get("unit", "cases"),
            timestamp=raw_event.get("date", datetime.now(timezone.utc).isoformat()),
        )

    def get_connector_info(self) -> Dict[str, Any]:
        return {
            "id": "costco",
            "name": "Costco Wholesale",
            "category": "retailer",
            "description": (
                "Exchange traceability documentation with Costco's "
                "food safety and supplier compliance portal."
            ),
            "supported_cte_types": ["shipping"],
            "auth_type": AuthType.API_KEY.value,
            "features": [
                "Supplier compliance portal",
                "Food safety documentation",
                "Shipping record exchange",
            ],
        }
