"""
Relational rule evaluators — 5-arg functions
(event_data, logic, rule, session, *, tenant_id).

These evaluators perform cross-event validation by querying the database
for related events on the same traceability lot code.

Security (#1344):
    tenant_id is ALWAYS sourced from the authenticated request context
    (passed in as a kwarg by the engine). ANY tenant_id field embedded
    in event_data is IGNORED — a malicious or buggy caller could embed
    another tenant's id and cause cross-tenant reads from the related-
    events lookup.

    The only tenant_id an evaluator is allowed to act on is the kwarg.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.rules.container_factors import ContainerFactorResolver
from shared.rules.types import RuleDefinition, RuleEvaluationResult
from shared.rules.uom import (
    CONTAINER_UOMS,
    COUNT_UOMS,
    CTE_LIFECYCLE_ORDER,
    UnitConversionError,
    normalize_to_lbs_strict,
)

logger = logging.getLogger("rules-engine.relational")


def _resolve_tenant(
    event_data: Dict[str, Any],
    session_tenant_id: Optional[str],
    rule: RuleDefinition,
) -> Optional[str]:
    """Return the authenticated tenant_id, or None if unavailable.

    Logs a security alert if event_data contains a tenant_id that does
    NOT match the session tenant — that is a forged-payload attempt or
    a caller bug, and either way we treat the session value as ground
    truth.
    """
    if not session_tenant_id:
        return None
    payload_tid = event_data.get("tenant_id")
    if payload_tid and str(payload_tid) != str(session_tenant_id):
        logger.warning(
            "rules_engine_tenant_mismatch",
            extra={
                "rule_id": rule.rule_id,
                "session_tenant_id": str(session_tenant_id),
                "payload_tenant_id": str(payload_tid),
                "note": (
                    "event_data.tenant_id differs from authenticated "
                    "tenant — payload value ignored (#1344)"
                ),
            },
        )
    return str(session_tenant_id)


def fetch_related_events(
    session: Session,
    traceability_lot_code: str,
    tenant_id: str,
    exclude_event_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch all ACTIVE events for the same TLC + tenant.

    Returns list of dicts with event_id, event_type, event_timestamp,
    product_reference, quantity, unit_of_measure.
    """
    query = text("""
        SELECT event_id, event_type, event_timestamp,
               product_reference, quantity, unit_of_measure
        FROM fsma.traceability_events
        WHERE traceability_lot_code = :tlc
          AND tenant_id = :tenant_id
          AND status = 'active'
          AND (:exclude_id IS NULL OR event_id != CAST(:exclude_id AS uuid))
        ORDER BY event_timestamp ASC
    """)
    rows = session.execute(query, {
        "tlc": traceability_lot_code,
        "tenant_id": tenant_id,
        "exclude_id": exclude_event_id,
    }).fetchall()

    return [
        {
            "event_id": str(r[0]),
            "event_type": r[1],
            "event_timestamp": r[2],
            "product_reference": r[3],
            "quantity": float(r[4]) if r[4] is not None else None,
            "unit_of_measure": r[5],
        }
        for r in rows
    ]


def evaluate_temporal_order(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
    session: Session,
    *,
    tenant_id: Optional[str] = None,
) -> RuleEvaluationResult:
    """Detect chronology paradoxes -- e.g. shipping before harvesting.

    #1344 — tenant_id MUST come from the caller (authenticated context).
    Any tenant_id in event_data is ignored.
    """
    tlc = event_data.get("traceability_lot_code", "")
    event_id = event_data.get("event_id", "")
    auth_tid = _resolve_tenant(event_data, tenant_id, rule)

    if not tlc or not auth_tid:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="skip",
            why_failed=(
                "Missing TLC or authenticated tenant context for temporal check"
            ),
            category=rule.category,
        )

    related = fetch_related_events(session, tlc, auth_tid, str(event_id))
    if not related:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", category=rule.category,
            evidence_fields_inspected=[{"note": "No related events for TLC", "tlc": tlc}],
        )

    current_type = event_data.get("event_type", "")
    current_ts = event_data.get("event_timestamp")
    if isinstance(current_ts, str):
        current_ts = datetime.fromisoformat(current_ts.replace("Z", "+00:00"))

    current_stage = CTE_LIFECYCLE_ORDER.get(current_type)
    if current_stage is None:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="skip", why_failed=f"Unknown CTE type: {current_type}",
            category=rule.category,
        )

    violations = []
    for evt in related:
        other_type = evt["event_type"]
        other_stage = CTE_LIFECYCLE_ORDER.get(other_type)
        if other_stage is None:
            continue

        other_ts = evt["event_timestamp"]
        if isinstance(other_ts, str):
            other_ts = datetime.fromisoformat(other_ts.replace("Z", "+00:00"))

        if other_stage < current_stage and other_ts > current_ts:
            violations.append({
                "earlier_stage": other_type,
                "earlier_timestamp": str(other_ts),
                "later_stage": current_type,
                "later_timestamp": str(current_ts),
                "event_id": evt["event_id"],
            })
        elif other_stage > current_stage and other_ts < current_ts:
            violations.append({
                "earlier_stage": current_type,
                "earlier_timestamp": str(current_ts),
                "later_stage": other_type,
                "later_timestamp": str(other_ts),
                "event_id": evt["event_id"],
            })

    if violations:
        v = violations[0]
        why = (
            f"Chronology paradox for TLC '{tlc}': {v['later_stage']} "
            f"(at {v['later_timestamp']}) occurs before {v['earlier_stage']} "
            f"(at {v['earlier_timestamp']}). "
            f"CTE events must follow the supply chain lifecycle order "
            f"({rule.citation_reference or '21 CFR §1.1310'})."
        )
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="fail", why_failed=why,
            evidence_fields_inspected=violations,
            citation_reference=rule.citation_reference,
            remediation_suggestion=rule.remediation_suggestion,
            category=rule.category,
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id, rule_version=rule.rule_version,
        rule_title=rule.title, severity=rule.severity,
        result="pass", category=rule.category,
        evidence_fields_inspected=[{
            "tlc": tlc, "events_checked": len(related),
            "current_stage": current_type,
        }],
    )


