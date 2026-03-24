"""Generate recall drill scenarios for FSMA 204 compliance testing.

Supports both random mutation selection and FSMA 204-specific named
scenarios (allergen recall, pathogen contamination, foreign material).
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from recall_drill.failure_engine.generator import DatasetGenerator
from recall_drill.failure_engine.mutation_library import MutationType


class RecallTrigger(str, Enum):
    """FDA recall classification triggers relevant to FSMA 204."""

    ALLERGEN = "undeclared_allergen"
    PATHOGEN = "pathogen_contamination"
    FOREIGN_MATERIAL = "foreign_material"
    CHEMICAL = "chemical_contamination"
    LABELING = "labeling_error"
    TEMPERATURE_ABUSE = "temperature_abuse"


# Pre-configured FSMA 204 scenario templates
_SCENARIO_TEMPLATES: dict[RecallTrigger, dict[str, Any]] = {
    RecallTrigger.ALLERGEN: {
        "description": "Undeclared allergen detected in finished product",
        "verticals": ["deli-prepared", "dairy"],
        "mutations": [
            MutationType.REMOVE_REQUIRED_FIELD,
            MutationType.MISSING_SUPPLIER,
        ],
        "requirements": [
            "Identify all lots containing allergen within 24 hours",
            "Trace upstream to ingredient supplier",
            "Identify all downstream retail locations",
            "Validate TLC linkage for every affected lot",
            "Export FDA 204 Sortable Spreadsheet",
        ],
        "severity": "Class I",
    },
    RecallTrigger.PATHOGEN: {
        "description": "Salmonella/Listeria/E. coli positive test result",
        "verticals": ["fresh-produce", "seafood"],
        "mutations": [
            MutationType.BREAK_CTE_CHAIN,
            MutationType.PARTIAL_INGESTION,
        ],
        "requirements": [
            "Trace all lots from contaminated facility",
            "Identify harvest dates within contamination window",
            "Map full downstream distribution",
            "Validate CTE chain completeness",
            "Confirm no trace gaps in supply chain",
            "Export FDA 204 Sortable Spreadsheet within 24h",
        ],
        "severity": "Class I",
    },
    RecallTrigger.FOREIGN_MATERIAL: {
        "description": "Physical contaminant (metal, glass, plastic) found in product",
        "verticals": ["fresh-produce", "deli-prepared"],
        "mutations": [
            MutationType.DUPLICATE_TLC,
            MutationType.SHUFFLE_TIMESTAMPS,
        ],
        "requirements": [
            "Identify production lot and transformation CTEs",
            "Trace affected equipment/facility",
            "Validate temporal ordering of CTEs",
            "Identify all lots processed on same line/date",
            "Export FDA 204 Sortable Spreadsheet",
        ],
        "severity": "Class I",
    },
    RecallTrigger.CHEMICAL: {
        "description": "Pesticide residue or chemical contaminant above tolerance",
        "verticals": ["fresh-produce"],
        "mutations": [
            MutationType.CREATE_ORPHAN,
            MutationType.MISSING_SUPPLIER,
        ],
        "requirements": [
            "Trace to farm/grower origin",
            "Identify all harvest lots within window",
            "Validate supplier linkage (immediate_previous_source)",
            "Map downstream receivers",
            "Export FDA 204 Sortable Spreadsheet",
        ],
        "severity": "Class II",
    },
    RecallTrigger.LABELING: {
        "description": "Incorrect or missing labeling on food product",
        "verticals": ["dairy", "deli-prepared"],
        "mutations": [
            MutationType.CORRUPT_TYPE,
            MutationType.ENCODING_ERROR,
        ],
        "requirements": [
            "Identify all labeled lots from production run",
            "Validate product_description accuracy",
            "Map distribution to retail",
            "Export FDA 204 Sortable Spreadsheet",
        ],
        "severity": "Class II",
    },
    RecallTrigger.TEMPERATURE_ABUSE: {
        "description": "Cold chain break detected during transit or storage",
        "verticals": ["seafood", "dairy"],
        "mutations": [
            MutationType.SHUFFLE_TIMESTAMPS,
            MutationType.PARTIAL_INGESTION,
        ],
        "requirements": [
            "Identify shipments with temperature excursion",
            "Validate cooling CTE timestamps",
            "Trace affected facilities and lots",
            "Confirm temporal integrity of cold chain",
            "Export FDA 204 Sortable Spreadsheet",
        ],
        "severity": "Class II",
    },
}

# General requirements that apply to every scenario
_GENERAL_REQUIREMENTS = [
    "All CTEs have linked TLCs",
    "Required KDEs present on every record",
    "Temporal ordering is monotonic per lot",
    "No orphan records in trace graph",
    "Supplier linkage is complete",
    "Export produced within 24-hour SLA",
]


@dataclass
class RecallScenario:
    """A single recall drill scenario with dataset and mutation plan."""

    scenario_id: str
    product: str
    vertical: str
    time_window: tuple[str, str]
    target_tlc: str | None
    mutations: list[MutationType]
    dataset: list[dict]
    requirements: list[str]
    trigger: RecallTrigger | None = None
    trigger_description: str = ""
    severity_class: str = ""
    affected_facilities: list[str] = field(default_factory=list)

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
            "trigger": self.trigger.value if self.trigger else None,
            "trigger_description": self.trigger_description,
            "severity_class": self.severity_class,
            "affected_facilities": self.affected_facilities,
        }


class ScenarioGenerator:
    """Generate parameterized recall drill scenarios.

    Supports:
    - Random mutation scenarios via ``generate()``
    - Named FSMA 204 trigger scenarios via ``generate_fsma_scenario()``
    - Full suites mixing both
    """

    FSMA_REQUIREMENTS = _GENERAL_REQUIREMENTS

    def __init__(self, seed: int = 42):
        self._gen = DatasetGenerator(seed=seed)
        self._rng = random.Random(seed)

    def _extract_scenario_metadata(
        self, dataset: list[dict]
    ) -> tuple[str, str, tuple[str, str], str | None, list[str]]:
        """Extract common metadata from a generated dataset."""
        products = {r["product_description"] for r in dataset}
        tlcs = {r["traceability_lot_code"] for r in dataset}
        dates = sorted(r["event_date"] for r in dataset)
        facilities = sorted(
            {r.get("origin_name", "") for r in dataset}
            | {r.get("destination_name", "") for r in dataset}
        )
        facilities = [f for f in facilities if f]

        product = ", ".join(sorted(products))
        vertical = dataset[0].get("vertical", "unknown") if dataset else "unknown"
        time_window = (dates[0], dates[-1]) if dates else ("", "")
        target_tlc = next(iter(tlcs)) if tlcs else None

        return product, vertical, time_window, target_tlc, facilities

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
        product, vertical, time_window, target_tlc, facilities = (
            self._extract_scenario_metadata(dataset)
        )

        return RecallScenario(
            scenario_id=f"DRILL-{uuid.uuid4().hex[:8].upper()}",
            product=product,
            vertical=vertical,
            time_window=time_window,
            target_tlc=target_tlc,
            mutations=mutations or [],
            dataset=dataset,
            requirements=list(_GENERAL_REQUIREMENTS),
            affected_facilities=facilities,
        )

    def generate_fsma_scenario(
        self,
        trigger: RecallTrigger,
        num_lots: int = 5,
        chain_depth: int = 4,
    ) -> RecallScenario:
        """Generate a scenario based on a specific FSMA 204 recall trigger.

        Uses the pre-configured template for the trigger type, including
        appropriate mutations, requirements, and severity classification.
        """
        template = _SCENARIO_TEMPLATES[trigger]
        dataset = self._gen.generate_supply_chain(
            num_lots=num_lots, chain_depth=chain_depth
        )
        product, vertical, time_window, target_tlc, facilities = (
            self._extract_scenario_metadata(dataset)
        )

        return RecallScenario(
            scenario_id=f"FSMA-{trigger.value.upper()[:8]}-{uuid.uuid4().hex[:6].upper()}",
            product=product,
            vertical=vertical,
            time_window=time_window,
            target_tlc=target_tlc,
            mutations=list(template["mutations"]),
            dataset=dataset,
            requirements=template["requirements"] + _GENERAL_REQUIREMENTS,
            trigger=trigger,
            trigger_description=template["description"],
            severity_class=template["severity"],
            affected_facilities=facilities,
        )

    def generate_suite(
        self, count: int = 10, mutations_per_scenario: int = 1
    ) -> list[RecallScenario]:
        """Generate a suite of scenarios with varied mutations.

        Automatically includes one scenario for each FSMA 204 trigger
        type, then fills the remainder with random-mutation scenarios.
        """
        all_mutations = list(MutationType)
        triggers = list(RecallTrigger)
        scenarios: list[RecallScenario] = []

        # Include FSMA-specific scenarios first
        for i, trigger in enumerate(triggers):
            if i >= count:
                break
            scenario = self.generate_fsma_scenario(
                trigger=trigger,
                num_lots=self._rng.randint(3, 8),
            )
            scenarios.append(scenario)

        # Fill remaining with random-mutation scenarios
        remaining = count - len(scenarios)
        for _ in range(remaining):
            muts = self._rng.sample(
                all_mutations, min(mutations_per_scenario, len(all_mutations))
            )
            scenario = self.generate(
                mutations=muts, num_lots=self._rng.randint(3, 8)
            )
            scenarios.append(scenario)

        return scenarios
