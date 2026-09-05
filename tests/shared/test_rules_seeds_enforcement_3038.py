"""Seed-level enforcement regression — #3038 / #3041.

The per-CTE negative tests (#1133) build *synthetic* ``field_presence``
rules, so they prove the engine works while saying nothing about the
production seeds. That gap is exactly how #3038 survived: every date
rule in ``FSMA_RULE_SEEDS`` listed ``event_timestamp`` as an acceptable
alternate, and canonical events always carry ``event_timestamp``, so
the seeded date rules could never fail.

These tests run the **actual seeds** through the engine:

- an event with only the envelope ``event_timestamp`` must FAIL its
  CTE's date rule (#3038);
- quantity without unit of measure must FAIL (#3041);
- a 13-digit GLN with a bad check digit must FAIL, and a location
  *description* must not trip the GLN rule (#3041);
- initial packing without a harvester phone must FAIL even with an
  unresolved entity reference (#3041).
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Dict

import pytest
from shared.rules.engine import RulesEngine
from shared.rules.seeds import FSMA_RULE_SEEDS
from shared.rules.types import RuleDefinition


def _seed_rules() -> list[RuleDefinition]:
    """Materialize the production seed dicts as engine rule objects."""
    rules = []
    for i, seed in enumerate(FSMA_RULE_SEEDS):
        rules.append(
            RuleDefinition(
                rule_id=f"seed-{i}",
                rule_version=1,
                title=seed["title"],
                description=seed.get("description"),
                severity=seed["severity"],
                category=seed["category"],
                applicability_conditions=seed.get("applicability_conditions", {}),
                citation_reference=seed.get("citation_reference"),
                effective_date=date(2026, 1, 1),
                retired_date=None,
                evaluation_logic=seed["evaluation_logic"],
                failure_reason_template=seed["failure_reason_template"],
                remediation_suggestion=seed.get("remediation_suggestion"),
            )
        )
    return rules


def _engine() -> RulesEngine:
    engine = RulesEngine.__new__(RulesEngine)
    engine.session = None
    engine._cache_ttl_seconds = 60
    engine._rules_cache = _seed_rules()
    engine._rules_cache_loaded_at = time.monotonic()
    return engine


def _event(event_type: str, kdes: Dict[str, Any] | None = None, **overrides: Any) -> Dict[str, Any]:
    """FTL-covered canonical-shaped event with the envelope timestamp
    every canonical event carries — the exact shape that used to
    satisfy the date rules vacuously."""
    body: Dict[str, Any] = {
        "event_id": f"evt-{event_type}",
        "event_type": event_type,
        "event_timestamp": "2026-04-14T10:30:00+00:00",
        "traceability_lot_code": "TLC-1",
        "product_reference": "Romaine Lettuce",
        "quantity": 100.0,
        "unit_of_measure": "cases",
        "ftl_covered": True,
        "ftl_category": "Leafy Greens",
        "from_facility_reference": "Acme Farms Packing Shed",
        "kdes": kdes or {},
    }
    body.update(overrides)
    return body


def _results_by_title(engine: RulesEngine, event: Dict[str, Any]):
    summary = engine.evaluate_event(event)
    return {r.rule_title: r for r in summary.results}


# (cte_type, date rule title, kde field)
_DATE_RULES = [
    ("receiving", "Receiving: Receive Date Required", "receive_date"),
    ("shipping", "Shipping: Ship Date Required", "ship_date"),
    ("harvesting", "Harvesting: Harvest Date Required", "harvest_date"),
    ("initial_packing", "Initial Packing: Packing Date Required", "packing_date"),
    ("transformation", "Transformation: Transformation Date Required", "transformation_date"),
    ("cooling", "Cooling: Cooling Date Required", "cooling_date"),
    ("first_land_based_receiving", "First Land-Based Receiving: Landing Date Required", "landing_date"),
]


@pytest.mark.parametrize(
    "cte_type,rule_title,kde_field",
    _DATE_RULES,
    ids=[c for c, _, _ in _DATE_RULES],
)
def test_envelope_timestamp_alone_fails_date_rule(cte_type: str, rule_title: str, kde_field: str):
    """#3038 core regression: event_timestamp must NOT satisfy a date KDE."""
    engine = _engine()
    results = _results_by_title(engine, _event(cte_type))
    assert rule_title in results, f"seed rule {rule_title!r} did not run for {cte_type}"
    assert results[rule_title].result == "fail", (
        f"{rule_title} passed on an event whose only date is the envelope event_timestamp — the #3038 tautology is back"
    )