def evaluate_identity_consistency(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
    session: Session,
    *,
    tenant_id: Optional[str] = None,
) -> RuleEvaluationResult:
    """Detect product identity drift -- same TLC changing product mid-chain.

    #1344 — tenant_id MUST come from the caller (authenticated context).
    """
    tlc = event_data.get("traceability_lot_code", "")
    event_id = event_data.get("event_id", "")
    current_product = event_data.get("product_reference")
    auth_tid = _resolve_tenant(event_data, tenant_id, rule)

    if not current_product or not tlc or not auth_tid:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="skip",
            why_failed=(
                "Missing product_reference, TLC, or authenticated tenant "
                "context for identity check"
            ),
            category=rule.category,
        )

    related = fetch_related_events(session, tlc, auth_tid, str(event_id))
    if not related:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", category=rule.category,
            evidence_fields_inspected=[{"note": "No related events for TLC", "tlc": tlc}],
        )

    normalized_current = " ".join(current_product.strip().lower().split())
    mismatches = []

    for evt in related:
        other_product = evt.get("product_reference")
        if not other_product:
            continue
        normalized_other = " ".join(other_product.strip().lower().split())
        if normalized_other != normalized_current:
            mismatches.append({
                "event_id": evt["event_id"],
                "event_type": evt["event_type"],
                "product_reference": other_product,
                "current_product": current_product,
            })

    if mismatches:
        m = mismatches[0]
        why = (
            f"Product identity changed for TLC '{tlc}': "
            f"'{m['product_reference']}' (at {m['event_type']}) vs "
            f"'{current_product}' (current event). "
            f"The same TLC must refer to the same product throughout the supply chain "
            f"({rule.citation_reference or '21 CFR §1.1310(a)'})."
        )
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="fail", why_failed=why,
            evidence_fields_inspected=mismatches,
            citation_reference=rule.citation_reference,
            remediation_suggestion=rule.remediation_suggestion,
            category=rule.category,
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id, rule_version=rule.rule_version,
        rule_title=rule.title, severity=rule.severity,
        result="pass", category=rule.category,
        evidence_fields_inspected=[{
            "tlc": tlc, "events_checked": len(related),
            "product": current_product,
        }],
    )


