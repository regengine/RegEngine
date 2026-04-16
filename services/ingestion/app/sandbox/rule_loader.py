"""
Sandbox rule loading — build RuleDefinition objects from FSMA_RULE_SEEDS
without touching the database.

Moved from sandbox_router.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from shared.rules_engine import (
    FSMA_RULE_SEEDS,
    RuleDefinition,
)


# ---------------------------------------------------------------------------
# Demo custom business rules — showcase the paid product's rule builder
# ---------------------------------------------------------------------------

_DEMO_CUSTOM_RULES: List[Dict[str, Any]] = [
    {
        "title": "Cold Chain: Temperature Must Be Recorded",
        "description": "Custom rule: cooling and receiving events should include a temperature reading to verify cold chain integrity",
        "severity": "warning",
        "category": "custom_business_rule",
        "applicability_conditions": {"cte_types": ["cooling", "receiving"]},
        "citation_reference": "Custom Rule",
        "evaluation_logic": {"type": "field_presence", "field": "kdes.temperature"},
        "failure_reason_template": "No temperature recorded for {cte_type} event — cold chain cannot be verified",
        "remediation_suggestion": "Record temperature at time of cooling/receiving (e.g., 34°F). Configure threshold alerts in RegEngine's rule builder.",
    },
    {
        "title": "Supplier Certification: Harvester Must Be Named",
        "description": "Custom rule: harvesting events should identify the farm or grower business for supplier verification",
        "severity": "warning",
        "category": "custom_business_rule",
        "applicability_conditions": {"cte_types": ["harvesting"]},
        "citation_reference": "Custom Rule",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.harvester_business_name",
            "params": {"fields": ["kdes.harvester_business_name", "from_entity_reference"]},
        },
        "failure_reason_template": "Harvesting event missing grower/farm name — cannot verify supplier certification",
        "remediation_suggestion": "Record the harvester business name. Use RegEngine's supplier portal to manage certifications.",
    },
    {
        "title": "Reference Doc: Every Shipment Needs a BOL",
        "description": "Custom rule: shipping events must include a bill of lading or reference document for audit trail",
        "severity": "warning",
        "category": "custom_business_rule",
        "applicability_conditions": {"cte_types": ["shipping"]},
        "citation_reference": "Custom Rule",
        "evaluation_logic": {"type": "field_presence", "field": "kdes.reference_document"},
        "failure_reason_template": "Shipping event missing reference document (BOL) — audit trail incomplete",
        "remediation_suggestion": "Record the BOL, invoice, or purchase order number. RegEngine can auto-generate reference IDs.",
    },
    {
        "title": "Field Traceability: Growing Area Required",
        "description": "Custom rule: harvesting events should specify the field or growing area for precise trace-back",
        "severity": "warning",
        "category": "custom_business_rule",
        "applicability_conditions": {"cte_types": ["harvesting"]},
        "citation_reference": "Custom Rule",
        "evaluation_logic": {"type": "field_presence", "field": "kdes.field_name"},
        "failure_reason_template": "Harvesting event missing field/growing area — trace-back to specific plot not possible",
        "remediation_suggestion": "Record the field name, growing area, or ranch block. Enables precise recall boundaries.",
    },
]


def _build_rules_from_seeds(
    *,
    include_custom: bool = False,
) -> List[RuleDefinition]:
    """Build RuleDefinition objects from FSMA_RULE_SEEDS without touching the database."""
    seeds = list(FSMA_RULE_SEEDS)
    if include_custom:
        seeds.extend(_DEMO_CUSTOM_RULES)

    rules = []
    for i, seed in enumerate(seeds):
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
_SANDBOX_RULES_WITH_CUSTOM = _build_rules_from_seeds(include_custom=True)


def _get_applicable_rules(
    event_type: str,
    *,
    include_custom: bool = False,
) -> List[RuleDefinition]:
    """Filter sandbox rules to those applicable to the given event type."""
    rules = _SANDBOX_RULES_WITH_CUSTOM if include_custom else _SANDBOX_RULES
    applicable = []
    for rule in rules:
        cte_types = rule.applicability_conditions.get("cte_types", [])
        if not cte_types or event_type in cte_types or "all" in cte_types:
            applicable.append(rule)
    return applicable
