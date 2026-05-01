"""
Sandbox evaluation logic — stateless per-event and in-memory relational
(cross-event) evaluators.

Moved from sandbox_router.py. Both evaluator types share in-memory context
so they live in the same module.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from shared.rules_engine import (
    RuleDefinition,
    RuleEvaluationResult,
    EvaluationSummary,
    _CTE_LIFECYCLE_ORDER,
    _EVALUATORS,
    _normalize_to_lbs,
)

from app.sandbox.rule_loader import _SANDBOX_RULES, _get_applicable_rules


# Relational evaluation types handled by _evaluate_relational_in_memory
_RELATIONAL_EVAL_TYPES = {"temporal_order", "identity_consistency", "mass_balance"}


def _evaluate_event_stateless(
    event_data: Dict[str, Any],
    *,
    include_custom: bool = False,
) -> EvaluationSummary:
    """Evaluate an event against all applicable stateless rules (no DB).

    Relational rules (temporal_order, identity_consistency, mass_balance) are
    excluded here — they are evaluated separately by _evaluate_relational_in_memory
    which has access to the full event batch.
    """
    event_type = event_data.get("event_type", "")
    event_id = event_data.get("event_id", str(uuid4()))

    applicable = _get_applicable_rules(event_type, include_custom=include_custom)
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
            # #1354 — unknown eval_type must fail, not silently skip.
            result = RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                rule_title=rule.title,
                severity=rule.severity,
                result="error",
                why_failed=f"Unknown evaluation type: {eval_type}",
                category=rule.category,
            )
        else:
            try:
                result = evaluator(event_data, logic, rule)
                if (
                    result.result == "fail"
                    and result.severity == "warning"
                    and result.category == "operational_quality"
                ):
                    result.result = "warn"
            except Exception as e:
                # #1354 — evaluator crashes must not fail-open as "skip".
                result = RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    rule_title=rule.title,
                    severity=rule.severity,
                    result="error",
                    why_failed=f"Evaluator crashed ({type(e).__name__}): {str(e)}",
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
        elif result.result == "error":
            summary.errored += 1
            if result.severity == "critical":
                summary.critical_failures.append(result)
        elif result.result == "not_ftl_scoped":
            summary.not_ftl_scoped += 1
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

    # -----------------------------------------------------------------------
    # Cross-TLC Mass Balance for Transformations
    # A transformation event consumes input TLCs and produces an output TLC.
    # Sum input TLC quantities, compare against transformation output quantity.
    # -----------------------------------------------------------------------
    mass_rule = relational_rules.get("mass_balance")
    if mass_rule:
        tolerance = mass_rule.evaluation_logic.get("params", {}).get("tolerance_percent", 1.0)

        for evt in all_canonical:
            if evt.get("event_type") != "transformation":
                continue

            input_tlcs = evt.get("kdes", {}).get("input_traceability_lot_codes", [])
            if isinstance(input_tlcs, str):
                input_tlcs = [t.strip() for t in input_tlcs.split(",") if t.strip()]
            if not input_tlcs:
                continue

            output_qty = evt.get("quantity")
            output_uom = evt.get("unit_of_measure", "")
            if output_qty is None:
                continue
            output_qty = float(output_qty)

            # Sum input quantities from events matching input TLCs
            total_input = 0.0
            input_units: set = set()
            for input_tlc in input_tlcs:
                for other in tlc_groups.get(input_tlc, []):
                    oq = other.get("quantity")
                    ou = other.get("unit_of_measure", "")
                    if oq is not None:
                        total_input += float(oq)
                        if ou:
                            input_units.add(ou.lower().strip())

            if total_input == 0:
                continue  # No input quantities found — skip

            # Check UOM compatibility
            all_units = set(input_units)
            if output_uom:
                all_units.add(output_uom.lower().strip())

            use_converted = False
            if len(all_units) > 1:
                # Try UOM conversion
                converted_input = 0.0
                all_ok = True
                for input_tlc in input_tlcs:
                    for other in tlc_groups.get(input_tlc, []):
                        oq = other.get("quantity")
                        ou = other.get("unit_of_measure", "")
                        if oq is not None and ou:
                            lbs = _normalize_to_lbs(float(oq), ou)
                            if lbs is None:
                                all_ok = False
                                break
                            converted_input += lbs
                    if not all_ok:
                        break

                converted_output = _normalize_to_lbs(output_qty, output_uom) if output_uom else None
                if all_ok and converted_output is not None:
                    use_converted = True
                    total_input = converted_input
                    output_qty = converted_output

            evidence = [{
                "tlc": evt.get("traceability_lot_code", ""),
                "input_tlcs": input_tlcs,
                "total_input": total_input,
                "total_output": output_qty,
                "tolerance_percent": tolerance,
                "units_seen": list(all_units),
                "uom_converted": use_converted,
                "check_type": "cross_tlc_transformation",
            }]

            if output_qty > total_input * (1 + tolerance / 100):
                max_allowed = total_input * (1 + tolerance / 100)
                results[evt["event_id"]].append(RuleEvaluationResult(
                    rule_id=mass_rule.rule_id,
                    rule_version=mass_rule.rule_version,
                    rule_title=mass_rule.title,
                    severity=mass_rule.severity,
                    result="fail",
                    why_failed=(
                        f"Mass balance violation for transformation "
                        f"'{evt.get('traceability_lot_code', '')}': "
                        f"output ({output_qty}) exceeds combined input from "
                        f"{', '.join(input_tlcs)} ({total_input}) "
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
