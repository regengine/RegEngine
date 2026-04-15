"""
FSMA 204 Versioned Rules Engine — modular package.

Split from the original monolithic rules_engine.py (1,547 lines) into:
    rules/types.py          — RuleDefinition, RuleEvaluationResult, EvaluationSummary
    rules/utils.py          — get_nested_value helper
    rules/uom.py            — UOM conversion table, CTE lifecycle ordering
    rules/evaluators/
        stateless.py        — field_presence, field_format, multi_field_presence
        relational.py       — temporal_order, identity_consistency, mass_balance
    rules/engine.py         — RulesEngine class (load, evaluate, persist)
    rules/seeds.py          — FSMA_RULE_SEEDS data + seed_rule_definitions()

All public names are re-exported here for backward compatibility:
    from shared.rules import RulesEngine, FSMA_RULE_SEEDS, seed_rule_definitions
"""

from shared.rules.types import RuleDefinition, RuleEvaluationResult, EvaluationSummary
from shared.rules.engine import RulesEngine
from shared.rules.seeds import FSMA_RULE_SEEDS, seed_rule_definitions
from shared.rules.uom import normalize_to_lbs, CTE_LIFECYCLE_ORDER

__all__ = [
    "RuleDefinition",
    "RuleEvaluationResult",
    "EvaluationSummary",
    "RulesEngine",
    "FSMA_RULE_SEEDS",
    "seed_rule_definitions",
    "normalize_to_lbs",
    "CTE_LIFECYCLE_ORDER",
]
