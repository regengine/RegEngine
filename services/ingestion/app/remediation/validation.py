"""Deterministic parsing + validation for supplier CSV manifests.

Reuses the sandbox column-alias maps and the stateless rules evaluators
(``_evaluate_event_stateless`` returns a real ``EvaluationSummary`` from
in-memory ``FSMA_RULE_SEEDS`` — no DB rule seeding needed).

Design constraints from the remediation PRD:
- Never invent facts: no default timestamps, no dropped rows, unparseable
  values stay raw and fail validation instead of being replaced.
- Every safe normalization (trim/case/UoM alias/CTE alias/date format) is
  recorded in per-field provenance.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from ..csv_templates import _normalize_uom, _parse_date_flexible
from ..sandbox.csv_parser import (
    _CSV_COLUMN_MAP,
    _CTE_TYPE_ALIASES,
    _KDE_FIELD_ALIASES,
    _KDE_FIELDS,
    _normalize_for_rules,
)
from ..sandbox.evaluators import _evaluate_event_stateless
from ..sandbox.rule_loader import _SANDBOX_RULES
from ..sandbox.validation import _validate_kdes

# Top-level canonical event fields; everything else lives under kdes.*
_TOP_LEVEL_FIELDS = {
    "cte_type",
    "traceability_lot_code",
    "product_description",
    "quantity",
    "unit_of_measure",
    "location_name",
    "location_gln",
    "timestamp",
}

_DATE_KDE_RE = re.compile(r"^[a-z_]*date$")
_KDE_ERROR_FIELD_RE = re.compile(r"KDE '([a-z_]+)'")

# The versioned ruleset identity for this validation path: the in-memory
# sandbox rules built from FSMA_RULE_SEEDS.
RULESET_HASH: str = hashlib.sha256(
    json.dumps(
        sorted((r.title, r.rule_version) for r in _SANDBOX_RULES),
        separators=(",", ":"),
    ).encode()
).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def row_fingerprint(raw_row: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(raw_row).encode()).hexdigest()


def _field_path(canonical: str) -> str:
    return canonical if canonical in _TOP_LEVEL_FIELDS else f"kdes.{canonical}"


def build_event_from_row(
    raw_row: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Map one verbatim CSV row into the canonical event dict.

    Returns (event, field_provenance, service_failures). Unlike the sandbox
    parser this never drops a row and never injects a default timestamp.
    """
    event: Dict[str, Any] = {"kdes": {}}
    provenance: Dict[str, Any] = {}
    service_failures: List[Dict[str, Any]] = []

    def _record(field_path: str, source_column: str, raw_value: str, value: Any, rule: Optional[str]) -> None:
        provenance[field_path] = {
            "source_column": source_column,
            "raw_value": raw_value,
            "value": value,
            "source": "auto_normalization" if rule else "csv",
            **({"rule": rule} if rule else {}),
        }

    for col, raw_value in raw_row.items():
        if col is None or raw_value is None:
            continue
        col_lower = col.strip().lower().replace(" ", "_")
        stripped = raw_value.strip() if isinstance(raw_value, str) else raw_value
        if stripped == "" or stripped is None:
            continue
        trim_rule = "trim_whitespace" if stripped != raw_value else None

        mapped = _CSV_COLUMN_MAP.get(col_lower)
        if mapped:
            value: Any = stripped
            rule = trim_rule
            if mapped == "quantity":
                try:
                    value = float(stripped)
                    if not math.isfinite(value):
                        raise ValueError("non-finite quantity")
                except (TypeError, ValueError):
                    service_failures.append(
                        _service_failure(
                            "invalid_quantity",
                            field="quantity",
                            source_column=col,
                            why=f"Quantity '{stripped}' is not a finite number.",
                            remediation="Provide a positive numeric quantity.",
                        )
                    )
                    value = stripped
            elif mapped == "unit_of_measure":
                normalized = _normalize_uom(str(stripped))
                if normalized != stripped:
                    rule = "uom_alias"
                value = normalized
            elif mapped == "cte_type":
                cte_lower = str(stripped).strip().lower().replace(" ", "_").replace("-", "_")
                canonical_cte = _CTE_TYPE_ALIASES.get(cte_lower, cte_lower)
                if canonical_cte != stripped:
                    rule = "cte_type_alias"
                value = canonical_cte
            elif mapped == "timestamp":
                value, rule = _normalize_date(stripped, col, "timestamp", trim_rule, service_failures)
            event[mapped] = value
            _record(_field_path(mapped), col, str(raw_value), value, rule)
            continue

        kde = _KDE_FIELD_ALIASES.get(col_lower)
        target = kde or col_lower
        value = stripped
        rule = trim_rule
        if kde and _DATE_KDE_RE.match(kde):
            value, rule = _normalize_date(stripped, col, f"kdes.{kde}", trim_rule, service_failures)
        event["kdes"][target] = value
        _record(f"kdes.{target}", col, str(raw_value), value, rule)

    if isinstance(event.get("quantity"), float) and event["quantity"] <= 0:
        service_failures.append(
            _service_failure(
                "invalid_quantity",
                field="quantity",
                source_column="quantity",
                why=f"Quantity {event['quantity']} must be greater than zero.",
                remediation="Provide a positive numeric quantity.",
            )
        )

    tlc = event.get("traceability_lot_code")
    if isinstance(tlc, str) and 0 < len(tlc) < 3:
        # The canonical model requires >= 3 chars; catch it here so it blocks
        # with an intelligible reason instead of crashing at release time.
        service_failures.append(
            _service_failure(
                "invalid_tlc",
                field="traceability_lot_code",
                source_column=None,
                why=f"Traceability lot code '{tlc}' is too short (minimum 3 characters).",
                remediation="Provide the full traceability lot code (at least 3 characters).",
            )
        )

    return event, provenance, service_failures


