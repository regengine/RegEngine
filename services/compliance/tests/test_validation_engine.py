"""Comprehensive tests for FSMA 204 validation engine.

Covers:
- Required field validation
- CTE type enumeration
- RECEIVING-specific requirements
- Strict mode behavior
- Warning generation for recommended fields
"""

import sys
import os
from pathlib import Path
from uuid import uuid4

# Ensure service imports resolve
service_dir = Path(__file__).parent.parent
_to_remove = [key for key in sys.modules if key == "app" or key.startswith("app.") or key == "main"]
for key in _to_remove:
    del sys.modules[key]
sys.path.insert(0, str(service_dir))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REGENGINE_ENV", "test")
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-validation-engine")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-validation-engine")

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

API_KEY = os.environ["AUTH_TEST_BYPASS_TOKEN"]


def _headers(tenant_id: str | None = None) -> dict:
    h = {"X-RegEngine-API-Key": API_KEY}
    if tenant_id:
        h["X-Tenant-Id"] = tenant_id
    return h


def _valid_config(**overrides) -> dict:
    """Return a minimally valid FSMA 204 configuration."""
    base = {
        "tlc": "TLC-001",
        "cte_type": "SHIPPING",
        "event_date": "2026-01-15",
        "location": "GLN-1234567890123",
        "quantity": 100,
        "unit_of_measure": "cases",
        "product_description": "Organic Romaine Lettuce",
        "responsible_party_contact": "Jane Doe, 555-0100, jane@example.com",
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


# ─── Validation: happy path ────────────────────────────────────────────


class TestValidationHappyPath:
    def test_fully_valid_config_passes(self):
        resp = client.post(
            "/validate",
            json=_payload(_valid_config()),
            headers=_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["errors"] == []

    def test_valid_config_with_all_recommended_fields_no_warnings(self):
        config = _valid_config(
            lot_size_unit="lbs",
            supplier_reference="SUP-001",
        )
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        body = resp.json()
        assert body["valid"] is True
        assert body["warnings"] == []

    def test_all_allowed_cte_types_pass(self):
        allowed = [
            "HARVESTING", "COOLING", "INITIAL_PACKING",
            "FIRST_LAND_BASED_RECEIVING", "SHIPPING", "RECEIVING",
            "TRANSFORMATION",
        ]
        for cte in allowed:
            config = _valid_config(cte_type=cte)
            # RECEIVING needs extra fields
            if cte == "RECEIVING":
                config["prior_source_tlc"] = "TLC-PRIOR"
            resp = client.post(
                "/validate",
                json=_payload(config),
                headers=_headers(),
            )
            body = resp.json()
            assert body["valid"] is True, f"CTE type {cte} should be valid"

    def test_cte_type_case_insensitive(self):
        resp = client.post(
            "/validate",
            json=_payload(_valid_config(cte_type="shipping")),
            headers=_headers(),
        )
        assert resp.json()["valid"] is True


# ─── Validation: required field errors ──────────────────────────────────


class TestRequiredFieldValidation:
    def test_missing_required_field_produces_error(self):
        config = _valid_config()
        del config["tlc"]
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        body = resp.json()
        assert body["valid"] is False
        error_codes = [e["code"] for e in body["errors"]]
        assert "MISSING_REQUIRED_FIELD" in error_codes
        error_paths = [e["path"] for e in body["errors"]]
        assert "tlc" in error_paths

    def test_null_required_field_produces_error(self):
        config = _valid_config(tlc=None)
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        body = resp.json()
        assert body["valid"] is False
        tlc_errors = [e for e in body["errors"] if e["path"] == "tlc"]
        assert len(tlc_errors) == 1
        assert tlc_errors[0]["code"] == "NULL_REQUIRED_FIELD"

    def test_multiple_missing_fields_all_reported(self):
        """Empty config should report errors for every required field."""
        resp = client.post(
            "/validate",
            json=_payload({}),
            headers=_headers(),
        )
        body = resp.json()
        assert body["valid"] is False
        # At minimum, tlc, cte_type, event_date, location, quantity, unit_of_measure,
        # product_description, responsible_party_contact
        assert len(body["errors"]) >= 8

    def test_missing_responsible_party_contact_produces_error(self):
        config = _valid_config()
        del config["responsible_party_contact"]
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        body = resp.json()
        assert body["valid"] is False
        error_paths = [e["path"] for e in body["errors"]]
        assert "responsible_party_contact" in error_paths

    def test_null_responsible_party_contact_produces_error(self):
        config = _valid_config(responsible_party_contact=None)
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        body = resp.json()
        assert body["valid"] is False
        rpc_errors = [e for e in body["errors"] if e["path"] == "responsible_party_contact"]
        assert len(rpc_errors) == 1
        assert rpc_errors[0]["code"] == "NULL_REQUIRED_FIELD"

    def test_empty_string_is_not_null(self):
        """An empty string is present and non-null, so it should pass the null check."""
        config = _valid_config(tlc="")
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        body = resp.json()
        # Empty string is not None, so no NULL_REQUIRED_FIELD error for tlc
        tlc_null_errors = [
            e for e in body["errors"]
            if e["path"] == "tlc" and e["code"] == "NULL_REQUIRED_FIELD"
        ]
        assert len(tlc_null_errors) == 0


# ─── Validation: CTE type enum ──────────────────────────────────────────


class TestCTETypeValidation:
    def test_invalid_cte_type_rejected(self):
        config = _valid_config(cte_type="INVALID_TYPE")
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        body = resp.json()
        assert body["valid"] is False
        cte_errors = [e for e in body["errors"] if e["path"] == "cte_type"]
        assert len(cte_errors) == 1
        assert cte_errors[0]["code"] == "INVALID_CTE_TYPE"

    def test_numeric_cte_type_not_uppercased(self):
        """Non-string cte_type should not crash .upper()."""
        config = _valid_config(cte_type=123)
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        # Should not 500 — graceful handling
        assert resp.status_code == 200


# ─── Validation: RECEIVING CTE special rules ─────────────────────────────


class TestReceivingCTEValidation:
    def test_receiving_requires_prior_source_tlc(self):
        config = _valid_config(cte_type="RECEIVING")
        # Intentionally omit prior_source_tlc
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        body = resp.json()
        assert body["valid"] is False
        error_paths = [e["path"] for e in body["errors"]]
        assert "prior_source_tlc" in error_paths

    def test_receiving_with_null_prior_source_tlc_fails(self):
        config = _valid_config(cte_type="RECEIVING", prior_source_tlc=None)
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        body = resp.json()
        assert body["valid"] is False
        prior_errors = [e for e in body["errors"] if e["path"] == "prior_source_tlc"]
        assert len(prior_errors) == 1
        assert prior_errors[0]["code"] == "NULL_REQUIRED_FIELD"

    def test_receiving_with_prior_source_tlc_passes(self):
        config = _valid_config(cte_type="RECEIVING", prior_source_tlc="TLC-PRIOR-001")
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        assert resp.json()["valid"] is True

    def test_non_receiving_does_not_require_prior_source_tlc(self):
        config = _valid_config(cte_type="SHIPPING")
        resp = client.post(
            "/validate",
            json=_payload(config),
            headers=_headers(),
        )
        body = resp.json()
        # Should not have prior_source_tlc errors
        prior_errors = [e for e in body["errors"] if e["path"] == "prior_source_tlc"]
        assert len(prior_errors) == 0


# ─── Validation: warnings & strict mode ──────────────────────────────────


class TestWarningsAndStrictMode:
    def test_missing_recommended_fields_produce_warnings(self):
        config = _valid_config()
        # Remove product_description to trigger warning
        # (it's also required, so use a config that has required fields but not lot_size_unit)
        resp = client.post(
            "/validate",
            json=_payload(_valid_config()),
            headers=_headers(),
        )
        body = resp.json()
        # lot_size_unit and supplier_reference are recommended but not in _valid_config
        warning_paths = [w["path"] for w in body["warnings"]]
        assert "lot_size_unit" in warning_paths
        assert "supplier_reference" in warning_paths

    def test_warnings_have_suggestions(self):
        resp = client.post(
            "/validate",
            json=_payload(_valid_config()),
            headers=_headers(),
        )
        for w in resp.json()["warnings"]:
            assert w["suggestion"] is not None
            assert len(w["suggestion"]) > 0

    def test_strict_mode_converts_warnings_to_errors(self):
        resp = client.post(
            "/validate",
            json=_payload(_valid_config(), strict=True),
            headers=_headers(),
        )
        body = resp.json()
        assert body["valid"] is False
        assert body["warnings"] == []
        strict_errors = [e for e in body["errors"] if e["code"] == "STRICT_MODE_WARNING"]
        assert len(strict_errors) > 0

    def test_non_strict_mode_keeps_warnings_separate(self):
        resp = client.post(
            "/validate",
            json=_payload(_valid_config(), strict=False),
            headers=_headers(),
        )
        body = resp.json()
        assert body["valid"] is True
        assert len(body["warnings"]) > 0
        assert body["errors"] == []


# ─── Validation: auth ────────────────────────────────────────────────────


class TestValidationAuth:
    def test_validate_requires_api_key(self):
        resp = client.post("/validate", json={"config": _valid_config()})
        assert resp.status_code in (401, 403, 422)
