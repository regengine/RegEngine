"""Base integration connector framework.

All external connectors (SafetyCulture, ERPs, retailers, IoT) extend
IntegrationConnector. This provides:
  - Standardized auth (API key, OAuth2, webhook secret)
  - Health checking and connection status
  - CTE event normalization to RegEngine's WebhookPayload format
  - Rate limiting and retry logic
  - Audit logging for compliance
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("integration-connector")


class ConnectionStatus(str, Enum):
    """Integration connection states."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    PENDING = "pending"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


class AuthType(str, Enum):
    """Supported authentication methods."""
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    WEBHOOK_SECRET = "webhook_secret"
    BASIC = "basic"
    NONE = "none"


@dataclass
class ConnectorConfig:
    """Configuration for an integration connector."""
    connector_id: str          # e.g. "safetyculture", "sap_s4hana"
    display_name: str          # e.g. "SafetyCulture (iAuditor)"
    category: str              # iot, erp, retailer, food_safety, developer
    auth_type: AuthType = AuthType.API_KEY
    base_url: str = ""
    api_key: str = ""
    api_secret: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_token_url: str = ""
    webhook_secret: str = ""
    tenant_id: str = ""
    rate_limit_rpm: int = 60   # requests per minute
    timeout_seconds: int = 30
    retry_max: int = 3
    retry_backoff: float = 1.0  # base seconds for exponential backoff
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncResult:
    """Result of a sync operation."""
    connector_id: str
    events_fetched: int = 0
    events_accepted: int = 0
    events_rejected: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0
    next_cursor: Optional[str] = None  # pagination token

    @property
    def success(self) -> bool:
        return len(self.errors) == 0 and self.events_rejected == 0


@dataclass
class NormalizedCTEEvent:
    """A CTE event normalized from any external source into RegEngine format.

    This maps directly to the WebhookPayload / IngestEvent models in
    webhook_models.py, so it can be fed directly into the V2 ingestion
    pipeline.
    """
    cte_type: str               # harvesting, cooling, shipping, receiving, etc.
    traceability_lot_code: str
    product_description: str
    quantity: float
    unit_of_measure: str
    timestamp: str              # ISO 8601
    location_gln: Optional[str] = None
    location_name: Optional[str] = None
    kdes: Dict[str, Any] = field(default_factory=dict)
    source_event_id: Optional[str] = None  # ID from the external system

    def to_ingest_dict(self) -> Dict[str, Any]:
        """Convert to dict matching IngestEvent schema."""
        d: Dict[str, Any] = {
            "cte_type": self.cte_type,
            "traceability_lot_code": self.traceability_lot_code,
            "product_description": self.product_description,
            "quantity": self.quantity,
            "unit_of_measure": self.unit_of_measure,
            "timestamp": self.timestamp,
            "kdes": dict(self.kdes),
        }
        if self.location_gln:
            d["location_gln"] = self.location_gln
        if self.location_name:
            d["location_name"] = self.location_name
        if self.source_event_id:
            d["kdes"]["source_event_id"] = self.source_event_id
        return d


