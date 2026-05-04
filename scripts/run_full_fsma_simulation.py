#!/usr/bin/env python3
"""Run RegEngine's deterministic FSMA golden-path simulation.

This is the investor/demo-safe runner for the production spine:

    simulate data -> canonicalize -> validate -> evidence hashes -> FDA export

It is intentionally DB-free. The heavier live-service check remains
``scripts/e2e_brutal_scenario.py``; this script is the fast contract that proves
the core model, rule evaluators, hash chain, and FDA CSV formatter still line up.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "services" / "ingestion", ROOT / "services"):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from app.fda_export_service import FDA_COLUMNS, _generate_csv  # noqa: E402
from shared.canonical_event import CTEType, IngestionSource, TraceabilityEvent  # noqa: E402
from shared.cte_persistence import compute_chain_hash  # noqa: E402
from shared.rules.evaluators.stateless import (  # noqa: E402
    evaluate_field_presence,
    evaluate_multi_field_presence,
)
from shared.rules.seeds import FSMA_RULE_SEEDS  # noqa: E402
from shared.rules.types import EvaluationSummary, RuleDefinition  # noqa: E402


TENANT_ID = UUID("00000000-0000-0000-0000-000000000204")
RUN_STARTED_AT = datetime(2026, 4, 15, 17, 0, 0, tzinfo=timezone.utc)

EVALUATORS = {
    "field_presence": evaluate_field_presence,
    "multi_field_presence": evaluate_multi_field_presence,
}


@dataclass(frozen=True)
class ScenarioEvent:
    """A deterministic Inflow-style source event plus demo metadata."""

    key: str
    persist_after_preflight: bool
    payload: dict[str, Any]


def _iso(hour: int, minute: int = 0) -> str:
    return datetime(2026, 4, 15, hour, minute, 0, tzinfo=timezone.utc).isoformat()


def simulate_inflow_events() -> list[ScenarioEvent]:
    """Generate a deterministic supplier lifecycle with one intentional gap."""
    return [
        ScenarioEvent(
            key="receiving-romaine",
            persist_after_preflight=True,
            payload={
                "event_id": "00000000-0000-0000-0000-000000000001",
                "source_record_id": "inflow-lab:receiving-romaine",
                "source_system": IngestionSource.SUPPLIER_PORTAL,
                "event_type": CTEType.RECEIVING,
                "event_timestamp": _iso(8, 30),
                "traceability_lot_code": "TLC-ROMAINE-2026-0415",
                "product_reference": "Romaine Hearts 3pk",
                "quantity": 900,
                "unit_of_measure": "cases",
                "from_entity_reference": "Desert Valley Farms",
                "to_entity_reference": "RegEngine Demo DC",
                "from_facility_reference": "0614141099001",
                "to_facility_reference": "0614141033391",
                "kdes": {
                    "ftl_covered": True,
                    "ftl_category": "Leafy greens",
                    "receive_date": "2026-04-15",
                    "reference_document": "BOL-DV-0415",
                    "reference_document_number": "BOL-DV-0415",
                    "tlc_source_reference": "Desert Valley Farms",
                    "tlc_source_gln": "0614141099001",
                    "immediate_previous_source": "Desert Valley Farms",
                    "ship_from_location": "Yuma, AZ",
                    "ship_from_gln": "0614141099001",
                    "ship_to_location": "Fresno, CA",
                    "ship_to_gln": "0614141033391",
                },
            },
        ),
        ScenarioEvent(
            key="shipping-missing-destination",
            persist_after_preflight=False,
            payload={
                "event_id": "00000000-0000-0000-0000-000000000002",
                "source_record_id": "inflow-lab:shipping-missing-destination",
                "source_system": IngestionSource.SUPPLIER_PORTAL,
                "event_type": CTEType.SHIPPING,
                "event_timestamp": _iso(10, 15),
                "traceability_lot_code": "TLC-ROMAINE-2026-0415",
                "product_reference": "Romaine Hearts 3pk",
                "quantity": 900,
                "unit_of_measure": "cases",
                "from_entity_reference": "RegEngine Demo DC",
                "to_entity_reference": None,
                "from_facility_reference": "0614141033391",
                "to_facility_reference": None,
                "kdes": {
                    "ftl_covered": True,
                    "ftl_category": "Leafy greens",
                    "ship_date": "2026-04-15",
                    "reference_document": "BOL-DC-0415",
                    "reference_document_number": "BOL-DC-0415",
                    "tlc_source_reference": "Desert Valley Farms",
                    "ship_from_location": "Fresno, CA",
                    "ship_from_gln": "0614141033391",
                },
            },
        ),
        ScenarioEvent(
            key="shipping-corrected-destination",
            persist_after_preflight=True,
            payload={
                "event_id": "00000000-0000-0000-0000-000000000003",
                "source_record_id": "inflow-lab:shipping-corrected-destination",
                "source_system": IngestionSource.SUPPLIER_PORTAL,
                "event_type": CTEType.SHIPPING,
                "event_timestamp": _iso(10, 20),
                "traceability_lot_code": "TLC-ROMAINE-2026-0415",
                "product_reference": "Romaine Hearts 3pk",
                "quantity": 900,
                "unit_of_measure": "cases",
                "from_entity_reference": "RegEngine Demo DC",
                "to_entity_reference": "Retailer Store 1842",
                "from_facility_reference": "0614141033391",
                "to_facility_reference": "0614141184200",
                "supersedes_event_id": "00000000-0000-0000-0000-000000000002",
                "kdes": {
                    "ftl_covered": True,
                    "ftl_category": "Leafy greens",
                    "ship_date": "2026-04-15",
                    "reference_document": "BOL-DC-0415-CORRECTED",
                    "reference_document_number": "BOL-DC-0415-CORRECTED",
                    "tlc_source_reference": "Desert Valley Farms",
                    "ship_from_location": "Fresno, CA",
                    "ship_from_gln": "0614141033391",
                    "ship_to_location": "Retailer Store 1842",
                    "ship_to_gln": "0614141184200",
                },
            },
        ),
        ScenarioEvent(
            key="transformation-salad-kit",
            persist_after_preflight=True,
            payload={
                "event_id": "00000000-0000-0000-0000-000000000004",
                "source_record_id": "inflow-lab:transformation-salad-kit",
                "source_system": IngestionSource.SUPPLIER_PORTAL,
                "event_type": CTEType.TRANSFORMATION,
                "event_timestamp": _iso(13, 45),
                "traceability_lot_code": "TLC-SALADKIT-2026-0415",
                "product_reference": "Romaine Caesar Salad Kit",
                "quantity": 840,
                "unit_of_measure": "cases",
                "from_entity_reference": "FreshPak Processing",
                "to_entity_reference": "FreshPak Processing",
                "from_facility_reference": "0614141099888",
                "to_facility_reference": "0614141099888",
                "kdes": {
                    "ftl_covered": True,
                    "ftl_category": "Leafy greens",
                    "transformation_date": "2026-04-15",
                    "reference_document": "XFORM-FP-0415",
                    "reference_document_number": "XFORM-FP-0415",
                    "input_traceability_lot_codes": ["TLC-ROMAINE-2026-0415"],
                    "input_quantities": [900],
                    "process_type": "wash_cut_pack",
                },
            },
        ),
    ]


def canonicalize(event: ScenarioEvent) -> TraceabilityEvent:
    """Normalize an Inflow-style payload into the canonical event model."""
    payload = {
        **event.payload,
        "tenant_id": TENANT_ID,
        "raw_payload": {"source": "inflow-lab", "event_key": event.key},
        "ingested_at": RUN_STARTED_AT,
        "created_at": RUN_STARTED_AT,
    }
    return TraceabilityEvent(**payload)


def load_stateless_rules() -> list[RuleDefinition]:
    """Load production seed rules that can run without database state."""
    rules: list[RuleDefinition] = []
    for index, seed in enumerate(FSMA_RULE_SEEDS, start=1):
        logic = seed.get("evaluation_logic", {})
        if logic.get("type") not in EVALUATORS:
            continue
        rules.append(
            RuleDefinition(
                rule_id=f"fsma-seed-{index:03d}",
                rule_version=1,
                title=seed["title"],
                description=seed.get("description"),
                severity=seed["severity"],
                category=seed["category"],
                applicability_conditions=seed.get("applicability_conditions", {}),
                citation_reference=seed.get("citation_reference"),
                effective_date=date(2026, 1, 1),
                retired_date=None,
                evaluation_logic=logic,
                failure_reason_template=seed["failure_reason_template"],
                remediation_suggestion=seed.get("remediation_suggestion"),
            )
        )
    return rules


def _rule_applies(rule: RuleDefinition, event: TraceabilityEvent) -> bool:
    cte_types = rule.applicability_conditions.get("cte_types", [])
    return not cte_types or event.event_type.value in cte_types or "all" in cte_types


def evaluate_event(event: TraceabilityEvent, rules: Iterable[RuleDefinition]) -> EvaluationSummary:
    """Evaluate one canonical event with stateless production seed rules."""
    event_data = event.model_dump(mode="json")
    summary = EvaluationSummary(event_id=str(event.event_id))

    for rule in rules:
        if not _rule_applies(rule, event):
            continue

        evaluator = EVALUATORS.get(rule.evaluation_logic.get("type"))
        if evaluator is None:
            continue

        result = evaluator(event_data, rule.evaluation_logic, rule)
        summary.results.append(result)
        summary.total_rules += 1

        if result.result == "pass":
            summary.passed += 1
        elif result.result == "fail":
            summary.failed += 1
            if result.severity == "critical":
                summary.critical_failures.append(result)
        elif result.result == "warn":
            summary.warned += 1
        elif result.result == "error":
            summary.errored += 1
        else:
            summary.skipped += 1

    return summary


def finalize_evidence(events: Iterable[TraceabilityEvent]) -> list[TraceabilityEvent]:
    """Prepare active events for persistence and compute an ordered hash chain."""
    finalized: list[TraceabilityEvent] = []
    previous_chain_hash: str | None = None

    for event in events:
        event.prepare_for_persistence()
        if event.sha256_hash is None:
            raise RuntimeError(f"event {event.event_id} did not compute sha256_hash")
        event.chain_hash = compute_chain_hash(event.sha256_hash, previous_chain_hash)
        previous_chain_hash = event.chain_hash
        finalized.append(event)

    return finalized


def _event_to_export_record(event: TraceabilityEvent) -> dict[str, Any]:
    data = event.model_dump(mode="json")
    kdes = dict(data["kdes"])
    return {
        "traceability_lot_code": data["traceability_lot_code"],
        "product_description": data["product_reference"],
        "quantity": data["quantity"],
        "unit_of_measure": data["unit_of_measure"],
        "event_type": data["event_type"],
        "event_timestamp": data["event_timestamp"],
        "location_gln": data["to_facility_reference"] or data["from_facility_reference"] or "",
        "location_name": data["to_entity_reference"] or data["from_entity_reference"] or "",
        "source": data["source_system"],
        "kdes": kdes,
        "sha256_hash": data["sha256_hash"],
        "chain_hash": data["chain_hash"],
        "ingested_at": data["ingested_at"],
    }


def _summary_for_event(event: ScenarioEvent, model: TraceabilityEvent, summary: EvaluationSummary) -> dict[str, Any]:
    return {
        "key": event.key,
        "event_id": str(model.event_id),
        "event_type": model.event_type.value,
        "traceability_lot_code": model.traceability_lot_code,
        "preflight_status": "pass" if summary.compliant is True else "blocked",
        "rules_evaluated": summary.total_rules,
        "passed": summary.passed,
        "failed": summary.failed,
        "critical_failures": [
            {
                "rule": failure.rule_title,
                "citation": failure.citation_reference,
                "why_failed": failure.why_failed,
                "remediation": failure.remediation_suggestion,
            }
            for failure in summary.critical_failures
        ],
    }


def run_simulation(output_dir: Path) -> dict[str, Any]:
    """Execute the full deterministic golden path and write artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)

    scenario_events = simulate_inflow_events()
    canonical_events = [(event, canonicalize(event)) for event in scenario_events]
    rules = load_stateless_rules()
    evaluations = [(event, model, evaluate_event(model, rules)) for event, model in canonical_events]

    initial_failure_points = [
        _summary_for_event(event, model, summary)
        for event, model, summary in evaluations
        if not event.persist_after_preflight and summary.critical_failures
    ]
    export_candidates = [
        model
        for event, model, summary in evaluations
        if event.persist_after_preflight and summary.compliant is True
    ]
    exportable_events = finalize_evidence(export_candidates)
    export_records = [_event_to_export_record(event) for event in exportable_events]

    csv_text = _generate_csv(export_records, include_pii=False)
    csv_path = output_dir / "fda_export.csv"
    csv_path.write_text(csv_text, encoding="utf-8")

    summary = {
        "passed": bool(initial_failure_points and len(exportable_events) == 3),
        "tenant_id": str(TENANT_ID),
        "flow": [
            "simulate data",
            "canonicalize",
            "validate",
            "persist evidence hashes",
            "generate FDA export",
        ],
        "events_generated": len(scenario_events),
        "stateless_rules_loaded": len(rules),
        "initial_preflight": [
            _summary_for_event(event, model, event_summary)
            for event, model, event_summary in evaluations
            if not event.persist_after_preflight
        ],
        "failure_points": initial_failure_points,
        "remediation": {
            "blocked_event_key": "shipping-missing-destination",
            "corrected_event_key": "shipping-corrected-destination",
            "exportable_events": len(exportable_events),
        },
        "evidence": {
            "records_with_sha256_hash": sum(1 for event in exportable_events if event.sha256_hash),
            "records_with_chain_hash": sum(1 for event in exportable_events if event.chain_hash),
            "last_chain_hash": exportable_events[-1].chain_hash if exportable_events else None,
        },
        "export": {
            "csv_path": str(csv_path),
            "rows": len(export_records),
            "columns": len(FDA_COLUMNS),
            "contains_system_entry_timestamp": "System Entry Timestamp" in csv_text.splitlines()[0],
        },
    }

    summary_path = output_dir / "summary.json"
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def _print_human_summary(summary: dict[str, Any]) -> None:
    status = "PASS" if summary["passed"] else "FAIL"
    print(f"{status} RegEngine golden path")
    print(f"tenant_id: {summary['tenant_id']}")
    print(f"events generated: {summary['events_generated']}")
    print(f"stateless rules loaded: {summary['stateless_rules_loaded']}")
    print(f"failure points detected: {len(summary['failure_points'])}")
    print(f"export rows: {summary['export']['rows']} ({summary['export']['columns']} columns)")
    print(f"fda export: {summary['export']['csv_path']}")
    print(f"summary: {summary['summary_path']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/regengine-golden-path"),
        help="Directory for summary.json and fda_export.csv",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only")
    args = parser.parse_args(argv)

    summary = run_simulation(args.output_dir)
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        _print_human_summary(summary)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
