"""Notification system for webhook delivery.

Delivers enforcement alerts to configured webhook endpoints with
retry logic and dead-letter handling.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
import structlog

from .config import get_settings
from .models import EnforcementItem, WebhookPayload

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


# ── #1084: SSRF guard ────────────────────────────────────────────────────────
# Private / loopback / link-local networks that webhook targets must never
# resolve to. Bypassed when WEBHOOK_ALLOW_PRIVATE=true (dev only).
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # loopback IPv4
    ipaddress.ip_network("10.0.0.0/8"),        # RFC-1918
    ipaddress.ip_network("172.16.0.0/12"),     # RFC-1918
    ipaddress.ip_network("192.168.0.0/16"),    # RFC-1918
    ipaddress.ip_network("169.254.0.0/16"),    # link-local (IMDS)
    ipaddress.ip_network("::1/128"),           # loopback IPv6
    ipaddress.ip_network("fc00::/7"),          # unique local IPv6
    ipaddress.ip_network("fe80::/10"),         # link-local IPv6
]

# Default response-body cap (1 MB). Override with WEBHOOK_MAX_RESPONSE_BYTES.
_DEFAULT_MAX_RESPONSE_BYTES: int = 1 * 1024 * 1024  # 1 MB


def _get_max_response_bytes() -> int:
    try:
        return int(os.environ.get("WEBHOOK_MAX_RESPONSE_BYTES", _DEFAULT_MAX_RESPONSE_BYTES))
    except (ValueError, TypeError):
        return _DEFAULT_MAX_RESPONSE_BYTES


def _check_ssrf(url: str) -> None:
    """Raise ``ValueError`` if *url* targets a private/loopback/link-local host.

    Checks:
    - Scheme must be ``https`` unless env ``WEBHOOK_ALLOW_HTTP=true``.
    - Resolves the hostname via ``socket.getaddrinfo`` and rejects any address
      in a blocked network range.

    Bypassed entirely when ``WEBHOOK_ALLOW_PRIVATE=true`` (dev/test only).
    """
    if os.environ.get("WEBHOOK_ALLOW_PRIVATE", "").lower() == "true":
        return

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    allow_http = os.environ.get("WEBHOOK_ALLOW_HTTP", "").lower() == "true"

    if scheme not in ("https", "http") or (scheme == "http" and not allow_http):
        raise ValueError(
            f"Webhook URL scheme '{scheme}' is not allowed. "
            "Use https (or set WEBHOOK_ALLOW_HTTP=true for http)."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Webhook URL has no resolvable hostname: {url!r}")

    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve webhook hostname '{hostname}': {exc}") from exc

    for _family, _type, _proto, _canon, sockaddr in results:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                raise ValueError(
                    f"Webhook URL '{url}' resolves to private/loopback address "
                    f"{ip_str} ({net}) — SSRF blocked (#1084)."
                )


def _read_capped_body(response: httpx.Response, max_bytes: int) -> str:
    """Read up to *max_bytes* from *response* content and return as text.

    httpx buffers the full body by default when not using streaming; this
    helper truncates at the cap so a huge response body can't cause OOM.
    """
    raw: bytes = response.content[:max_bytes]
    return raw.decode("utf-8", errors="replace")


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
        """
        # #1084: SSRF guard — reject private/loopback targets before any I/O.
        try:
            _check_ssrf(url)
        except ValueError as ssrf_err:
            logger.error("webhook_ssrf_blocked", url=url, reason=str(ssrf_err))
            return DeliveryResult(url=url, success=False, error=str(ssrf_err), attempts=0)

        last_error: Optional[str] = None
        last_status: Optional[int] = None
        attempts = 0
        payload_dict = payload.to_dict()
        _max_body = _get_max_response_bytes()

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            start = time.time()
            retry_after_seconds: Optional[float] = None

            try:
                response = self.session.post(
                    url,
                    json=payload_dict,
                    timeout=self.timeout,
                )

                duration_ms = (time.time() - start) * 1000
                last_status = response.status_code

                if response.status_code < 300:
                    return DeliveryResult(
                        url=url,
                        success=True,
                        status_code=response.status_code,
                        attempts=attempts,
                        duration_ms=duration_ms,
                    )

                # Non-2xx response. Cap body read to avoid OOM (#1084).
                last_error = f"HTTP {response.status_code}: {_read_capped_body(response, _max_body)[:200]}"

                # Don't retry on client errors (4xx) — except 429 which is
                # a transient rate-limit and should be retried with
                # Retry-After.
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    return DeliveryResult(
                        url=url,
                        success=False,
                        status_code=response.status_code,
                        error=last_error,
                        attempts=attempts,
                        duration_ms=duration_ms,
                    )

                # 429 or 5xx — honor Retry-After if present.
                retry_after_seconds = _parse_retry_after(
                    response.headers.get("Retry-After") if hasattr(response, "headers") else None
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
        """
        # #1084: SSRF guard on outbox retries too.
        try:
            _check_ssrf(entry.url)
        except ValueError as ssrf_err:
            entry.last_error = str(ssrf_err)
            entry.last_status_code = None
            logger.error("webhook_outbox_ssrf_blocked", url=entry.url, reason=str(ssrf_err))
            return False

        try:
            response = self.session.post(
                entry.url,
                json=entry.payload,
                timeout=self.timeout,
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

        _max_body = _get_max_response_bytes()
        entry.last_status_code = response.status_code
        if response.status_code < 300:
            self._record_success(entry.url)
            return True
        entry.last_error = f"HTTP {response.status_code}: {_read_capped_body(response, _max_body)[:200]}"
        self._record_failure(entry.url, entry.last_error, response.status_code)
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
