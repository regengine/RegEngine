"""Batch injection runner — sends datasets through the full pipeline.

Supports configurable concurrency via ``asyncio.Semaphore`` and
token-bucket rate limiting to avoid overwhelming the target API.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from recall_drill.failure_engine.mutator import MutationResult, Mutator
from recall_drill.injection.api_runner import APIRunner, InjectionResult

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Aggregate result for an entire batch injection."""

    mutation_metadata: dict
    injection_results: list[InjectionResult]
    total_records: int
    success_count: int
    failure_count: int
    avg_latency_ms: float
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "mutation": self.mutation_metadata,
            "total_records": self.total_records,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_latency_ms": self.avg_latency_ms,
            "elapsed_ms": self.elapsed_ms,
        }


class _TokenBucket:
    """Simple async token-bucket rate limiter.

    Parameters
    ----------
    rate:
        Maximum requests per second.
    burst:
        Maximum burst size (tokens available immediately).
    """

    def __init__(self, rate: float, burst: int | None = None):
        self._rate = rate
        self._burst = burst or max(1, int(rate))
        self._tokens = float(self._burst)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(
                self._burst, self._tokens + elapsed * self._rate
            )
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


class BatchRunner:
    """Orchestrate mutation + injection for an entire dataset.

    Parameters
    ----------
    api_runner:
        The ``APIRunner`` instance used to send records.
    mutator:
        The ``Mutator`` instance for applying failure mutations.
    max_concurrency:
        Maximum number of concurrent HTTP requests.
    rate_limit:
        Maximum requests per second (0 = unlimited).
    """

    def __init__(
        self,
        api_runner: APIRunner,
        mutator: Mutator,
        max_concurrency: int = 10,
        rate_limit: float = 0.0,
    ):
        self._api = api_runner
        self._mutator = mutator
        self._max_concurrency = max_concurrency
        self._rate_limit = rate_limit

    async def _inject_with_controls(
        self,
        record: dict,
        mutation_id: str | None,
        semaphore: asyncio.Semaphore,
        bucket: _TokenBucket | None,
    ) -> InjectionResult:
        """Inject a single record respecting concurrency and rate limits."""
        if bucket:
            await bucket.acquire()
        async with semaphore:
            return await self._api.inject_record(record, mutation_id=mutation_id)

    async def run_mutation_scenario(
        self,
        clean_data: list[dict],
        mutation_fn: str,
        **mutation_kwargs: Any,
    ) -> BatchResult:
        """Apply a named mutation, inject results, return structured output."""
        start = time.perf_counter()

        fn = getattr(self._mutator, mutation_fn)
        mutation_result: MutationResult = fn(clean_data, **mutation_kwargs)

        mutated = mutation_result.data
        mutation_id = mutation_result.metadata["mutation_id"]

        if isinstance(mutated, list):
            results = await self._inject_concurrent(mutated, mutation_id)
        else:
            results = [
                await self._api.inject_record(
                    {"raw": mutated}, mutation_id=mutation_id
                )
            ]

        elapsed = (time.perf_counter() - start) * 1000
        successes = [r for r in results if r.success]
        latencies = [r.latency_ms for r in results]

        return BatchResult(
            mutation_metadata=mutation_result.metadata,
            injection_results=results,
            total_records=len(results),
            success_count=len(successes),
            failure_count=len(results) - len(successes),
            avg_latency_ms=round(sum(latencies) / max(len(latencies), 1), 2),
            elapsed_ms=round(elapsed, 2),
        )

    async def inject_batch(
        self,
        records: list[dict],
        mutation_id: str | None = None,
    ) -> BatchResult:
        """Inject a batch of records with concurrency and rate limiting."""
        start = time.perf_counter()
        results = await self._inject_concurrent(records, mutation_id)
        elapsed = (time.perf_counter() - start) * 1000

        successes = [r for r in results if r.success]
        latencies = [r.latency_ms for r in results]

        return BatchResult(
            mutation_metadata={"mutation_id": mutation_id},
            injection_results=results,
            total_records=len(results),
            success_count=len(successes),
            failure_count=len(results) - len(successes),
            avg_latency_ms=round(sum(latencies) / max(len(latencies), 1), 2),
            elapsed_ms=round(elapsed, 2),
        )

    async def _inject_concurrent(
        self, records: list[dict], mutation_id: str | None
    ) -> list[InjectionResult]:
        """Send records concurrently, respecting limits."""
        semaphore = asyncio.Semaphore(self._max_concurrency)
        bucket = (
            _TokenBucket(self._rate_limit)
            if self._rate_limit > 0
            else None
        )

        tasks = [
            self._inject_with_controls(rec, mutation_id, semaphore, bucket)
            for rec in records
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final: list[InjectionResult] = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("Injection task failed: %s", r)
                final.append(
                    InjectionResult(
                        trace_id="error",
                        mutation_id=mutation_id,
                        endpoint="unknown",
                        status_code=0,
                        latency_ms=0.0,
                        response_body={},
                        success=False,
                        error=str(r),
                    )
                )
            else:
                final.append(r)
        return final
