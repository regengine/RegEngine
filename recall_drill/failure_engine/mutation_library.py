"""Catalog of deterministic mutations for FSMA 204 traceability data.

Each mutation type maps to a severity level, a human-readable description,
and the specific FSMA 204 requirement(s) it is designed to stress-test.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MutationType(str, Enum):
    REMOVE_REQUIRED_FIELD = "remove_required_field"
    CORRUPT_TYPE = "corrupt_type"
    DUPLICATE_TLC = "duplicate_tlc"
    BREAK_CTE_CHAIN = "break_cte_chain"
    SHUFFLE_TIMESTAMPS = "shuffle_timestamps"
    CREATE_ORPHAN = "create_orphan"
    PARTIAL_INGESTION = "partial_ingestion"
    ENCODING_ERROR = "encoding_error"
    INVALID_GLN = "invalid_gln"
    MISSING_SUPPLIER = "missing_supplier"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Which KDE fields are required per FSMA 204
REQUIRED_KDES = {
    "traceability_lot_code",
    "event_type",
    "event_date",
    "product_description",
    "quantity",
    "unit_of_measure",
}

REQUIRED_CTE_FIELDS = {
    "origin_gln",
    "destination_gln",
}

# Mapping from mutation type to default severity
MUTATION_SEVERITY: dict[MutationType, Severity] = {
    MutationType.REMOVE_REQUIRED_FIELD: Severity.CRITICAL,
    MutationType.CORRUPT_TYPE: Severity.HIGH,
    MutationType.DUPLICATE_TLC: Severity.HIGH,
    MutationType.BREAK_CTE_CHAIN: Severity.CRITICAL,
    MutationType.SHUFFLE_TIMESTAMPS: Severity.MEDIUM,
    MutationType.CREATE_ORPHAN: Severity.HIGH,
    MutationType.PARTIAL_INGESTION: Severity.MEDIUM,
    MutationType.ENCODING_ERROR: Severity.LOW,
    MutationType.INVALID_GLN: Severity.MEDIUM,
    MutationType.MISSING_SUPPLIER: Severity.HIGH,
}


@dataclass(frozen=True)
class MutationSpec:
    """Full specification for a single mutation type."""

    mutation_type: MutationType
    severity: Severity
    description: str
    fsma_requirement: str
    affected_layer: str  # ingestion | validation | trace | export
    applies_to: str  # record | dataset | csv

    def to_dict(self) -> dict:
        return {
            "mutation_type": self.mutation_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "fsma_requirement": self.fsma_requirement,
            "affected_layer": self.affected_layer,
            "applies_to": self.applies_to,
        }


# Complete catalog of mutations with FSMA 204 context
MUTATION_CATALOG: dict[MutationType, MutationSpec] = {
    MutationType.REMOVE_REQUIRED_FIELD: MutationSpec(
        mutation_type=MutationType.REMOVE_REQUIRED_FIELD,
        severity=Severity.CRITICAL,
        description=(
            "Remove a required Key Data Element (KDE) from a CTE record. "
            "Tests whether the system detects and rejects incomplete records."
        ),
        fsma_requirement=(
            "21 CFR 1.1340 — Each KDE must be maintained for every CTE. "
            "Missing TLC, event_type, event_date, product_description, "
            "quantity, or unit_of_measure constitutes a compliance failure."
        ),
        affected_layer="ingestion",
        applies_to="record",
    ),
    MutationType.CORRUPT_TYPE: MutationSpec(
        mutation_type=MutationType.CORRUPT_TYPE,
        severity=Severity.HIGH,
        description=(
            "Replace a field value with an incompatible data type "
            "(e.g., string where integer is expected). Tests type "
            "validation at the API boundary."
        ),
        fsma_requirement=(
            "21 CFR 1.1340 — KDE values must conform to specified data types. "
            "Quantities must be numeric; dates must be valid ISO-8601."
        ),
        affected_layer="ingestion",
        applies_to="record",
    ),
    MutationType.DUPLICATE_TLC: MutationSpec(
        mutation_type=MutationType.DUPLICATE_TLC,
        severity=Severity.HIGH,
        description=(
            "Duplicate a Traceability Lot Code across two different "
            "records, creating an ambiguous lot identity. Tests "
            "uniqueness enforcement."
        ),
        fsma_requirement=(
            "21 CFR 1.1310 — Each TLC must uniquely identify a "
            "traceability lot. Duplicate TLCs across distinct lots "
            "prevent accurate one-up / one-back tracing."
        ),
        affected_layer="trace",
        applies_to="dataset",
    ),
    MutationType.BREAK_CTE_CHAIN: MutationSpec(
        mutation_type=MutationType.BREAK_CTE_CHAIN,
        severity=Severity.CRITICAL,
        description=(
            "Remove CTE linking fields (origin_gln, destination_gln) "
            "so events cannot be chained into a supply-chain graph. "
            "Tests graph connectivity enforcement."
        ),
        fsma_requirement=(
            "21 CFR 1.1335 — Each CTE must record the location "
            "identifiers for the origin and destination. Broken chains "
            "make 24-hour recall tracing impossible."
        ),
        affected_layer="trace",
        applies_to="dataset",
    ),
    MutationType.SHUFFLE_TIMESTAMPS: MutationSpec(
        mutation_type=MutationType.SHUFFLE_TIMESTAMPS,
        severity=Severity.MEDIUM,
        description=(
            "Randomly reorder event timestamps within a lot, breaking "
            "temporal monotonicity. Tests whether the system detects "
            "out-of-order CTE sequences."
        ),
        fsma_requirement=(
            "21 CFR 1.1340(a) — Event date and time must accurately "
            "reflect when the CTE occurred. Shuffled timestamps "
            "corrupt the supply-chain timeline."
        ),
        affected_layer="validation",
        applies_to="dataset",
    ),
    MutationType.CREATE_ORPHAN: MutationSpec(
        mutation_type=MutationType.CREATE_ORPHAN,
        severity=Severity.HIGH,
        description=(
            "Insert a record that references a non-existent upstream "
            "source, creating an orphan node in the trace graph. "
            "Tests referential integrity."
        ),
        fsma_requirement=(
            "21 CFR 1.1350 — Persons who receive food on the FTL "
            "must maintain records of immediate previous sources. "
            "Orphan records indicate incomplete supply-chain coverage."
        ),
        affected_layer="trace",
        applies_to="dataset",
    ),
    MutationType.PARTIAL_INGESTION: MutationSpec(
        mutation_type=MutationType.PARTIAL_INGESTION,
        severity=Severity.MEDIUM,
        description=(
            "Randomly drop a percentage of records to simulate a "
            "partial ingestion failure (network timeout, batch "
            "interruption). Tests pipeline resilience."
        ),
        fsma_requirement=(
            "21 CFR 1.1305 — Records must be maintained for all "
            "applicable CTEs. Partial ingestion leaves gaps that "
            "prevent complete recall tracing."
        ),
        affected_layer="ingestion",
        applies_to="dataset",
    ),
    MutationType.ENCODING_ERROR: MutationSpec(
        mutation_type=MutationType.ENCODING_ERROR,
        severity=Severity.LOW,
        description=(
            "Inject character encoding errors (null bytes, accented "
            "character substitution) into CSV data. Tests parser "
            "robustness and data cleaning."
        ),
        fsma_requirement=(
            "21 CFR 1.1340 — Records must be legible and accurate. "
            "Encoding errors may render KDE values unreadable during "
            "FDA inspection."
        ),
        affected_layer="ingestion",
        applies_to="csv",
    ),
    MutationType.INVALID_GLN: MutationSpec(
        mutation_type=MutationType.INVALID_GLN,
        severity=Severity.MEDIUM,
        description=(
            "Replace a GLN with an invalid format (wrong length, "
            "bad check digit). Tests GLN validation at ingestion."
        ),
        fsma_requirement=(
            "21 CFR 1.1335 — Location identifiers (GLNs) must "
            "conform to GS1 standards. Invalid GLNs break facility "
            "identification during recall."
        ),
        affected_layer="validation",
        applies_to="record",
    ),
    MutationType.MISSING_SUPPLIER: MutationSpec(
        mutation_type=MutationType.MISSING_SUPPLIER,
        severity=Severity.HIGH,
        description=(
            "Remove the immediate_previous_source field from a "
            "receiving or transformation CTE. Tests one-back "
            "traceability enforcement."
        ),
        fsma_requirement=(
            "21 CFR 1.1350 — Receiving CTEs must identify the "
            "immediate previous source. Missing supplier linkage "
            "breaks backward traceability."
        ),
        affected_layer="ingestion",
        applies_to="record",
    ),
}


def get_mutations_by_severity(severity: Severity) -> list[MutationSpec]:
    """Return all mutations at a given severity level."""
    return [spec for spec in MUTATION_CATALOG.values() if spec.severity == severity]


def get_mutations_by_layer(layer: str) -> list[MutationSpec]:
    """Return all mutations targeting a specific system layer."""
    return [spec for spec in MUTATION_CATALOG.values() if spec.affected_layer == layer]


def get_catalog_summary() -> list[dict]:
    """Return the full catalog as a list of dictionaries."""
    return [spec.to_dict() for spec in MUTATION_CATALOG.values()]
