"""Tests for the /validate endpoint (rules-engine backed, #1203 option 2).

WS-9 rewired /validate from a local 8-field contract check to the versioned
rules engine in ``services/shared/rules`` — verdicts now derive from the
active rule definitions, and issues carry rule provenance (rule_id, CFR
citation, remediation). This suite covers the endpoint behaviors through
that path with a deterministic in-memory ruleset (``load_active_rules`` is
patched; no ``fsma.rule_definitions`` table is required):

- Happy path: KDE-complete configs pass; verdicts are engine-derived
  (``rules_evaluated`` > 0).
- KDE-presence failures: incomplete configs fail with RULE_FAILED issues
  carrying the engine's field paths and citations.
- RECEIVING semantics: the per-CTE receiving rules (immediate previous
  source / TLC source reference) replace the legacy ``prior_source_tlc``
  contract.
- CTE type gate: INVALID_CTE_TYPE short-circuits before the engine
  (including non-string cte_type — no crash).
- Strict mode: engine warnings escalate to STRICT_MODE_WARNING errors.
- Fail-closed: an empty ruleset yields NO_VERDICT, never valid=true.
- Auth: API key still required.

Deeper golden coverage (endpoint verdict vs direct engine evaluation on the
real seed rules) lives in ``tests/compliance/test_validate_rules_engine_golden.py``.
"""

import os
import sys
from datetime import date
from pathlib import Path

# Ensure service imports resolve
service_dir = Path(__file__).parent.parent
_to_remove = [key for key in sys.modules if key == "app" or key.startswith("services.compliance.app.") or key == "main"]
for key in _to_remove:
    del sys.modules[key]
sys.path.insert(0, str(service_dir))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["REGENGINE_ENV"] = "test"
os.environ["AUTH_TEST_BYPASS_TOKEN"] = "test-bypass-token-compliance"
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-validation-engine")

import pytest
from fastapi.testclient import TestClient
from services.compliance.main import app

client = TestClient(app)

API_KEY = os.environ["AUTH_TEST_BYPASS_TOKEN"]


def _headers(tenant_id: str | None = None) -> dict:
    h = {"X-RegEngine-API-Key": API_KEY}
    if tenant_id:
        h["X-Tenant-Id"] = tenant_id
    return h


def _rule(
    rule_id: str,
    title: str,
    cte_types: list[str],
    logic: dict,
    *,
    severity: str = "critical",
    category: str = "kde_presence",
    citation: str | None = "21 CFR §1.1345",
):
    from shared.rules.types import RuleDefinition

    return RuleDefinition(
        rule_id=rule_id,
        rule_version=1,
        title=title,
        description=None,
        severity=severity,
        category=category,
        applicability_conditions={"cte_types": cte_types, "ftl_scope": ["ALL"]},
        citation_reference=citation,
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic=logic,
        failure_reason_template="{event_type} event missing {field_name} ({citation})",
        remediation_suggestion="Record the missing field",
    )


def _fixture_rules():
    """Deterministic stateless ruleset mirroring the built-in seed shapes."""
    all_ctes = [
        "harvesting",
        "cooling",
        "initial_packing",
        "first_land_based_receiving",
        "shipping",
        "receiving",
        "transformation",
    ]
    return [
        _rule(
            "tlc-required",
            "TLC required",
            all_ctes,
            {"type": "field_presence", "field": "traceability_lot_code"},
        ),
        _rule(
            "quantity-required",
            "Quantity required",
            all_ctes,
            {"type": "field_presence", "field": "quantity"},
        ),
        # RECEIVING-specific: replaces the legacy prior_source_tlc contract.
        _rule(
            "receiving-prev-source",
            "Receiving: Immediate Previous Source Required",
            ["receiving"],
            {
                "type": "multi_field_presence",
                "field": "from_entity_reference",
                "params": {"fields": ["from_entity_reference", "kdes.immediate_previous_source"]},
            },
        ),
        # warn-class rule (severity=warning + operational_quality → engine
        # downgrades a failure to "warn") for the strict-mode tests.
        _rule(
            "lot-size-unit",
            "Operational: lot size unit recommended",
            all_ctes,
            {"type": "field_presence", "field": "kdes.lot_size_unit"},
            severity="warning",
            category="operational_quality",
            citation=None,
        ),
    ]


