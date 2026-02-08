"""
PCOS API Endpoint Tests

Comprehensive test suite for all Production Compliance OS API endpoints.
Tests cover budget, classification, compliance snapshots, audit packs, and more.

These are integration tests that require a live PostgreSQL database with
the full PCOS schema, including tenant and user tables.
"""

import os
import pytest
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

# These tests require a live PostgreSQL database with the full PCOS schema.
# Skip when running in unit test / CI environments without the database.
pytestmark = pytest.mark.skipif(
    not os.getenv("PCOS_INTEGRATION_DB_URL"),
    reason="PCOS integration tests require PCOS_INTEGRATION_DB_URL to be set"
)


# =============================================================================
# Budget Endpoint Tests
# =============================================================================

class TestBudgetEndpoints:
    """Tests for budget-related API endpoints."""
    
    def test_create_budget_success(self, client, auth_headers, sample_project):
        """Test successful budget creation."""
        response = client.post(
            f"/pcos/projects/{sample_project['id']}/budgets",
            json={
                "source_file_name": "test_budget.xlsx",
                "grand_total": 150000.00,
                "currency": "USD"
            },
            headers=auth_headers
        )
        assert response.status_code in (200, 201)
        data = response.json()
        assert "id" in data
        assert data["grand_total"] == 150000.00
    
    def test_list_budgets_for_project(self, client, auth_headers, sample_project):
        """Test listing budgets for a project."""
        response = client.get(
            f"/pcos/projects/{sample_project['id']}/budgets",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_budget_details(self, client, auth_headers, sample_budget):
        """Test getting budget with line items."""
        response = client.get(
            f"/pcos/budgets/{sample_budget['id']}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_budget['id'])
    
    def test_validate_budget_rates(self, client, auth_headers, sample_budget):
        """Test union rate validation endpoint."""
        response = client.post(
            f"/pcos/budgets/{sample_budget['id']}/validate-rates",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data or "items_checked" in data
    
    def test_fringe_analysis(self, client, auth_headers, sample_budget):
        """Test fringe analysis endpoint."""
        response = client.get(
            f"/pcos/budgets/{sample_budget['id']}/fringe-analysis",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_labor_cost" in data
        assert "total_union_fringes" in data


# =============================================================================
# Classification Endpoint Tests
# =============================================================================

class TestClassificationEndpoints:
    """Tests for worker classification endpoints."""
    
    def test_classify_engagement(self, client, auth_headers, sample_engagement):
        """Test ABC Test classification endpoint."""
        response = client.post(
            f"/pcos/engagements/{sample_engagement['id']}/classify",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "overall_result" in data
        assert "prong_a" in data
        assert "prong_b" in data
        assert "prong_c" in data
        assert data["overall_result"] in ("employee", "contractor", "uncertain")
    
    def test_get_classification_result(self, client, auth_headers, sample_engagement):
        """Test getting stored classification result."""
        # First classify
        client.post(
            f"/pcos/engagements/{sample_engagement['id']}/classify",
            headers=auth_headers
        )
        
        # Then retrieve
        response = client.get(
            f"/pcos/engagements/{sample_engagement['id']}/classification",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "overall_result" in data
        assert "risk_level" in data


# =============================================================================
# Tax Credit Endpoint Tests
# =============================================================================

class TestTaxCreditEndpoints:
    """Tests for CA tax credit pre-screening."""
    
    def test_tax_credit_analysis(self, client, auth_headers, sample_project_with_budget):
        """Test tax credit eligibility endpoint."""
        response = client.get(
            f"/pcos/projects/{sample_project_with_budget['id']}/tax-credits",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "is_eligible" in data or "eligibility_status" in data


# =============================================================================
# Form Auto-Fill Endpoint Tests
# =============================================================================

class TestFormEndpoints:
    """Tests for form auto-fill endpoints."""
    
    def test_filmla_form_generation(self, client, auth_headers, sample_project_with_location):
        """Test FilmLA permit form generation."""
        response = client.get(
            f"/pcos/projects/{sample_project_with_location['id']}/forms/filmla",
            headers=auth_headers
        )
        # May be 200 or 404 depending on location setup
        if response.status_code == 200:
            data = response.json()
            assert "pdf_fields" in data or "fields" in data


# =============================================================================
# Paperwork Tracking Endpoint Tests
# =============================================================================

class TestPaperworkEndpoints:
    """Tests for document/paperwork tracking."""
    
    def test_project_paperwork_status(self, client, auth_headers, sample_project_with_engagements):
        """Test paperwork completion status endpoint."""
        response = client.get(
            f"/pcos/projects/{sample_project_with_engagements['id']}/paperwork-status",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "overall_completion_pct" in data
        assert "engagements" in data


# =============================================================================
# Visa Timeline Endpoint Tests
# =============================================================================

class TestVisaEndpoints:
    """Tests for visa status and timeline."""
    
    def test_visa_timeline_no_visa(self, client, auth_headers, sample_person):
        """Test visa timeline for person without visa record."""
        response = client.get(
            f"/pcos/people/{sample_person['id']}/visa-timeline",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_visa_record"] == False
        assert "warnings" in data


# =============================================================================
# Compliance Snapshot Endpoint Tests
# =============================================================================

class TestComplianceSnapshotEndpoints:
    """Tests for compliance snapshots."""
    
    def test_create_snapshot(self, client, auth_headers, sample_project):
        """Test creating a compliance snapshot."""
        response = client.post(
            f"/pcos/projects/{sample_project['id']}/compliance-snapshots",
            params={"snapshot_type": "manual", "snapshot_name": "Test Snapshot"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "snapshot_id" in data
        assert "compliance_status" in data
        assert "overall_score" in data
    
    def test_list_snapshots(self, client, auth_headers, sample_project):
        """Test listing compliance snapshots."""
        # Create one first
        client.post(
            f"/pcos/projects/{sample_project['id']}/compliance-snapshots",
            params={"snapshot_type": "manual"},
            headers=auth_headers
        )
        
        response = client.get(
            f"/pcos/projects/{sample_project['id']}/compliance-snapshots",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_snapshot_with_evaluations(self, client, auth_headers, sample_project):
        """Test getting snapshot with rule evaluations."""
        # Create snapshot
        create_resp = client.post(
            f"/pcos/projects/{sample_project['id']}/compliance-snapshots",
            params={"snapshot_type": "manual"},
            headers=auth_headers
        )
        snapshot_id = create_resp.json()["snapshot_id"]
        
        # Get with evaluations
        response = client.get(
            f"/pcos/compliance-snapshots/{snapshot_id}",
            params={"include_evaluations": True},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "evaluations" in data


# =============================================================================
# Audit Pack Endpoint Tests
# =============================================================================

class TestAuditPackEndpoints:
    """Tests for audit pack generation."""
    
    def test_generate_audit_pack(self, client, auth_headers, sample_project):
        """Test generating an audit pack."""
        response = client.get(
            f"/pcos/projects/{sample_project['id']}/audit-pack",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "project" in data
        assert "generated_at" in data
    
    def test_audit_pack_with_options(self, client, auth_headers, sample_project):
        """Test audit pack with optional sections."""
        response = client.get(
            f"/pcos/projects/{sample_project['id']}/audit-pack",
            params={"include_evidence": True, "include_budget": True},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "evidence_inventory" in data or "budget_summary" in data


# =============================================================================
# Attestation Endpoint Tests
# =============================================================================

class TestAttestationEndpoints:
    """Tests for attestation workflow."""
    
    def test_attest_snapshot(self, client, auth_headers, sample_project):
        """Test attesting to a compliance snapshot."""
        # Create snapshot
        create_resp = client.post(
            f"/pcos/projects/{sample_project['id']}/compliance-snapshots",
            params={"snapshot_type": "manual"},
            headers=auth_headers
        )
        snapshot_id = create_resp.json()["snapshot_id"]
        
        # Attest
        response = client.post(
            f"/pcos/compliance-snapshots/{snapshot_id}/attest",
            params={"attestation_notes": "Reviewed and approved"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_attested"] == True
    
    def test_double_attestation_fails(self, client, auth_headers, sample_project):
        """Test that double attestation is blocked."""
        # Create and attest
        create_resp = client.post(
            f"/pcos/projects/{sample_project['id']}/compliance-snapshots",
            params={"snapshot_type": "manual"},
            headers=auth_headers
        )
        snapshot_id = create_resp.json()["snapshot_id"]
        
        client.post(
            f"/pcos/compliance-snapshots/{snapshot_id}/attest",
            headers=auth_headers
        )
        
        # Try again
        response = client.post(
            f"/pcos/compliance-snapshots/{snapshot_id}/attest",
            headers=auth_headers
        )
        assert response.status_code == 400


# =============================================================================
# Audit Events Endpoint Tests
# =============================================================================

class TestAuditEventEndpoints:
    """Tests for audit event logging."""
    
    def test_list_audit_events(self, client, auth_headers, sample_project):
        """Test listing audit events."""
        response = client.get(
            f"/pcos/projects/{sample_project['id']}/audit-events",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_filter_audit_events_by_type(self, client, auth_headers, sample_project):
        """Test filtering audit events by type."""
        response = client.get(
            f"/pcos/projects/{sample_project['id']}/audit-events",
            params={"event_type": "attestation"},
            headers=auth_headers
        )
        assert response.status_code == 200


# =============================================================================
# Health Check Endpoint Test
# =============================================================================

class TestHealthCheck:
    """Tests for health check endpoint."""
    
    def test_health_check(self, client):
        """Test PCOS health check."""
        response = client.get("/pcos/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["module"] == "Production Compliance OS"
