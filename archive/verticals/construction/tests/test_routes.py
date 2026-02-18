"""
Unit tests for construction service API routes.

Tests all endpoints with mocked dependencies, authentication,
status codes, and schema validation.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import uuid
from datetime import datetime

# Add services directory to path for shared imports
SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SERVICES_DIR))

from fastapi.testclient import TestClient
from services.construction.app.main import app
from services.construction.app.db_session import get_db
from services.construction.app.auth import require_api_key
from services.construction.app.models import BIMChangeRecord, OSHASafetyInspection
from shared.middleware import get_current_tenant_id


class TestConstructionRoutes(unittest.TestCase):
    """Test suite for construction service API routes."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_db = MagicMock()
        self.client = TestClient(app)
        self.tenant_id = uuid.uuid4()
        self.test_api_key = "test-api-key"
        
        # Mock db.refresh to simulate ID assignment
        def mock_refresh(obj):
            if hasattr(obj, 'id') and obj.id is None:
                obj.id = 1
        self.mock_db.refresh.side_effect = mock_refresh
        
        # Override dependencies
        app.dependency_overrides[get_db] = lambda: self.mock_db
        app.dependency_overrides[require_api_key] = lambda: self.test_api_key
        app.dependency_overrides[get_current_tenant_id] = lambda: self.tenant_id

    def tearDown(self):
        """Clean up test fixtures."""
        app.dependency_overrides = {}

    def test_health_endpoint(self):
        """Test health check endpoint."""
        response = self.client.get("/health")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "construction")

    def test_create_bim_change_success(self):
        """Test successful BIM change record creation."""
        bim_data = {
            "project_id": "PRJ-001",
            "project_name": "Downtown Tower",
            "change_number": "CHG-001",
            "change_type": "DESIGN_REVISION",
            "description": "Updated structural plans",
            "file_name": "structural-v2.ifc",
            "file_version": "2.0",
            "file_content": "mock file content",
            "submitted_by": "john.doe@example.com"
        }
        
        response = self.client.post("/v1/construction/bim-change", json=bim_data)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertEqual(data["change_number"], "CHG-001")
        self.assertIn("file_hash", data)
        
        # Verify db operations
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()
        self.mock_db.refresh.assert_called_once()
        
        # Verify BIMChangeRecord was created with correct tenant_id
        args, _ = self.mock_db.add.call_args
        bim_change = args[0]
        self.assertIsInstance(bim_change, BIMChangeRecord)
        self.assertEqual(bim_change.tenant_id, self.tenant_id)
        self.assertEqual(bim_change.project_id, "PRJ-001")
        self.assertEqual(bim_change.change_type, "DESIGN_REVISION")
        self.assertEqual(bim_change.status, "PENDING")

    def test_create_bim_change_tenant_isolation(self):
        """Test BIM change record enforces tenant isolation."""
        bim_data = {
            "project_id": "PRJ-002",
            "project_name": "City Hall Renovation",
            "change_number": "CHG-002",
            "change_type": "RFI",
            "description": "Request for information",
            "file_name": "rfi-001.pdf",
            "file_version": "1.0",
            "file_content": "content",
            "submitted_by": "jane.smith@example.com"
        }
        
        response = self.client.post("/v1/construction/bim-change", json=bim_data)
        
        self.assertEqual(response.status_code, 201)
        
        # Verify tenant_id is set correctly
        args, _ = self.mock_db.add.call_args
        bim_change = args[0]
        self.assertEqual(bim_change.tenant_id, self.tenant_id)

    def test_create_bim_change_requires_auth(self):
        """Test BIM change creation requires API key."""
        # Remove auth override to test actual auth logic
        del app.dependency_overrides[require_api_key]
        
        bim_data = {
            "project_id": "PRJ-003",
            "project_name": "Test Project",
            "change_number": "CHG-003",
            "change_type": "SUBMITTAL",
            "description": "Test",
            "file_name": "test.pdf",
            "file_version": "1.0",
            "file_content": "test",
            "submitted_by": "test@example.com"
        }
        
        response = self.client.post("/v1/construction/bim-change", json=bim_data)
        
        # Should fail without API key
        self.assertEqual(response.status_code, 401)
        
        # Restore override
        app.dependency_overrides[require_api_key] = lambda: self.test_api_key

    def test_create_bim_change_invalid_change_type(self):
        """Test BIM change creation validates change_type."""
        bim_data = {
            "project_id": "PRJ-004",
            "project_name": "Test Project",
            "change_number": "CHG-004",
            "change_type": "INVALID_TYPE",  # Invalid type
            "description": "Test",
            "file_name": "test.pdf",
            "file_version": "1.0",
            "file_content": "test",
            "submitted_by": "test@example.com"
        }
        
        response = self.client.post("/v1/construction/bim-change", json=bim_data)
        
        # Should fail validation
        self.assertEqual(response.status_code, 422)

    def test_create_bim_change_file_hash_generation(self):
        """Test BIM change generates correct SHA-256 file hash."""
        bim_data = {
            "project_id": "PRJ-005",
            "project_name": "Test Project",
            "change_number": "CHG-005",
            "change_type": "CHANGE_ORDER",
            "description": "Test change order",
            "file_name": "change-order.pdf",
            "file_version": "1.0",
            "file_content": "test content",
            "submitted_by": "test@example.com"
        }
        
        response = self.client.post("/v1/construction/bim-change", json=bim_data)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        
        # Verify hash was generated
        self.assertIn("file_hash", data)
        self.assertEqual(len(data["file_hash"]), 64)  # SHA-256 is 64 hex chars
        
        # Verify hash is deterministic
        import hashlib
        expected_hash = hashlib.sha256(b"test content").hexdigest()
        self.assertEqual(data["file_hash"], expected_hash)

    def test_create_osha_inspection_success(self):
        """Test successful OSHA inspection creation."""
        inspection_data = {
            "project_id": "PRJ-001",
            "inspection_date": "2024-02-09T10:00:00",
            "inspector_name": "John Safety",
            "inspection_type": "WEEKLY",
            "violations_found": 0,
            "violation_description": None
        }
        
        response = self.client.post("/v1/construction/osha-inspection", json=inspection_data)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertEqual(data["violations_found"], 0)
        
        # Verify db operations
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()
        self.mock_db.refresh.assert_called_once()
        
        # Verify OSHASafetyInspection was created
        args, _ = self.mock_db.add.call_args
        inspection = args[0]
        self.assertIsInstance(inspection, OSHASafetyInspection)
        self.assertEqual(inspection.tenant_id, self.tenant_id)
        self.assertEqual(inspection.project_id, "PRJ-001")
        self.assertEqual(inspection.status, "CLOSED")  # No violations = CLOSED

    def test_create_osha_inspection_with_violations(self):
        """Test OSHA inspection with violations sets status to OPEN."""
        inspection_data = {
            "project_id": "PRJ-002",
            "inspection_date": "2024-02-09T10:00:00",
            "inspector_name": "Jane Safety",
            "inspection_type": "MONTHLY",
            "violations_found": 2,
            "violation_description": "Fall protection issues"
        }
        
        response = self.client.post("/v1/construction/osha-inspection", json=inspection_data)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["violations_found"], 2)
        
        # Verify status is OPEN when violations exist
        args, _ = self.mock_db.add.call_args
        inspection = args[0]
        self.assertEqual(inspection.status, "OPEN")
        self.assertEqual(inspection.violations_found, 2)

    def test_create_osha_inspection_tenant_isolation(self):
        """Test OSHA inspection enforces tenant isolation."""
        inspection_data = {
            "project_id": "PRJ-003",
            "inspection_date": "2024-02-09T10:00:00",
            "inspector_name": "Bob Safety",
            "inspection_type": "INCIDENT",
            "violations_found": 1,
            "violation_description": "Safety incident"
        }
        
        response = self.client.post("/v1/construction/osha-inspection", json=inspection_data)
        
        self.assertEqual(response.status_code, 201)
        
        # Verify tenant_id is set correctly
        args, _ = self.mock_db.add.call_args
        inspection = args[0]
        self.assertEqual(inspection.tenant_id, self.tenant_id)

    def test_create_osha_inspection_requires_auth(self):
        """Test OSHA inspection creation requires API key."""
        # Remove auth override to test actual auth logic
        del app.dependency_overrides[require_api_key]
        
        inspection_data = {
            "project_id": "PRJ-004",
            "inspection_date": "2024-02-09T10:00:00",
            "inspector_name": "Test Inspector",
            "inspection_type": "WEEKLY",
            "violations_found": 0
        }
        
        response = self.client.post("/v1/construction/osha-inspection", json=inspection_data)
        
        # Should fail without API key
        self.assertEqual(response.status_code, 401)
        
        # Restore override
        app.dependency_overrides[require_api_key] = lambda: self.test_api_key

    def test_create_osha_inspection_invalid_inspection_type(self):
        """Test OSHA inspection validates inspection_type."""
        inspection_data = {
            "project_id": "PRJ-005",
            "inspection_date": "2024-02-09T10:00:00",
            "inspector_name": "Test Inspector",
            "inspection_type": "INVALID_TYPE",  # Invalid type
            "violations_found": 0
        }
        
        response = self.client.post("/v1/construction/osha-inspection", json=inspection_data)
        
        # Should fail validation
        self.assertEqual(response.status_code, 422)

    def test_dashboard_success(self):
        """Test dashboard metrics retrieval."""
        # Mock database query results
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_scalar = MagicMock()
        
        # Chain the mock calls
        self.mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.scalar.side_effect = [10, 3, 5, 2]  # total_changes, pending, total_inspections, open_violations
        
        response = self.client.get("/v1/construction/dashboard")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify dashboard structure
        self.assertIn("total_bim_changes", data)
        self.assertIn("pending_approvals", data)
        self.assertIn("total_osha_inspections", data)
        self.assertIn("open_violations", data)
        
        # Verify values
        self.assertEqual(data["total_bim_changes"], 10)
        self.assertEqual(data["pending_approvals"], 3)
        self.assertEqual(data["total_osha_inspections"], 5)
        self.assertEqual(data["open_violations"], 2)

    def test_dashboard_tenant_isolation(self):
        """Test dashboard respects tenant isolation."""
        # Mock database query
        mock_query = MagicMock()
        mock_filter = MagicMock()
        
        self.mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.scalar.return_value = 0
        
        response = self.client.get("/v1/construction/dashboard")
        
        self.assertEqual(response.status_code, 200)
        
        # Verify tenant_id was used in filter calls
        # Each metric query should filter by tenant_id
        filter_calls = mock_query.filter.call_args_list
        self.assertGreater(len(filter_calls), 0)

    def test_dashboard_requires_auth(self):
        """Test dashboard requires API key."""
        # Remove auth override to test actual auth logic
        del app.dependency_overrides[require_api_key]
        
        response = self.client.get("/v1/construction/dashboard")
        
        # Should fail without API key
        self.assertEqual(response.status_code, 401)
        
        # Restore override
        app.dependency_overrides[require_api_key] = lambda: self.test_api_key

    def test_dashboard_empty_database(self):
        """Test dashboard with no data returns zeros."""
        # Mock database query to return None (no results)
        mock_query = MagicMock()
        mock_filter = MagicMock()
        
        self.mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.scalar.return_value = None  # No data
        
        response = self.client.get("/v1/construction/dashboard")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should return zeros for empty database
        self.assertEqual(data["total_bim_changes"], 0)
        self.assertEqual(data["pending_approvals"], 0)
        self.assertEqual(data["total_osha_inspections"], 0)
        self.assertEqual(data["open_violations"], 0)


if __name__ == '__main__':
    unittest.main()
