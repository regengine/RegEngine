"""
Unit tests for automotive service API routes.
Tests PPAP vault, LPA audit, dashboard, and health endpoints.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import uuid
from datetime import datetime

SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SERVICES_DIR))

from fastapi.testclient import TestClient
from services.automotive.app.main import app
from services.automotive.app.db_session import get_db
from services.automotive.app.auth import require_api_key
from services.automotive.app.models import PPAPSubmission, LPAAudit
from shared.middleware import get_current_tenant_id


class TestAutomotiveRoutes(unittest.TestCase):
    """Test suite for automotive service API routes."""

    def setUp(self):
        self.mock_db = MagicMock()
        self.client = TestClient(app)
        self.tenant_id = uuid.uuid4()
        self.test_api_key = "test-api-key"

        def mock_refresh(obj):
            if hasattr(obj, 'id') and obj.id is None:
                obj.id = 1
        self.mock_db.refresh.side_effect = mock_refresh

        app.dependency_overrides[get_db] = lambda: self.mock_db
        app.dependency_overrides[require_api_key] = lambda: self.test_api_key
        app.dependency_overrides[get_current_tenant_id] = lambda: self.tenant_id

    def tearDown(self):
        app.dependency_overrides = {}

    # --- Health & Root ---

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("service", data)
        self.assertIn("docs", data)

    # --- PPAP Submission ---

    def test_create_ppap_submission_success(self):
        ppap_data = {
            "part_number": "PT-12345",
            "part_name": "Brake Caliper Assembly",
            "submission_level": 3,
            "oem_customer": "Ford Motor Company",
            "submission_date": "2024-02-09T10:00:00"
        }
        response = self.client.post("/v1/automotive/ppap", json=ppap_data)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertEqual(data["part_number"], "PT-12345")
        self.assertEqual(data["approval_status"], "PENDING")
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()

    def test_create_ppap_tenant_isolation(self):
        ppap_data = {
            "part_number": "PT-99999",
            "part_name": "Engine Mount",
            "submission_level": 1,
            "oem_customer": "Toyota",
            "submission_date": "2024-02-09T11:00:00"
        }
        response = self.client.post("/v1/automotive/ppap", json=ppap_data)
        self.assertEqual(response.status_code, 201)
        args, _ = self.mock_db.add.call_args
        ppap = args[0]
        self.assertIsInstance(ppap, PPAPSubmission)
        self.assertEqual(ppap.tenant_id, self.tenant_id)

    def test_create_ppap_requires_auth(self):
        del app.dependency_overrides[require_api_key]
        ppap_data = {
            "part_number": "PT-00001",
            "part_name": "Test Part",
            "submission_level": 1,
            "oem_customer": "GM",
            "submission_date": "2024-02-09T12:00:00"
        }
        response = self.client.post("/v1/automotive/ppap", json=ppap_data)
        self.assertEqual(response.status_code, 401)
        app.dependency_overrides[require_api_key] = lambda: self.test_api_key

    def test_create_ppap_invalid_level(self):
        ppap_data = {
            "part_number": "PT-00001",
            "part_name": "Test Part",
            "submission_level": 6,
            "oem_customer": "GM",
            "submission_date": "2024-02-09T12:00:00"
        }
        response = self.client.post("/v1/automotive/ppap", json=ppap_data)
        self.assertEqual(response.status_code, 422)

    def test_get_ppap_not_found(self):
        mock_query = MagicMock()
        self.mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        response = self.client.get("/v1/automotive/ppap/99999")
        self.assertEqual(response.status_code, 404)

    # --- LPA Audit ---

    def test_create_lpa_audit_success(self):
        lpa_data = {
            "layer": "FRONTLINE",
            "process_step": "Brake Assembly Line",
            "question": "Are torque values within specification?",
            "result": "PASS",
            "auditor_name": "John Smith"
        }
        response = self.client.post("/v1/automotive/lpa", json=lpa_data)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertEqual(data["result"], "PASS")

        args, _ = self.mock_db.add.call_args
        lpa = args[0]
        self.assertIsInstance(lpa, LPAAudit)
        self.assertEqual(lpa.tenant_id, self.tenant_id)

    def test_create_lpa_audit_fail_with_corrective_action(self):
        lpa_data = {
            "layer": "MANAGEMENT",
            "process_step": "Paint Line QC",
            "question": "Is paint thickness within tolerance?",
            "result": "FAIL",
            "auditor_name": "Jane Doe",
            "corrective_action": "Recalibrate spray nozzle #4"
        }
        response = self.client.post("/v1/automotive/lpa", json=lpa_data)
        self.assertEqual(response.status_code, 201)

    def test_create_lpa_invalid_layer(self):
        lpa_data = {
            "layer": "INVALID",
            "process_step": "Test",
            "question": "Test?",
            "result": "PASS",
            "auditor_name": "Test User"
        }
        response = self.client.post("/v1/automotive/lpa", json=lpa_data)
        self.assertEqual(response.status_code, 422)

    def test_create_lpa_requires_auth(self):
        del app.dependency_overrides[require_api_key]
        lpa_data = {
            "layer": "FRONTLINE",
            "process_step": "Test",
            "question": "Test?",
            "result": "PASS",
            "auditor_name": "Test"
        }
        response = self.client.post("/v1/automotive/lpa", json=lpa_data)
        self.assertEqual(response.status_code, 401)
        app.dependency_overrides[require_api_key] = lambda: self.test_api_key

    # --- Dashboard ---

    def test_dashboard_success(self):
        self.mock_db.query.return_value.filter.return_value.scalar.return_value = 0
        response = self.client.get("/v1/automotive/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_ppap_submissions", data)
        self.assertIn("lpa_pass_rate_30d", data)

    def test_dashboard_requires_auth(self):
        del app.dependency_overrides[require_api_key]
        response = self.client.get("/v1/automotive/dashboard")
        self.assertEqual(response.status_code, 401)
        app.dependency_overrides[require_api_key] = lambda: self.test_api_key


if __name__ == '__main__':
    unittest.main()
