"""
LIFE-05: Shared resilient HTTP client for inter-service communication.

Wraps ``httpx.AsyncClient`` with automatic retry on transient failures
(5xx, connection errors) using exponential backoff, plus per-service
circuit breaker protection to fail fast when downstream is unhealthy.

Usage::

    from shared.resilient_http import resilient_client

    async with resilient_client() as client:
        resp = await client.get("https://other-service/api/data")

    # Named circuit breaker for a specific downstream service:
    async with resilient_client(circuit_name="graph-service") as client:
        resp = await client.get("http://graph-service:8200/v1/...")
"""

from __future__ import annotations

import asyncio
import logging
import random
from contextlib import asynccontextmanager
from typing import Optional

import httpx

from shared.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)

# Per-service circuit breaker registry (lazily populated)
_http_circuits: dict[str, CircuitBreaker] = {}


def get_http_circuit(name: str) -> CircuitBreaker:
    """Get or create a circuit breaker for a named HTTP downstream service."""
    if name not in _http_circuits:
        _http_circuits[name] = CircuitBreaker(
            name=f"http_{name}",
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_max_calls=3,
            exceptions=(httpx.ConnectError, httpx.ConnectTimeout),
        )
    return _http_circuits[name]

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
    circuit_name: Optional[str] = None,
    **kwargs,
):
    """Context manager yielding an ``httpx.AsyncClient`` with retry transport.

    Parameters
    ----------
    timeout:
        Per-request timeout in seconds.
    retries:
        Max retry attempts on transient failures.
    circuit_name:
        Optional name for a per-service circuit breaker. When provided,
        the client will fail fast with ``CircuitOpenError`` if the
        downstream service has been unhealthy (5 consecutive failures
        within 30s). Omit for fire-and-forget calls that don't need
        circuit protection.
    **kwargs:
        Extra keyword args forwarded to ``httpx.AsyncClient``.
    """
    if circuit_name:
        circuit = get_http_circuit(circuit_name)
        circuit._check_state()  # Fail fast before creating transport

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
        if circuit_name:
            circuit = get_http_circuit(circuit_name)
            original_send = client.send

            async def _tracked_send(request, **send_kwargs):
                try:
                    response = await original_send(request, **send_kwargs)
                    if response.status_code < 500:
                        circuit._record_success()
                    else:
                        circuit._record_failure(
                            httpx.HTTPStatusError(
                                f"{response.status_code}",
                                request=request,
                                response=response,
                            )
                        )
                    return response
                except Exception as exc:
                    circuit._record_failure(exc)
                    raise

            client.send = _tracked_send  # type: ignore[assignment]

        yield client