@pytest.fixture(autouse=True)
def seeded_rules(monkeypatch):
    from shared.rules.engine import RulesEngine

    rules = _fixture_rules()
    monkeypatch.setattr(RulesEngine, "load_active_rules", lambda self: rules)
    return rules


def _valid_config(**overrides) -> dict:
    """A config satisfying every critical rule in the fixture ruleset."""
    base = {
        "tlc": "TLC-001",
        "cte_type": "SHIPPING",
        "quantity": 100,
        "unit_of_measure": "cases",
        "product_description": "Organic Romaine Lettuce",
        "kdes": {"lot_size_unit": "cases"},
    }
    base.update(overrides)
    return base


def _payload(config: dict | None = None, *, strict: bool | None = None) -> dict:
    payload = {"ftl_commodity": "leafy_greens"}
    if config is not None:
        payload["config"] = config
    if strict is not None:
        payload["strict"] = strict
    return payload


def _post(payload: dict) -> dict:
    resp = client.post("/validate", json=payload, headers=_headers())
    assert resp.status_code == 200, resp.text
    return resp.json()


# ─── Happy path ──────────────────────────────────────────────────────────


class TestValidationHappyPath:
    def test_fully_valid_config_passes(self):
        body = _post(_payload(_valid_config()))
        assert body["valid"] is True
        assert body["errors"] == []
        # The verdict is engine-derived, not a local stub.
        assert body["rules_evaluated"] > 0
        assert body["no_verdict_reason"] is None

    def test_all_allowed_cte_types_pass(self):
        allowed = [
            "HARVESTING",
            "COOLING",
            "INITIAL_PACKING",
            "FIRST_LAND_BASED_RECEIVING",
            "SHIPPING",
            "RECEIVING",
            "TRANSFORMATION",
        ]
        for cte in allowed:
            config = _valid_config(cte_type=cte)
            if cte == "RECEIVING":
                # Per-CTE receiving rule requires the previous-source KDE.
                config["from_entity_reference"] = "SUPPLIER-GLN-1"
            body = _post(_payload(config))
            assert body["valid"] is True, f"CTE type {cte}: {body['errors']}"

    def test_cte_type_case_insensitive(self):
        body = _post(_payload(_valid_config(cte_type="shipping")))
        assert body["valid"] is True


# ─── KDE-presence failures (engine-derived) ──────────────────────────────


class TestRuleFailures:
    def test_missing_tlc_fails_with_rule_provenance(self):
        config = _valid_config()
        del config["tlc"]
        body = _post(_payload(config))
        assert body["valid"] is False
        tlc_errors = [e for e in body["errors"] if e["path"] == "traceability_lot_code"]
        assert len(tlc_errors) == 1
        assert tlc_errors[0]["code"] == "RULE_FAILED"
        assert tlc_errors[0]["rule_id"] == "tlc-required"
        assert tlc_errors[0]["citation_reference"]

    def test_multiple_missing_fields_all_reported(self):
        """A config missing every critical field reports each failing rule."""
        body = _post(_payload({"cte_type": "SHIPPING"}))
        assert body["valid"] is False
        failed_rules = {e["rule_id"] for e in body["errors"]}
        assert {"tlc-required", "quantity-required"} <= failed_rules

    def test_errors_carry_remediation_suggestions(self):
        config = _valid_config()
        del config["tlc"]
        body = _post(_payload(config))
        assert all(e.get("suggestion") for e in body["errors"])


# ─── CTE type gate (unchanged pre-engine behavior) ───────────────────────