@pytest.mark.parametrize(
    "cte_type,rule_title,kde_field",
    _DATE_RULES,
    ids=[c for c, _, _ in _DATE_RULES],
)
def test_kde_date_passes_date_rule(cte_type: str, rule_title: str, kde_field: str):
    engine = _engine()
    results = _results_by_title(engine, _event(cte_type, kdes={kde_field: "2026-04-14"}))
    assert results[rule_title].result == "pass"


def test_quantity_without_unit_of_measure_fails():
    """#3041: the rule's title promises both fields; logic must too."""
    engine = _engine()
    event = _event("receiving", kdes={"receive_date": "2026-04-14"})
    event.pop("unit_of_measure")
    results = _results_by_title(engine, event)
    verdict = results["Quantity and Unit of Measure Required"]
    assert verdict.result == "fail"
    assert "unit of measure" in (verdict.why_failed or "")


def test_quantity_with_unit_of_measure_passes():
    engine = _engine()
    results = _results_by_title(engine, _event("receiving", kdes={"receive_date": "2026-04-14"}))
    assert results["Quantity and Unit of Measure Required"].result == "pass"


def test_gln_with_invalid_check_digit_fails():
    """#3041: 13 digits with a wrong check digit used to pass the regex."""
    engine = _engine()
    results = _results_by_title(
        engine,
        _event("receiving", kdes={"receive_date": "2026-04-14"}, from_facility_reference="0614141000004"),
    )
    assert results["GLN Format Validation"].result == "fail"


def test_gln_with_valid_check_digit_passes():
    engine = _engine()
    results = _results_by_title(
        engine,
        _event("receiving", kdes={"receive_date": "2026-04-14"}, from_facility_reference="0614141000005"),
    )
    assert results["GLN Format Validation"].result == "pass"


def test_location_description_skips_gln_rule():
    """A business-name facility reference is not a GLN — no false fail."""
    engine = _engine()
    results = _results_by_title(engine, _event("receiving", kdes={"receive_date": "2026-04-14"}))
    assert results["GLN Format Validation"].result == "skip"


def test_initial_packing_without_harvester_phone_fails():
    """#3041: §1.1330(a)(7) requires the harvester phone number."""
    engine = _engine()
    results = _results_by_title(
        engine,
        _event(
            "initial_packing",
            kdes={"packing_date": "2026-04-14", "harvester_business_name": "Acme Farms"},
        ),
    )
    assert results["Initial Packing: Harvester Phone Required"].result == "fail"


def test_initial_packing_with_harvester_phone_passes():
    engine = _engine()
    results = _results_by_title(
        engine,
        _event(
            "initial_packing",
            kdes={
                "packing_date": "2026-04-14",
                "harvester_business_name": "Acme Farms",
                "harvester_business_phone": "+1-555-0100",
            },
        ),
    )
    assert results["Initial Packing: Harvester Phone Required"].result == "pass"


def test_no_seed_date_rule_accepts_event_timestamp():
    """Structural guard: no date-KDE seed may list event_timestamp as an
    acceptable alternate ever again."""
    for seed in FSMA_RULE_SEEDS:
        logic = seed["evaluation_logic"]
        fields = (logic.get("params") or {}).get("fields", [])
        if any(f.endswith("_date") for f in [logic.get("field", ""), *fields]):
            assert "event_timestamp" not in fields, (
                f"seed {seed['title']!r} lists event_timestamp as an alternate for a date KDE — #3038 regression"
            )


def test_entity_reference_cannot_replace_harvester_phone():
    results = _results_by_title(_engine(), _event("initial_packing", from_entity_reference="entity-1"))
    assert results["Initial Packing: Harvester Phone Required"].result == "fail"
