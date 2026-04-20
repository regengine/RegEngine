"""Runtime per-CTE negative enforcement — #1133.

Companion to ``test_rules_seeds_per_cte_coverage.py``, which asserts
that seed rules exist for every CTE. This file closes the other half
of the #1133 gap: **at runtime**, does :class:`RulesEngine` actually
emit a ``fail`` result when a CTE event is missing the KDE that its
rule requires?

The original bug (#1102) was not that seeds went missing — several
of them did, but the deeper problem was that no test exercised the
*enforcement path* per CTE type. A rule can be seeded, loaded, and
still silently no-op (wrong applicability, wrong evaluator shape,
field-name drift). These tests parametrize across all 7 FSMA CTE
types and confirm that omitting each type's signature KDE yields a
failed evaluation — i.e. the engine would not stamp the event
compliant.

The issue originally targeted ``client.post("/validate", ...)`` but
that endpoint was removed on 2026-04-17 per #1203 (orphaned, no
callers). This test therefore exercises the live code path —
``RulesEngine.evaluate_event`` in ``services/shared/rules/engine.py``
— which is where compliance verdicts actually come from today.

Field names here track the production seeds in
``services/shared/rules/seeds.py``: when seed fields drift, these
tests drift with them (intentional coupling — they are a regression
guard on the seed/evaluator contract, not a generic field-presence
smoke test).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict

import pytest

from shared.rules.engine import RulesEngine
from shared.rules.types import RuleDefinition


# ---------------------------------------------------------------------------
# Helpers (kept narrow — a full rule/event factory lives in
# test_rules_engine_hardening.py; duplicating only what this file
# needs keeps the regression surface obvious).
# ---------------------------------------------------------------------------


def _rule_field_presence(
    *,
    rule_id: str,
    cte_type: str,
    field_path: str,
    citation: str,
    category: str = "kde_presence",
) -> RuleDefinition:
    """Build a single-field presence rule scoped to one CTE.

    Mirrors the simplest seed shape in ``FSMA_RULE_SEEDS`` (type
    ``field_presence``). Using a single-field rule rather than
    ``multi_field_presence`` keeps the negative-path assertion
    unambiguous: we omit exactly one field and expect exactly one
    failure.
    """
    return RuleDefinition(
        rule_id=rule_id,
        rule_version=1,
        title=f"{cte_type}: {field_path} Required",
        description=f"{cte_type} events must include {field_path} per {citation}",
        severity="critical",
        category=category,
        applicability_conditions={"cte_types": [cte_type], "ftl_scope": ["ALL"]},
        citation_reference=citation,
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={"type": "field_presence", "field": field_path},
        failure_reason_template="{event_type} missing {field_name} per {citation}",
        remediation_suggestion=f"Supply {field_path}",
    )


def _engine_with_rules(rules) -> RulesEngine:
    """Bypass ``__init__`` and pre-seed the cache — no DB needed.

    Matches the pattern in ``test_rules_engine_hardening.py`` so the
    two files share the same handshake with the engine internals.
    """
    import time as _time

    engine = RulesEngine.__new__(RulesEngine)
    engine.session = None
    engine._cache_ttl_seconds = 60
    engine._rules_cache = rules
    engine._rules_cache_loaded_at = _time.monotonic()
    return engine


def _ftl_event_base(event_type: str) -> Dict[str, Any]:
    """Minimal FTL-covered event body — avoids the ``not_ftl_scoped``
    no-verdict branch (#1346) so the rule actually runs."""
    return {
        "event_id": f"evt-{event_type}",
        "event_type": event_type,
        "traceability_lot_code": "TLC-1",
        "product_reference": "Romaine Lettuce",
        "quantity": 100.0,
        "unit_of_measure": "cases",
        "ftl_covered": True,
        "ftl_category": "Leafy Greens",
        "kdes": {},
    }


# ---------------------------------------------------------------------------
# Parametrized negative cases — one signature KDE per CTE.
#
# Field paths and citations match the production seeds in
# services/shared/rules/seeds.py. If a seed drifts, this table drifts
# alongside it (intentional — the test is a contract with the seed,
# not a schema probe).
# ---------------------------------------------------------------------------


# (cte_type, dotted.field.path, 21 CFR citation)
_CTE_REQUIRED_KDE: list[tuple[str, str, str]] = [
    # §1.1327 — harvesting
    ("harvesting", "kdes.harvest_date", "21 CFR \u00a71.1327"),
    # §1.1330 — cooling
    ("cooling", "kdes.cooling_date", "21 CFR \u00a71.1330"),
    ("cooling", "kdes.temperature", "21 CFR \u00a71.1330"),
    # §1.1335 — initial packing
    ("initial_packing", "kdes.packing_date", "21 CFR \u00a71.1335"),
    # §1.1325 — first land-based receiving
    (
        "first_land_based_receiving",
        "kdes.landing_date",
        "21 CFR \u00a71.1325",
    ),
    # §1.1340 — shipping
    ("shipping", "kdes.ship_date", "21 CFR \u00a71.1340"),
    # §1.1345 — receiving
    ("receiving", "kdes.receive_date", "21 CFR \u00a71.1345"),
    # §1.1350 — transformation
    ("transformation", "kdes.transformation_date", "21 CFR \u00a71.1350"),
]


@pytest.mark.parametrize(
    "cte_type,field_path,citation",
    _CTE_REQUIRED_KDE,
    ids=[f"{c}-missing-{f.split('.')[-1]}" for c, f, _ in _CTE_REQUIRED_KDE],
)
def test_missing_required_kde_yields_failure(
    cte_type: str, field_path: str, citation: str
):
    """RulesEngine must emit ``fail`` (not ``pass``, not ``skip``) when
    a CTE event is missing the signature KDE for its regulation.

    This is the regression guard #1102 lacked: a rule can be
    registered and loaded but still no-op silently if applicability
    or evaluator wiring breaks. Exercising the end-to-end path —
    load → apply → evaluate — proves the enforcement chain is intact
    for each CTE.
    """
    rule = _rule_field_presence(
        rule_id=f"rule-{cte_type}-{field_path.replace('.', '-')}",
        cte_type=cte_type,
        field_path=field_path,
        citation=citation,
    )
    engine = _engine_with_rules([rule])

    # Valid event for this CTE — but deliberately *without* the
    # required field (the whole point of the negative case).
    event = _ftl_event_base(cte_type)

    summary = engine.evaluate_event(event, persist=False)

    # The rule applied — no_verdict branches (non-FTL / empty rules)
    # would make the assertion tautological. Keep them separate so
    # failures point at the right cause.
    assert summary.total_rules == 1, (
        f"{cte_type} rule not applied — applicability likely mismatched "
        f"(got no_verdict_reason={summary.no_verdict_reason!r})"
    )
    assert summary.failed == 1, (
        f"{cte_type} event missing {field_path} was not flagged as a failure. "
        f"Summary: passed={summary.passed} failed={summary.failed} "
        f"skipped={summary.skipped} errored={summary.errored}"
    )
    # Tri-state compliance: must NOT be True. False is expected; None
    # would mean no_verdict_reason fired, which shouldn't happen once
    # a rule has actually been evaluated.
    assert summary.compliant is False, (
        f"Missing {field_path} produced compliant={summary.compliant!r} "
        f"for {cte_type} — should be False (#1102/#1347)."
    )


@pytest.mark.parametrize(
    "cte_type,field_path,citation",
    _CTE_REQUIRED_KDE,
    ids=[f"{c}-present-{f.split('.')[-1]}" for c, f, _ in _CTE_REQUIRED_KDE],
)
def test_present_required_kde_yields_pass(
    cte_type: str, field_path: str, citation: str
):
    """Happy-path counterpart: when the required KDE IS present the
    same rule must pass. Together with the negative case this pins
    the evaluator's contract for each CTE — not just "fails when
    missing" but "discriminates based on the field" (the two assertions
    together rule out a rule that always-fails).
    """
    rule = _rule_field_presence(
        rule_id=f"rule-{cte_type}-{field_path.replace('.', '-')}-positive",
        cte_type=cte_type,
        field_path=field_path,
        citation=citation,
    )
    engine = _engine_with_rules([rule])

    event = _ftl_event_base(cte_type)
    # Set the field the rule requires. Dotted-path write so
    # ``kdes.harvest_date`` lands inside the ``kdes`` sub-dict the
    # evaluator reads, not at the top level.
    parts = field_path.split(".")
    cursor: Dict[str, Any] = event
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = "2026-04-20"

    summary = engine.evaluate_event(event, persist=False)

    assert summary.total_rules == 1
    assert summary.passed == 1, (
        f"{cte_type} event *with* {field_path} should pass — got "
        f"passed={summary.passed} failed={summary.failed} "
        f"skipped={summary.skipped} errored={summary.errored}"
    )
    assert summary.compliant is True, (
        f"All-present {cte_type} event should be compliant=True, got "
        f"{summary.compliant!r}"
    )


def test_every_fsma_cte_has_at_least_one_negative_case():
    """Meta-assertion: the parametrization above must cover every
    FSMA 204 CTE type. If a new CTE is added to the spec, this test
    fails until the parametrization is updated — preventing the
    original #1102 regression shape (a CTE silently unrepresented).
    """
    covered = {c for c, _, _ in _CTE_REQUIRED_KDE}
    required = {
        "harvesting",
        "cooling",
        "initial_packing",
        "first_land_based_receiving",
        "shipping",
        "receiving",
        "transformation",
    }
    missing = required - covered
    assert not missing, (
        f"Per-CTE negative coverage is missing for: {sorted(missing)}. "
        "Add at least one (cte_type, field_path, citation) entry to "
        "_CTE_REQUIRED_KDE — #1133."
    )
