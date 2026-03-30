"""
Sandbox Evaluation Router.

Provides POST /api/v1/sandbox/evaluate — a stateless endpoint that accepts
raw CTE events (JSON or CSV), runs normalization + FSMA 204 rule evaluation,
and returns results WITHOUT persisting anything.

This powers the live demo on the marketing site, letting prospects drop their
own data and see RegEngine's validation in action.

No auth required. No data stored. Rate-limited to prevent abuse.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import string
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.webhook_models import (
    REQUIRED_KDES_BY_CTE,
    WebhookCTEType,
)
from shared.rules_engine import (
    FSMA_RULE_SEEDS,
    RuleDefinition,
    RuleEvaluationResult,
    EvaluationSummary,
    _CTE_LIFECYCLE_ORDER,
    _EVALUATORS,
    _get_nested_value,
    _normalize_to_lbs,
)

logger = logging.getLogger("sandbox")

router = APIRouter(prefix="/api/v1/sandbox", tags=["Sandbox"])


# ---------------------------------------------------------------------------
# Rate Limiting (simple in-memory, per-IP)
# ---------------------------------------------------------------------------

_rate_buckets: Dict[str, list] = {}
_SANDBOX_RATE_LIMIT = 30  # requests per minute
_SANDBOX_WINDOW = 60


def _check_sandbox_rate_limit(client_ip: str) -> None:
    """Simple per-IP rate limit for sandbox endpoint."""
    now = datetime.now(timezone.utc).timestamp()
    bucket = _rate_buckets.setdefault(client_ip, [])
    # Prune old entries
    bucket[:] = [t for t in bucket if now - t < _SANDBOX_WINDOW]
    if len(bucket) >= _SANDBOX_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Sandbox rate limit exceeded. Try again in a minute.",
        )
    bucket.append(now)


# ---------------------------------------------------------------------------
# In-Memory Rules (no DB needed)
# ---------------------------------------------------------------------------

def _build_rules_from_seeds() -> List[RuleDefinition]:
    """Build RuleDefinition objects from FSMA_RULE_SEEDS without touching the database."""
    rules = []
    for i, seed in enumerate(FSMA_RULE_SEEDS):
        rules.append(RuleDefinition(
            rule_id=f"sandbox-rule-{i:03d}",
            rule_version=1,
            title=seed["title"],
            description=seed.get("description"),
            severity=seed["severity"],
            category=seed["category"],
            applicability_conditions=seed.get("applicability_conditions", {}),
            citation_reference=seed.get("citation_reference"),
            effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic=seed["evaluation_logic"],
            failure_reason_template=seed["failure_reason_template"],
            remediation_suggestion=seed.get("remediation_suggestion"),
        ))
    return rules


_SANDBOX_RULES = _build_rules_from_seeds()


def _get_applicable_rules(event_type: str) -> List[RuleDefinition]:
    """Filter sandbox rules to those applicable to the given event type."""
    applicable = []
    for rule in _SANDBOX_RULES:
        cte_types = rule.applicability_conditions.get("cte_types", [])
        if not cte_types or event_type in cte_types or "all" in cte_types:
            applicable.append(rule)
    return applicable


# Relational evaluation types handled by _evaluate_relational_in_memory
_RELATIONAL_EVAL_TYPES = {"temporal_order", "identity_consistency", "mass_balance"}


def _evaluate_event_stateless(event_data: Dict[str, Any]) -> EvaluationSummary:
    """Evaluate an event against all applicable stateless rules (no DB).

    Relational rules (temporal_order, identity_consistency, mass_balance) are
    excluded here — they are evaluated separately by _evaluate_relational_in_memory
    which has access to the full event batch.
    """
    event_type = event_data.get("event_type", "")
    event_id = event_data.get("event_id", str(uuid4()))

    applicable = _get_applicable_rules(event_type)
    # Filter out relational rules — they're handled by the batch evaluator
    stateless_rules = [r for r in applicable if r.evaluation_logic.get("type") not in _RELATIONAL_EVAL_TYPES]

    summary = EvaluationSummary(
        event_id=event_id,
        total_rules=len(stateless_rules),
    )

    for rule in stateless_rules:
        logic = rule.evaluation_logic
        eval_type = logic.get("type", "field_presence")
        evaluator = _EVALUATORS.get(eval_type)

        if not evaluator:
            result = RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                rule_title=rule.title,
                severity=rule.severity,
                result="skip",
                why_failed=f"Unknown evaluation type: {eval_type}",
                category=rule.category,
            )
        else:
            try:
                result = evaluator(event_data, logic, rule)
            except Exception as e:
                result = RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    rule_title=rule.title,
                    severity=rule.severity,
                    result="skip",
                    why_failed=f"Evaluation error: {str(e)}",
                    category=rule.category,
                )

        summary.results.append(result)
        if result.result == "pass":
            summary.passed += 1
        elif result.result == "fail":
            summary.failed += 1
            if result.severity == "critical":
                summary.critical_failures.append(result)
        elif result.result == "warn":
            summary.warned += 1
        else:
            summary.skipped += 1

    return summary


# ---------------------------------------------------------------------------
# In-Memory Relational Evaluation (cross-event, no DB)
# ---------------------------------------------------------------------------

def _get_relational_rules() -> Dict[str, RuleDefinition]:
    """Get the 3 relational rules from sandbox rules by evaluation type."""
    relational = {}
    for rule in _SANDBOX_RULES:
        eval_type = rule.evaluation_logic.get("type", "")
        if eval_type in ("temporal_order", "identity_consistency", "mass_balance"):
            relational[eval_type] = rule
    return relational


def _evaluate_relational_in_memory(
    all_canonical: List[Dict[str, Any]],
) -> Dict[str, List[RuleEvaluationResult]]:
    """Run relational validation across events in memory (no DB needed).

    Groups events by TLC, then for each event checks:
    - Temporal order: lifecycle-earlier events should have earlier timestamps
    - Identity consistency: product_reference must match across same TLC
    - Mass balance: output quantity can't exceed input quantity

    Returns: {event_id: [RuleEvaluationResult, ...]}
    """
    relational_rules = _get_relational_rules()
    if not relational_rules:
        return {}

    # Group by TLC
    tlc_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for evt in all_canonical:
        tlc = evt.get("traceability_lot_code", "")
        if tlc:
            tlc_groups[tlc].append(evt)

    results: Dict[str, List[RuleEvaluationResult]] = defaultdict(list)

    for tlc, events in tlc_groups.items():
        if len(events) < 2:
            continue  # Single event — no cross-event checks possible

        # --- Temporal Order ---
        temporal_rule = relational_rules.get("temporal_order")
        if temporal_rule:
            for evt in events:
                event_type = evt.get("event_type", "")
                cte_types = temporal_rule.applicability_conditions.get("cte_types", [])
                if cte_types and event_type not in cte_types and "all" not in cte_types:
                    continue

                current_stage = _CTE_LIFECYCLE_ORDER.get(event_type)
                if current_stage is None:
                    continue

                current_ts = evt.get("event_timestamp", "")
                if isinstance(current_ts, str) and current_ts:
                    current_ts = datetime.fromisoformat(current_ts.replace("Z", "+00:00"))

                violations = []
                for other in events:
                    if other.get("event_id") == evt.get("event_id"):
                        continue
                    other_type = other.get("event_type", "")
                    other_stage = _CTE_LIFECYCLE_ORDER.get(other_type)
                    if other_stage is None:
                        continue

                    other_ts = other.get("event_timestamp", "")
                    if isinstance(other_ts, str) and other_ts:
                        other_ts = datetime.fromisoformat(other_ts.replace("Z", "+00:00"))

                    if other_stage < current_stage and other_ts > current_ts:
                        violations.append({
                            "earlier_stage": other_type,
                            "earlier_timestamp": str(other_ts),
                            "later_stage": event_type,
                            "later_timestamp": str(current_ts),
                        })
                    elif other_stage > current_stage and other_ts < current_ts:
                        violations.append({
                            "earlier_stage": event_type,
                            "earlier_timestamp": str(current_ts),
                            "later_stage": other_type,
                            "later_timestamp": str(other_ts),
                        })

                if violations:
                    v = violations[0]
                    results[evt["event_id"]].append(RuleEvaluationResult(
                        rule_id=temporal_rule.rule_id,
                        rule_version=temporal_rule.rule_version,
                        rule_title=temporal_rule.title,
                        severity=temporal_rule.severity,
                        result="fail",
                        why_failed=(
                            f"Chronology paradox for TLC '{tlc}': {v['later_stage']} "
                            f"(at {v['later_timestamp']}) occurs before {v['earlier_stage']} "
                            f"(at {v['earlier_timestamp']}). "
                            f"CTE events must follow the supply chain lifecycle order "
                            f"({temporal_rule.citation_reference})."
                        ),
                        evidence_fields_inspected=violations,
                        citation_reference=temporal_rule.citation_reference,
                        remediation_suggestion=temporal_rule.remediation_suggestion,
                        category=temporal_rule.category,
                    ))
                else:
                    results[evt["event_id"]].append(RuleEvaluationResult(
                        rule_id=temporal_rule.rule_id,
                        rule_version=temporal_rule.rule_version,
                        rule_title=temporal_rule.title,
                        severity=temporal_rule.severity,
                        result="pass",
                        category=temporal_rule.category,
                    ))

        # --- Identity Consistency ---
        identity_rule = relational_rules.get("identity_consistency")
        if identity_rule:
            # Collect all products for this TLC
            products: Dict[str, str] = {}  # normalized -> original
            for evt in events:
                pr = evt.get("product_reference", "")
                if pr:
                    products[" ".join(pr.strip().lower().split())] = pr

            for evt in events:
                event_type = evt.get("event_type", "")
                cte_types = identity_rule.applicability_conditions.get("cte_types", [])
                if cte_types and event_type not in cte_types and "all" not in cte_types:
                    continue

                current_product = evt.get("product_reference", "")
                if not current_product:
                    continue

                normalized_current = " ".join(current_product.strip().lower().split())
                mismatches = []
                for norm, orig in products.items():
                    if norm != normalized_current:
                        mismatches.append({"product": orig, "current": current_product})

                if mismatches:
                    m = mismatches[0]
                    results[evt["event_id"]].append(RuleEvaluationResult(
                        rule_id=identity_rule.rule_id,
                        rule_version=identity_rule.rule_version,
                        rule_title=identity_rule.title,
                        severity=identity_rule.severity,
                        result="fail",
                        why_failed=(
                            f"Product identity changed for TLC '{tlc}': "
                            f"'{m['product']}' vs '{current_product}'. "
                            f"The same TLC must refer to the same product "
                            f"({identity_rule.citation_reference})."
                        ),
                        evidence_fields_inspected=mismatches,
                        citation_reference=identity_rule.citation_reference,
                        remediation_suggestion=identity_rule.remediation_suggestion,
                        category=identity_rule.category,
                    ))
                else:
                    results[evt["event_id"]].append(RuleEvaluationResult(
                        rule_id=identity_rule.rule_id,
                        rule_version=identity_rule.rule_version,
                        rule_title=identity_rule.title,
                        severity=identity_rule.severity,
                        result="pass",
                        category=identity_rule.category,
                    ))

        # --- Mass Balance ---
        mass_rule = relational_rules.get("mass_balance")
        if mass_rule:
            input_types = {"harvesting", "receiving", "first_land_based_receiving"}
            output_types = {"shipping"}
            tolerance = mass_rule.evaluation_logic.get("params", {}).get("tolerance_percent", 1.0)

            total_input = 0.0
            total_output = 0.0
            units_seen: set = set()
            use_converted = False

            # Collect all entries
            all_entries = []
            for evt in events:
                qty = evt.get("quantity")
                uom = evt.get("unit_of_measure", "")
                if qty is None:
                    continue
                if uom:
                    units_seen.add(uom.lower().strip())
                all_entries.append((float(qty), uom, evt.get("event_type", "")))

            # Try UOM conversion if units differ
            if len(units_seen) > 1:
                converted = []
                all_ok = True
                for qty, uom, etype in all_entries:
                    lbs = _normalize_to_lbs(qty, uom) if uom else None
                    if lbs is None:
                        all_ok = False
                        break
                    converted.append((lbs, etype))
                if all_ok:
                    use_converted = True
                    for lbs, etype in converted:
                        if etype in input_types:
                            total_input += lbs
                        elif etype in output_types:
                            total_output += lbs

            if not use_converted:
                for qty, uom, etype in all_entries:
                    if etype in input_types:
                        total_input += qty
                    elif etype in output_types:
                        total_output += qty

            for evt in events:
                event_type = evt.get("event_type", "")
                cte_types = mass_rule.applicability_conditions.get("cte_types", [])
                if cte_types and event_type not in cte_types and "all" not in cte_types:
                    continue

                evidence = [{
                    "tlc": tlc,
                    "total_input": total_input,
                    "total_output": total_output,
                    "tolerance_percent": tolerance,
                    "units_seen": list(units_seen),
                    "uom_converted": use_converted,
                }]

                if len(units_seen) > 1 and not use_converted:
                    results[evt["event_id"]].append(RuleEvaluationResult(
                        rule_id=mass_rule.rule_id,
                        rule_version=mass_rule.rule_version,
                        rule_title=mass_rule.title,
                        severity=mass_rule.severity,
                        result="warn",
                        why_failed=(
                            f"Mass balance check inconclusive for TLC '{tlc}': "
                            f"mixed units ({', '.join(sorted(units_seen))}) "
                            f"could not all be converted."
                        ),
                        evidence_fields_inspected=evidence,
                        citation_reference=mass_rule.citation_reference,
                        category=mass_rule.category,
                    ))
                elif total_input > 0 and total_output > total_input * (1 + tolerance / 100):
                    max_allowed = total_input * (1 + tolerance / 100)
                    results[evt["event_id"]].append(RuleEvaluationResult(
                        rule_id=mass_rule.rule_id,
                        rule_version=mass_rule.rule_version,
                        rule_title=mass_rule.title,
                        severity=mass_rule.severity,
                        result="fail",
                        why_failed=(
                            f"Mass balance violation for TLC '{tlc}': "
                            f"total output ({total_output}) exceeds total input ({total_input}) "
                            f"by more than {tolerance}% (max: {max_allowed:.2f}) "
                            f"({mass_rule.citation_reference})."
                        ),
                        evidence_fields_inspected=evidence,
                        citation_reference=mass_rule.citation_reference,
                        remediation_suggestion=mass_rule.remediation_suggestion,
                        category=mass_rule.category,
                    ))
                else:
                    results[evt["event_id"]].append(RuleEvaluationResult(
                        rule_id=mass_rule.rule_id,
                        rule_version=mass_rule.rule_version,
                        rule_title=mass_rule.title,
                        severity=mass_rule.severity,
                        result="pass",
                        evidence_fields_inspected=evidence,
                        category=mass_rule.category,
                    ))

    return dict(results)


# ---------------------------------------------------------------------------
# CSV Parsing
# ---------------------------------------------------------------------------

# Map common CSV column headers to our internal field names.
# Aliases cover abbreviations, snake_case variants, and common spreadsheet headers.
_CSV_COLUMN_MAP = {
    # CTE type
    "cte_type": "cte_type",
    "event_type": "cte_type",
    "type": "cte_type",
    "cte": "cte_type",
    "event": "cte_type",
    # Traceability lot code
    "traceability_lot_code": "traceability_lot_code",
    "tlc": "traceability_lot_code",
    "lot_code": "traceability_lot_code",
    "lot": "traceability_lot_code",
    "lot_number": "traceability_lot_code",
    "lot_no": "traceability_lot_code",
    "lot_id": "traceability_lot_code",
    "trace_lot_code": "traceability_lot_code",
    "batch": "traceability_lot_code",
    "batch_number": "traceability_lot_code",
    "batch_no": "traceability_lot_code",
    "batch_id": "traceability_lot_code",
    # Product
    "product_description": "product_description",
    "product": "product_description",
    "product_name": "product_description",
    "description": "product_description",
    "commodity": "product_description",
    "commodity_variety": "product_description",
    "item": "product_description",
    "item_description": "product_description",
    "sku": "product_description",
    "sku_description": "product_description",
    "material": "product_description",
    "material_description": "product_description",
    # Quantity
    "quantity": "quantity",
    "qty": "quantity",
    "amount": "quantity",
    "count": "quantity",
    "units": "quantity",
    "weight": "quantity",
    "volume": "quantity",
    # Unit of measure
    "unit_of_measure": "unit_of_measure",
    "unit": "unit_of_measure",
    "uom": "unit_of_measure",
    "measure": "unit_of_measure",
    "unit_measure": "unit_of_measure",
    # Location GLN
    "location_gln": "location_gln",
    "gln": "location_gln",
    "facility_gln": "location_gln",
    "site_gln": "location_gln",
    # Location name
    "location_name": "location_name",
    "location": "location_name",
    "facility": "location_name",
    "facility_name": "location_name",
    "site": "location_name",
    "site_name": "location_name",
    "loc_name": "location_name",
    "plant": "location_name",
    "plant_name": "location_name",
    "warehouse": "location_name",
    # Timestamp
    "timestamp": "timestamp",
    "date": "timestamp",
    "event_date": "timestamp",
    "event_time": "timestamp",
    "event_timestamp": "timestamp",
    "datetime": "timestamp",
    "date_time": "timestamp",
    # Supplier / source
    "supplier": "location_name",
    "supplier_name": "location_name",
    "vendor": "location_name",
    "vendor_name": "location_name",
}

# Fields that go into kdes dict rather than top-level.
# Includes aliases — multiple header names map to the same KDE key.
_KDE_FIELD_ALIASES = {
    # Harvest
    "harvest_date": "harvest_date",
    "harvested": "harvest_date",
    "date_harvested": "harvest_date",
    "harvest_dt": "harvest_date",
    # Cooling
    "cooling_date": "cooling_date",
    "cooled_date": "cooling_date",
    "date_cooled": "cooling_date",
    "cool_date": "cooling_date",
    # Packing
    "packing_date": "packing_date",
    "pack_date": "packing_date",
    "date_packed": "packing_date",
    "packed_date": "packing_date",
    # Landing (seafood)
    "landing_date": "landing_date",
    "land_date": "landing_date",
    "date_landed": "landing_date",
    # Ship date
    "ship_date": "ship_date",
    "shipped_date": "ship_date",
    "date_shipped": "ship_date",
    "shipping_date": "ship_date",
    # Receive date
    "receive_date": "receive_date",
    "received_date": "receive_date",
    "date_received": "receive_date",
    "receiving_date": "receive_date",
    "receipt_date": "receive_date",
    # Transformation
    "transformation_date": "transformation_date",
    "transform_date": "transformation_date",
    "date_transformed": "transformation_date",
    # Ship-from
    "ship_from_location": "ship_from_location",
    "ship_from": "ship_from_location",
    "shipped_from": "ship_from_location",
    "from_location": "ship_from_location",
    "origin": "ship_from_location",
    "origin_location": "ship_from_location",
    "source_location": "ship_from_location",
    "from_facility": "ship_from_location",
    "from_site": "ship_from_location",
    # Ship-to
    "ship_to_location": "ship_to_location",
    "ship_to": "ship_to_location",
    "shipped_to": "ship_to_location",
    "to_location": "ship_to_location",
    "destination": "ship_to_location",
    "destination_location": "ship_to_location",
    "dest_location": "ship_to_location",
    "to_facility": "ship_to_location",
    "to_site": "ship_to_location",
    # GLNs
    "ship_from_gln": "ship_from_gln",
    "from_gln": "ship_from_gln",
    "origin_gln": "ship_from_gln",
    "ship_to_gln": "ship_to_gln",
    "to_gln": "ship_to_gln",
    "destination_gln": "ship_to_gln",
    "dest_gln": "ship_to_gln",
    # Receiving location
    "receiving_location": "receiving_location",
    "received_at": "receiving_location",
    "receive_location": "receiving_location",
    # Reference documents
    "reference_document": "reference_document",
    "ref_doc": "reference_document",
    "reference_doc": "reference_document",
    "document": "reference_document",
    "doc_number": "reference_document",
    "doc_no": "reference_document",
    "bol": "reference_document",
    "bol_number": "reference_document",
    "bill_of_lading": "reference_document",
    "invoice": "reference_document",
    "invoice_number": "reference_document",
    "invoice_no": "reference_document",
    "po": "reference_document",
    "po_number": "reference_document",
    "purchase_order": "reference_document",
    # Carrier / transport
    "carrier": "carrier",
    "carrier_name": "carrier",
    "transport": "carrier",
    "transport_reference": "carrier",
    "trucker": "carrier",
    "freight_carrier": "carrier",
    # Harvester
    "harvester_business_name": "harvester_business_name",
    "harvester": "harvester_business_name",
    "harvester_name": "harvester_business_name",
    "grower": "harvester_business_name",
    "grower_name": "harvester_business_name",
    "farm": "harvester_business_name",
    "farm_name": "harvester_business_name",
    # TLC source
    "tlc_source_reference": "tlc_source_reference",
    "tlc_source": "tlc_source_reference",
    "lot_code_source": "tlc_source_reference",
    "source_reference": "tlc_source_reference",
    "assigned_by": "tlc_source_reference",
    # Previous source
    "immediate_previous_source": "immediate_previous_source",
    "previous_source": "immediate_previous_source",
    "prev_source": "immediate_previous_source",
    "ips": "immediate_previous_source",
    "source": "immediate_previous_source",
    # Input TLCs (transformation)
    "input_traceability_lot_codes": "input_traceability_lot_codes",
    "input_tlcs": "input_traceability_lot_codes",
    "input_lots": "input_traceability_lot_codes",
    "input_lot_codes": "input_traceability_lot_codes",
    "source_lots": "input_traceability_lot_codes",
    "source_tlcs": "input_traceability_lot_codes",
    # Other
    "temperature": "temperature",
    "temp": "temperature",
    "field_name": "field_name",
    "field": "field_name",
    "growing_area": "field_name",
}

# Set of canonical KDE field names for quick lookup
_KDE_FIELDS = set(_KDE_FIELD_ALIASES.values())


def _parse_csv_to_events(csv_text: str) -> List[Dict[str, Any]]:
    """Parse CSV text into a list of event dicts matching our JSON format.

    Supports flexible header naming — maps common aliases, abbreviations,
    and spreadsheet conventions to canonical field names.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    events = []

    for row in reader:
        event: Dict[str, Any] = {"kdes": {}}
        for col, value in row.items():
            if not col or not value or not value.strip():
                continue
            col_lower = col.strip().lower().replace(" ", "_")

            # 1. Check top-level field map
            mapped = _CSV_COLUMN_MAP.get(col_lower)
            if mapped:
                if mapped == "quantity":
                    try:
                        event[mapped] = float(value.strip())
                    except ValueError:
                        event[mapped] = value.strip()
                else:
                    event[mapped] = value.strip()
                continue

            # 2. Check KDE alias map → store under canonical KDE name
            kde_canonical = _KDE_FIELD_ALIASES.get(col_lower)
            if kde_canonical:
                val = value.strip()
                # Parse comma-separated input TLCs into a list
                if kde_canonical == "input_traceability_lot_codes" and "," in val:
                    val = [t.strip() for t in val.split(",") if t.strip()]
                event["kdes"][kde_canonical] = val
                continue

            # 3. Unknown columns go into kdes as-is
            event["kdes"][col_lower] = value.strip()

        # Default timestamp if missing
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(timezone.utc).isoformat()

        if "cte_type" in event:
            events.append(event)

    return events


