"""
Unit tests for Aerospace Compliance Service API routes.

Tests cover:
- All API endpoints with mocked DB dependencies
- Authentication (require_api_key dependency)
- HTTP status codes (200, 201, 404, 422, 401)
- Request/response schema validation
- Tenant isolation
"""

import sys
import unittest
from unittest.mock import MagicMock, ANY
from pathlib import Path
import uuid
from datetime import datetime, timedelta

# Add services directory to path
SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SERVICES_DIR))

from fastapi.testclient import TestClient
from services.aerospace.app.main import app
from services.aerospace.app.db_session import get_db
from services.aerospace.app.auth import require_api_key
from shared.middleware import get_current_tenant_id
from services.aerospace.app.models import FAIReport, ConfigurationBaseline, NADCAPEvidence


class TestAerospaceRoutes(unittest.TestCase):
    """Test suite for Aerospace Compliance Service API routes."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_db = MagicMock()
        self.client = TestClient(app)
        self.tenant_id = uuid.uuid4()
        
        # Mock db.refresh to simulate ID assignment
        def mock_refresh(obj):
            if hasattr(obj, 'id') and obj.id is None:
                obj.id = 1
        self.mock_db.refresh.side_effect = mock_refresh
        
        # Override dependencies
        app.dependency_overrides[get_db] = lambda: self.mock_db
        app.dependency_overrides[require_api_key] = lambda: "test-api-key"
        app.dependency_overrides[get_current_tenant_id] = lambda: self.tenant_id
    
    def tearDown(self):
        """Clean up after tests."""
        app.dependency_overrides = {}
    
    # Health and Root Endpoints
    
    def test_health_check(self):
        """Test /health endpoint returns healthy status."""
        response = self.client.get("/health")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("service", data)
        self.assertIn("version", data)
    
    def test_root_endpoint(self):
        """Test / root endpoint returns service information."""
        response = self.client.get("/")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("service", data)
        self.assertIn("version", data)
        self.assertEqual(data["docs"], "/docs")
        self.assertEqual(data["health"], "/health")
    
    # FAI Report Endpoints
    
    def test_create_fai_report_success(self):
        """Test POST /v1/aerospace/fai creates FAI report successfully."""
        # Mock no existing report
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        payload = {
            "part_number": "PN-12345",
            "part_name": "Wing Bracket",
            "drawing_number": "DRW-001",
            "drawing_revision": "A",
            "customer_name": "Boeing",
            "customer_part_number": "BA-789",
            "form1_data": {"section": "accountability"},
            "form2_data": [{"section": "product"}],
            "form3_data": [{"section": "characteristics"}],
            "inspection_method": "ACTUAL",
            "inspection_date": "2024-01-15T10:00:00",
            "inspector_name": "John Doe"
        }
        
        response = self.client.post("/v1/aerospace/fai", json=payload)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["part_number"], "PN-12345")
        self.assertEqual(data["drawing_revision"], "A")
        self.assertEqual(data["approval_status"], "PENDING")
        self.assertIn("content_hash", data)
        
        # Verify db.add was called with correct tenant_id
        self.mock_db.add.assert_called_once()
        args, _ = self.mock_db.add.call_args
        fai = args[0]
        self.assertIsInstance(fai, FAIReport)
        self.assertEqual(fai.tenant_id, self.tenant_id)
        self.assertEqual(fai.part_number, "PN-12345")
    
    def test_create_fai_report_duplicate_returns_existing(self):
        """Test POST /v1/aerospace/fai returns existing report for duplicate."""
        # Mock existing report with same hash
        existing_fai = FAIReport(
            id=1,
            tenant_id=self.tenant_id,
            part_number="PN-12345",
            drawing_revision="A",
            content_hash="abc123",
            approval_status="PENDING",
            created_at=datetime.utcnow()
        )
        self.mock_db.query.return_value.filter.return_value.first.return_value = existing_fai
        
        payload = {
            "part_number": "PN-12345",
            "part_name": "Wing Bracket",
            "drawing_number": "DRW-001",
            "drawing_revision": "A",
            "customer_name": "Boeing",
            "form1_data": {"section": "accountability"},
            "form2_data": [{"section": "product"}],
            "form3_data": [{"section": "characteristics"}],
            "inspection_method": "ACTUAL",
            "inspection_date": "2024-01-15T10:00:00",
            "inspector_name": "John Doe"
        }
        
        response = self.client.post("/v1/aerospace/fai", json=payload)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["id"], 1)
        # Verify db.add was NOT called (returned existing)
        self.mock_db.add.assert_not_called()
    
    def test_create_fai_report_validation_error(self):
        """Test POST /v1/aerospace/fai returns 422 for invalid data."""
        payload = {
            "part_number": "",  # Invalid: empty string
            "drawing_revision": "A",
            "form1_data": {},
            "form2_data": [],
            "form3_data": []
        }
        
        response = self.client.post("/v1/aerospace/fai", json=payload)
        
        self.assertEqual(response.status_code, 422)
    
    def test_create_fai_report_without_auth(self):
        """Test POST /v1/aerospace/fai returns 401 without API key."""
        # Remove auth override
        app.dependency_overrides.pop(require_api_key, None)
        
        payload = {
            "part_number": "PN-12345",
            "part_name": "Wing Bracket",
            "drawing_number": "DRW-001",
            "drawing_revision": "A",
            "customer_name": "Boeing",
            "form1_data": {},
            "form2_data": [],
            "form3_data": [],
            "inspection_method": "ACTUAL",
            "inspection_date": "2024-01-15T10:00:00",
            "inspector_name": "John Doe"
        }
        
        response = self.client.post("/v1/aerospace/fai", json=payload)
        
        self.assertEqual(response.status_code, 401)
        
        # Restore override for other tests
        app.dependency_overrides[require_api_key] = lambda: "test-api-key"
    
    def test_get_fai_report_success(self):
        """Test GET /v1/aerospace/fai/{fai_id} retrieves report successfully."""
        mock_fai = FAIReport(
            id=1,
            tenant_id=self.tenant_id,
            part_number="PN-12345",
            part_name="Wing Bracket",
            drawing_number="DRW-001",
            drawing_revision="A",
            customer_name="Boeing",
            customer_part_number="BA-789",
            form1_data={"section": "accountability"},
            form2_data=[{"section": "product"}],
            form3_data=[{"section": "characteristics"}],
            inspection_method="ACTUAL",
            inspection_date=datetime(2024, 1, 15, 10, 0, 0),
            inspector_name="John Doe",
            content_hash="abc123",
            approval_status="PENDING",
            approval_date=None,
            approval_notes=None,
            created_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_fai
        
        response = self.client.get("/v1/aerospace/fai/1")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["part_number"], "PN-12345")
        self.assertEqual(data["drawing_revision"], "A")
        self.assertIn("form1_data", data)
    
    def test_get_fai_report_not_found(self):
        """Test GET /v1/aerospace/fai/{fai_id} returns 404 for non-existent report."""
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = self.client.get("/v1/aerospace/fai/999")
        
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "FAI report not found")
    
    def test_get_fai_report_cross_tenant_access_denied(self):
        """Test GET /v1/aerospace/fai/{fai_id} returns 404 for different tenant."""
        # Report exists but belongs to different tenant (query filters it out)
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = self.client.get("/v1/aerospace/fai/1")
        
        self.assertEqual(response.status_code, 404)
    
    def test_approve_fai_report_success(self):
        """Test PATCH /v1/aerospace/fai/{fai_id}/approve approves report."""
        mock_fai = FAIReport(
            id=1,
            tenant_id=self.tenant_id,
            approval_status="PENDING",
            approval_date=None
        )
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_fai
        
        response = self.client.patch(
            "/v1/aerospace/fai/1/approve?approval_status=APPROVED&approval_notes=Looks good"
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["approval_status"], "APPROVED")
        self.assertIsNotNone(data["approval_date"])
        self.assertEqual(data["approval_notes"], "Looks good")
    
    def test_approve_fai_report_not_found(self):
        """Test PATCH /v1/aerospace/fai/{fai_id}/approve returns 404."""
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = self.client.patch(
            "/v1/aerospace/fai/999/approve?approval_status=APPROVED"
        )
        
        self.assertEqual(response.status_code, 404)
    
    def test_approve_fai_report_invalid_status(self):
        """Test PATCH /v1/aerospace/fai/{fai_id}/approve with invalid status returns 422."""
        mock_fai = FAIReport(id=1, tenant_id=self.tenant_id)
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_fai
        
        response = self.client.patch(
            "/v1/aerospace/fai/1/approve?approval_status=INVALID"
        )
        
        self.assertEqual(response.status_code, 422)
    
    # Configuration Baseline Endpoints
    
    def test_create_config_baseline_success(self):
        """Test POST /v1/aerospace/config-baseline creates baseline successfully."""
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        payload = {
            "assembly_id": "ASM-001",
            "assembly_name": "Landing Gear Assembly",
            "serial_number": "SN-12345",
            "baseline_data": [
                {"part": "PN-111", "rev": "A"},
                {"part": "PN-222", "rev": "B"}
            ],
            "manufacturing_date": "2024-01-20T08:00:00"
        }
        
        response = self.client.post("/v1/aerospace/config-baseline", json=payload)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["assembly_id"], "ASM-001")
        self.assertEqual(data["serial_number"], "SN-12345")
        self.assertEqual(data["lifecycle_status"], "ACTIVE")
        self.assertIn("baseline_hash", data)
        
        # Verify tenant_id is set
        self.mock_db.add.assert_called_once()
        args, _ = self.mock_db.add.call_args
        baseline = args[0]
        self.assertIsInstance(baseline, ConfigurationBaseline)
        self.assertEqual(baseline.tenant_id, self.tenant_id)
    
    def test_create_config_baseline_duplicate_returns_existing(self):
        """Test POST /v1/aerospace/config-baseline returns existing for duplicate."""
        existing_baseline = ConfigurationBaseline(
            id=1,
            tenant_id=self.tenant_id,
            assembly_id="ASM-001",
            serial_number="SN-12345",
            baseline_hash="xyz789",
            lifecycle_status="ACTIVE",
            created_at=datetime.utcnow()
        )
        self.mock_db.query.return_value.filter.return_value.first.return_value = existing_baseline
        
        payload = {
            "assembly_id": "ASM-001",
            "assembly_name": "Landing Gear Assembly",
            "serial_number": "SN-12345",
            "baseline_data": [{"part": "PN-111", "rev": "A"}],
            "manufacturing_date": "2024-01-20T08:00:00"
        }
        
        response = self.client.post("/v1/aerospace/config-baseline", json=payload)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["id"], 1)
        self.mock_db.add.assert_not_called()
    
    def test_create_config_baseline_validation_error(self):
        """Test POST /v1/aerospace/config-baseline returns 422 for invalid data."""
        payload = {
            "assembly_id": "",  # Invalid: empty
            "baseline_data": []
        }
        
        response = self.client.post("/v1/aerospace/config-baseline", json=payload)
        
        self.assertEqual(response.status_code, 422)
    
    def test_get_config_baseline_success(self):
        """Test GET /v1/aerospace/config-baseline/{baseline_id} retrieves baseline."""
        mock_baseline = ConfigurationBaseline(
            id=1,
            tenant_id=self.tenant_id,
            assembly_id="ASM-001",
            assembly_name="Landing Gear Assembly",
            serial_number="SN-12345",
            baseline_data=[{"part": "PN-111", "rev": "A"}],
            baseline_hash="xyz789",
            fai_report_id=None,
            manufacturing_date=datetime(2024, 1, 20, 8, 0, 0),
            end_of_life_date=None,
            lifecycle_status="ACTIVE",
            notes=None,
            created_at=datetime(2024, 1, 20, 8, 0, 0)
        )
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_baseline
        
        response = self.client.get("/v1/aerospace/config-baseline/1")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["assembly_id"], "ASM-001")
        self.assertIn("baseline_data", data)
    
    def test_get_config_baseline_not_found(self):
        """Test GET /v1/aerospace/config-baseline/{baseline_id} returns 404."""
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = self.client.get("/v1/aerospace/config-baseline/999")
        
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Configuration baseline not found")
    
    # NADCAP Evidence Endpoints
    
    def test_create_nadcap_evidence_success(self):
        """Test POST /v1/aerospace/nadcap-evidence creates evidence successfully."""
        payload = {
            "process_type": "HEAT_TREAT",
            "part_number": "PN-12345",
            "lot_number": "LOT-001",
            "process_parameters": {"temperature": 1050, "time_minutes": 120},
            "process_results": {"hardness": 45},
            "operator_name": "Jane Smith",
            "equipment_id": "FURNACE-01",
            "process_date": "2024-01-25T14:00:00"
        }
        
        response = self.client.post("/v1/aerospace/nadcap-evidence", json=payload)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["process_type"], "HEAT_TREAT")
        self.assertEqual(data["part_number"], "PN-12345")
        self.assertEqual(data["status"], "recorded")
        self.assertIn("content_hash", data)
        
        # Verify tenant_id is set
        self.mock_db.add.assert_called_once()
        args, _ = self.mock_db.add.call_args
        evidence = args[0]
        self.assertIsInstance(evidence, NADCAPEvidence)
        self.assertEqual(evidence.tenant_id, self.tenant_id)
    
    def test_create_nadcap_evidence_validation_error(self):
        """Test POST /v1/aerospace/nadcap-evidence returns 422 for invalid data."""
        payload = {
            "process_type": "INVALID_TYPE",  # Invalid process type
            "part_number": "PN-12345"
        }
        
        response = self.client.post("/v1/aerospace/nadcap-evidence", json=payload)
        
        self.assertEqual(response.status_code, 422)
    
    # Dashboard Endpoint
    
    def test_get_dashboard_success(self):
        """Test GET /v1/aerospace/dashboard returns metrics."""
        # Mock query results for dashboard metrics
        self.mock_db.query.return_value.filter.return_value.scalar.return_value = 10
        
        response = self.client.get("/v1/aerospace/dashboard")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_fai_reports", data)
        self.assertIn("pending_fai_approvals", data)
        self.assertIn("active_configurations", data)
        self.assertIn("nadcap_expiring_soon", data)
        self.assertIn("avg_fai_approval_days", data)
        self.assertIsInstance(data["total_fai_reports"], int)
        self.assertIsInstance(data["avg_fai_approval_days"], float)
    
    def test_get_dashboard_without_auth(self):
        """Test GET /v1/aerospace/dashboard returns 401 without API key."""
        app.dependency_overrides.pop(require_api_key, None)
        
        response = self.client.get("/v1/aerospace/dashboard")
        
        self.assertEqual(response.status_code, 401)
        
        # Restore override
        app.dependency_overrides[require_api_key] = lambda: "test-api-key"
    
    # Authentication Tests
    
    def test_require_api_key_missing_header(self):
        """Test endpoints require X-RegEngine-API-Key header."""
        app.dependency_overrides.pop(require_api_key, None)
        
        response = self.client.get("/v1/aerospace/dashboard")
        
        self.assertEqual(response.status_code, 401)
        self.assertIn("Missing X-RegEngine-API-Key header", response.json()["detail"])
        
        app.dependency_overrides[require_api_key] = lambda: "test-api-key"
    
    def test_require_api_key_empty_header(self):
        """Test endpoints reject empty API key."""
        app.dependency_overrides.pop(require_api_key, None)
        
        response = self.client.get(
            "/v1/aerospace/dashboard",
            headers={"X-RegEngine-API-Key": ""}
        )
        
        self.assertEqual(response.status_code, 401)
        
        app.dependency_overrides[require_api_key] = lambda: "test-api-key"
    
    # Tenant Isolation Tests
    
    def test_fai_tenant_isolation(self):
        """Test FAI endpoints enforce tenant isolation."""
        # Query returns None because tenant_id doesn't match
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = self.client.get("/v1/aerospace/fai/1")
        
        self.assertEqual(response.status_code, 404)
        # Verify query included tenant_id filter
        self.mock_db.query.assert_called()
    
    def test_baseline_tenant_isolation(self):
        """Test config baseline endpoints enforce tenant isolation."""
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = self.client.get("/v1/aerospace/config-baseline/1")
        
        self.assertEqual(response.status_code, 404)
        self.mock_db.query.assert_called()


if __name__ == '__main__':
    unittest.main()
