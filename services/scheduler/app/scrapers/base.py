"""Base scraper interface."""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, List, Mapping, Optional

import httpx
import structlog

from ..models import EnforcementItem, ScrapeResult, SourceType

logger = structlog.get_logger("scraper.base")


# ── #1138: FDA HTTP retry / backoff ─────────────────────────────────────────
# All three FDA scrapers were issuing a single ``session.get(...)`` with no
# retry. A transient 502/503 from openFDA or a 1-second TCP blip aborted the
# entire scrape, and the next attempt didn't happen until the next interval
# (often 30+ minutes later). For Class I recalls that's a real safety delay.
#
# We retry on:
#   - 5xx HTTP responses (but NOT 4xx — those indicate a real bug)
#   - ``httpx.TimeoutException`` (subclasses: Connect/Read/Pool timeouts)
#   - ``httpx.TransportError`` (connection reset, DNS failure, etc.)
#
# Wait schedule: exponential backoff with full jitter (AWS recommendation —
# keeps a herd of concurrent clients from synchronizing their retries).
# If the server sends a ``Retry-After`` header we honor it: ``max(header,
# computed_wait)`` — we never sleep LESS than what the server asked for.

_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_BASE_DELAY_SECONDS = 1.0
_DEFAULT_MAX_DELAY_SECONDS = 10.0
_DEFAULT_RETRY_AFTER_CAP_SECONDS = 60.0


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Parse an HTTP ``Retry-After`` header.

    Returns the delay in seconds, or ``None`` if the header is missing or
    unparseable. Per RFC 7231 the value can be either:
      - a non-negative integer number of seconds, or
      - an HTTP-date (absolute timestamp)

    We support the integer form (the common case for APIs) and silently
    fall back to ``None`` on HTTP-date values — they're rare for API
    endpoints and the computed backoff will kick in instead.
    """
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except (ValueError, AttributeError):
        return None
    if seconds < 0:
        return None
    return min(seconds, _DEFAULT_RETRY_AFTER_CAP_SECONDS)


def _compute_backoff(attempt: int, *, base: float, max_delay: float) -> float:
    """Full-jitter exponential backoff.

    attempt is 1-indexed (first retry → attempt=1). Each attempt doubles
    the cap, and we sample uniformly in [0, cap]. Capped at ``max_delay``.
    """
    cap = min(max_delay, base * (2 ** (attempt - 1)))
    return random.uniform(0.0, cap)


def fetch_with_retry(
    session: httpx.Client,
    url: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    timeout: Optional[float] = None,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    base_delay_seconds: float = _DEFAULT_BASE_DELAY_SECONDS,
    max_delay_seconds: float = _DEFAULT_MAX_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    allow_404_passthrough: bool = True,
    log_scope: str = "fda_http",
) -> httpx.Response:
    """GET ``url`` with retry on 5xx / transport errors, honoring Retry-After.

    On 2xx or 3xx: returns immediately.
    On 4xx: returns the response (caller decides — 404 is often benign).
    On 5xx or transport error: sleep with full-jitter exponential backoff
      (or ``Retry-After``, whichever is longer) and retry up to
      ``max_attempts`` total attempts. The final failure re-raises — either
      ``httpx.HTTPStatusError`` (by calling ``raise_for_status`` on the last
      5xx response) or the underlying transport exception.

    Parameters
    ----------
    allow_404_passthrough
        Historical behavior: some scrapers (e.g. warning letters RSS feed)
        need to see 404 responses to fall back to an alternate source. When
        True, we return 4xx responses directly so the caller can branch on
        ``response.status_code`` without having to catch
        ``HTTPStatusError``.
    log_scope
        Structlog context label for retry telemetry.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    last_exc: Optional[BaseException] = None
    last_response: Optional[httpx.Response] = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            last_response = None
            if attempt == max_attempts:
                logger.error(
                    f"{log_scope}_exhausted_retries",
                    url=url,
                    attempt=attempt,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise
            delay = _compute_backoff(
                attempt, base=base_delay_seconds, max_delay=max_delay_seconds,
            )
            logger.warning(
                f"{log_scope}_transport_error_retry",
                url=url,
                attempt=attempt,
                next_attempt=attempt + 1,
                delay_seconds=round(delay, 2),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            sleep(delay)
            continue

        # Success or caller-visible 4xx.
        if response.status_code < 500:
            if allow_404_passthrough or response.status_code < 400:
                return response
            # Non-404 4xx and caller doesn't want passthrough — raise.
            response.raise_for_status()
            return response

        # 5xx path: retry unless exhausted.
        last_response = response
        last_exc = None
        if attempt == max_attempts:
            logger.error(
                f"{log_scope}_exhausted_retries",
                url=url,
                attempt=attempt,
                status_code=response.status_code,
            )
            response.raise_for_status()  # always raises for 5xx
            return response  # pragma: no cover (raise_for_status raised)

        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        computed_delay = _compute_backoff(
            attempt, base=base_delay_seconds, max_delay=max_delay_seconds,
        )
        delay = max(retry_after or 0.0, computed_delay)
        logger.warning(
            f"{log_scope}_5xx_retry",
            url=url,
            attempt=attempt,
            next_attempt=attempt + 1,
            status_code=response.status_code,
            retry_after_header=retry_after,
            delay_seconds=round(delay, 2),
        )
        sleep(delay)

    # Unreachable — the loop always either returns or raises.
    if last_response is not None:  # pragma: no cover
        last_response.raise_for_status()
        return last_response
    assert last_exc is not None  # pragma: no cover
    raise last_exc  # pragma: no cover


class BaseScraper(ABC):
    """Abstract base class for regulatory scrapers.

    All scrapers must implement:
    - source_type: The type of source being scraped
    - scrape(): Fetches and parses items from the source
    """

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """Return the source type for this scraper."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this scraper."""
        pass

    @abstractmethod
    def scrape(self) -> ScrapeResult:
        """Execute the scrape operation.

        Returns:
            ScrapeResult containing found items and metadata
        """
        pass

    def _create_source_id(self, *parts: str) -> str:
        """Create a stable source ID from parts."""
        return ":".join(str(p) for p in parts)
