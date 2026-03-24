"""Root-cause analysis engine for recall drill failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from recall_drill.failure_engine.mutation_library import MutationType
from recall_drill.validation.fsma_validator import ValidationIssue, ValidationReport


@dataclass
class RootCause:
    layer: str  # ingestion | validation | trace | export
    rule: str
    field: str | None
    tlc: str | None
    mutation_type: str | None
    message: str
    fix: str
    repro_payload: dict | None = None

    def to_dict(self) -> dict:
        return {
            "layer": self.layer,
            "rule": self.rule,
            "field": self.field,
            "tlc": self.tlc,
            "mutation_type": self.mutation_type,
            "message": self.message,
            "suggested_fix": self.fix,
            "repro_payload": self.repro_payload,
        }


@dataclass
class DebugReport:
    scenario_id: str
    mutation_id: str | None
    root_causes: list[RootCause]
    summary: str

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "mutation_id": self.mutation_id,
            "root_cause_count": len(self.root_causes),
            "root_causes": [rc.to_dict() for rc in self.root_causes],
            "summary": self.summary,
        }


# Mapping from validation rules to likely layers and fixes
_RULE_TO_FIX: dict[str, tuple[str, str]] = {
    "required_kde_missing": (
        "ingestion",
        "Add server-side validation to reject records missing required KDEs before persistence.",
    ),
    "cte_link_missing": (
        "ingestion",
        "Enforce origin_gln and destination_gln as required fields in the ingest endpoint schema.",
    ),
    "missing_supplier": (
        "ingestion",
        "Require immediate_previous_source for receiving/transformation CTEs in the API schema.",
    ),
    "temporal_order_violation": (
        "validation",
        "Add temporal monotonicity check per TLC during ingestion; reject or reorder out-of-sequence events.",
    ),
    "type_mismatch": (
        "ingestion",
        "Add Pydantic type coercion/validation for numeric fields (quantity, temperature) at the API boundary.",
    ),
    "orphan_reference": (
        "trace",
        "Implement referential integrity check: validate immediate_previous_source exists in the graph before accepting.",
    ),
    "invalid_cte_type": (
        "validation",
        "Restrict event_type to the FSMA 204 CTE vocabulary via enum validation.",
    ),
}


class DebugEngine:
    """Analyze validation failures and produce root-cause reports."""

    def analyze(
        self,
        scenario_id: str,
        mutation_metadata: dict | None,
        validation: ValidationReport,
        records: list[dict],
    ) -> DebugReport:
        mutation_id = mutation_metadata.get("mutation_id") if mutation_metadata else None
        mutation_type = mutation_metadata.get("type") if mutation_metadata else None

        root_causes: list[RootCause] = []

        for issue in validation.errors:
            layer, fix = _RULE_TO_FIX.get(issue.rule, ("unknown", "Investigate manually."))

            repro = None
            if issue.record_index is not None and issue.record_index < len(records):
                repro = records[issue.record_index]

            root_causes.append(RootCause(
                layer=layer,
                rule=issue.rule,
                field=issue.field,
                tlc=issue.tlc,
                mutation_type=mutation_type,
                message=issue.message,
                fix=fix,
                repro_payload=repro,
            ))

        # Deduplicate by (rule, field) — keep first occurrence
        seen: set[tuple[str, str | None]] = set()
        deduped: list[RootCause] = []
        for rc in root_causes:
            key = (rc.rule, rc.field)
            if key not in seen:
                seen.add(key)
                deduped.append(rc)

        if not deduped:
            summary = "No failures detected. All FSMA 204 validation rules passed."
        else:
            layers = {rc.layer for rc in deduped}
            rules = {rc.rule for rc in deduped}
            summary = (
                f"{len(deduped)} root cause(s) identified across {', '.join(sorted(layers))} layer(s). "
                f"Rules violated: {', '.join(sorted(rules))}."
            )
            if mutation_type:
                summary += f" Triggered by mutation: {mutation_type}."

        return DebugReport(
            scenario_id=scenario_id,
            mutation_id=mutation_id,
            root_causes=deduped,
            summary=summary,
        )