class TestCTETypeValidation:
    def test_invalid_cte_type_rejected(self):
        body = _post(_payload(_valid_config(cte_type="INVALID_TYPE")))
        assert body["valid"] is False
        cte_errors = [e for e in body["errors"] if e["path"] == "cte_type"]
        assert len(cte_errors) == 1
        assert cte_errors[0]["code"] == "INVALID_CTE_TYPE"

    def test_numeric_cte_type_not_uppercased(self):
        """Non-string cte_type should not crash .upper()."""
        resp = client.post(
            "/validate",
            json=_payload(_valid_config(cte_type=123)),
            headers=_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_missing_cte_type_is_structured_error(self):
        body = _post(_payload({"tlc": "TLC-1"}))
        assert body["valid"] is False
        assert body["errors"][0]["code"] == "INVALID_CTE_TYPE"


# ─── RECEIVING per-CTE rules ─────────────────────────────────────────────


class TestReceivingCTEValidation:
    def test_receiving_requires_previous_source(self):
        config = _valid_config(cte_type="RECEIVING")
        body = _post(_payload(config))
        assert body["valid"] is False
        failed = [e for e in body["errors"] if e["rule_id"] == "receiving-prev-source"]
        assert len(failed) == 1
        assert failed[0]["code"] == "RULE_FAILED"

    def test_receiving_with_previous_source_passes(self):
        config = _valid_config(
            cte_type="RECEIVING",
            from_entity_reference="SUPPLIER-GLN-1",
        )
        body = _post(_payload(config))
        assert body["valid"] is True, body["errors"]

    def test_receiving_accepts_kde_form_too(self):
        config = _valid_config(cte_type="RECEIVING")
        config["kdes"] = {**config["kdes"], "immediate_previous_source": "Acme Farms"}
        body = _post(_payload(config))
        assert body["valid"] is True, body["errors"]

    def test_non_receiving_does_not_run_receiving_rules(self):
        body = _post(_payload(_valid_config(cte_type="SHIPPING")))
        assert all(e["rule_id"] != "receiving-prev-source" for e in body["errors"])


# ─── Warnings & strict mode ──────────────────────────────────────────────


class TestWarningsAndStrictMode:
    def _config_missing_lot_size_unit(self) -> dict:
        config = _valid_config()
        config["kdes"] = {}
        return config

    def test_warn_class_rule_produces_warning_not_error(self):
        body = _post(_payload(self._config_missing_lot_size_unit()))
        assert body["valid"] is True
        assert [w["rule_id"] for w in body["warnings"]] == ["lot-size-unit"]
        assert body["warnings"][0]["code"] == "RULE_WARNING"

    def test_warnings_have_suggestions(self):
        body = _post(_payload(self._config_missing_lot_size_unit()))
        for w in body["warnings"]:
            assert w["suggestion"]

    def test_strict_mode_converts_warnings_to_errors(self):
        body = _post(_payload(self._config_missing_lot_size_unit(), strict=True))
        assert body["valid"] is False
        assert body["warnings"] == []
        strict_errors = [e for e in body["errors"] if e["code"] == "STRICT_MODE_WARNING"]
        assert len(strict_errors) == 1

    def test_non_strict_mode_keeps_warnings_separate(self):
        body = _post(_payload(self._config_missing_lot_size_unit(), strict=False))
        assert body["valid"] is True
        assert len(body["warnings"]) == 1
        assert body["errors"] == []


# ─── Fail-closed (no-verdict) ────────────────────────────────────────────


class TestFailClosed:
    def test_empty_ruleset_yields_no_verdict_not_valid(self, monkeypatch):
        from shared.rules.engine import RulesEngine

        monkeypatch.setattr(RulesEngine, "load_active_rules", lambda self: [])
        body = _post(_payload(_valid_config()))
        assert body["valid"] is False
        assert body["rules_evaluated"] == 0
        assert body["no_verdict_reason"] == "no_rules_loaded"
        assert any(e["code"] == "NO_VERDICT" for e in body["errors"])

    def test_config_none_is_not_a_compliance_verdict(self):
        body = _post(_payload(None))
        assert body["valid"] is True
        assert body["rules_evaluated"] == 0


# ─── Auth ────────────────────────────────────────────────────────────────


class TestValidationAuth:
    def test_validate_requires_api_key(self):
        resp = client.post("/validate", json={"config": _valid_config()})
        assert resp.status_code in (401, 403, 422)
