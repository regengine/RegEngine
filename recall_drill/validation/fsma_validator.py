"""FSMA 204 validation engine — enforce KDE/CTE compliance on traceability records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class ValidationIssue:
    severity: ValidationSeverity
    rule: str
    field: str | None
    record_index: int | None
    tlc: str | None
    message: str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "rule": self.rule,
            "field": self.field,
            "record_index": self.record_index,
            "tlc": self.tlc,
            "message": self.message,
        }


@dataclass
class ValidationReport:
    total_records: int
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "total_records": self.total_records,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }


REQUIRED_KDES = {
    "traceability_lot_code",
    "event_type",
    "event_date",
    "product_description",
    "quantity",
    "unit_of_measure",
}

REQUIRED_LOCATION_FIELDS = {"origin_gln", "destination_gln"}

VALID_CTE_TYPES = {
    "harvesting", "cooling", "packing", "shipping",
    "receiving", "transformation", "creating",
}


class FSMAValidator:
    """Validate FSMA 204 CTE/KDE datasets for compliance."""

    def validate(self, records: list[dict]) -> ValidationReport:
        report = ValidationReport(total_records=len(records))

        seen_tlcs: dict[str, list[int]] = {}
        prev_dates: dict[str, str] = {}

        for idx, rec in enumerate(records):
            tlc = rec.get("traceability_lot_code")

            # Rule 1: Required KDEs
            for kde in REQUIRED_KDES:
                val = rec.get(kde)
                if val is None or (isinstance(val, str) and val.strip() == ""):
                    report.errors.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        rule="required_kde_missing",
                        field=kde,
                        record_index=idx,
                        tlc=tlc,
                        message=f"Required KDE '{kde}' is missing or empty",
                    ))

            # Rule 2: Location fields
            for loc_field in REQUIRED_LOCATION_FIELDS:
                val = rec.get(loc_field)
                if val is None or (isinstance(val, str) and val.strip() == ""):
                    report.errors.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        rule="cte_link_missing",
                        field=loc_field,
                        record_index=idx,
                        tlc=tlc,
                        message=f"CTE linking field '{loc_field}' is missing",
                    ))

            # Rule 3: Valid CTE type
            cte_type = rec.get("event_type")
            if cte_type and cte_type not in VALID_CTE_TYPES:
                report.warnings.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    rule="invalid_cte_type",
                    field="event_type",
                    record_index=idx,
                    tlc=tlc,
                    message=f"Unrecognized CTE type: '{cte_type}'",
                ))

            # Rule 4: Supplier linkage
            if cte_type in ("receiving", "transformation"):
                ips = rec.get("immediate_previous_source")
                if not ips or (isinstance(ips, str) and ips.strip() == ""):
                    report.errors.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        rule="missing_supplier",
                        field="immediate_previous_source",
                        record_index=idx,
                        tlc=tlc,
                        message="Receiving/transformation CTE missing immediate_previous_source",
                    ))

            # Rule 5: Temporal ordering per lot
            if tlc:
                event_date = rec.get("event_date", "")
                if tlc in prev_dates and event_date < prev_dates[tlc]:
                    report.errors.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        rule="temporal_order_violation",
                        field="event_date",
                        record_index=idx,
                        tlc=tlc,
                        message=f"Event date {event_date} is before previous event {prev_dates[tlc]} for lot {tlc}",
                    ))
                prev_dates[tlc] = event_date

                # Track TLC duplicates
                seen_tlcs.setdefault(tlc, []).append(idx)

            # Rule 6: Type validation
            qty = rec.get("quantity")
            if qty is not None and not isinstance(qty, (int, float)):
                report.errors.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    rule="type_mismatch",
                    field="quantity",
                    record_index=idx,
                    tlc=tlc,
                    message=f"Quantity has invalid type: {type(qty).__name__}",
                ))

        # Rule 7: Orphan detection (records referencing non-existent upstream)
        all_glns = {rec.get("origin_gln") for rec in records} | {rec.get("destination_gln") for rec in records}
        for idx, rec in enumerate(records):
            ips = rec.get("immediate_previous_source")
            if ips and ips not in all_glns and not ips.startswith("GHOST"):
                report.warnings.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    rule="orphan_reference",
                    field="immediate_previous_source",
                    record_index=idx,
                    tlc=rec.get("traceability_lot_code"),
                    message=f"References unknown upstream source: {ips}",
                ))

        return report
