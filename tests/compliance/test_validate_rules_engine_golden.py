"""Golden tests for the /validate → rules-engine rewire (#1203 option 2, WS-9).

The compliance ``POST /validate`` endpoint must derive its verdicts from
``services/shared/rules`` — not from a local contract check. These tests
compare the endpoint's verdict against a *direct* engine evaluation of the
same mapped event with the same rule set, so any drift between the endpoint
mapping and the engine's semantics fails here.

The rule fixture is built from the built-in ``FSMA_RULE_SEEDS`` (stateless
rules only — relational rules require cross-event database state that a
hypothetical /validate config, by definition, does not have). The engine's
``load_active_rules`` is patched to return the fixture so no database is
needed; the endpoint's DB dependency is overridden with a stub session.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# No importorskip here (#3248): this module runs in the blocking
# repo-root-suite gate, where a skipped suite exits 0 and proves nothing.
# fastapi and httpx are pinned in requirements.lock; the import below fails
# collection loudly if either is missing.
from fastapi.testclient import TestClient  # noqa: E402


def _stateless_seed_rules():
    """Materialize RuleDefinitions from the built-in seeds (stateless only)."""
    from shared.rules.evaluators.stateless import EVALUATORS
    from shared.rules.seeds import FSMA_RULE_SEEDS
    from shared.rules.types import RuleDefinition

    rules = []
    for index, seed in enumerate(FSMA_RULE_SEEDS):
        if seed["evaluation_logic"].get("type") not in EVALUATORS:
            continue
        rules.append(
            RuleDefinition(
                rule_id=f"seed-{index}",
                rule_version=1,
                title=seed["title"],
                description=seed.get("description"),
                severity=seed["severity"],
                category=seed["category"],
                applicability_conditions=seed["applicability_conditions"],
                citation_reference=seed.get("citation_reference"),
                effective_date=date(2026, 1, 1),
                retired_date=None,
                evaluation_logic=seed["evaluation_logic"],
                failure_reason_template=seed["failure_reason_template"],
                remediation_suggestion=seed.get("remediation_suggestion"),
            )
        )
    assert rules, "seed fixture must contain stateless rules"
    return rules


@pytest.fixture
def seeded_engine_rules(monkeypatch):
    """Patch RulesEngine.load_active_rules to the seed-derived fixture."""
    from shared.rules.engine import RulesEngine

    rules = _stateless_seed_rules()
    monkeypatch.setattr(RulesEngine, "load_active_rules", lambda self: rules)
    return rules


@pytest.fixture
def validate_client(monkeypatch, seeded_engine_rules):
    """TestClient with mocked auth and a stub DB session for /validate."""
    monkeypatch.setenv("COMPLIANCE_API_KEY", "test-compliance-key")

    from shared import auth as shared_auth
    from shared.database import get_db_session

    store = shared_auth.APIKeyStore()
    tenant_id = str(uuid4())
    raw_key, _ = store.create_key("golden", tenant_id=tenant_id)
    monkeypatch.setattr(shared_auth, "_key_store", store, raising=False)

    from services.compliance.main import app

    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    try:
        yield TestClient(app), raw_key, tenant_id
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def _direct_engine_summary(config, commodity, tenant_id):
    """Evaluate the same config directly against the engine (the golden)."""
    from shared.rules.engine import RulesEngine

    from services.compliance.app.routes import _config_to_engine_event

    event = _config_to_engine_event(config, commodity)
    engine = RulesEngine(MagicMock())
    return engine.evaluate_event(event, persist=False, tenant_id=tenant_id)


COMPLETE_HARVESTING_CONFIG = {
    "cte_type": "HARVESTING",
    "tlc": "TLC-GOLDEN-001",
    "quantity": 120,
    "unit_of_measure": "case",
    "product_description": "romaine lettuce",
    "kdes": {
        "harvest_date": "2026-07-01",
        "harvest_location_ref": "FIELD-12",
        "harvester_business_name": "Golden Farms LLC",
        "reference_document": "HARVEST-LOG-2026-07-01",
    },
    "from_facility_reference": "FARM-GLN-0001",
}

INCOMPLETE_HARVESTING_CONFIG = {
    "cte_type": "HARVESTING",
    "tlc": "TLC-GOLDEN-002",
    # harvest_date / harvest_location_ref / from_facility_reference omitted
    "quantity": 40,
    "unit_of_measure": "case",
    "product_description": "cut romaine",
}


class TestValidateGoldenAgainstEngine:
    """Endpoint verdicts must match direct engine evaluation exactly."""

    @pytest.mark.parametrize(
        "config",
        [COMPLETE_HARVESTING_CONFIG, INCOMPLETE_HARVESTING_CONFIG],
        ids=["complete-harvesting", "incomplete-harvesting"],
    )
    def test_endpoint_verdict_matches_direct_engine(self, validate_client, config):
        client, api_key, tenant_id = validate_client
        commodity = "leafy greens"

        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={"ftl_commodity": commodity, "config": config},
        )
        assert resp.status_code == 200
        payload = resp.json()

        summary = _direct_engine_summary(config, commodity, tenant_id)

        # Verdict parity: the endpoint's boolean is the engine's tri-state
        # collapsed fail-closed (None -> False).
        assert payload["valid"] == (summary.compliant is True)
        assert payload["rules_evaluated"] == summary.total_rules
        assert payload["no_verdict_reason"] == summary.no_verdict_reason

        # Issue parity: every engine fail/error surfaces as an error, every
        # warn as a warning (non-strict).
        expected_errors = summary.failed + summary.errored
        expected_warnings = summary.warned
        assert len(payload["errors"]) == expected_errors
        assert len(payload["warnings"]) == expected_warnings

        # Errors carry rule provenance back to the engine's rule ids.
        engine_failed_ids = {
            r.rule_id for r in summary.results if r.result in ("fail", "error")
        }
        endpoint_failed_ids = {e["rule_id"] for e in payload["errors"]}
        assert endpoint_failed_ids == engine_failed_ids

    def test_incomplete_config_fails_with_kde_rules(self, validate_client):
        """The incomplete config must actually exercise failing KDE rules."""
        client, api_key, _ = validate_client

        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={
                "ftl_commodity": "leafy greens",
                "config": INCOMPLETE_HARVESTING_CONFIG,
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["valid"] is False
        assert payload["rules_evaluated"] > 0
        codes = {e["code"] for e in payload["errors"]}
        assert "RULE_FAILED" in codes
        # Issues carry the FSMA citation through from the rule definition.
        assert any(e.get("citation_reference") for e in payload["errors"])

    def test_complete_config_passes(self, validate_client):
        client, api_key, _ = validate_client

        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={
                "ftl_commodity": "leafy greens",
                "config": COMPLETE_HARVESTING_CONFIG,
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["valid"] is True, payload["errors"]
        assert payload["rules_evaluated"] > 0
        assert payload["errors"] == []


class TestValidateFailClosed:
    """No-verdict and unavailable-DB paths must never produce a green stamp."""

    def test_no_rules_loaded_is_not_valid(self, validate_client, monkeypatch):
        from shared.rules.engine import RulesEngine

        monkeypatch.setattr(RulesEngine, "load_active_rules", lambda self: [])
        client, api_key, _ = validate_client

        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={
                "ftl_commodity": "leafy greens",
                "config": COMPLETE_HARVESTING_CONFIG,
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["valid"] is False
        assert payload["rules_evaluated"] == 0
        assert payload["no_verdict_reason"] == "no_rules_loaded"
        assert any(e["code"] == "NO_VERDICT" for e in payload["errors"])

    def test_db_unavailable_returns_503(self, validate_client):
        from shared.database import get_db_session

        from services.compliance.main import app

        client, api_key, _ = validate_client
        app.dependency_overrides[get_db_session] = lambda: None

        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={
                "ftl_commodity": "leafy greens",
                "config": COMPLETE_HARVESTING_CONFIG,
            },
        )
        assert resp.status_code == 503

    def test_invalid_cte_type_is_structured_error(self, validate_client):
        client, api_key, _ = validate_client

        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={
                "ftl_commodity": "leafy greens",
                "config": {"cte_type": "NOT_A_CTE", "tlc": "TLC-X"},
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["valid"] is False
        assert payload["errors"][0]["code"] == "INVALID_CTE_TYPE"


class TestValidateStrictMode:
    """strict=true escalates engine warnings to errors (legacy contract)."""

    def test_strict_escalates_warnings(self, validate_client, monkeypatch):
        from shared.rules.engine import RulesEngine
        from shared.rules.types import RuleDefinition

        # One passing rule plus one warn-class rule (severity=warning,
        # category=operational_quality — the engine downgrades its "fail"
        # to "warn").
        warn_rule = RuleDefinition(
            rule_id="warn-1",
            rule_version=1,
            title="Operational: recommended field",
            description=None,
            severity="warning",
            category="operational_quality",
            applicability_conditions={"cte_types": ["harvesting"], "ftl_scope": ["ALL"]},
            citation_reference=None,
            effective_date=date(2026, 1, 1),
            retired_date=None,
            evaluation_logic={"type": "field_presence", "field": "kdes.lot_size_unit"},
            failure_reason_template="Missing {field_name}",
            remediation_suggestion="Add the field",
        )
        pass_rule = RuleDefinition(
            rule_id="pass-1",
            rule_version=1,
            title="TLC required",
            description=None,
            severity="critical",
            category="kde_presence",
            applicability_conditions={"cte_types": ["harvesting"], "ftl_scope": ["ALL"]},
            citation_reference=None,
            effective_date=date(2026, 1, 1),
            retired_date=None,
            evaluation_logic={"type": "field_presence", "field": "traceability_lot_code"},
            failure_reason_template="Missing {field_name}",
            remediation_suggestion=None,
        )
        monkeypatch.setattr(
            RulesEngine, "load_active_rules", lambda self: [pass_rule, warn_rule]
        )

        client, api_key, _ = validate_client
        base = {
            "ftl_commodity": "leafy greens",
            "config": {"cte_type": "HARVESTING", "tlc": "TLC-STRICT-1"},
        }

        lenient = client.post(
            "/validate", headers={"X-RegEngine-API-Key": api_key}, json=base
        ).json()
        assert lenient["valid"] is True
        assert len(lenient["warnings"]) == 1
        assert lenient["warnings"][0]["code"] == "RULE_WARNING"

        strict = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={**base, "strict": True},
        ).json()
        assert strict["valid"] is False
        assert strict["warnings"] == []
        assert strict["errors"][0]["code"] == "STRICT_MODE_WARNING"