def _normalize_date(
    stripped: str,
    source_column: str,
    field_path: str,
    trim_rule: Optional[str],
    service_failures: List[Dict[str, Any]],
) -> Tuple[str, Optional[str]]:
    """Parse a date deterministically; unparseable values stay raw and fail."""
    iso_ts, warning = _parse_date_flexible(str(stripped))
    if warning is not None:
        service_failures.append(
            _service_failure(
                "invalid_date",
                field=field_path,
                source_column=source_column,
                why=f"Date '{stripped}' could not be parsed: {warning}.",
                remediation="Provide the date as YYYY-MM-DD.",
            )
        )
        return str(stripped), trim_rule
    if iso_ts != stripped:
        return iso_ts, "date_format"
    return iso_ts, trim_rule


def _service_failure(
    check: str,
    *,
    field: str,
    source_column: Optional[str],
    why: str,
    remediation: str,
    severity: str = "critical",
) -> Dict[str, Any]:
    return {
        "issue_id": f"svc:{check}:{field}",
        "rule_id": f"svc.{check}",
        "rule_version": 1,
        "rule_title": f"Service check: {check.replace('_', ' ')}",
        "severity": severity,
        "category": "service_check",
        "result": "fail" if severity == "critical" else "warn",
        "why_failed": why,
        "remediation": remediation,
        "source": "service",
        "field": field,
        "source_column": source_column,
        "remediation_owner": "supplier",
        "auto_resolvable": False,
    }