class IntegrationConnector(ABC):
    """Base class for all external integration connectors.

    Subclasses implement:
      - test_connection()   → verify credentials
      - fetch_events()      → pull CTE events from external system
      - normalize_event()   → map vendor-specific data to NormalizedCTEEvent
      - get_connector_info() → metadata for the integrations page

    Optional overrides:
      - push_event()        → send CTE events TO external system
      - handle_webhook()    → process inbound webhooks from external system
    """

    def __init__(self, config: ConnectorConfig):
        self.config = config
        self._status = ConnectionStatus.DISCONNECTED
        self._last_sync: Optional[str] = None
        self._request_timestamps: List[float] = []

    @property
    def connector_id(self) -> str:
        return self.config.connector_id

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    @property
    def last_sync(self) -> Optional[str]:
        return self._last_sync

    # ── Abstract methods ─────────────────────────────────────────

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test that credentials are valid and the external system is reachable.

        Returns True if connected, False otherwise.
        Sets self._status accordingly.
        """
        pass

    @abstractmethod
    async def fetch_events(
        self,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[List[NormalizedCTEEvent], Optional[str]]:
        """Fetch CTE events from the external system.

        Args:
            since: Only fetch events after this timestamp.
            cursor: Pagination cursor from a previous fetch.
            limit: Maximum events to fetch.

        Returns:
            Tuple of (events, next_cursor). next_cursor is None if no more pages.
        """
        pass

    @abstractmethod
    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        """Convert a vendor-specific event dict into NormalizedCTEEvent."""
        pass

    @abstractmethod
    def get_connector_info(self) -> Dict[str, Any]:
        """Return metadata for the integrations page / settings UI.

        Should include: id, name, category, description, logo_url,
        supported_cte_types, auth_type, docs_url.
        """
        pass

    # ── Optional methods (override as needed) ────────────────────

    async def push_event(self, event: NormalizedCTEEvent) -> bool:
        """Push a CTE event TO the external system (outbound sync).

        Default: not supported. Override in connectors that support
        bidirectional sync.
        """
        raise NotImplementedError(
            f"{self.connector_id} does not support outbound event push"
        )

    async def handle_webhook(
        self,
        payload: bytes,
        headers: Dict[str, str],
    ) -> List[NormalizedCTEEvent]:
        """Process an inbound webhook from the external system.

        Default: not supported. Override for webhook-driven integrations.
        """
        raise NotImplementedError(
            f"{self.connector_id} does not support inbound webhooks"
        )

    # ── Sync orchestration ───────────────────────────────────────

    async def sync(
        self,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> SyncResult:
        """Full sync cycle: connect → fetch → return results.

        This is the main entry point for scheduled syncs.
        """
        result = SyncResult(
            connector_id=self.connector_id,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        start = time.monotonic()

        try:
            connected = await self.test_connection()
            if not connected:
                result.errors.append("Connection test failed")
                return result

            all_events: List[NormalizedCTEEvent] = []
            current_cursor = cursor
            fetched = 0

            while fetched < limit:
                batch_limit = min(100, limit - fetched)
                events, next_cursor = await self.fetch_events(
                    since=since, cursor=current_cursor, limit=batch_limit
                )
                all_events.extend(events)
                fetched += len(events)
                current_cursor = next_cursor

                if not next_cursor or not events:
                    break

            result.events_fetched = len(all_events)
            result.events_accepted = len(all_events)
            result.next_cursor = current_cursor
            self._last_sync = datetime.now(timezone.utc).isoformat()
            self._status = ConnectionStatus.CONNECTED

        except Exception as exc:
            logger.error(
                "sync_failed connector=%s error=%s",
                self.connector_id, str(exc),
            )
            result.errors.append(str(exc))
            self._status = ConnectionStatus.ERROR

        finally:
            elapsed = time.monotonic() - start
            result.duration_ms = int(elapsed * 1000)
            result.completed_at = datetime.now(timezone.utc).isoformat()

        return result

    # ── Rate limiting ────────────────────────────────────────────

    def _check_rate_limit(self) -> None:
        """Simple sliding-window rate limiter."""
        now = time.monotonic()
        window = 60.0  # 1 minute
        self._request_timestamps = [
            ts for ts in self._request_timestamps if now - ts < window
        ]
        if len(self._request_timestamps) >= self.config.rate_limit_rpm:
            self._status = ConnectionStatus.RATE_LIMITED
            sleep_time = window - (now - self._request_timestamps[0])
            raise RateLimitError(
                f"{self.connector_id} rate limited. Retry in {sleep_time:.1f}s"
            )
        self._request_timestamps.append(now)

    # ── Webhook signature verification ───────────────────────────

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        algorithm: str = "sha256",
    ) -> bool:
        """Verify HMAC signature on inbound webhook payloads."""
        if not self.config.webhook_secret:
            logger.warning("webhook_no_secret connector=%s", self.connector_id)  # nosemgrep: python-logger-credential-disclosure
            return False

        if algorithm == "sha256":
            expected = hmac.new(
                self.config.webhook_secret.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()
        elif algorithm == "sha1":
            expected = hmac.new(
                self.config.webhook_secret.encode(),
                payload,
                hashlib.sha1,
            ).hexdigest()
        else:
            return False

        return hmac.compare_digest(expected, signature)

    # ── Serialization ────────────────────────────────────────────

    def to_integration_status(self) -> Dict[str, Any]:
        """Convert to IntegrationStatus format for the settings API."""
        return {
            "id": self.config.connector_id,
            "name": self.config.display_name,
            "category": self.config.category,
            "status": self._status.value,
            "last_sync": self._last_sync,
        }


class RateLimitError(Exception):
    """Raised when connector exceeds rate limit."""
    pass
