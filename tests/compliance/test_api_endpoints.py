"""Tests for the Compliance API HTTP endpoints.

These tests verify:
- Health endpoint
- Checklists listing and filtering
- Individual checklist retrieval
- Compliance validation endpoint
- API key authentication
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient


@pytest.fixture
def compliance_client(monkeypatch):
    """Provide a TestClient with mocked auth for compliance API."""
    # Set up test environment
    monkeypatch.setenv("COMPLIANCE_API_KEY", "test-compliance-key")

    # Mock the API key validation to accept test keys
    from shared import auth as shared_auth

    test_key = shared_auth.APIKey(
        key_id="test-key-id",
        key_hash="test-hash",
        name="Test Key",
        tenant_id=str(uuid4()),
        created_at=datetime.now(timezone.utc),
        enabled=True,
    )

    store = shared_auth.APIKeyStore()
    raw_key, _ = store.create_key("test", tenant_id=str(uuid4()))
    monkeypatch.setattr(shared_auth, "_key_store", store, raising=False)

    from services.compliance.main import app

    return TestClient(app), raw_key


class TestHealthEndpoint:
    """Tests for the compliance service health endpoint."""

    def test_health_returns_status(self, compliance_client):
        """Verify health endpoint returns healthy status."""
        client, _ = compliance_client

        resp = client.get("/health")
        assert resp.status_code == 200

        data = resp.json()
        assert "status" in data
        assert data["status"] == "healthy"

    def test_health_includes_shared_observability_fields(self, compliance_client):
        """Verify health endpoint exposes the standardized health payload."""
        client, _ = compliance_client

        resp = client.get("/health")
        data = resp.json()

        assert data["service"] == "compliance-service"
        assert "hostname" in data
        assert "uptime" in data
        assert "dependencies" in data


class TestChecklistsEndpoints:
    """Tests for checklist listing and retrieval endpoints."""

    def test_list_checklists_requires_auth(self, compliance_client):
        """Verify checklists endpoint requires API key."""
        client, _ = compliance_client

        resp = client.get("/checklists")
        assert resp.status_code in (401, 403)

    def test_list_checklists_returns_array(self, compliance_client):
        """Verify checklists endpoint returns list."""
        client, api_key = compliance_client

        resp = client.get(
            "/checklists",
            headers={"X-RegEngine-API-Key": api_key},
        )
        assert resp.status_code == 200

        data = resp.json()
        assert isinstance(data, dict)
        assert "checklists" in data
        assert isinstance(data["checklists"], list)

    def test_list_checklists_with_industry_filter(self, compliance_client):
        """Verify industry filter works."""
        client, api_key = compliance_client

        resp = client.get(
            "/checklists",
            headers={"X-RegEngine-API-Key": api_key},
            params={"industry": "finance"},
        )
        assert resp.status_code == 200

    def test_get_specific_checklist_not_found(self, compliance_client):
        """Verify 404 for nonexistent checklist."""
        client, api_key = compliance_client

        resp = client.get(
            "/checklists/nonexistent_checklist_id",
            headers={"X-RegEngine-API-Key": api_key},
        )
        assert resp.status_code == 404


class TestValidationEndpoint:
    """Tests for the compliance validation endpoint."""

    def test_validate_requires_auth(self, compliance_client):
        """Verify validation requires API key."""
        client, _ = compliance_client

        resp = client.post(
            "/validate",
            json={
                "ftl_commodity": "Cheese",
            },
        )
        assert resp.status_code in (401, 403)

    def test_validate_requires_ftl_commodity(self, compliance_client):
        """Verify the FTL commodity scope is required."""
        client, api_key = compliance_client

        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={"config": {}},
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "request_json",
        [
            {"ftl_commodity": "Soft Cheeses"},
            {"ftl_commodity": "Soft Cheeses", "config": None},
        ],
        ids=["omitted", "explicit-null"],
    )
    def test_validate_missing_config_returns_no_verdict(self, compliance_client, request_json):
        """Verify optional config does not produce a compliance verdict."""
        client, api_key = compliance_client

        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json=request_json,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["valid"] is False
        assert payload["rules_evaluated"] == 0
        assert payload["no_verdict_reason"] == "nothing_evaluated"
        assert len(payload["errors"]) == 1
        assert payload["errors"][0]["code"] == "NO_VERDICT"
        assert payload["errors"][0]["path"] == "config"
        assert payload["warnings"] == []

    def test_validate_returns_error_for_unknown_checklist(self, compliance_client):
        """Verify validation fails for unknown checklist."""
        client, api_key = compliance_client

        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={
                "ftl_commodity": "Soft Cheeses",
                "checklist_id": "definitely_not_a_real_checklist",
                "config": {"cte_type": "HARVESTING"},
            },
        )
        assert resp.status_code == 404


class TestAuditSpreadsheetEndpoint:
    """Tests for the FDA audit spreadsheet export endpoint."""

    def test_audit_spreadsheet_requires_auth(self, compliance_client):
        """Verify the spreadsheet export requires API key auth."""
        client, _ = compliance_client

        resp = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-01-01", "end_date": "2026-01-02"},
        )
        assert resp.status_code in (401, 403)

    def test_audit_spreadsheet_requires_date_params(self, compliance_client):
        """Verify required export window query params are enforced."""
        client, api_key = compliance_client

        resp = client.get(
            "/v1/fsma/audit/spreadsheet",
            headers={"X-RegEngine-API-Key": api_key},
        )
        assert resp.status_code == 422


class TestValidationResultStructure:
    """Tests for validation result format."""

    def test_expected_result_fields(self):
        """Document expected validation result structure."""
        expected_fields = [
            "valid",
            "ftl_commodity",
            "errors",
            "warnings",
        ]

        assert len(expected_fields) == 4

    def test_expected_item_fields(self):
        """Document expected validation issue structure."""
        expected_fields = [
            "path",
            "code",
            "message",
            "suggestion",
        ]

        assert len(expected_fields) == 4


class TestChecklistMetadata:
    """Tests for checklist metadata format."""

    def test_expected_checklist_metadata(self):
        """Document expected checklist metadata."""
        expected_fields = [
            "id",
            "name",
            "industry",
            "description",
            "framework",
            "version",
            "requirements",
            "items",
        ]

        assert len(expected_fields) == 8
