"""Notification system for webhook delivery.

Delivers enforcement alerts to configured webhook endpoints with
retry logic and dead-letter handling.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, List, Optional, Tuple

import httpx
import structlog

from shared.url_validation import SSRFError, validate_url

from .config import get_settings
from .models import EnforcementItem, WebhookPayload
from .webhook_security import (
    CappedBody,
    WebhookURLBlocked,
    get_max_response_bytes,
    read_response_capped,
    validate_webhook_url,
)

logger = structlog.get_logger("notifications")


# ── #1150: webhook retry constants ───────────────────────────────────────────
# Before the fix, ``WebhookNotifier`` gave up after 3 attempts over ~3 seconds
# (1s + 2s backoff) and appended to an IN-MEMORY dead-letter list that was
# lost on restart. Customer webhook endpoints routinely have transient issues
# (cold starts, deploys, rate limits) that last longer than 3 seconds — so
# every such blip dropped a HIGH-severity alert permanently. Compliance
# customers can't miss recall alerts.
#
# Fix:
#   1. In-thread retry now honors ``Retry-After`` and uses a longer schedule
#      (1s, 5s, 30s) capped to ``max_retries``. Worker threads aren't
#      indefinitely blocked; after max_retries the delivery goes to the outbox.
#   2. Dead letters write through to an on-disk JSONL file so a scheduler
#      restart doesn't drop pending retries. Callers can point the file at
#      durable storage (a mounted volume) via ``outbox_path``.
#   3. Outbox retries follow a longer cadence (60s, 5m, 30m, 1h, 6h). A
#      caller-invoked ``retry_outbox_once()`` method walks the file,
#      attempts expired entries, and rewrites the outbox. Schedule this via
#      the existing BlockingScheduler on a 60s interval.
#   4. Per-URL failure counters (in-memory only; reset on success) so
#      operators see which endpoints are flaky.
_IN_THREAD_BACKOFF_SCHEDULE_SECONDS: Tuple[float, ...] = (1.0, 5.0, 30.0)
_OUTBOX_BACKOFF_SCHEDULE_SECONDS: Tuple[float, ...] = (
    60.0,       # 1 min
    5 * 60.0,   # 5 min
    30 * 60.0,  # 30 min
    60 * 60.0,  # 1h
    6 * 60 * 60.0,  # 6h
)
_MAX_OUTBOX_ATTEMPTS = len(_OUTBOX_BACKOFF_SCHEDULE_SECONDS)
# Per #1138 the Retry-After cap is 60s — keep the same cap here to prevent a
# misbehaving endpoint from stalling the worker thread.
_RETRY_AFTER_CAP_SECONDS = 60.0
# #1084: cap response body reads to prevent OOM from hostile endpoints
_RESPONSE_BODY_MAX_BYTES = 1024 * 1024  # 1 MB


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Parse an HTTP ``Retry-After`` header.

    Integer/float seconds are supported; HTTP-date is not (returns None
    and the computed backoff takes over). Negative values rejected.
    Capped at 60s to prevent a misbehaving server from stalling us.
    """
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except (ValueError, AttributeError):
        return None
    if seconds < 0:
        return None
    return min(seconds, _RETRY_AFTER_CAP_SECONDS)


@dataclass
class DeliveryResult:
    """Result of a webhook delivery attempt."""

    url: str
    success: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    attempts: int = 1
    duration_ms: float = 0


@dataclass
class OutboxEntry:
    """A dead-letter awaiting durable retry.

    Serialized one-per-line to the outbox JSONL file. Each field is a
    primitive so the entry can be round-tripped through json.dumps /
    json.loads without custom codecs.
    """

    url: str
    payload: Dict  # webhook payload, already serialized via WebhookPayload.to_dict()
    attempt_count: int = 0  # outbox-level attempts (separate from in-thread)
    first_attempted_at: float = field(default_factory=time.time)
    last_attempted_at: float = field(default_factory=time.time)
    next_retry_at: float = field(default_factory=time.time)
    last_error: Optional[str] = None
    last_status_code: Optional[int] = None

    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "payload": self.payload,
            "attempt_count": self.attempt_count,
            "first_attempted_at": self.first_attempted_at,
            "last_attempted_at": self.last_attempted_at,
            "next_retry_at": self.next_retry_at,
            "last_error": self.last_error,
            "last_status_code": self.last_status_code,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "OutboxEntry":
        return cls(
            url=data["url"],
            payload=data.get("payload", {}),
            attempt_count=int(data.get("attempt_count", 0)),
            first_attempted_at=float(data.get("first_attempted_at", time.time())),
            last_attempted_at=float(data.get("last_attempted_at", time.time())),
            next_retry_at=float(data.get("next_retry_at", time.time())),
            last_error=data.get("last_error"),
            last_status_code=data.get("last_status_code"),
        )


