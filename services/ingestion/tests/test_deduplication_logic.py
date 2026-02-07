"""Unit tests for deduplication logic in the ingestion framework."""

import pytest
from unittest.mock import MagicMock
from regengine_ingestion.storage.database import DatabaseManager
from regengine_ingestion.models import Document, DocumentHash, DocumentType

class TestDeduplicationLogic:
    def test_get_document_by_hash_called(self):
        # Mock connection, we don't want real DB
        mock_conn = MagicMock()
        db_manager = DatabaseManager(MagicMock())
        db_manager.conn = mock_conn
        
        # Mock cursor
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchone.return_value = {
            "id": "existing-id",
            "storage_key": "s3://existing-path"
        }
        
        doc_hash = "test-hash"
        result = db_manager.get_document_by_hash(doc_hash)
        
        assert result["id"] == "existing-id"
        assert result["storage_key"] == "s3://existing-path"
        
    def test_insert_document_on_conflict_do_nothing(self):
        mock_conn = MagicMock()
        db_manager = DatabaseManager(MagicMock())
        db_manager.conn = mock_conn
        
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        
        # Create a document
        doc = Document(
            id="00000000-0000-0000-0000-000000000001",
            tenant_id="00000000-0000-0000-0000-000000000001",
            title="Test Doc",
            source_type="url",
            document_type=DocumentType.REGULATION,
            vertical="test",
            hash=DocumentHash(content_sha256="hash", content_sha512="hash512"),
            source_metadata=MagicMock(),
            storage_key="s3://path"
        )
        
        db_manager.insert_document(doc)
        
        # Verify execute was called with correct SQL
        call_args = mock_cur.execute.call_args[0][0]
        assert "ON CONFLICT (content_sha256) DO NOTHING" in call_args
