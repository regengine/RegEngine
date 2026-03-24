"""Generate recall drill scenarios for FSMA 204 compliance testing."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from recall_drill.failure_engine.generator import DatasetGenerator
from recall_drill.failure_engine.mutation_library import MutationType


class RecallScenario:
    """A single recall drill scenario with dataset and mutation plan."""

    def __init__(
        self,
        scenario_id: str,
        product: str,
        vertical: str,
        time_window: tuple[str, str],
        target_tlc: str | None,
        mutations: list[MutationType],
        dataset: list[dict],
        requirements: list[str],
    ):
        self.scenario_id = scenario_id
        self.product = product
        self.vertical = vertical
        self.time_window = time_window
        self.target_tlc = target_tlc
        self.mutations = mutations
        self.dataset = dataset
        self.requirements = requirements

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "product": self.product,
            "vertical": self.vertical,
            "time_window": list(self.time_window),
            "target_tlc": self.target_tlc,
            "mutations": [m.value for m in self.mutations],
            "record_count": len(self.dataset),
            "requirements": self.requirements,
        }


class ScenarioGenerator:
    """Generate parameterized recall drill scenarios."""

    FSMA_REQUIREMENTS = [
        "All CTEs have linked TLCs",
        "Required KDEs present on every record",
        "Temporal ordering is monotonic per lot",
        "No orphan records in trace graph",
        "Supplier linkage is complete",
        "Export produced within 24-hour SLA",
    ]

    def __init__(self, seed: int = 42):
        self._gen = DatasetGenerator(seed=seed)

    def generate(
        self,
        mutations: list[MutationType] | None = None,
        num_lots: int = 5,
        chain_depth: int = 4,
    ) -> RecallScenario:
        """Generate a single recall scenario with clean data."""
        dataset = self._gen.generate_supply_chain(
            num_lots=num_lots, chain_depth=chain_depth
        )
        products = {r["product_description"] for r in dataset}
        tlcs = {r["traceability_lot_code"] for r in dataset}
        dates = sorted(r["event_date"] for r in dataset)

        return RecallScenario(
            scenario_id=f"DRILL-{uuid.uuid4().hex[:8].upper()}",
            product=", ".join(sorted(products)),
            vertical=dataset[0].get("vertical", "unknown") if dataset else "unknown",
            time_window=(dates[0], dates[-1]) if dates else ("", ""),
            target_tlc=next(iter(tlcs)) if tlcs else None,
            mutations=mutations or [],
            dataset=dataset,
            requirements=self.FSMA_REQUIREMENTS,
        )

    def generate_suite(
        self, count: int = 10, mutations_per_scenario: int = 1
    ) -> list[RecallScenario]:
        """Generate a suite of scenarios with varied mutations."""
        import random
        rng = random.Random(42)
        all_mutations = list(MutationType)
        scenarios = []
        for _ in range(count):
            muts = rng.sample(all_mutations, min(mutations_per_scenario, len(all_mutations)))
            scenario = self.generate(mutations=muts, num_lots=rng.randint(3, 8))
            scenarios.append(scenario)
        return scenarios
