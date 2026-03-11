"""SafetyCulture (iAuditor) integration connector.

SafetyCulture is the most widely used food safety audit platform.
This connector pulls completed inspection/audit data and normalizes
it into FSMA 204 CTE events.

API docs: https://developer.safetyculture.com/
Auth: Bearer token (API key from SafetyCulture dashboard)
Rate limit: 100 req/min

Mapping strategy:
  - SafetyCulture "inspections" → RegEngine CTE events
  - Template-based mapping: cooling logs → COOLING CTE,
    receiving inspections → RECEIVING CTE, etc.
  - KDEs extracted from inspection responses (temperature,
    location, product details, corrective actions)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from .base import (
    AuthType,
    ConnectorConfig,
    ConnectionStatus,
    IntegrationConnector,
    NormalizedCTEEvent,
)

logger = logging.getLogger("connector-safetyculture")

# SafetyCulture bizStep → RegEngine CTE type mapping
# Customers configure this per-template in their SafetyCulture setup
_DEFAULT_TEMPLATE_CTE_MAP: Dict[str, str] = {
    "receiving": "receiving",
    "receive": "receiving",
    "incoming": "receiving",
    "shipping": "shipping",
    "dispatch": "shipping",
    "outbound": "shipping",
    "cooling": "cooling",
    "cold_chain": "cooling",
    "temperature": "cooling",
    "harvest": "harvesting",
    "packing": "initial_packing",
    "pack": "initial_packing",
    "transformation": "transformation",
    "processing": "transformation",
}


def _infer_cte_type(template_name: str) -> str:
    """Infer CTE type from SafetyCulture template name."""
    name_lower = template_name.lower()
    for keyword, cte_type in _DEFAULT_TEMPLATE_CTE_MAP.items():
        if keyword in name_lower:
            return cte_type
    return "receiving"  # default fallback


class SafetyCultureConnector(IntegrationConnector):
    """Connector for SafetyCulture (iAuditor) food safety platform.

    Pulls completed inspections and maps them to FSMA 204 CTE events.
    Supports:
      - Pulling completed audits/inspections
      - Extracting temperature readings as KDEs
      - Mapping inspection templates to CTE types
      - Webhook-driven real-time sync
    """

    API_BASE = "https://api.safetyculture.io"

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        if not config.base_url:
            config.base_url = self.API_BASE
        self._client: Optional[httpx.AsyncClient] = None
        # Custom template → CTE type overrides from tenant config
        self._template_cte_map: Dict[str, str] = config.extra.get(
            "template_cte_map", {}
        )

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "RegEngine/1.0 (FSMA 204 Compliance)",
                },
                timeout=self.config.timeout_seconds,
            )
        return self._client

    async def test_connection(self) -> bool:
        """Verify SafetyCulture API key by fetching user info."""
        try:
            self._check_rate_limit()
            client = self._get_client()
            resp = await client.get("/users/v1/users/me")
            if resp.status_code == 200:
                self._status = ConnectionStatus.CONNECTED
                data = resp.json()
                logger.info(
                    "safetyculture_connected org=%s user=%s",
                    data.get("organisation_id", "unknown"),
                    data.get("email", "unknown"),
                )
                return True
            else:
                self._status = ConnectionStatus.ERROR
                logger.warning(
                    "safetyculture_auth_failed status=%d", resp.status_code
                )
                return False
        except Exception as exc:
            self._status = ConnectionStatus.ERROR
            logger.error("safetyculture_connection_error error=%s", str(exc))
            return False

    async def fetch_events(
        self,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[List[NormalizedCTEEvent], Optional[str]]:
        """Fetch completed inspections from SafetyCulture.

        Uses the /audits/search endpoint with modified_after filter.
        """
        self._check_rate_limit()
        client = self._get_client()

        params: Dict[str, Any] = {
            "field": ["audit_id", "modified_at", "template_id", "audit_title",
                       "created_at", "completed_at", "audit_data"],
            "order": "asc",
            "limit": min(limit, 100),
            "completed": "true",  # only completed inspections
        }

        if since:
            params["modified_after"] = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if cursor:
            params["cursor"] = cursor

        resp = await client.get("/audits/search", params=params)
        resp.raise_for_status()
        data = resp.json()

        audits = data.get("audits", [])
        next_cursor = data.get("metadata", {}).get("next_page")

        events: List[NormalizedCTEEvent] = []
        for audit in audits:
            try:
                # Fetch full audit detail for KDE extraction
                audit_id = audit.get("audit_id")
                if audit_id:
                    detail = await self._fetch_audit_detail(audit_id)
                    event = self.normalize_event(detail)
                    events.append(event)
            except Exception as exc:
                logger.warning(
                    "safetyculture_normalize_failed audit_id=%s error=%s",
                    audit.get("audit_id"), str(exc),
                )

        return events, next_cursor if next_cursor else None

    async def _fetch_audit_detail(self, audit_id: str) -> Dict[str, Any]:
        """Fetch full audit detail including responses."""
        self._check_rate_limit()
        client = self._get_client()
        resp = await client.get(f"/audits/{audit_id}")
        resp.raise_for_status()
        return resp.json()

    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        """Convert a SafetyCulture audit into a RegEngine CTE event.

        Mapping:
          - template_name → CTE type (via _template_cte_map or inference)
          - audit responses → KDEs (temperature, product, location)
          - audit location → location_name
          - completed_at → timestamp
        """
        audit_data = raw_event.get("audit_data", raw_event)
        template_id = raw_event.get("template_id", "")
        template_name = audit_data.get("name", raw_event.get("audit_title", ""))

        # Determine CTE type from template
        cte_type = self._template_cte_map.get(template_id)
        if not cte_type:
            cte_type = _infer_cte_type(template_name)

        # Extract location from audit
        location_name = None
        audit_location = audit_data.get("location", {})
        if isinstance(audit_location, dict):
            location_name = audit_location.get("name")

        # Extract responses as KDEs
        kdes = self._extract_kdes_from_responses(raw_event)

        # Derive lot code from KDEs or audit title
        tlc = (
            kdes.get("traceability_lot_code")
            or kdes.get("lot_code")
            or kdes.get("lot_number")
            or f"SC-{raw_event.get('audit_id', 'unknown')}"
        )

        # Product description
        product = (
            kdes.get("product_description")
            or kdes.get("product_name")
            or kdes.get("product")
            or template_name
        )

        # Quantity
        quantity = 1.0
        if kdes.get("quantity"):
            try:
                quantity = float(kdes["quantity"])
            except (ValueError, TypeError):
                pass

        # Unit
        unit = kdes.get("unit_of_measure", "units")

        # Timestamp
        timestamp = (
            raw_event.get("completed_at")
            or raw_event.get("modified_at")
            or datetime.now(timezone.utc).isoformat()
        )

        # Add SafetyCulture-specific KDEs
        kdes["safetyculture_audit_id"] = raw_event.get("audit_id", "")
        kdes["safetyculture_template_id"] = template_id
        kdes["safetyculture_template_name"] = template_name
        kdes["inspection_score"] = audit_data.get("score_percentage")
        kdes["conducted_by"] = audit_data.get("authorship", {}).get("author", "")

        return NormalizedCTEEvent(
            cte_type=cte_type,
            traceability_lot_code=tlc,
            product_description=product,
            quantity=quantity,
            unit_of_measure=unit,
            timestamp=timestamp,
            location_name=location_name,
            kdes=kdes,
            source_event_id=raw_event.get("audit_id"),
        )

    def _extract_kdes_from_responses(self, audit: Dict) -> Dict[str, Any]:
        """Extract KDEs from SafetyCulture inspection responses.

        Looks for common FSMA-relevant fields in audit item responses:
        temperature, lot code, product name, quantity, carrier, etc.
        """
        kdes: Dict[str, Any] = {}
        items = audit.get("items", [])
        if not items:
            header_items = audit.get("header_items", [])
            items = header_items

        for item in items:
            label = (item.get("label") or "").lower().strip()
            responses = item.get("responses", {})
            value = None

            # Extract the response value
            if "text" in responses:
                value = responses["text"]
            elif "selected" in responses:
                selected = responses["selected"]
                if isinstance(selected, list) and selected:
                    value = selected[0].get("label", "")
            elif "number" in responses:
                value = responses["number"]
            elif "datetime" in responses:
                value = responses["datetime"]

            if value is None:
                continue

            # Map common SafetyCulture fields to FSMA KDEs
            if any(k in label for k in ["lot", "tlc", "traceability"]):
                kdes["traceability_lot_code"] = str(value)
            elif any(k in label for k in ["product", "item name", "commodity"]):
                kdes["product_description"] = str(value)
            elif "quantity" in label or "amount" in label:
                kdes["quantity"] = value
            elif "unit" in label:
                kdes["unit_of_measure"] = str(value)
            elif any(k in label for k in ["temp", "temperature"]):
                kdes["temperature"] = value
                kdes["temperature_unit"] = "F"  # default, override if specified
            elif "carrier" in label:
                kdes["carrier_name"] = str(value)
            elif "po" in label or "purchase order" in label:
                kdes["purchase_order"] = str(value)
            elif "gln" in label:
                kdes["location_gln"] = str(value)
            elif any(k in label for k in ["corrective", "action"]):
                kdes["corrective_action"] = str(value)
            elif any(k in label for k in ["seal", "container"]):
                kdes["container_seal_number"] = str(value)
            else:
                # Store as generic KDE
                safe_key = label.replace(" ", "_").replace("-", "_")[:50]
                if safe_key:
                    kdes[f"sc_{safe_key}"] = value

        return kdes

    async def handle_webhook(
        self,
        payload: bytes,
        headers: Dict[str, str],
    ) -> List[NormalizedCTEEvent]:
        """Handle inbound webhook from SafetyCulture.

        SafetyCulture sends webhooks on audit completion.
        Webhook signature is verified via X-Sc-Signature header.
        """
        # Verify signature
        signature = headers.get("x-sc-signature", "")
        if self.config.webhook_secret and signature:
            if not self.verify_webhook_signature(payload, signature):
                raise ValueError("Invalid SafetyCulture webhook signature")

        import json
        data = json.loads(payload)
        event_type = data.get("event_type", "")

        if event_type not in ("INSPECTION_COMPLETED", "AUDIT_COMPLETED"):
            return []  # ignore non-completion events

        audit_id = data.get("audit_id") or data.get("inspection_id")
        if not audit_id:
            return []

        # Fetch full audit detail and normalize
        detail = await self._fetch_audit_detail(audit_id)
        event = self.normalize_event(detail)
        return [event]

    def get_connector_info(self) -> Dict[str, Any]:
        return {
            "id": "safetyculture",
            "name": "SafetyCulture (iAuditor)",
            "category": "food_safety",
            "description": (
                "Pull completed food safety inspections and audits from "
                "SafetyCulture (iAuditor). Automatically maps inspection "
                "templates to FSMA 204 CTE types and extracts KDEs from "
                "audit responses."
            ),
            "supported_cte_types": [
                "receiving", "shipping", "cooling", "harvesting",
                "initial_packing", "transformation",
            ],
            "auth_type": AuthType.API_KEY.value,
            "docs_url": "https://developer.safetyculture.com/",
            "features": [
                "Pull completed inspections",
                "Template-to-CTE mapping",
                "KDE extraction from responses",
                "Real-time webhook sync",
                "Temperature monitoring data",
            ],
        }
