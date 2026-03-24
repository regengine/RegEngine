"""Batch injection runner — sends datasets through the full pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from recall_drill.failure_engine.mutator import MutationResult, Mutator
from recall_drill.injection.api_runner import APIRunner, InjectionResult


@dataclass
class BatchResult:
    mutation_metadata: dict
    injection_results: list[InjectionResult]
    total_records: int
    success_count: int
    failure_count: int
    avg_latency_ms: float

    def to_dict(self) -> dict:
        return {
            "mutation": self.mutation_metadata,
            "total_records": self.total_records,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_latency_ms": self.avg_latency_ms,
        }


class BatchRunner:
    """Orchestrate mutation + injection for an entire dataset."""

    def __init__(self, api_runner: APIRunner, mutator: Mutator):
        self._api = api_runner
        self._mutator = mutator

    async def run_mutation_scenario(
        self,
        clean_data: list[dict],
        mutation_fn: str,
        **mutation_kwargs: Any,
    ) -> BatchResult:
        """Apply a named mutation, inject results, return structured output."""
        fn = getattr(self._mutator, mutation_fn)
        mutation_result: MutationResult = fn(clean_data, **mutation_kwargs)

        mutated = mutation_result.data
        mutation_id = mutation_result.metadata["mutation_id"]

        if isinstance(mutated, list):
            results = await self._api.inject_batch(mutated, mutation_id=mutation_id)
        else:
            results = [await self._api.inject_record(
                {"raw": mutated}, mutation_id=mutation_id
            )]

        successes = [r for r in results if r.success]
        latencies = [r.latency_ms for r in results]

        return BatchResult(
            mutation_metadata=mutation_result.metadata,
            injection_results=results,
            total_records=len(results),
            success_count=len(successes),
            failure_count=len(results) - len(successes),
            avg_latency_ms=round(sum(latencies) / max(len(latencies), 1), 2),
        )
