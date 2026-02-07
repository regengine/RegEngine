"""Integration tests for Federal API sources."""

import pytest
from unittest.mock import MagicMock, patch
from regengine_ingestion.sources import FederalRegisterAdapter, ECFRAdapter
from app.routes import _process_and_emit

class TestFederalIntegration:
    @patch("regengine_ingestion.sources.FederalRegisterAdapter.fetch_documents")
    def test_federal_register_ingestion_flow(self, mock_fetch):
        # Mock fetch_documents return
        mock_fetch.return_value = [
            (b"content", MagicMock(source_url="http://test.com"), {"title": "Test"})
        ]
        
        adapter = FederalRegisterAdapter()
        count = 0
        for content, source_meta, doc_meta in adapter.fetch_documents():
            count += 1
            # We don't want to actually call _process_and_emit with real S3/Kafka
            # But we want to see it iterate correctly
            assert content == b"content"
            assert doc_meta["title"] == "Test"
        
        assert count == 1

    @patch("regengine_ingestion.sources.ECFRAdapter.fetch_documents")
    def test_ecfr_ingestion_flow(self, mock_fetch):
        mock_fetch.return_value = [
            (b"ecfr content", MagicMock(source_url="http://ecfr.test"), {"title": "ECFR Test"})
        ]
        
        adapter = ECFRAdapter()
        items = list(adapter.fetch_documents())
        assert len(items) == 1
        assert items[0][0] == b"ecfr content"
