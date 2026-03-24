"""
LIFE-05: Shared resilient HTTP client for inter-service communication.

Wraps ``httpx.AsyncClient`` with automatic retry on transient failures
(5xx, connection errors) using exponential backoff.

Usage::

    from shared.resilient_http import resilient_client

    async with resilient_client() as client:
        resp = await client.get("https://other-service/api/data")
"""

from __future__ import annotations

import asyncio
import logging
import random
from contextlib import asynccontextmanager
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {502, 503, 504}
_DEFAULT_RETRIES = 3
_DEFAULT_BACKOFF_BASE = 0.5  # seconds
_DEFAULT_BACKOFF_MAX = 8.0   # seconds


class RetryTransport(httpx.AsyncBaseTransport):
    """Async transport that retries on transient failures with exponential backoff."""

    def __init__(
        self,
        wrapped: httpx.AsyncHTTPTransport,
        retries: int = _DEFAULT_RETRIES,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
        backoff_max: float = _DEFAULT_BACKOFF_MAX,
    ):
        self._wrapped = wrapped
        self._retries = retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self._retries + 1):
            try:
                response = await self._wrapped.handle_async_request(request)
                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < self._retries:
                    delay = self._delay(attempt)
                    logger.warning(
                        "http_retry",
                        url=str(request.url),
                        status=response.status_code,
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                return response
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_exc = exc
                if attempt < self._retries:
                    delay = self._delay(attempt)
                    logger.warning(
                        "http_retry_connection",
                        url=str(request.url),
                        error=str(exc),
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

        # Should not reach here, but satisfy type checker
        if last_exc:
            raise last_exc
        raise httpx.ConnectError("Retries exhausted")  # pragma: no cover

    def _delay(self, attempt: int) -> float:
        """Exponential backoff with 20% jitter."""
        base = min(self._backoff_base * (2 ** attempt), self._backoff_max)
        jitter = base * 0.2 * random.random()
        return base + jitter

    async def aclose(self) -> None:
        await self._wrapped.aclose()


@asynccontextmanager
async def resilient_client(
    timeout: float = 30.0,
    retries: int = _DEFAULT_RETRIES,
    **kwargs,
):
    """Context manager yielding an ``httpx.AsyncClient`` with retry transport.

    Parameters
    ----------
    timeout:
        Per-request timeout in seconds.
    retries:
        Max retry attempts on transient failures.
    **kwargs:
        Extra keyword args forwarded to ``httpx.AsyncClient``.
    """
    transport = RetryTransport(
        wrapped=httpx.AsyncHTTPTransport(http2=True),
        retries=retries,
    )
    async with httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=True,
        **kwargs,
    ) as client:
        yield client
