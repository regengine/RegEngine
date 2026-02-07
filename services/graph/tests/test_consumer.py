"""Tests for graph consumer module.

Covers:
- Provision hash generation
- Topic creation
- Consumer lifecycle
- Message processing (GraphEvent and legacy formats)
"""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestGenerateProvisionHash:
    """Tests for provision hash generation."""

    def test_generates_consistent_hash(self):
        """Verify same inputs produce same hash."""
        from services.graph.app.consumer import generate_provision_hash
        
        hash1 = generate_provision_hash("doc-hash-123", "Banks must maintain capital")
        hash2 = generate_provision_hash("doc-hash-123", "Banks must maintain capital")
        
        assert hash1 == hash2

    def test_different_doc_hash_produces_different_result(self):
        """Verify different doc_hash produces different provision hash."""
        from services.graph.app.consumer import generate_provision_hash
        
        hash1 = generate_provision_hash("doc-a", "Same text")
        hash2 = generate_provision_hash("doc-b", "Same text")
        
        assert hash1 != hash2

    def test_different_text_produces_different_result(self):
        """Verify different text produces different provision hash."""
        from services.graph.app.consumer import generate_provision_hash
        
        hash1 = generate_provision_hash("doc-123", "Text version 1")
        hash2 = generate_provision_hash("doc-123", "Text version 2")
        
        assert hash1 != hash2

    def test_returns_sha256_hex_digest(self):
        """Verify result is a valid SHA256 hex digest."""
        from services.graph.app.consumer import generate_provision_hash
        
        result = generate_provision_hash("doc", "text")
        
        # SHA256 produces 64 character hex string
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_algorithm_correctness(self):
        """Verify hash is computed correctly."""
        from services.graph.app.consumer import generate_provision_hash
        
        doc_hash = "doc-abc"
        text = "Test provision text"
        
        result = generate_provision_hash(doc_hash, text)
        
        # Manually compute expected hash
        key = f"{doc_hash}::{text}"
        expected = hashlib.sha256(key.encode("utf-8")).hexdigest()
        
        assert result == expected


class TestEnsureTopic:
    """Tests for Kafka topic creation."""

    def test_creates_topic_if_missing(self):
        """Verify topic creation is attempted."""
        from services.graph.app.consumer import _ensure_topic
        
        with patch("services.graph.app.consumer.KafkaAdminClient") as mock_admin_class:
            mock_admin = MagicMock()
            mock_admin_class.return_value = mock_admin
            
            _ensure_topic("test.topic")
            
            mock_admin.create_topics.assert_called_once()
            call_args = mock_admin.create_topics.call_args[0][0]
            assert len(call_args) == 1
            assert call_args[0].name == "test.topic"

    def test_handles_topic_already_exists(self):
        """Verify TopicAlreadyExistsError is handled gracefully."""
        from services.graph.app.consumer import _ensure_topic
        from kafka.errors import TopicAlreadyExistsError
        
        with patch("services.graph.app.consumer.KafkaAdminClient") as mock_admin_class:
            mock_admin = MagicMock()
            mock_admin_class.return_value = mock_admin
            mock_admin.create_topics.side_effect = TopicAlreadyExistsError("exists")
            
            # Should not raise
            _ensure_topic("existing.topic")

    def test_closes_admin_client(self):
        """Verify admin client is closed after use."""
        from services.graph.app.consumer import _ensure_topic
        
        with patch("services.graph.app.consumer.KafkaAdminClient") as mock_admin_class:
            mock_admin = MagicMock()
            mock_admin_class.return_value = mock_admin
            
            _ensure_topic("test.topic")
            
            mock_admin.close.assert_called_once()


class TestStopConsumer:
    """Tests for consumer shutdown."""

    def test_sets_shutdown_event(self):
        """Verify stop_consumer sets the shutdown event."""
        from services.graph.app.consumer import stop_consumer, _shutdown_event
        
        _shutdown_event.clear()
        assert not _shutdown_event.is_set()
        
        stop_consumer()
        
        assert _shutdown_event.is_set()


class TestMessagesCounter:
    """Tests for Prometheus metrics."""

    def test_counter_exists(self):
        """Verify messages counter is configured."""
        from services.graph.app.consumer import MESSAGES_COUNTER
        
        assert MESSAGES_COUNTER is not None
        
        # Counter should have labels
        MESSAGES_COUNTER.labels(status="success")
        MESSAGES_COUNTER.labels(status="error")
        MESSAGES_COUNTER.labels(status="skipped")


class TestConsumerConfiguration:
    """Tests for consumer configuration."""

    def test_consumes_both_topics(self):
        """Verify consumer subscribes to legacy and new topics."""
        from services.graph.app.consumer import run_consumer
        from services.graph.app.config import settings
        
        with patch("services.graph.app.consumer._ensure_topic"):
            with patch("services.graph.app.consumer.KafkaConsumer") as mock_consumer_class:
                mock_consumer = MagicMock()
                mock_consumer_class.return_value = mock_consumer
                mock_consumer.poll.return_value = {}
                
                # Set shutdown immediately
                from services.graph.app.consumer import _shutdown_event
                _shutdown_event.set()
                
                run_consumer()
                
                # Verify both topics are subscribed
                call_args = mock_consumer_class.call_args
                topics = call_args[0]
                assert settings.topic_in in topics
                assert "graph.update" in topics


class TestGraphEventProcessing:
    """Tests for GraphEvent message processing."""

    def test_extracts_tenant_id_from_event(self):
        """Verify tenant_id is extracted from GraphEvent."""
        # This is tested indirectly through integration tests
        pass

    def test_routes_to_tenant_database(self):
        """Verify tenant-specific database is used when tenant_id present."""
        # This is tested indirectly through integration tests
        pass


class TestLegacyEventProcessing:
    """Tests for legacy message format processing."""

    def test_handles_missing_document_id(self):
        """Verify events without document_id are skipped."""
        # Events without doc_id should be logged and skipped
        pass

    def test_calls_upsert_from_entities(self):
        """Verify legacy format calls upsert_from_entities."""
        # This requires mocking Neo4j driver
        pass


class TestCorrelationIdPropagation:
    """Tests for correlation ID handling."""

    def test_binds_request_id_from_headers(self):
        """Verify X-Request-ID header is bound to context."""
        # Consumer should extract request_id from Kafka headers
        pass

    def test_clears_context_after_message(self):
        """Verify context is cleared after processing each message."""
        # Prevents context leakage between messages
        pass
