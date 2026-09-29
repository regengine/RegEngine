"""Unit tests for deduplication logic in the ingestion framework."""

from unittest.mock import MagicMock

import pytest
from regengine_ingestion.models import Document, DocumentHash, DocumentType
from regengine_ingestion.storage.database import DatabaseManager


class TestDeduplicationLogic:
    def test_get_document_by_hash_called(self):
        # Mock connection, we don't want real DB
        mock_conn = MagicMock()
        db_manager = DatabaseManager(MagicMock())
        db_manager.conn = mock_conn

        # Mock cursor
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchone.return_value = {"id": "existing-id", "storage_key": "s3://existing-path"}

        doc_hash = "test-hash"
        result = db_manager.get_document_by_hash(doc_hash, tenant_id="00000000-0000-0000-0000-000000000001")

        assert result["id"] == "existing-id"
        assert result["storage_key"] == "s3://existing-path"

    @pytest.mark.parametrize("inserted", [True, False])
    def test_insert_document_returns_inserted_or_same_tenant_existing_row(self, inserted):
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
            storage_key="s3://path",
        )

        owned_row = {
            "id": doc.id,
            "tenant_id": doc.tenant_id,
            "content_sha256": "hash",
            "storage_key": "s3://path",
        }
        mock_cur.fetchone.side_effect = [owned_row] if inserted else [None, owned_row]
        result = db_manager.insert_document(doc)

        assert result == owned_row
        statements = [call.args for call in mock_cur.execute.call_args_list]
        insert = next(args for args in statements if "INSERT INTO ingestion.documents" in args[0])
        # Simultaneous identical inserts can collide on either the primary
        # key or tenant/hash key. Both must reach the owned-row lookup.
        assert "ON CONFLICT DO NOTHING" in insert[0]
        if not inserted:
            assert "tenant_id = %s" in statements[-1][0]
            assert statements[-1][1] == ("hash", doc.tenant_id)

    @pytest.mark.parametrize("conflict", ["missing", "foreign_tenant_pk", "different_content_pk"])
    def test_insert_conflict_without_owned_row_raises_and_rolls_back(self, conflict):
        mock_conn = MagicMock()
        db_manager = DatabaseManager(MagicMock())
        db_manager.conn = mock_conn
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchone.return_value = None
        doc = Document(
            id="00000000-0000-0000-0000-000000000001",
            tenant_id="00000000-0000-0000-0000-000000000001",
            title="Test Doc",
            source_type="url",
            document_type=DocumentType.REGULATION,
            vertical="test",
            hash=DocumentHash(content_sha256="hash", content_sha512="hash512"),
            source_metadata=MagicMock(),
            storage_key="s3://path",
        )
        occupied = {
            "id": doc.id,
            "tenant_id": "00000000-0000-0000-0000-000000000002" if conflict == "foreign_tenant_pk" else doc.tenant_id,
            "content_sha256": "other-hash" if conflict == "different_content_pk" else "hash",
            "storage_key": "s3://existing/unrelated.json",
        }

        def execute(query, params):
            if "SELECT * FROM ingestion.documents" in query:
                assert "content_sha256 = %s AND tenant_id = %s" in query
                assert params == ("hash", doc.tenant_id)
                visible_match = (occupied["content_sha256"], occupied["tenant_id"]) == params
                mock_cur.fetchone.return_value = occupied if conflict != "missing" and visible_match else None

        mock_cur.execute.side_effect = execute

        with pytest.raises(RuntimeError, match="persist"):
            db_manager.insert_document(doc)

        mock_conn.rollback.assert_called_once()