# ---------------------------------------------------------------------------
# Normalization (webhook event → canonical-like dict for rules engine)
# ---------------------------------------------------------------------------

def _normalize_for_rules(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a raw event dict into the canonical format expected by the rules engine.
    Maps webhook-style fields to canonical TraceabilityEvent field names.
    """
    kdes = dict(event.get("kdes", {}))
    event_type = event.get("cte_type", "")

    # Build facility references from available data
    from_facility = (
        event.get("location_gln")
        or kdes.get("ship_from_gln")
        or kdes.get("ship_from_location")
        or event.get("location_name")
    )
    to_facility = (
        kdes.get("ship_to_gln")
        or kdes.get("ship_to_location")
        or kdes.get("receiving_location")
    )

    if event_type == "shipping":
        from_facility = from_facility or event.get("location_name")
    elif event_type == "receiving":
        to_facility = to_facility or event.get("location_name") or event.get("location_gln")

    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "traceability_lot_code": event.get("traceability_lot_code", ""),
        "product_reference": event.get("product_description", ""),
        "quantity": event.get("quantity"),
        "unit_of_measure": event.get("unit_of_measure", ""),
        "event_timestamp": event.get("timestamp", ""),
        "from_facility_reference": from_facility,
        "to_facility_reference": to_facility,
        "from_entity_reference": kdes.get("ship_from_entity") or kdes.get("harvester_business_name"),
        "to_entity_reference": kdes.get("ship_to_entity") or kdes.get("immediate_previous_source"),
        "transport_reference": kdes.get("carrier") or kdes.get("transport_reference"),
        "kdes": kdes,
    }


# ---------------------------------------------------------------------------
# KDE Validation (reused from webhook_router_v2 logic)
# ---------------------------------------------------------------------------

def _detect_duplicate_lots(events: List[Dict[str, Any]]) -> Dict[int, List[str]]:
    """
    Detect duplicate traceability lot codes within the same CTE type.

    Uses (TLC, CTE type, reference_document) as the uniqueness key so that
    split shipments with different BOL/invoice numbers are NOT flagged as
    duplicates. Only flags when both TLC + CTE + ref_doc match exactly.

    Returns a mapping of event_index -> list of warning strings for the second
    and subsequent occurrences.
    """
    seen: Dict[tuple, int] = {}
    warnings: Dict[int, List[str]] = {}

    for i, event in enumerate(events):
        tlc = (event.get("traceability_lot_code") or "").strip().lower()
        cte = (event.get("cte_type") or "").strip().lower()
        if not tlc or not cte:
            continue

        # Include reference_document in key to allow split shipments
        kdes = event.get("kdes", {})
        ref_doc = (
            kdes.get("reference_document")
            or event.get("reference_document")
            or ""
        ).strip().lower()

        key = (tlc, cte, ref_doc)
        if key in seen:
            first_index = seen[key]
            original_tlc = (event.get("traceability_lot_code") or "").strip()
            original_cte = (event.get("cte_type") or "").strip()
            msg = (
                f"Duplicate lot code '{original_tlc}' for CTE type "
                f"'{original_cte}'"
            )
            if ref_doc:
                msg += f" with same reference document"
            msg += f" \u2014 row may be redundant (see event {first_index})"
            warnings.setdefault(i, []).append(msg)
        else:
            seen[key] = i

    return warnings


def _validate_kdes(event: Dict[str, Any]) -> List[str]:
    """Validate required KDEs for a raw event dict."""
    errors: List[str] = []
    cte_type_str = event.get("cte_type", "")

    try:
        cte_type = WebhookCTEType(cte_type_str)
    except ValueError:
        valid_types = [t.value for t in WebhookCTEType]
        return [f"Invalid CTE type '{cte_type_str}'. Valid types: {', '.join(valid_types)}"]

    required = REQUIRED_KDES_BY_CTE.get(cte_type, [])
    kdes = event.get("kdes", {})

    available = {
        "traceability_lot_code": event.get("traceability_lot_code"),
        "product_description": event.get("product_description"),
        "quantity": event.get("quantity"),
        "unit_of_measure": event.get("unit_of_measure"),
        "location_name": event.get("location_name"),
        "location_gln": event.get("location_gln"),
        **kdes,
    }

    for kde_name in required:
        val = available.get(kde_name)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            errors.append(f"Missing required KDE '{kde_name}' for {cte_type_str} CTE")

    return errors


# ---------------------------------------------------------------------------
# Entity Resolution Warnings
# ---------------------------------------------------------------------------

# Suffixes to strip during normalization (longer/more specific first)
_ENTITY_SUFFIXES = [
    "incorporated", "corporation", "limited", "company",
    "l.l.c.", "l.l.p.", "l.p.", "corp.", "inc.", "ltd.", "co.",
    "llc", "llp", "corp", "inc", "ltd", "co", "lp",
]

# Compiled pattern: match any suffix at end of string (preceded by whitespace or comma)
_SUFFIX_PATTERN = re.compile(
    r"[,\s]+(?:" + "|".join(re.escape(s) for s in _ENTITY_SUFFIXES) + r")\s*$",
    re.IGNORECASE,
)

# Fields to inspect explicitly
_ENTITY_FIELDS_EXPLICIT = {
    "location_name", "ship_from_location", "ship_to_location",
    "receiving_location", "from_entity_reference", "immediate_previous_source",
}

# Substrings that mark a field as entity-like
_ENTITY_FIELD_MARKERS = {"location", "entity", "source", "facility"}


def _is_entity_field(field_name: str) -> bool:
    """Return True if *field_name* is an entity-like field."""
    lower = field_name.lower()
    if lower in _ENTITY_FIELDS_EXPLICIT:
        return True
    return any(marker in lower for marker in _ENTITY_FIELD_MARKERS)


def _normalize_entity_name(name: str) -> str:
    """Normalize an entity name for comparison."""
    norm = name.lower().strip()
    # Strip common business-entity suffixes
    norm = _SUFFIX_PATTERN.sub("", norm)
    # Strip punctuation
    norm = norm.translate(str.maketrans("", "", string.punctuation))
    # Collapse internal whitespace
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


def _detect_entity_mismatches(events: List[Dict[str, Any]]) -> List[str]:
    """
    Scan all events for entity-like field values that normalize to the same
    string but differ in their original form.  Returns a list of warning
    strings, one per mismatched pair.
    """
    # normalized_form -> set of original values
    groups: Dict[str, set] = defaultdict(set)

    for event in events:
        # Top-level fields
        for field, value in event.items():
            if _is_entity_field(field) and isinstance(value, str) and value.strip():
                groups[_normalize_entity_name(value)].add(value.strip())

        # Nested kdes dict
        kdes = event.get("kdes", {})
        if isinstance(kdes, dict):
            for field, value in kdes.items():
                if _is_entity_field(field) and isinstance(value, str) and value.strip():
                    groups[_normalize_entity_name(value)].add(value.strip())

    warnings: List[str] = []
    for _norm, originals in sorted(groups.items()):
        if len(originals) < 2:
            continue
        sorted_originals = sorted(originals)
        for i in range(len(sorted_originals)):
            for j in range(i + 1, len(sorted_originals)):
                warnings.append(
                    f"Possible entity mismatch: '{sorted_originals[i]}' and "
                    f"'{sorted_originals[j]}' may refer to the same entity "
                    f"\u2014 consider standardizing"
                )
    return warnings


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class SandboxEvent(BaseModel):
    """A single event for sandbox evaluation."""
    cte_type: str = Field(..., description="CTE type (harvesting, shipping, receiving, etc.)")
    traceability_lot_code: str = Field(..., description="Traceability Lot Code")
    product_description: str = Field(default="", description="Product name")
    quantity: Optional[float] = Field(default=None, description="Quantity")
    unit_of_measure: str = Field(default="", description="Unit of measure")
    location_gln: Optional[str] = Field(default=None, description="GLN")
    location_name: Optional[str] = Field(default=None, description="Location name")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )
    kdes: Dict[str, Any] = Field(default_factory=dict, description="Additional KDEs")


class SandboxRequest(BaseModel):
    """Request body for sandbox evaluation."""
    events: Optional[List[SandboxEvent]] = Field(default=None, description="JSON events")
    csv: Optional[str] = Field(default=None, description="Raw CSV text")


class RuleResultResponse(BaseModel):
    """A single rule evaluation result."""
    rule_title: str
    severity: str
    result: str  # pass, fail, warn, skip
    why_failed: Optional[str] = None
    citation: Optional[str] = None
    remediation: Optional[str] = None
    category: str
    evidence: Optional[List[Dict[str, Any]]] = None


class EventEvaluationResponse(BaseModel):
    """Evaluation results for a single event."""
    event_index: int
    cte_type: str
    traceability_lot_code: str
    product_description: str
    kde_errors: List[str]
    rules_evaluated: int
    rules_passed: int
    rules_failed: int
    rules_warned: int
    compliant: bool
    blocking_defects: List[RuleResultResponse]
    all_results: List[RuleResultResponse]


class SandboxResponse(BaseModel):
    """Response from sandbox evaluation."""
    total_events: int
    compliant_events: int
    non_compliant_events: int
    total_kde_errors: int
    total_rule_failures: int
    submission_blocked: bool
    blocking_reasons: List[str]
    duplicate_warnings: List[str] = Field(default_factory=list, description="Warnings about duplicate lot codes within same CTE type")
    entity_warnings: List[str] = Field(default_factory=list, description="Warnings about possible entity name mismatches that may need standardization")
    events: List[EventEvaluationResponse]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/evaluate",
    response_model=SandboxResponse,
    summary="Evaluate traceability events (stateless sandbox)",
    description=(
        "Accept CTE events as JSON or CSV, run FSMA 204 KDE validation and "
        "rules evaluation, and return results. No data is persisted. "
        "No authentication required. Rate-limited to 30 requests/minute."
    ),
)
async def sandbox_evaluate(payload: SandboxRequest, request: Request) -> SandboxResponse:
    """Stateless evaluation of traceability events against FSMA 204 rules."""
    # Rate limit by IP
    client_ip = request.client.host if request.client else "unknown"
    _check_sandbox_rate_limit(client_ip)

    # Parse events from JSON or CSV
    raw_events: List[Dict[str, Any]] = []

    if payload.csv:
        try:
            raw_events = _parse_csv_to_events(payload.csv)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"CSV parsing error: {str(e)}")
        if not raw_events:
            raise HTTPException(status_code=400, detail="No valid events found in CSV. Ensure 'cte_type' column exists.")

    elif payload.events:
        for ev in payload.events:
            raw_events.append(ev.model_dump())
    else:
        raise HTTPException(status_code=400, detail="Provide either 'events' (JSON) or 'csv' (raw CSV text)")

    # Cap at 50 events per request
    if len(raw_events) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 events per sandbox request")

    # Detect duplicate lot codes within same CTE type
    dup_warnings_by_index = _detect_duplicate_lots(raw_events)
    all_duplicate_warnings: List[str] = []
    for idx in sorted(dup_warnings_by_index):
        all_duplicate_warnings.extend(dup_warnings_by_index[idx])

    # Normalize all events first (needed for relational checks)
    all_canonical: List[Dict[str, Any]] = []
    for raw_event in raw_events:
        all_canonical.append(_normalize_for_rules(raw_event))

    # Run cross-event relational validation (temporal order, identity, mass balance)
    relational_results = _evaluate_relational_in_memory(all_canonical)

    # Evaluate each event
    event_results: List[EventEvaluationResponse] = []
    total_kde_errors = 0
    total_rule_failures = 0
    compliant_count = 0
    all_blocking_reasons: List[str] = []

    for i, raw_event in enumerate(raw_events):
        canonical = all_canonical[i]

        # Step 1: KDE validation
        kde_errors = _validate_kdes(raw_event)
        total_kde_errors += len(kde_errors)

        # Step 2: Stateless per-event rules evaluation
        summary = _evaluate_event_stateless(canonical)

        # Step 3: Merge relational results for this event
        event_id = canonical.get("event_id", "")
        rel_results = relational_results.get(event_id, [])
        for rr in rel_results:
            summary.results.append(rr)
            summary.total_rules += 1
            if rr.result == "pass":
                summary.passed += 1
            elif rr.result == "fail":
                summary.failed += 1
                if rr.severity == "critical":
                    summary.critical_failures.append(rr)
            elif rr.result == "warn":
                summary.warned += 1
            else:
                summary.skipped += 1

        total_rule_failures += summary.failed

        # Build blocking defects list
        blocking = []
        for r in summary.results:
            if r.result == "fail" and r.severity == "critical":
                reason = r.why_failed or r.rule_title
                blocking.append(RuleResultResponse(
                    rule_title=r.rule_title,
                    severity=r.severity,
                    result=r.result,
                    why_failed=r.why_failed,
                    citation=r.citation_reference,
                    remediation=r.remediation_suggestion,
                    category=r.category,
                    evidence=r.evidence_fields_inspected or None,
                ))
                all_blocking_reasons.append(f"Event {i+1} ({raw_event.get('cte_type', '?')}): {reason}")

        # Inject duplicate lot warnings into kde_errors
        if i in dup_warnings_by_index:
            kde_errors.extend(dup_warnings_by_index[i])
            total_kde_errors += len(dup_warnings_by_index[i])

        is_compliant = len(kde_errors) == 0 and summary.compliant
        if is_compliant:
            compliant_count += 1

        event_results.append(EventEvaluationResponse(
            event_index=i,
            cte_type=raw_event.get("cte_type", "unknown"),
            traceability_lot_code=raw_event.get("traceability_lot_code", ""),
            product_description=raw_event.get("product_description", ""),
            kde_errors=kde_errors,
            rules_evaluated=summary.total_rules,
            rules_passed=summary.passed,
            rules_failed=summary.failed,
            rules_warned=summary.warned,
            compliant=is_compliant,
            blocking_defects=blocking,
            all_results=[
                RuleResultResponse(
                    rule_title=r.rule_title,
                    severity=r.severity,
                    result=r.result,
                    why_failed=r.why_failed,
                    citation=r.citation_reference,
                    remediation=r.remediation_suggestion,
                    category=r.category,
                    evidence=r.evidence_fields_inspected or None,
                )
                for r in summary.results
            ],
        ))

    # Deduplicate blocking reasons
    unique_blocking = list(dict.fromkeys(all_blocking_reasons))

    # Detect entity name mismatches across all events
    entity_warnings = _detect_entity_mismatches(raw_events)

    return SandboxResponse(
        total_events=len(raw_events),
        compliant_events=compliant_count,
        non_compliant_events=len(raw_events) - compliant_count,
        total_kde_errors=total_kde_errors,
        total_rule_failures=total_rule_failures,
        submission_blocked=len(unique_blocking) > 0,
        blocking_reasons=unique_blocking,
        duplicate_warnings=all_duplicate_warnings,
        entity_warnings=entity_warnings,
        events=event_results,
    )
