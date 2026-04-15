"""Rule evaluator dispatch tables."""

from shared.rules.evaluators.stateless import EVALUATORS
from shared.rules.evaluators.relational import RELATIONAL_EVALUATORS

__all__ = ["EVALUATORS", "RELATIONAL_EVALUATORS"]
