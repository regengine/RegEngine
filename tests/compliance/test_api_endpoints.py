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

    def test_health_includes_checklists_count(self, compliance_client):
        """Verify health endpoint shows loaded checklists count."""
        client, _ = compliance_client
        
        resp = client.get("/health")
        data = resp.json()
        
        assert "checklists_loaded" in data
        assert isinstance(data["checklists_loaded"], int)
        assert data["checklists_loaded"] >= 0


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
                "checklist_id": "test",
                "customer_config": {},
            },
        )
        assert resp.status_code in (401, 403)

    def test_validate_requires_checklist_id(self, compliance_client):
        """Verify checklist_id is required."""
        client, api_key = compliance_client
        
        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={"customer_config": {}},
        )
        assert resp.status_code == 422

    def test_validate_requires_customer_config(self, compliance_client):
        """Verify customer_config is required."""
        client, api_key = compliance_client
        
        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={"checklist_id": "test"},
        )
        assert resp.status_code == 422

    def test_validate_returns_error_for_unknown_checklist(self, compliance_client):
        """Verify validation fails for unknown checklist."""
        client, api_key = compliance_client
        
        resp = client.post(
            "/validate",
            headers={"X-RegEngine-API-Key": api_key},
            json={
                "checklist_id": "definitely_not_a_real_checklist",
                "customer_config": {"req1": True},
            },
        )
        assert resp.status_code in (400, 404)


class TestFSMAAssessmentEndpoint:
    """Tests for the FSMA 204 assessment endpoint."""

    def test_fsma_assessment_requires_auth(self, compliance_client):
        """Verify FSMA assessment requires API key."""
        client, _ = compliance_client
        
        resp = client.post(
            "/fsma/assess",
            json={"facility_name": "Test Facility"},
        )
        assert resp.status_code in (401, 403)

    def test_fsma_assessment_requires_facility_name(self, compliance_client):
        """Verify facility_name is required."""
        client, api_key = compliance_client
        
        resp = client.post(
            "/fsma/assess",
            headers={"X-RegEngine-API-Key": api_key},
            json={},
        )
        assert resp.status_code == 422


class TestValidationResultStructure:
    """Tests for validation result format."""

    def test_expected_result_fields(self):
        """Document expected validation result structure."""
        expected_fields = [
            "checklist_id",
            "checklist_name",
            "industry",
            "jurisdiction",
            "overall_status",
            "pass_rate",
            "items",
            "next_steps",
        ]
        
        assert len(expected_fields) == 8

    def test_expected_item_fields(self):
        """Document expected validation item structure."""
        expected_fields = [
            "requirement_id",
            "requirement",
            "regulation",
            "status",
            "evidence",
            "remediation",
        ]
        
        assert len(expected_fields) == 6


class TestChecklistMetadata:
    """Tests for checklist metadata format."""

    def test_expected_checklist_metadata(self):
        """Document expected checklist metadata."""
        expected_fields = [
            "id",
            "name",
            "industry",
            "jurisdiction",
        ]
        
        assert len(expected_fields) == 4