def evaluate_mass_balance(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
    session: Session,
    *,
    tenant_id: Optional[str] = None,
) -> RuleEvaluationResult:
    """Detect mass balance violations -- output exceeding input for same TLC.

    #1344 — tenant_id MUST come from the caller (authenticated context).
    """
    tlc = event_data.get("traceability_lot_code", "")
    event_id = event_data.get("event_id", "")
    current_quantity = event_data.get("quantity")
    current_uom = event_data.get("unit_of_measure", "")
    current_type = event_data.get("event_type", "")
    auth_tid = _resolve_tenant(event_data, tenant_id, rule)

    if not tlc or not auth_tid or current_quantity is None:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="skip",
            why_failed=(
                "Missing TLC, authenticated tenant context, or quantity for "
                "mass balance check"
            ),
            category=rule.category,
        )

    related = fetch_related_events(session, tlc, auth_tid, str(event_id))
    if not related:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", category=rule.category,
            evidence_fields_inspected=[{"note": "No related events for TLC", "tlc": tlc}],
        )

    tolerance_percent = logic.get("params", {}).get("tolerance_percent", 1.0)

    input_types = {"harvesting", "receiving", "first_land_based_receiving"}
    output_types = {"shipping"}

    # #1362 — collect every (qty, uom, product, etype) up-front so we can
    # convert everything into a common base (lbs) and fail-closed if any
    # one entry can't be converted. The old code silently fell back to
    # cross-unit arithmetic when normalize_to_lbs returned None, which
    # produced nonsensical totals like "10 cases" + "100 lbs" = 110.
    all_entries: List[tuple] = [(
        float(current_quantity),
        current_uom,
        event_data.get("product_reference"),
        current_type,
    )]
    units_seen = set()
    if current_uom:
        units_seen.add(current_uom.lower().strip())

    for evt in related:
        evt_qty = evt.get("quantity")
        evt_uom = evt.get("unit_of_measure", "")
        if evt_qty is None:
            continue
        if evt_uom:
            units_seen.add(evt_uom.lower().strip())
        all_entries.append((
            float(evt_qty),
            evt_uom,
            evt.get("product_reference"),
            evt["event_type"],
        ))

    # Detect whether ANY entry requires a per-product container factor.
    # If so we need a resolver; otherwise we can short-circuit and avoid
    # the DB roundtrip.
    needs_factor = any(
        (uom or "").strip().lower().rstrip(".") in (CONTAINER_UOMS | COUNT_UOMS)
        for _, uom, _, _ in all_entries
    )
    factor_resolver = ContainerFactorResolver(session) if needs_factor else None

    # Convert every entry into lbs. A single unconvertible entry aborts
    # the whole rule with result="error" — we refuse to stamp a mass-
    # balance verdict on partially-convertible inputs (#1362 / #1363).
    total_input = 0.0
    total_output = 0.0
    converted_rows: List[Dict[str, Any]] = []
    try:
        for qty, uom, product_ref, etype in all_entries:
            lbs = normalize_to_lbs_strict(
                qty,
                uom,
                container_resolver=factor_resolver,
                product_reference=product_ref,
                tenant_id=auth_tid,
            )
            converted_rows.append({
                "event_type": etype,
                "quantity": qty,
                "uom": uom,
                "product_reference": product_ref,
                "lbs": lbs,
            })
            if etype in input_types:
                total_input += lbs
            elif etype in output_types:
                total_output += lbs
    except UnitConversionError as exc:
        logger.warning(
            "mass_balance_conversion_failed",
            extra={
                "rule_id": rule.rule_id,
                "tlc": tlc,
                "tenant_id": auth_tid,
                "value": exc.value,
                "from_unit": exc.from_unit,
                "reason": exc.reason,
            },
        )
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            # #1362 — fail-closed: a non-convertible line-item means we
            # cannot produce a mass-balance verdict. `errored` is tallied
            # into summary.errored, which forces summary.compliant=False
            # (see types.py). No silent pass.
            result="error",
            why_failed=(
                f"Mass balance check cannot complete for TLC '{tlc}': "
                f"could not convert {exc.value} {exc.from_unit!r} to lbs "
                f"(reason: {exc.reason}). Configure a container factor "
                f"for this product/UoM in product_container_factors, or "
                f"record quantities in a direct mass unit (lbs/kg/oz/tons)."
            ),
            evidence_fields_inspected=[{
                "tlc": tlc,
                "units_seen": sorted(units_seen),
                "events_checked": len(related) + 1,
                "conversion_failure": {
                    "value": exc.value,
                    "from_unit": exc.from_unit,
                    "reason": exc.reason,
                },
            }],
            citation_reference=rule.citation_reference,
            remediation_suggestion=(
                "Seed fsma.product_container_factors with a factor for this "
                "(tenant_id, product_reference, uom) triple, or change the "
                "rule to only apply to direct-mass UoMs."
            ),
            category=rule.category,
        )

    evidence = [{
        "tlc": tlc,
        "total_input_lbs": total_input,
        "total_output_lbs": total_output,
        "tolerance_percent": tolerance_percent,
        "units_seen": sorted(units_seen),
        "events_checked": len(related) + 1,
        "uom_converted": True,
        "rows": converted_rows,
    }]

    if total_input == 0 and total_output > 0:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="warn",
            why_failed=(
                f"Mass balance check for TLC '{tlc}': "
                f"output quantity ({total_output}) recorded but no input events found. "
                f"Input events (harvesting/receiving) may not yet be recorded."
            ),
            evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            category=rule.category,
        )

    max_allowed = total_input * (1 + tolerance_percent / 100)
    if total_output > max_allowed:
        why = (
            f"Mass balance violation for TLC '{tlc}': "
            f"total output ({total_output}) exceeds total input ({total_input}) "
            f"by more than {tolerance_percent}% tolerance "
            f"(max allowed: {max_allowed:.2f}). "
            f"({rule.citation_reference or '21 CFR §1.1310'})."
        )
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="fail", why_failed=why,
            evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            remediation_suggestion=rule.remediation_suggestion,
            category=rule.category,
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id, rule_version=rule.rule_version,
        rule_title=rule.title, severity=rule.severity,
        result="pass", category=rule.category,
        evidence_fields_inspected=evidence,
    )


# Relational evaluator dispatch -- 4-arg (event_data, logic, rule, session)
RELATIONAL_EVALUATORS = {
    "temporal_order": evaluate_temporal_order,
    "identity_consistency": evaluate_identity_consistency,
    "mass_balance": evaluate_mass_balance,
}
