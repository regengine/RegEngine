"""Catalog of deterministic mutations for FSMA 204 traceability data."""

from __future__ import annotations

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
