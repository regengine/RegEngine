"""Inject mutated data into RegEngine FastAPI endpoints."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx


@dataclass
class InjectionResult:
    trace_id: str
    mutation_id: str | None
    endpoint: str
    status_code: int
    latency_ms: float
    response_body: dict
    success: bool
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class APIRunner:
    """Send mutated CTE data to RegEngine ingestion endpoints."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str = "",
        timeout: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self, trace_id: str, mutation_id: str | None = None) -> dict:
        h = {
            "X-RegEngine-API-Key": self._api_key,
            "X-Request-ID": trace_id,
            "Content-Type": "application/json",
        }
        if mutation_id:
            h["X-Mutation-ID"] = mutation_id
        return h

    async def inject_record(
        self,
        record: dict,
        mutation_id: str | None = None,
        endpoint: str = "/v1/ingest",
    ) -> InjectionResult:
        """Send a single CTE record to the ingestion API."""
        trace_id = str(uuid.uuid4())
        url = f"{self._base_url}{endpoint}"

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url,
                    json={
                        "text": str(record),
                        "source_system": "recall_drill",
                        "source_url": f"drill://{trace_id}",
                    },
                    headers=self._headers(trace_id, mutation_id),
                )
            latency = (time.perf_counter() - start) * 1000
            return InjectionResult(
                trace_id=trace_id,
                mutation_id=mutation_id,
                endpoint=endpoint,
                status_code=resp.status_code,
                latency_ms=round(latency, 2),
                response_body=resp.json() if resp.status_code < 500 else {},
                success=200 <= resp.status_code < 300,
            )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            return InjectionResult(
                trace_id=trace_id,
                mutation_id=mutation_id,
                endpoint=endpoint,
                status_code=0,
                latency_ms=round(latency, 2),
                response_body={},
                success=False,
                error=str(exc),
            )

    async def inject_batch(
        self,
        records: list[dict],
        mutation_id: str | None = None,
    ) -> list[InjectionResult]:
        """Inject a batch of records sequentially."""
        results = []
        for rec in records:
            result = await self.inject_record(rec, mutation_id=mutation_id)
            results.append(result)
        return results
