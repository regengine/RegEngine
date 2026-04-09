"""Notification system for webhook delivery.

Delivers enforcement alerts to configured webhook endpoints with
retry logic and dead-letter handling.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import httpx
import structlog

from .config import get_settings
from .models import EnforcementItem, WebhookPayload

logger = structlog.get_logger("notifications")


@dataclass
class DeliveryResult:
    """Result of a webhook delivery attempt."""

    url: str
    success: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    attempts: int = 1
    duration_ms: float = 0


class WebhookNotifier:
    """Delivers notifications to webhook endpoints.

    Features:
    - Parallel delivery to multiple endpoints
    - Retry with exponential backoff
    - Dead-letter queue for failed deliveries
    - Configurable timeouts and max retries
    """

    def __init__(
        self,
        urls: Optional[List[str]] = None,
        timeout: int = 10,
        max_retries: int = 3,
        max_workers: int = 5,
    ):
        settings = get_settings()
        self.urls = urls or settings.webhook_url_list
        self.timeout = timeout or settings.webhook_timeout_seconds
        self.max_retries = max_retries or settings.webhook_max_retries
        self.max_workers = max_workers
        self.session = httpx.Client()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "User-Agent": "RegEngine-Scheduler/1.0",
            }
        )
        self._dead_letter: List[Dict] = []

    def notify(self, items: List[EnforcementItem]) -> List[DeliveryResult]:
        """Send notifications to all configured webhooks.

        Args:
            items: List of enforcement items to notify about

        Returns:
            List of delivery results for each webhook
        """
        if not self.urls:
            logger.debug("no_webhooks_configured")
            return []

        if not items:
            logger.debug("no_items_to_notify")
            return []

        # Build payload
        payload = WebhookPayload(
            items=items,
            summary=self._build_summary(items),
        )

        # Deliver to all webhooks in parallel
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._deliver_with_retry, url, payload): url
                for url in self.urls
            }

            for future in as_completed(futures):
                url = futures[future]
                try:
                    result = future.result()
                    results.append(result)

                    if result.success:
                        logger.info(
                            "webhook_delivered",
                            url=url,
                            status=result.status_code,
                            duration_ms=result.duration_ms,
                        )
                    else:
                        logger.warning(
                            "webhook_failed",
                            url=url,
                            error=result.error,
                            attempts=result.attempts,
                        )
                        self._dead_letter.append(
                            {
                                "url": url,
                                "payload": payload.to_dict(),
                                "error": result.error,
                                "timestamp": time.time(),
                            }
                        )

                except Exception as e:
                    logger.error(
                        "webhook_exception",
                        url=url,
                        error=str(e),
                    )
                    results.append(
                        DeliveryResult(url=url, success=False, error=str(e))
                    )

        return results

    def _deliver_with_retry(
        self, url: str, payload: WebhookPayload
    ) -> DeliveryResult:
        """Deliver to a single webhook with retry logic."""
        last_error = None
        attempts = 0
        delay = 1  # Initial delay in seconds

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            start = time.time()

            try:
                response = self.session.post(
                    url,
                    json=payload.to_dict(),
                    timeout=self.timeout,
                )

                duration_ms = (time.time() - start) * 1000

                if response.status_code < 300:
                    return DeliveryResult(
                        url=url,
                        success=True,
                        status_code=response.status_code,
                        attempts=attempts,
                        duration_ms=duration_ms,
                    )

                # Non-2xx response
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"

                # Don't retry on client errors (4xx)
                if 400 <= response.status_code < 500:
                    return DeliveryResult(
                        url=url,
                        success=False,
                        status_code=response.status_code,
                        error=last_error,
                        attempts=attempts,
                        duration_ms=duration_ms,
                    )

            except httpx.TimeoutException:
                last_error = f"Timeout after {self.timeout}s"
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
            except Exception as e:
                last_error = str(e)

            # Exponential backoff before retry
            if attempt < self.max_retries:
                time.sleep(delay)
                delay *= 2

        return DeliveryResult(
            url=url,
            success=False,
            error=last_error,
            attempts=attempts,
        )

    def _build_summary(self, items: List[EnforcementItem]) -> str:
        """Build a human-readable summary of enforcement items."""
        if not items:
            return "No new enforcement items detected."

        # Group by severity
        by_severity = {}
        for item in items:
            sev = item.severity.value
            if sev not in by_severity:
                by_severity[sev] = []
            by_severity[sev].append(item)

        parts = [f"Detected {len(items)} enforcement item(s):"]

        for severity in ["critical", "high", "medium", "low"]:
            if severity in by_severity:
                count = len(by_severity[severity])
                parts.append(f"  - {count} {severity.upper()}")

        return " ".join(parts)

    def get_dead_letters(self) -> List[Dict]:
        """Get failed deliveries from dead-letter queue."""
        return self._dead_letter.copy()

    def clear_dead_letters(self) -> int:
        """Clear and return count of dead letters."""
        count = len(self._dead_letter)
        self._dead_letter.clear()
        return count

    def close(self) -> None:
        """Close the underlying HTTP client to release connections."""
        self.session.close()

    def retry_dead_letters(self) -> List[DeliveryResult]:
        """Retry all failed deliveries."""
        results = []
        dead_letters = self._dead_letter.copy()
        self._dead_letter.clear()

        for dl in dead_letters:
            # Reconstruct payload
            items = [
                EnforcementItem(**item_data)
                for item_data in dl["payload"].get("items", [])
            ]
            if items:
                result = self.notify(items)
                results.extend(result)

        return results