class WebhookNotifier:
    """Delivers notifications to webhook endpoints.

    Features:
    - Parallel delivery to multiple endpoints
    - Retry with exponential backoff, honoring Retry-After (#1150)
    - Persistent on-disk outbox survives restart (#1150)
    - Per-URL failure counter for observability (#1150)
    - Configurable timeouts and max retries
    """

    def __init__(
        self,
        urls: Optional[List[str]] = None,
        timeout: int = 10,
        max_retries: int = 3,
        max_workers: int = 5,
        outbox_path: Optional[str] = None,
    ):
        settings = get_settings()
        self.urls = urls or settings.webhook_url_list
        self.timeout = timeout or settings.webhook_timeout_seconds
        self.max_retries = max_retries or settings.webhook_max_retries
        self.max_workers = max_workers
        self.session = httpx.Client(timeout=30.0)
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "User-Agent": "RegEngine-Scheduler/1.0",
            }
        )
        # Legacy in-memory buffer retained for backward compatibility
        # with get_dead_letters() / clear_dead_letters() callers.
        self._dead_letter: List[Dict] = []
        # #1150: persistence
        self._outbox_path: Optional[Path] = Path(outbox_path) if outbox_path else None
        self._outbox_lock = Lock()
        # #1150: per-URL consecutive-failure counter. Operators tail
        # `webhook_failure_streak` logs to see which endpoints are flaky.
        self._failure_streak: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public delivery API
    # ------------------------------------------------------------------

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
                        self._record_success(url)
                        logger.info(
                            "webhook_delivered",
                            url=url,
                            status=result.status_code,
                            duration_ms=result.duration_ms,
                        )
                    else:
                        self._record_failure(url, result.error, result.status_code)
                        logger.warning(
                            "webhook_failed",
                            url=url,
                            error=result.error,
                            attempts=result.attempts,
                        )
                        self._enqueue_dead_letter(url, payload, result)

                except Exception as e:
                    self._record_failure(url, str(e), None)
                    logger.error(
                        "webhook_exception",
                        url=url,
                        error=str(e),
                    )
                    fallback_result = DeliveryResult(url=url, success=False, error=str(e))
                    results.append(fallback_result)
                    self._enqueue_dead_letter(url, payload, fallback_result)

        return results

    def _deliver_with_retry(
        self, url: str, payload: WebhookPayload
    ) -> DeliveryResult:
        """Deliver to a single webhook with retry logic.

        Honors ``Retry-After`` on 429/503 responses (#1150). Retries on
        5xx and network errors. Does NOT retry on 4xx (real client bug).

        #1084: enforce SSRF guard + response body cap.
          * The URL is validated ONCE before the retry loop starts —
            a blocked URL is a permanent configuration error, retrying
            wastes cycles and generates log noise.
          * The response body is read via ``client.stream`` with a
            configurable cap (``WEBHOOK_MAX_RESPONSE_BYTES``, default
            1 MiB) so a malicious endpoint can't OOM the scheduler by
            streaming gigabytes of response.
          * A split timeout (connect=5s, read=10s) prevents slow-drip
            attacks from holding a worker thread for the full timeout.
        """
        # #1084: SSRF guard — validate at delivery time to catch DNS rebinding
        try:
            validate_url(url)
        except SSRFError as exc:
            logger.warning("webhook_ssrf_blocked", url=url, reason=str(exc))
            return DeliveryResult(
                url=url,
                success=False,
                error=f"SSRF blocked: {exc}",
                attempts=0,
            )

        last_error: Optional[str] = None
        last_status: Optional[int] = None
        attempts = 0
        payload_dict = payload.to_dict()

        # ── #1084: SSRF guard ───────────────────────────────────────
        # Validate the URL scheme + resolved host before any network
        # call. A blocked URL is a permanent configuration error —
        # don't retry, don't count attempts, just fail-fast.
        try:
            validate_webhook_url(url)
        except WebhookURLBlocked as blocked:
            logger.error(
                "webhook_delivery_blocked_ssrf",
                url=url,
                reason=str(blocked),
            )
            return DeliveryResult(
                url=url,
                success=False,
                status_code=None,
                error=f"SSRF blocked: {blocked}",
                attempts=0,
                duration_ms=0.0,
            )

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            start = time.time()
            retry_after_seconds: Optional[float] = None

            try:
                status_code, body, headers = self._post_with_body_cap(
                    url, payload_dict
                )

                duration_ms = (time.time() - start) * 1000
                last_status = status_code

                if status_code < 300:
                    return DeliveryResult(
                        url=url,
                        success=True,
                        status_code=status_code,
                        attempts=attempts,
                        duration_ms=duration_ms,
                    )

                # Non-2xx response. ``body`` is already capped — safe to log.
                last_error = f"HTTP {status_code}: {body.as_text_preview(200)}"

                # Don't retry on client errors (4xx) — except 429 which is
                # a transient rate-limit and should be retried with
                # Retry-After.
                if 400 <= status_code < 500 and status_code != 429:
                    return DeliveryResult(
                        url=url,
                        success=False,
                        status_code=status_code,
                        error=last_error,
                        attempts=attempts,
                        duration_ms=duration_ms,
                    )

                # 429 or 5xx — honor Retry-After if present.
                retry_after_seconds = _parse_retry_after(
                    headers.get("Retry-After") if headers else None
                )

            except httpx.TimeoutException:
                last_error = f"Timeout after {self.timeout}s"
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
            except Exception as e:
                last_error = str(e)

            # Exponential backoff before retry — honor Retry-After if the
            # server asked for a specific delay.
            if attempt < self.max_retries:
                schedule_idx = min(attempt - 1, len(_IN_THREAD_BACKOFF_SCHEDULE_SECONDS) - 1)
                computed_delay = _IN_THREAD_BACKOFF_SCHEDULE_SECONDS[schedule_idx]
                delay = max(retry_after_seconds or 0.0, computed_delay)
                logger.debug(
                    "webhook_retry_sleep",
                    url=url,
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    delay_seconds=round(delay, 2),
                    retry_after_header=retry_after_seconds,
                )
                time.sleep(delay)

        return DeliveryResult(
            url=url,
            success=False,
            status_code=last_status,
            error=last_error,
            attempts=attempts,
        )

    def _post_with_body_cap(
        self,
        url: str,
        payload_dict: Dict,
    ) -> tuple:
        """POST ``payload_dict`` as JSON and read the response body with
        a byte cap (#1084).

        Returns ``(status_code, CappedBody, headers_dict)``. Headers
        are returned as a plain dict so callers can read ``Retry-After``
        without depending on the httpx-specific mapping type.

        Uses ``httpx.Client.stream`` so the response body is read
        incrementally. If the remote sends more than
        ``WEBHOOK_MAX_RESPONSE_BYTES``, iteration stops early and the
        connection is closed — the scheduler cannot be OOM'd by a
        malicious endpoint.

        #1084: split timeout (connect=5s, read=10s) prevents slow-drip
        attacks from holding a worker thread for the full wall-clock
        timeout.
        """
        cap = get_max_response_bytes()
        # Split timeout: 5s to establish the TCP connection, 10s to
        # read the response. A single scalar would allow an attacker to
        # trickle bytes for the full timeout value.
        split_timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        # httpx.Client.stream is a context manager that hands back a
        # Response with ``iter_bytes`` / ``iter_raw`` available but
        # ``.content`` / ``.text`` NOT populated (calling them would
        # drain the stream). We rely on that to enforce the cap.
        with self.session.stream(
            "POST",
            url,
            json=payload_dict,
            timeout=split_timeout,
        ) as response:
            body = read_response_capped(response, limit=cap)
            # Copy the headers into a plain dict while the response
            # is still open — once we leave the ``with`` block the
            # connection returns to the pool.
            headers = dict(response.headers) if response.headers else {}
            status_code = response.status_code
        return status_code, body, headers

    # ------------------------------------------------------------------
    # Dead-letter / outbox API
    # ------------------------------------------------------------------

    def _enqueue_dead_letter(
        self,
        url: str,
        payload: WebhookPayload,
        result: DeliveryResult,
    ) -> None:
        """Append a failed delivery to the in-memory list AND (if
        configured) persist to the on-disk outbox.

        #1150: the legacy behavior kept a list that died with the process.
        Writing through to disk means an orchestrator-initiated restart
        doesn't silently drop in-flight retries.
        """
        entry_dict = {
            "url": url,
            "payload": payload.to_dict(),
            "error": result.error,
            "timestamp": time.time(),
        }
        self._dead_letter.append(entry_dict)

        # Also persist to disk for crash safety.
        if self._outbox_path is not None:
            now = time.time()
            entry = OutboxEntry(
                url=url,
                payload=payload.to_dict(),
                attempt_count=0,
                first_attempted_at=now,
                last_attempted_at=now,
                next_retry_at=now + _OUTBOX_BACKOFF_SCHEDULE_SECONDS[0],
                last_error=result.error,
                last_status_code=result.status_code,
            )
            self._append_outbox_entry(entry)

    def _append_outbox_entry(self, entry: OutboxEntry) -> None:
        """Append one JSONL record. Fail-open: a disk error must not
        cascade into an exception that aborts the scrape cycle."""
        assert self._outbox_path is not None  # caller checked
        try:
            self._outbox_path.parent.mkdir(parents=True, exist_ok=True)
            with self._outbox_lock:
                with open(self._outbox_path, "a", encoding="utf-8") as fp:
                    fp.write(json.dumps(entry.to_dict(), default=str))
                    fp.write("\n")
        except OSError as disk_err:
            logger.error(
                "webhook_outbox_append_failed",
                path=str(self._outbox_path),
                error=str(disk_err),
            )

    def _read_outbox(self) -> List[OutboxEntry]:
        """Load all entries from the outbox file. Tolerates corrupt
        lines (logs + skips)."""
        if self._outbox_path is None or not self._outbox_path.exists():
            return []
        entries: List[OutboxEntry] = []
        with self._outbox_lock:
            try:
                with open(self._outbox_path, "r", encoding="utf-8") as fp:
                    for line_no, raw in enumerate(fp, start=1):
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            entries.append(OutboxEntry.from_dict(json.loads(raw)))
                        except (json.JSONDecodeError, KeyError, ValueError) as parse_err:
                            logger.warning(
                                "webhook_outbox_corrupt_line_skipped",
                                path=str(self._outbox_path),
                                line=line_no,
                                error=str(parse_err),
                            )
            except OSError as disk_err:
                logger.error(
                    "webhook_outbox_read_failed",
                    path=str(self._outbox_path),
                    error=str(disk_err),
                )
        return entries

    def _write_outbox(self, entries: List[OutboxEntry]) -> None:
        """Rewrite the outbox file atomically (write tmp then rename)."""
        assert self._outbox_path is not None
        try:
            self._outbox_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._outbox_path.with_suffix(self._outbox_path.suffix + ".tmp")
            with self._outbox_lock:
                with open(tmp_path, "w", encoding="utf-8") as fp:
                    for entry in entries:
                        fp.write(json.dumps(entry.to_dict(), default=str))
                        fp.write("\n")
                os.replace(tmp_path, self._outbox_path)
        except OSError as disk_err:
            logger.error(
                "webhook_outbox_write_failed",
                path=str(self._outbox_path),
                error=str(disk_err),
            )

    def retry_outbox_once(self) -> Dict[str, int]:
        """Walk the outbox once: attempt delivery for every entry whose
        ``next_retry_at`` has passed. Rewrite the outbox with the
        surviving (still-pending or exhausted) entries.

        Returns a counter dict with:
          - ``attempted``: entries whose retry was attempted
          - ``delivered``: attempted AND succeeded
          - ``rescheduled``: failed but have attempts remaining
          - ``exhausted``: failed with max attempts used up (stays in
            outbox with ``next_retry_at`` set far in the future so
            operators can investigate manually)

        #1150: intended to be invoked periodically by the scheduler (e.g.
        every 60s). This is deliberately single-pass — a long-lived retry
        daemon would require additional synchronization.
        """
        counter = {"attempted": 0, "delivered": 0, "rescheduled": 0, "exhausted": 0}
        if self._outbox_path is None:
            return counter

        entries = self._read_outbox()
        if not entries:
            return counter

        now = time.time()
        remaining: List[OutboxEntry] = []

        for entry in entries:
            if entry.next_retry_at > now:
                # Not due yet — keep as-is.
                remaining.append(entry)
                continue

            if entry.attempt_count >= _MAX_OUTBOX_ATTEMPTS:
                # Already exhausted on a prior pass; keep for operator
                # inspection but bump next_retry_at far into the future
                # so we don't hot-loop.
                entry.next_retry_at = now + 30 * 24 * 60 * 60  # 30 days
                remaining.append(entry)
                counter["exhausted"] += 1
                continue

            counter["attempted"] += 1
            delivered = self._retry_one_entry(entry)
            if delivered:
                counter["delivered"] += 1
                # Entry leaves the outbox.
                continue

            # Still failing — reschedule.
            entry.attempt_count += 1
            entry.last_attempted_at = time.time()
            if entry.attempt_count >= _MAX_OUTBOX_ATTEMPTS:
                counter["exhausted"] += 1
                entry.next_retry_at = time.time() + 30 * 24 * 60 * 60
                logger.error(
                    "webhook_outbox_entry_exhausted",
                    url=entry.url,
                    attempt_count=entry.attempt_count,
                    last_error=entry.last_error,
                    last_status_code=entry.last_status_code,
                )
            else:
                counter["rescheduled"] += 1
                delay = _OUTBOX_BACKOFF_SCHEDULE_SECONDS[
                    min(entry.attempt_count, len(_OUTBOX_BACKOFF_SCHEDULE_SECONDS) - 1)
                ]
                entry.next_retry_at = time.time() + delay
                logger.info(
                    "webhook_outbox_entry_rescheduled",
                    url=entry.url,
                    attempt_count=entry.attempt_count,
                    next_retry_in_seconds=delay,
                )
            remaining.append(entry)

        self._write_outbox(remaining)

        if counter["attempted"]:
            logger.info(
                "webhook_outbox_drain",
                **counter,
                outbox_size=len(remaining),
            )
        return counter

    def _retry_one_entry(self, entry: OutboxEntry) -> bool:
        """Attempt delivery for a single outbox entry. Returns True on
        success (2xx), False otherwise. Updates ``entry`` fields
        (last_error / last_status_code) in-place regardless of outcome.

        #1084: enforces the same SSRF guard + body cap as the primary
        delivery path. A URL that was OK when enqueued but later maps
        to a private IP (DNS change) is now blocked on retry too.
        """
        # SSRF re-check on every retry: DNS could have changed.
        try:
            validate_webhook_url(entry.url)
        except WebhookURLBlocked as blocked:
            entry.last_error = f"SSRF blocked: {blocked}"
            entry.last_status_code = None
            self._record_failure(entry.url, entry.last_error, None)
            return False

        try:
            status_code, body, _headers = self._post_with_body_cap(
                entry.url, entry.payload
            )
        except httpx.TimeoutException:
            entry.last_error = f"Timeout after {self.timeout}s"
            entry.last_status_code = None
            return False
        except httpx.ConnectError as err:
            entry.last_error = f"Connection error: {err}"
            entry.last_status_code = None
            return False
        except Exception as err:  # noqa: BLE001
            entry.last_error = str(err)
            entry.last_status_code = None
            return False

        entry.last_status_code = status_code
        if status_code < 300:
            self._record_success(entry.url)
            return True
        entry.last_error = f"HTTP {status_code}: {body.as_text_preview(200)}"
        self._record_failure(entry.url, entry.last_error, status_code)
        return False

    # ------------------------------------------------------------------
    # Legacy in-memory dead-letter API (retained)
    # ------------------------------------------------------------------

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
        """Retry all failed deliveries (in-memory list only — use
        ``retry_outbox_once`` for durable retry via the persistent
        outbox)."""
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

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def _record_failure(
        self,
        url: str,
        error: Optional[str],
        status_code: Optional[int],
    ) -> None:
        """Bump per-URL failure streak and log."""
        streak = self._failure_streak.get(url, 0) + 1
        self._failure_streak[url] = streak
        logger.warning(
            "webhook_failure_streak",
            url=url,
            streak=streak,
            error=error,
            status_code=status_code,
        )

    def _record_success(self, url: str) -> None:
        """Reset streak counter."""
        if url in self._failure_streak and self._failure_streak[url] > 0:
            logger.info(
                "webhook_failure_streak_recovered",
                url=url,
                prior_streak=self._failure_streak[url],
            )
        self._failure_streak[url] = 0

    def get_failure_streaks(self) -> Dict[str, int]:
        """Return a copy of the per-URL consecutive-failure counts."""
        return dict(self._failure_streak)

    # ------------------------------------------------------------------
    # Summary (unchanged)
    # ------------------------------------------------------------------

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
