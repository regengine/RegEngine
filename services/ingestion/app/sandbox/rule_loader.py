"""
Sandbox rule loading — build RuleDefinition objects from FSMA_RULE_SEEDS
without touching the database.

Moved from sandbox_router.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from shared.rules_engine import (
    FSMA_RULE_SEEDS,
    RuleDefinition,
)


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
