"""
Backward-compatibility shim — all code has moved to shared.rules package.

Existing imports like ``from shared.rules_engine import RulesEngine`` continue
to work. New code should import from ``shared.rules`` directly.

Package layout:
    shared/rules/types.py          — data types
    shared/rules/engine.py         — RulesEngine class
    shared/rules/seeds.py          — FSMA_RULE_SEEDS + seed_rule_definitions
    shared/rules/uom.py            — UOM conversion
    shared/rules/evaluators/       — stateless + relational evaluators
"""

# Re-export everything so existing callers don't break
from shared.rules.types import (  # noqa: F401
    RuleDefinition,
    RuleEvaluationResult,
    EvaluationSummary,
)
from shared.rules.engine import RulesEngine  # noqa: F401
from shared.rules.seeds import (  # noqa: F401
    FSMA_RULE_SEEDS,
    seed_rule_definitions,
)
from shared.rules.uom import (  # noqa: F401
    normalize_to_lbs as _normalize_to_lbs,
    CTE_LIFECYCLE_ORDER as _CTE_LIFECYCLE_ORDER,
)
from shared.rules.utils import get_nested_value as _get_nested_value  # noqa: F401
from shared.rules.evaluators.stateless import (  # noqa: F401
    EVALUATORS as _EVALUATORS,
    evaluate_field_presence as _evaluate_field_presence,
    evaluate_field_format as _evaluate_field_format,
    evaluate_multi_field_presence as _evaluate_multi_field_presence,
)
from shared.rules.evaluators.relational import (  # noqa: F401
    RELATIONAL_EVALUATORS as _RELATIONAL_EVALUATORS,
    fetch_related_events as _fetch_related_events,
    evaluate_temporal_order as _evaluate_temporal_order,
    evaluate_identity_consistency as _evaluate_identity_consistency,
    evaluate_mass_balance as _evaluate_mass_balance,
)
