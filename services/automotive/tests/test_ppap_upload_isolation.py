import sys
import unittest
from unittest.mock import MagicMock, ANY
from pathlib import Path
import uuid
import tempfile
import shutil
import os
from datetime import datetime

# Add services directory to path so we can import 'shared'
# Assumes this test file is at services/automotive/tests/test_ppap_upload_isolation.py
SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SERVICES_DIR))

from fastapi.testclient import TestClient
from services.automotive.app.main import app
from services.automotive.app.db_session import get_db
from services.automotive.app.auth import require_api_key
# Import shared from 'shared' package directly, as the app does via sys.path hack
from shared.middleware import get_current_tenant_id
from services.automotive.app.models import PPAPSubmission, PPAPElement

class TestPPAPUploadIsolation(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        # Use a temp directory for file storage
        self._tmpdir = tempfile.mkdtemp()
        os.environ['PPAP_STORAGE_ROOT'] = self._tmpdir
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
        app.dependency_overrides = {}
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        os.environ.pop('PPAP_STORAGE_ROOT', None)

    def test_upload_enforces_tenant_id(self):
        """Verify that uploaded elements are associated with the current tenant."""
        submission_id = 123
        
        # Mock Submission (must belong to tenant)
        mock_submission = PPAPSubmission(
            id=submission_id,
            tenant_id=self.tenant_id,
            submission_level=3
        )
        
        # Configure DB query to return submission
        # querying PPAPSubmission -> return valid submission
        # query(PPAPElement) -> return None (no duplicates)
        self.mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_submission, # First query: check submission existence
        ]
        
        # The second query is checking for existing element (order_by().first())
        # We need to chain the mocks carefully or just use side_effect on the execution
        self.mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        # valid file upload
        files = {'file': ('test_file.pdf', b'fake content', 'application/pdf')}
        
        response = self.client.post(
            f"/v1/automotive/ppap/{submission_id}/element?element_type=PART_SUBMISSION_WARRANT",
            files=files
        )
        
        print(f"Response: {response.status_code} {response.json()}")

        # Assertions
        self.assertEqual(response.status_code, 201)
        
        # Verify db.add was called with an element
        self.mock_db.add.assert_called()
        args, _ = self.mock_db.add.call_args
        element = args[0]
        
        self.assertIsInstance(element, PPAPElement)
        self.assertEqual(element.tenant_id, self.tenant_id) # CRITICAL CHECK
        self.assertEqual(element.submission_id, submission_id)
        self.assertEqual(element.content_hash, "98b1ae45059b004178a8eee0c1f6179dcea139c0fd8a69ee47a6f02d97af1f17") # hash of "fake content"

    def test_upload_rejects_cross_tenant_access(self):
        """Verify 404 if submission exists but belongs to different tenant."""
        submission_id = 999
        
        # DB query returns None (simulating filter by tenant_id failing)
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        files = {'file': ('test.pdf', b'content', 'application/pdf')}
        
        response = self.client.post(
            f"/v1/automotive/ppap/{submission_id}/element?element_type=PART_SUBMISSION_WARRANT",
            files=files
        )
        
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "PPAP submission not found")

if __name__ == '__main__':
    unittest.main()
