"""
API Route Tests for Manufacturing Service.

Tests all endpoints with mocked DB, authentication, and CRUD operations.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


class TestHealthAndRootEndpoints:
    """Test health check and root endpoints (no auth required)."""

    def test_health_endpoint(self, client):
        """GET /health should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "manufacturing"
        assert "version" in data

    def test_root_endpoint(self, client):
        """GET / should return service information."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "Manufacturing" in data["service"]
        assert data["docs"] == "/docs"
        assert data["health"] == "/health"


class TestNCREndpoints:
    """Test NCR (Non-Conformance Report) endpoints."""

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_ncr_success(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data):
        """POST /v1/manufacturing/ncr with valid data should create NCR."""
        mock_tenant.return_value = tenant_id
        
        response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["ncr_number"] == sample_ncr_data["ncr_number"]
        assert data["severity"] == sample_ncr_data["severity"]
        assert data["status"] == "OPEN"
        assert "created_at" in data

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_ncr_duplicate_number(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data):
        """POST /v1/manufacturing/ncr with duplicate NCR number should fail."""
        mock_tenant.return_value = tenant_id
        
        # Create first NCR
        client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        
        # Try to create duplicate
        response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_create_ncr_missing_auth(self, client, sample_ncr_data):
        """POST /v1/manufacturing/ncr without auth should fail."""
        response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data
        )
        
        assert response.status_code == 401

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_ncr_invalid_severity(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data):
        """POST /v1/manufacturing/ncr with invalid severity should fail."""
        mock_tenant.return_value = tenant_id
        sample_ncr_data["severity"] = "INVALID"
        
        response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_ncr_invalid_detection_source(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data):
        """POST /v1/manufacturing/ncr with invalid detection_source should fail."""
        mock_tenant.return_value = tenant_id
        sample_ncr_data["detection_source"] = "INVALID_SOURCE"
        
        response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_get_ncr_success(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data):
        """GET /v1/manufacturing/ncr/{id} should return NCR details."""
        mock_tenant.return_value = tenant_id
        
        # Create NCR first
        create_response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        ncr_id = create_response.json()["id"]
        
        # Get NCR
        response = client.get(
            f"/v1/manufacturing/ncr/{ncr_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == ncr_id
        assert data["ncr_number"] == sample_ncr_data["ncr_number"]
        assert data["description"] == sample_ncr_data["description"]
        assert "capas" in data
        assert isinstance(data["capas"], list)

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_get_ncr_not_found(self, mock_tenant, client, auth_headers, tenant_id):
        """GET /v1/manufacturing/ncr/{id} for non-existent NCR should return 404."""
        mock_tenant.return_value = tenant_id
        
        response = client.get(
            "/v1/manufacturing/ncr/99999",
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_ncr_missing_auth(self, client):
        """GET /v1/manufacturing/ncr/{id} without auth should fail."""
        response = client.get("/v1/manufacturing/ncr/1")
        assert response.status_code == 401

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_update_root_cause_success(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data):
        """PATCH /v1/manufacturing/ncr/{id}/root-cause should update RCA."""
        mock_tenant.return_value = tenant_id
        
        # Create NCR
        create_response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        ncr_id = create_response.json()["id"]
        
        # Update root cause
        response = client.patch(
            f"/v1/manufacturing/ncr/{ncr_id}/root-cause",
            params={
                "root_cause": "Inadequate training on new equipment",
                "rca_method": "5_WHYS"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == ncr_id
        assert data["root_cause"] == "Inadequate training on new equipment"
        assert data["rca_method"] == "5_WHYS"
        assert "rca_completed_date" in data

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_update_root_cause_not_found(self, mock_tenant, client, auth_headers, tenant_id):
        """PATCH /v1/manufacturing/ncr/{id}/root-cause for non-existent NCR should fail."""
        mock_tenant.return_value = tenant_id
        
        response = client.patch(
            "/v1/manufacturing/ncr/99999/root-cause",
            params={
                "root_cause": "Test cause",
                "rca_method": "5_WHYS"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 404

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_update_root_cause_invalid_method(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data):
        """PATCH /v1/manufacturing/ncr/{id}/root-cause with invalid method should fail."""
        mock_tenant.return_value = tenant_id
        
        # Create NCR
        create_response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        ncr_id = create_response.json()["id"]
        
        response = client.patch(
            f"/v1/manufacturing/ncr/{ncr_id}/root-cause",
            params={
                "root_cause": "Test cause",
                "rca_method": "INVALID_METHOD"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 422


class TestCAPAEndpoints:
    """Test CAPA (Corrective and Preventive Action) endpoints."""

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_capa_success(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data, sample_capa_data):
        """POST /v1/manufacturing/capa with valid data should create CAPA."""
        mock_tenant.return_value = tenant_id
        
        # Create NCR first
        ncr_response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        ncr_id = ncr_response.json()["id"]
        
        # Create CAPA
        sample_capa_data["ncr_id"] = ncr_id
        response = client.post(
            "/v1/manufacturing/capa",
            json=sample_capa_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["ncr_id"] == ncr_id
        assert data["action_type"] == sample_capa_data["action_type"]
        assert data["assigned_to"] == sample_capa_data["assigned_to"]
        assert data["implementation_status"] == "PENDING"

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_capa_ncr_not_found(self, mock_tenant, client, auth_headers, tenant_id, sample_capa_data):
        """POST /v1/manufacturing/capa with non-existent NCR should fail."""
        mock_tenant.return_value = tenant_id
        sample_capa_data["ncr_id"] = 99999
        
        response = client.post(
            "/v1/manufacturing/capa",
            json=sample_capa_data,
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_capa_missing_auth(self, client, sample_capa_data):
        """POST /v1/manufacturing/capa without auth should fail."""
        response = client.post(
            "/v1/manufacturing/capa",
            json=sample_capa_data
        )
        
        assert response.status_code == 401

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_capa_invalid_action_type(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data, sample_capa_data):
        """POST /v1/manufacturing/capa with invalid action_type should fail."""
        mock_tenant.return_value = tenant_id
        
        # Create NCR
        ncr_response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        ncr_id = ncr_response.json()["id"]
        
        sample_capa_data["ncr_id"] = ncr_id
        sample_capa_data["action_type"] = "INVALID_TYPE"
        
        response = client.post(
            "/v1/manufacturing/capa",
            json=sample_capa_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_verify_capa_success(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data, sample_capa_data):
        """PATCH /v1/manufacturing/capa/{id}/verify should verify CAPA."""
        mock_tenant.return_value = tenant_id
        
        # Create NCR
        ncr_response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        ncr_id = ncr_response.json()["id"]
        
        # Create CAPA
        sample_capa_data["ncr_id"] = ncr_id
        capa_response = client.post(
            "/v1/manufacturing/capa",
            json=sample_capa_data,
            headers=auth_headers
        )
        capa_id = capa_response.json()["id"]
        
        # Verify CAPA
        response = client.patch(
            f"/v1/manufacturing/capa/{capa_id}/verify",
            params={
                "verification_result": "EFFECTIVE",
                "verified_by": "Quality Manager",
                "notes": "CAPA implementation successful"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == capa_id
        assert data["verification_result"] == "EFFECTIVE"
        assert data["verified_by"] == "Quality Manager"
        assert "verification_date" in data

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_verify_capa_not_found(self, mock_tenant, client, auth_headers, tenant_id):
        """PATCH /v1/manufacturing/capa/{id}/verify for non-existent CAPA should fail."""
        mock_tenant.return_value = tenant_id
        
        response = client.patch(
            "/v1/manufacturing/capa/99999/verify",
            params={
                "verification_result": "EFFECTIVE",
                "verified_by": "Test"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 404

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_verify_capa_invalid_result(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data, sample_capa_data):
        """PATCH /v1/manufacturing/capa/{id}/verify with invalid result should fail."""
        mock_tenant.return_value = tenant_id
        
        # Create NCR and CAPA
        ncr_response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        sample_capa_data["ncr_id"] = ncr_response.json()["id"]
        capa_response = client.post(
            "/v1/manufacturing/capa",
            json=sample_capa_data,
            headers=auth_headers
        )
        capa_id = capa_response.json()["id"]
        
        response = client.patch(
            f"/v1/manufacturing/capa/{capa_id}/verify",
            params={
                "verification_result": "INVALID_RESULT",
                "verified_by": "Test"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 422


class TestSupplierIssueEndpoints:
    """Test Supplier Quality Issue endpoints."""

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_supplier_issue_success(self, mock_tenant, client, auth_headers, tenant_id, sample_supplier_issue_data):
        """POST /v1/manufacturing/supplier-issue should create supplier issue."""
        mock_tenant.return_value = tenant_id
        
        response = client.post(
            "/v1/manufacturing/supplier-issue",
            json=sample_supplier_issue_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["supplier_name"] == sample_supplier_issue_data["supplier_name"]
        assert data["part_number"] == sample_supplier_issue_data["part_number"]
        assert data["status"] == "OPEN"

    def test_create_supplier_issue_missing_auth(self, client, sample_supplier_issue_data):
        """POST /v1/manufacturing/supplier-issue without auth should fail."""
        response = client.post(
            "/v1/manufacturing/supplier-issue",
            json=sample_supplier_issue_data
        )
        
        assert response.status_code == 401

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_supplier_issue_missing_required_field(self, mock_tenant, client, auth_headers, tenant_id):
        """POST /v1/manufacturing/supplier-issue without required fields should fail."""
        mock_tenant.return_value = tenant_id
        
        incomplete_data = {
            "supplier_name": "ABC Suppliers Inc",
            # Missing part_number and other required fields
        }
        
        response = client.post(
            "/v1/manufacturing/supplier-issue",
            json=incomplete_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422


class TestAuditFindingEndpoints:
    """Test Audit Finding endpoints."""

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_audit_finding_success(self, mock_tenant, client, auth_headers, tenant_id, sample_audit_finding_data):
        """POST /v1/manufacturing/audit-finding should create audit finding."""
        mock_tenant.return_value = tenant_id
        
        response = client.post(
            "/v1/manufacturing/audit-finding",
            json=sample_audit_finding_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["finding_number"] == sample_audit_finding_data["finding_number"]
        assert data["finding_type"] == sample_audit_finding_data["finding_type"]
        assert data["status"] == "OPEN"

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_audit_finding_duplicate_number(self, mock_tenant, client, auth_headers, tenant_id, sample_audit_finding_data):
        """POST /v1/manufacturing/audit-finding with duplicate finding number should fail."""
        mock_tenant.return_value = tenant_id
        
        # Create first finding
        client.post(
            "/v1/manufacturing/audit-finding",
            json=sample_audit_finding_data,
            headers=auth_headers
        )
        
        # Try to create duplicate
        response = client.post(
            "/v1/manufacturing/audit-finding",
            json=sample_audit_finding_data,
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_create_audit_finding_missing_auth(self, client, sample_audit_finding_data):
        """POST /v1/manufacturing/audit-finding without auth should fail."""
        response = client.post(
            "/v1/manufacturing/audit-finding",
            json=sample_audit_finding_data
        )
        
        assert response.status_code == 401

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_audit_finding_invalid_type(self, mock_tenant, client, auth_headers, tenant_id, sample_audit_finding_data):
        """POST /v1/manufacturing/audit-finding with invalid audit_type should fail."""
        mock_tenant.return_value = tenant_id
        sample_audit_finding_data["audit_type"] = "INVALID_TYPE"
        
        response = client.post(
            "/v1/manufacturing/audit-finding",
            json=sample_audit_finding_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_create_audit_finding_invalid_finding_type(self, mock_tenant, client, auth_headers, tenant_id, sample_audit_finding_data):
        """POST /v1/manufacturing/audit-finding with invalid finding_type should fail."""
        mock_tenant.return_value = tenant_id
        sample_audit_finding_data["finding_type"] = "INVALID"
        
        response = client.post(
            "/v1/manufacturing/audit-finding",
            json=sample_audit_finding_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422


class TestDashboardEndpoint:
    """Test Dashboard metrics endpoint."""

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_get_dashboard_empty(self, mock_tenant, client, auth_headers, tenant_id):
        """GET /v1/manufacturing/dashboard with no data should return zeros."""
        mock_tenant.return_value = tenant_id
        
        response = client.get(
            "/v1/manufacturing/dashboard",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "total_ncrs" in data
        assert "open_ncrs" in data
        assert "overdue_capas" in data
        assert "open_audit_findings" in data
        assert "capa_effectiveness_rate" in data
        assert data["total_ncrs"] == 0
        assert data["open_ncrs"] == 0
        assert data["overdue_capas"] == 0
        assert data["open_audit_findings"] == 0
        assert data["capa_effectiveness_rate"] == 100.0

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_get_dashboard_with_data(self, mock_tenant, client, auth_headers, tenant_id, sample_ncr_data):
        """GET /v1/manufacturing/dashboard with data should return metrics."""
        mock_tenant.return_value = tenant_id
        
        # Create an NCR
        client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=auth_headers
        )
        
        response = client.get(
            "/v1/manufacturing/dashboard",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_ncrs"] == 1
        assert data["open_ncrs"] == 1

    def test_get_dashboard_missing_auth(self, client):
        """GET /v1/manufacturing/dashboard without auth should fail."""
        response = client.get("/v1/manufacturing/dashboard")
        assert response.status_code == 401


class TestTenantIsolation:
    """Test tenant isolation between requests."""

    @patch("app.ncr_engine.get_current_tenant_id")
    def test_ncr_tenant_isolation(self, mock_tenant, client, sample_ncr_data):
        """NCRs should be isolated by tenant_id."""
        tenant1_id = "12345678-1234-5678-1234-567812345678"
        tenant2_id = "87654321-4321-8765-4321-876543218765"
        
        # Create NCR for tenant 1
        mock_tenant.return_value = tenant1_id
        headers1 = {
            "X-RegEngine-API-Key": "test-key",
            "X-RegEngine-Tenant-ID": tenant1_id
        }
        
        create_response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers=headers1
        )
        assert create_response.status_code == 201
        ncr_id = create_response.json()["id"]
        
        # Try to access from tenant 2
        mock_tenant.return_value = tenant2_id
        headers2 = {
            "X-RegEngine-API-Key": "test-key",
            "X-RegEngine-Tenant-ID": tenant2_id
        }
        
        get_response = client.get(
            f"/v1/manufacturing/ncr/{ncr_id}",
            headers=headers2
        )
        
        # Should not find NCR from different tenant
        assert get_response.status_code == 404


class TestAuthenticationFailures:
    """Test various authentication failure scenarios."""

    def test_missing_api_key_header(self, client, sample_ncr_data):
        """Request without X-RegEngine-API-Key header should fail."""
        response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data
        )
        
        assert response.status_code == 401
        assert "Missing X-RegEngine-API-Key header" in response.json()["detail"]

    def test_empty_api_key(self, client, sample_ncr_data):
        """Request with empty API key should fail."""
        response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers={"X-RegEngine-API-Key": ""}
        )
        
        assert response.status_code == 401

    def test_whitespace_api_key(self, client, sample_ncr_data):
        """Request with whitespace-only API key should fail."""
        response = client.post(
            "/v1/manufacturing/ncr",
            json=sample_ncr_data,
            headers={"X-RegEngine-API-Key": "   "}
        )
        
        assert response.status_code == 401
