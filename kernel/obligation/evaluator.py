"""
Regulatory Obligation Evaluator
===============================
Core logic for evaluating decisions against regulatory obligations.
"""

from typing import List, Dict, Any, Tuple
from datetime import datetime
import re
import uuid

import structlog

from .models import (
    ObligationDefinition,
    ObligationMatch,
    ObligationEvaluationResult,
    RiskLevel
)

logger = structlog.get_logger("obligation.evaluator")


# Heuristic ReDoS detector. This does not replace a real regex engine with
# guaranteed-linear matching (``re2`` would), but it catches the textbook
# patterns flagged in #1339 (nested unbounded quantifiers, repeated
# alternations that expand ambiguously).
_REDOS_NESTED_QUANT = re.compile(
    r"""
    \(                 # open group
    [^()]*             # inside the group, no more groups
    (?:[+*]|\{\d+,\})  # unbounded or open-ended quantifier
    [^()]*
    \)                 # close group
    (?:[+*]|\{\d+,\})  # another unbounded quantifier applied to the group
    """,
    re.VERBOSE,
)

_REDOS_ALTERNATION_REPEAT = re.compile(
    r"""
    \(                           # open group
    [^()|]*                      # optional leading chars inside group, no |
    (\w+)                        # first alt
    \|                           # alternation
    \1                           # same alt repeated
    [^()]*                       # optional trailing chars inside group
    \)
    [+*]                         # applied with +/*
    """,
    re.VERBOSE,
)


def _looks_redos_prone(pattern: str) -> bool:
    """Cheap heuristic for catastrophic-backtracking patterns.

    Returns True on patterns that match either known anti-pattern:
    * ``(...+)+``, ``(...*)+``, ``(...+){n,}`` — nested unbounded
      quantifiers over a quantified body.
    * ``(a|a)*`` / ``(a|a)+`` — alternation of identical literals with a
      repeated wrapper.

    False negatives are acceptable — this is belt-and-braces on top of
    curating who authors ``obligations.yaml``. False positives are very
    rare in the ids + CFR-style citations we expect; rejecting a borderline
    pattern at load time is the safer direction.
    """
    if _REDOS_NESTED_QUANT.search(pattern):
        return True
    if _REDOS_ALTERNATION_REPEAT.search(pattern):
        return True
    return False


