"""
Unit tests for gaming service API routes.

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
from services.gaming.app.main import app
from services.gaming.app.db_session import get_db
from services.gaming.app.auth import require_api_key
from services.gaming.app.models import TransactionLog, SelfExclusionRecord
from shared.middleware import get_current_tenant_id


class TestGamingRoutes(unittest.TestCase):
    """Test suite for gaming service API routes."""

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

        # Mock query to return no exclusion by default
        mock_query = MagicMock()
        self.mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_query.scalar.return_value = 0
        mock_query.all.return_value = []

        # Override dependencies
        app.dependency_overrides[get_db] = lambda: self.mock_db
        app.dependency_overrides[require_api_key] = lambda: self.test_api_key
        app.dependency_overrides[get_current_tenant_id] = lambda: self.tenant_id

    def tearDown(self):
        """Clean up test fixtures."""
        app.dependency_overrides = {}

    # --- Health & Root Endpoints ---

    def test_health_endpoint(self):
        """Test health check endpoint."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")

    def test_root_endpoint(self):
        """Test root endpoint returns service info."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("service", data)
        self.assertIn("docs", data)

    # --- Transaction Endpoints ---

    def test_create_transaction_success(self):
        """Test successful transaction log creation."""
        tx_data = {
            "player_id": "PLR-001",
            "transaction_type": "WAGER",
            "amount_cents": 10000,
            "game_id": "SLOT-001",
            "jurisdiction": "US-NV",
            "timestamp": "2024-02-09T10:00:00",
            "metadata": {"game_type": "slots"}
        }

        response = self.client.post("/v1/gaming/transaction-log", json=tx_data)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertIn("content_hash", data)
        self.assertEqual(data["status"], "sealed")

        # Verify db operations
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()

        # Verify TransactionLog was created with correct tenant_id
        args, _ = self.mock_db.add.call_args
        tx = args[0]
        self.assertIsInstance(tx, TransactionLog)
        self.assertEqual(tx.tenant_id, self.tenant_id)
        self.assertEqual(tx.player_id, "PLR-001")

    def test_create_transaction_tenant_isolation(self):
        """Test transaction creation enforces tenant isolation."""
        tx_data = {
            "player_id": "PLR-002",
            "transaction_type": "PAYOUT",
            "amount_cents": 50000,
            "game_id": "TABLE-001",
            "jurisdiction": "US-NJ",
            "timestamp": "2024-02-09T11:00:00"
        }

        response = self.client.post("/v1/gaming/transaction-log", json=tx_data)
        self.assertEqual(response.status_code, 201)

        args, _ = self.mock_db.add.call_args
        tx = args[0]
        self.assertEqual(tx.tenant_id, self.tenant_id)

    def test_create_transaction_requires_auth(self):
        """Test transaction creation requires API key."""
        del app.dependency_overrides[require_api_key]

        tx_data = {
            "player_id": "PLR-003",
            "transaction_type": "WAGER",
            "amount_cents": 5000,
            "game_id": "SLOT-002",
            "jurisdiction": "US-NV",
            "timestamp": "2024-02-09T12:00:00"
        }

        response = self.client.post("/v1/gaming/transaction-log", json=tx_data)
        self.assertEqual(response.status_code, 401)

        app.dependency_overrides[require_api_key] = lambda: self.test_api_key

    def test_create_transaction_hash_generated(self):
        """Test transaction generates SHA-256 content hash."""
        tx_data = {
            "player_id": "PLR-004",
            "transaction_type": "WAGER",
            "amount_cents": 7500,
            "game_id": "SLOT-003",
            "jurisdiction": "US-NV",
            "timestamp": "2024-02-09T13:00:00"
        }

        response = self.client.post("/v1/gaming/transaction-log", json=tx_data)
        self.assertEqual(response.status_code, 201)
        data = response.json()

        # Hash should be 64 hex chars (SHA-256)
        self.assertIn("content_hash", data)
        self.assertEqual(len(data["content_hash"]), 64)

    def test_get_transaction_success(self):
        """Test retrieving a transaction by ID."""
        mock_tx = MagicMock()
        mock_tx.id = 1
        mock_tx.player_id = "PLR-001"
        mock_tx.transaction_type = "WAGER"
        mock_tx.amount_cents = 10000
        mock_tx.game_id = "SLOT-001"
        mock_tx.jurisdiction = "US-NV"
        mock_tx.content_hash = "a" * 64
        mock_tx.created_at = datetime(2024, 2, 9, 10, 0, 0)
        mock_tx.timestamp = datetime(2024, 2, 9, 10, 0, 0)
        mock_tx.metadata = None
        mock_tx.tenant_id = self.tenant_id

        mock_query = MagicMock()
        self.mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_tx

        response = self.client.get("/v1/gaming/transaction-log/1")
        self.assertEqual(response.status_code, 200)

    def test_get_transaction_not_found(self):
        """Test retrieving nonexistent transaction returns 404."""
        mock_query = MagicMock()
        self.mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        response = self.client.get("/v1/gaming/transaction-log/99999")
        self.assertEqual(response.status_code, 404)

    # --- Self-Exclusion Endpoints ---

    def test_register_self_exclusion_success(self):
        """Test successful self-exclusion registration."""
        exclusion_data = {
            "player_id": "PLR-010",
            "duration_days": 90,
            "reason": "Responsible gaming break"
        }

        response = self.client.post("/v1/gaming/self-exclusion", json=exclusion_data)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["player_id"], "PLR-010")

        # Verify SelfExclusionRecord was created
        args, _ = self.mock_db.add.call_args
        record = args[0]
        self.assertIsInstance(record, SelfExclusionRecord)
        self.assertEqual(record.tenant_id, self.tenant_id)
        self.assertEqual(record.player_id, "PLR-010")
        self.assertEqual(record.duration_days, 90)

    def test_register_self_exclusion_permanent(self):
        """Test permanent self-exclusion (duration_days=0)."""
        exclusion_data = {
            "player_id": "PLR-011",
            "duration_days": 0,
            "reason": "Permanent exclusion"
        }

        response = self.client.post("/v1/gaming/self-exclusion", json=exclusion_data)
        self.assertEqual(response.status_code, 201)

        args, _ = self.mock_db.add.call_args
        record = args[0]
        self.assertEqual(record.duration_days, 0)

    def test_register_self_exclusion_requires_auth(self):
        """Test self-exclusion requires API key."""
        del app.dependency_overrides[require_api_key]

        exclusion_data = {
            "player_id": "PLR-012",
            "duration_days": 30
        }

        response = self.client.post("/v1/gaming/self-exclusion", json=exclusion_data)
        self.assertEqual(response.status_code, 401)

        app.dependency_overrides[require_api_key] = lambda: self.test_api_key

    # --- Dashboard Endpoint ---

    def test_dashboard_success(self):
        """Test dashboard metrics retrieval."""
        mock_query = MagicMock()
        mock_filter = MagicMock()

        self.mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.scalar.side_effect = [100, 5000, 3, 2, 1]
        mock_filter.all.return_value = []
        mock_filter.group_by.return_value = mock_filter

        response = self.client.get("/v1/gaming/dashboard")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_transactions", data)

    def test_dashboard_requires_auth(self):
        """Test dashboard requires API key."""
        del app.dependency_overrides[require_api_key]

        response = self.client.get("/v1/gaming/dashboard")
        self.assertEqual(response.status_code, 401)

        app.dependency_overrides[require_api_key] = lambda: self.test_api_key

    # --- Export Endpoint ---

    def test_export_compliance_report_success(self):
        """Test compliance report export."""
        mock_query = MagicMock()
        mock_filter = MagicMock()

        self.mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.filter.return_value = mock_filter
        mock_filter.order_by.return_value = mock_filter
        mock_filter.all.return_value = []

        response = self.client.post(
            "/v1/gaming/compliance-export",
            params={
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-02-01T00:00:00"
            }
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("transactions", data)

    def test_export_requires_auth(self):
        """Test export requires API key."""
        del app.dependency_overrides[require_api_key]

        response = self.client.post(
            "/v1/gaming/compliance-export",
            params={
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-02-01T00:00:00"
            }
        )
        self.assertEqual(response.status_code, 401)

        app.dependency_overrides[require_api_key] = lambda: self.test_api_key


if __name__ == '__main__':
    unittest.main()