def check_product_alias(
    db, tenant_id: str, event: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Supplier-scoped product-code alias check against fsma.entity_aliases.

    A known alias is a previously approved mapping (recorded in provenance);
    an unknown code is a blocking exception — never guessed.
    """
    code = (event.get("kdes") or {}).get("product_code")
    if not code:
        return [], None
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT entity_id FROM fsma.entity_aliases
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND alias_type IN ('internal_code', 'trade_name')
              AND alias_value = :alias_value
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "alias_value": str(code)},
    ).fetchone()
    if row:
        applied = {
            "field": "kdes.product_code",
            "source": "approved_mapping",
            "rule": "entity_alias",
            "entity_id": str(row[0]),
        }
        return [], applied
    return [
        _service_failure(
            "unknown_product_alias",
            field="kdes.product_code",
            source_column="product_code",
            why=f"Product code '{code}' is not an approved alias for this supplier.",
            remediation="Use an approved product code, or ask the buyer to approve this alias.",
        )
    ], None


def validate_event(event: Dict[str, Any]) -> Tuple[List[str], Any]:
    """Run KDE completeness + stateless rules. Returns (kde_errors, summary)."""
    kde_errors = _validate_kdes(event)
    canonical = _normalize_for_rules(event)
    summary = _evaluate_event_stateless(canonical, include_custom=False)
    return kde_errors, summary


def snapshot_failures(
    kde_errors: List[str],
    summary: Any,
    service_failures: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str], bool]:
    """Normalize all validation output into FR-3 issue records.

    Returns (failures, warnings, blocking). ``blocking`` mirrors the
    supplier-portal preflight definition: any KDE error, any critical rule
    failure, or any critical service-check failure.
    """
    failures: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for err in kde_errors:
        match = _KDE_ERROR_FIELD_RE.search(err)
        field = match.group(1) if match else None
        field_path = _field_path(field) if field else None
        failures.append(
            {
                "issue_id": f"kde:{field or 'row'}",
                "rule_id": "kde.completeness",
                "rule_version": 1,
                "rule_title": "Required KDE completeness",
                "severity": "critical",
                "category": "kde_presence",
                "result": "fail",
                "why_failed": err,
                "remediation": "Provide the missing key data element.",
                "source": "kde",
                "field": field_path,
                "source_column": None,
                "remediation_owner": "supplier",
                "auto_resolvable": False,
            }
        )

    for rule in summary.results:
        if rule.result == "error" or (rule.result == "fail" and rule.severity == "critical"):
            # 'error' is treated as FAIL regardless of severity (#1354 —
            # skipping would be fail-open, unsafe for a regulatory stamp).
            failures.append(_rule_failure(rule, result="fail"))
        elif rule.result in ("fail", "warn"):
            warnings.append(f"[{rule.rule_title}] {rule.why_failed or ''}".strip())

    for svc in service_failures:
        if svc["severity"] == "critical":
            failures.append(svc)
        else:
            warnings.append(f"[{svc['rule_title']}] {svc['why_failed']}")

    # De-duplicate by issue_id (a missing field can trip both the KDE check
    # and a seed rule; keep the first, most specific record).
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for f in failures:
        if f["issue_id"] in seen:
            continue
        seen.add(f["issue_id"])
        deduped.append(f)

    return deduped, warnings, bool(deduped)


def _rule_failure(rule: Any, *, result: str) -> Dict[str, Any]:
    fields = rule.evidence_fields_inspected or []
    field: Optional[str] = None
    for candidate in fields:
        if isinstance(candidate, str):
            field = candidate
            break
        if isinstance(candidate, dict) and isinstance(candidate.get("field"), str):
            field = candidate["field"]
            break
    return {
        "issue_id": f"rule:{rule.rule_title}",
        "rule_id": rule.rule_id,
        "rule_version": rule.rule_version,
        "rule_title": rule.rule_title,
        "severity": rule.severity,
        "category": rule.category,
        "result": result,
        "why_failed": rule.why_failed or rule.rule_title,
        "remediation": rule.remediation_suggestion,
        "source": "rule",
        "field": field,
        "source_column": None,
        "remediation_owner": "supplier",
        "auto_resolvable": False,
    }


# Canonical-rules field names → correctable event-dict field paths.
_RULE_FIELD_TO_EVENT_PATH = {
    "traceability_lot_code": "traceability_lot_code",
    "product_reference": "product_description",
    "quantity": "quantity",
    "from_facility_reference": "location_name",
    "to_facility_reference": "kdes.receiving_location",
    "ftl_covered": "product_description",
}


def correctable_fields(failures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Derive the default supplier-correctable field list from failures.

    Only real event fields become correctable: top-level canonical fields,
    explicit ``kdes.*`` paths, or known KDE names. Anything else (row-level
    findings like duplicates, unmapped rules-engine internals) is skipped —
    a fabricated path would let a junk value launder an uncorrectable
    failure through revalidation.
    """
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for f in failures:
        field = f.get("field")
        if not isinstance(field, str) or not field:
            continue
        field = _RULE_FIELD_TO_EVENT_PATH.get(field, field)
        if field in _TOP_LEVEL_FIELDS or field.startswith("kdes."):
            pass
        elif field in _KDE_FIELDS:
            field = f"kdes.{field}"
        else:
            continue
        if field in seen:
            continue
        seen.add(field)
        out.append(
            {
                "field_path": field,
                "reason": f["why_failed"],
                "expected_format": f.get("remediation") or "See failure reason.",
                "issue_id": f["issue_id"],
            }
        )
    return out