def _is_present(value: Any) -> bool:
    """Return True only if ``value`` represents substantive evidence.

    An FSMA 204 KDE with an empty string, whitespace-only string, empty
    list, or empty dict is **not** satisfied — the regulator expects a real
    value on every Key Data Element. Previously the evaluator treated
    anything other than ``None`` or absent keys as present, producing false
    ``met=True, risk_score=0.0`` compliance states for clearly-incomplete
    records (#1330).

    This helper is intentionally conservative:

    * ``None`` → missing
    * ``""`` / whitespace-only string → missing
    * ``[]`` / ``()`` / ``{}`` / ``set()`` → missing
    * Everything else (including ``0``, ``False``) → present

    The ``0``/``False`` carve-out preserves valid evidence like
    ``quantity=0`` or ``spoiled=False``; those are substantive facts.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    # Containers: empty means missing evidence.
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return len(value) > 0
    # Numbers / booleans / everything else — presence.
    return True


class ObligationEvaluator:
    """
    Evaluates decisions against regulatory obligations.
    
    Workflow:
    1. Load applicable obligations for decision type
    2. Check triggering conditions
    3. Verify required evidence present
    4. Compute coverage %
    5. Assign risk scores
    """
    
    def __init__(self, obligations: List[ObligationDefinition]):
        """
        Initialize evaluator with obligation definitions.

        Pre-compiles every regex triggering condition so that patterns with
        syntax errors fail loudly at load time (not silently at evaluation
        time) and per-evaluation calls don't hit the ``re`` cache for
        already-known patterns (#1339).

        Args:
            obligations: List of ObligationDefinition from obligations.yaml

        Raises:
            ValueError: If any regex pattern is syntactically invalid, or
                looks suspiciously ReDoS-prone (nested unbounded quantifiers).
        """
        self.obligations = obligations
        self.obligations_by_id = {o.id: o for o in obligations}
        self._compiled_regex: Dict[Tuple[str, str], "re.Pattern[str]"] = {}
        self._compile_all_regex_conditions()
        logger.info("evaluator_initialized", obligation_count=len(obligations))

    def _compile_all_regex_conditions(self) -> None:
        """Walk every obligation's triggering conditions and pre-compile
        regex patterns.

        Fails loudly on ``re.error`` or obviously-dangerous patterns so
        authoring bugs don't degrade to silent non-triggering (#1339).
        """
        for obligation in self.obligations:
            for key, value in obligation.triggering_conditions.items():
                if not (isinstance(value, dict) and value.get("op") == "regex"):
                    continue
                pattern = value.get("pattern", "")
                if not isinstance(pattern, str) or not pattern:
                    raise ValueError(
                        f"Obligation {obligation.id!r} has regex condition on "
                        f"{key!r} with empty/missing pattern"
                    )
                if _looks_redos_prone(pattern):
                    raise ValueError(
                        f"Obligation {obligation.id!r} regex pattern for "
                        f"{key!r} looks ReDoS-prone (nested unbounded "
                        f"quantifiers): {pattern!r}"
                    )
                try:
                    compiled = re.compile(pattern)
                except re.error as exc:
                    raise ValueError(
                        f"Obligation {obligation.id!r} regex pattern for "
                        f"{key!r} is invalid: {exc} (pattern={pattern!r})"
                    ) from exc
                self._compiled_regex[(obligation.id, key)] = compiled
    
    def evaluate_decision(
        self,
        decision_id: str,
        decision_type: str,
        decision_data: Dict[str, Any],
        vertical: str = "finance"
    ) -> ObligationEvaluationResult:
        """
        Evaluate a decision against all applicable obligations.
        
        Args:
            decision_id: Unique decision identifier
            decision_type: Type of decision (e.g., credit_denial)
            decision_data: Decision payload with evidence
            vertical: Vertical name
            
        Returns:
            ObligationEvaluationResult with coverage and matches
        """
        log = logger.bind(decision_id=decision_id, decision_type=decision_type, vertical=vertical)
        log.info("evaluation_started")
        
        # Step 1: Find applicable obligations
        applicable_obligations = self._find_applicable_obligations(
            decision_type,
            decision_data
        )
        
        log.info("applicable_obligations_found", count=len(applicable_obligations))
        
        # Step 2: Evaluate each obligation
        obligation_matches = []
        for obligation in applicable_obligations:
            match = self._evaluate_obligation(obligation, decision_data)
            obligation_matches.append(match)
        
        # Step 3: Compute metrics
        met_count = sum(1 for m in obligation_matches if m.met)
        violated_count = len(obligation_matches) - met_count
        coverage_percent = (met_count / len(obligation_matches) * 100) if obligation_matches else 100.0
        
        # Step 4: Compute overall risk score
        overall_risk_score = self._compute_overall_risk(obligation_matches)
        
        # Step 5: Determine risk level
        risk_level = self._determine_risk_level(coverage_percent, overall_risk_score)
        
        result = ObligationEvaluationResult(
            evaluation_id=str(uuid.uuid4()),
            decision_id=decision_id,
            timestamp=datetime.utcnow(),
            vertical=vertical,
            total_applicable_obligations=len(obligation_matches),
            met_obligations=met_count,
            violated_obligations=violated_count,
            coverage_percent=coverage_percent,
            overall_risk_score=overall_risk_score,
            risk_level=risk_level,
            obligation_matches=obligation_matches
        )
        
        log.info(
            "evaluation_complete",
            met=met_count,
            total=len(obligation_matches),
            coverage_pct=round(coverage_percent, 1),
            risk_level=risk_level.value
        )
        
        return result
    
    def _find_applicable_obligations(
        self,
        decision_type: str,
        decision_data: Dict[str, Any]
    ) -> List[ObligationDefinition]:
        """
        Find obligations applicable to this decision.
        
        Checks triggering_conditions to determine applicability.
        """
        applicable = []
        
        for obligation in self.obligations:
            if self._matches_triggering_conditions(obligation, decision_type, decision_data):
                applicable.append(obligation)
        
        return applicable
    
    def _matches_triggering_conditions(
        self,
        obligation: ObligationDefinition,
        decision_type: str,
        decision_data: Dict[str, Any]
    ) -> bool:
        """
        Check if obligation's triggering conditions are met.
        
        Triggering conditions are AND-ed together.
        """
        conditions = obligation.triggering_conditions

        # Iterate every condition. ``decision_type`` is a special-case key
        # because it's not stored inside ``decision_data`` — it arrives as a
        # separate argument — but it still supports the dict-with-op extended
        # operators (range/regex).
        for key, expected_value in conditions.items():
            if key == "decision_type":
                actual_value: Any = decision_type
            else:
                actual_value = decision_data.get(key)

            # Extended condition operators: dict with "op" key triggers structured evaluation.
            if isinstance(expected_value, dict) and "op" in expected_value:
                op = expected_value["op"]
                if op == "range":
                    # {"op": "range", "min": <number>, "max": <number>}
                    # Passes when min <= actual_value <= max (inclusive).
                    try:
                        numeric = float(actual_value)  # type: ignore[arg-type]
                    except (TypeError, ValueError):
                        return False
                    lo = expected_value.get("min")
                    hi = expected_value.get("max")
                    if lo is not None and numeric < float(lo):
                        return False
                    if hi is not None and numeric > float(hi):
                        return False
                elif op == "regex":
                    # {"op": "regex", "pattern": "<pattern>"}
                    # Passes when the string value matches the regex pattern.
                    if not isinstance(actual_value, str):
                        return False
                    compiled = self._compiled_regex.get((obligation.id, key))
                    if compiled is None:
                        # Patterns are compiled eagerly at __init__. If we
                        # reach this branch the author bypassed the loader —
                        # fail closed loudly rather than silently letting an
                        # obligation never trigger (#1339).
                        logger.error(
                            "triggering_condition_uncompiled_regex",
                            obligation_id=obligation.id,
                            key=key,
                        )
                        return False
                    if not compiled.search(actual_value):
                        return False
                else:
                    logger.warning("triggering_condition_unknown_op", key=key, op=op)
                    return False
            else:
                # Plain equality check (original behaviour preserved).
                if actual_value != expected_value:
                    return False

        return True
    
    def _evaluate_obligation(
        self,
        obligation: ObligationDefinition,
        decision_data: Dict[str, Any]
    ) -> ObligationMatch:
        """
        Evaluate a single obligation against decision data.
        
        Checks if all required evidence fields are present.
        """
        missing_evidence = []

        for required_field in obligation.required_evidence:
            if required_field not in decision_data:
                missing_evidence.append(required_field)
            elif not _is_present(decision_data[required_field]):
                # Empty strings, whitespace-only strings, empty containers —
                # all count as missing per FSMA 204 KDE requirements (#1330).
                missing_evidence.append(required_field)
        
        met = len(missing_evidence) == 0
        
        # Compute risk score based on missing evidence.
        # Score is proportional to the fraction of missing evidence fields,
        # ranging from 0.0 (all evidence present) to 1.0 (all evidence missing).
        # LOW risk (score < 0.3) is a valid output when only a small fraction
        # of evidence is absent; no artificial floor is applied.
        if met:
            risk_score = 0.0
        else:
            missing_ratio = len(missing_evidence) / len(obligation.required_evidence)
            risk_score = min(1.0, missing_ratio)
        
        return ObligationMatch(
            obligation_id=obligation.id,
            citation=obligation.citation,
            regulator=obligation.regulator,
            domain=obligation.domain,
            met=met,
            missing_evidence=missing_evidence,
            risk_score=risk_score
        )
    
    def _compute_overall_risk(self, obligation_matches: List[ObligationMatch]) -> float:
        """
        Compute overall risk score from individual obligation matches.
        
        Uses weighted average, with higher weight on higher individual risk scores.
        """
        if not obligation_matches:
            return 0.0
        
        total_risk = sum(m.risk_score for m in obligation_matches)
        avg_risk = total_risk / len(obligation_matches)
        
        return avg_risk
    
    def _determine_risk_level(self, coverage_percent: float, overall_risk_score: float) -> RiskLevel:
        """
        Determine risk level based on coverage and risk score.
        
        Thresholds:
        - coverage >= 90% AND risk < 0.3: LOW
        - coverage >= 70% AND risk < 0.5: MEDIUM
        - coverage >= 50% AND risk < 0.7: HIGH
        - Otherwise: CRITICAL
        """
        if coverage_percent >= 90 and overall_risk_score < 0.3:
            return RiskLevel.LOW
        elif coverage_percent >= 70 and overall_risk_score < 0.5:
            return RiskLevel.MEDIUM
        elif coverage_percent >= 50 and overall_risk_score < 0.7:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL
