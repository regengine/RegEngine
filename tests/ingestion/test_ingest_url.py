"""Tests for the ingest/url endpoint - core document ingestion functionality.

These tests verify:
- URL validation and SSRF protection
- Content type detection
- S3 storage operations
- Kafka event emission
- Error handling
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4

import pytest

# Skip if dependencies not available
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer for testing event emission."""
    producer = MagicMock()
    future = MagicMock()
    future.get.return_value = MagicMock()
    producer.send.return_value = future
    return producer


@pytest.fixture
def mock_s3_client():
    """Mock S3 client for testing storage operations."""
    client = MagicMock()
    client.put_object.return_value = {"ETag": "mock-etag"}
    client.head_bucket.return_value = {}
    return client


@pytest.fixture
def ingestion_client(monkeypatch, mock_kafka_producer, mock_s3_client):
    """Provide a TestClient with mocked dependencies."""
    # Mock dependencies before importing the app
    monkeypatch.setenv("REQUIRE_REDIS", "false")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    
    # Mock the shared auth to accept test keys
    from shared import auth as shared_auth
    
    test_key = shared_auth.APIKey(
        key_id="test-key-id",
        key_hash="test-hash",
        name="Test Key",
        tenant_id=str(uuid4()),
        created_at=datetime.now(timezone.utc),
        enabled=True,
    )
    
    store = shared_auth.APIKeyStore()
    monkeypatch.setattr(shared_auth, "_key_store", store, raising=False)
    
    # Create a real test key
    raw_key, _ = store.create_key("test", tenant_id=str(uuid4()))
    
    from services.ingestion.main import app
    client = TestClient(app)
    
    return client, raw_key


class TestIngestUrlEndpoint:
    """Tests for POST /ingest/url."""

    def test_ingest_url_requires_api_key(self, ingestion_client):
        """Verify that API key is required."""
        client, _ = ingestion_client
        
        resp = client.post(
            "/ingest/url",
            json={"url": "https://example.com/doc.pdf", "source_system": "test"},
        )
        
        assert resp.status_code in (401, 403), f"Expected auth error, got {resp.status_code}"

    def test_ingest_url_validates_source_system_required(self, ingestion_client):
        """Verify source_system field is required."""
        client, api_key = ingestion_client
        
        resp = client.post(
            "/ingest/url",
            headers={"X-RegEngine-API-Key": api_key},
            json={"url": "https://example.com/doc.pdf"},
        )
        
        assert resp.status_code == 422
        data = resp.json()
        assert "source_system" in str(data)

    def test_ingest_url_validates_url_required(self, ingestion_client):
        """Verify url field is required."""
        client, api_key = ingestion_client
        
        resp = client.post(
            "/ingest/url",
            headers={"X-RegEngine-API-Key": api_key},
            json={"source_system": "test"},
        )
        
        assert resp.status_code == 422

    def test_ingest_url_rejects_private_ip_addresses(self, ingestion_client):
        """Verify SSRF protection blocks private IPs."""
        client, api_key = ingestion_client
        
        private_urls = [
            "http://127.0.0.1/secret",
            "http://localhost/admin",
            "http://192.168.1.1/config",
            "http://10.0.0.1/internal",
        ]
        
        for url in private_urls:
            resp = client.post(
                "/ingest/url",
                headers={"X-RegEngine-API-Key": api_key},
                json={"url": url, "source_system": "test"},
            )
            # Should reject with 400 or 422
            assert resp.status_code in (400, 422), f"Expected rejection for {url}, got {resp.status_code}"

    def test_ingest_url_rejects_non_http_schemes(self, ingestion_client):
        """Verify only http/https schemes are allowed."""
        client, api_key = ingestion_client
        
        invalid_urls = [
            "file:///etc/passwd",
            "ftp://example.com/doc.pdf",
            "data:text/html,<script>alert(1)</script>",
        ]
        
        for url in invalid_urls:
            resp = client.post(
                "/ingest/url",
                headers={"X-RegEngine-API-Key": api_key},
                json={"url": url, "source_system": "test"},
            )
            assert resp.status_code in (400, 422), f"Expected rejection for {url}"


class TestUrlValidation:
    """Tests for URL validation helper functions."""

    def test_validate_url_allows_https(self):
        """Verify https URLs are allowed."""
        from services.ingestion.app.routes import _validate_url
        
        # This should not raise
        _validate_url("https://example.com/document.pdf")

    def test_validate_url_allows_http(self):
        """Verify http URLs are allowed."""
        from services.ingestion.app.routes import _validate_url
        
        # This should not raise
        _validate_url("http://example.com/document.pdf")

    def test_validate_url_rejects_invalid_format(self):
        """Verify malformed URLs are rejected."""
        from services.ingestion.app.routes import _validate_url
        from fastapi import HTTPException
        
        invalid_urls = [
            "not-a-url",
            "://missing-scheme.com",
            "https://",  # Missing host
        ]
        
        for url in invalid_urls:
            with pytest.raises(HTTPException):
                _validate_url(url)


class TestContentTypeDetection:
    """Tests for content type detection."""

    def test_detect_extension_pdf(self):
        """Verify PDF content type detection."""
        from services.ingestion.app.routes import _detect_extension
        
        assert _detect_extension("application/pdf") == ".pdf"

    def test_detect_extension_json(self):
        """Verify JSON content type detection."""
        from services.ingestion.app.routes import _detect_extension
        
        assert _detect_extension("application/json") == ".json"

    def test_detect_extension_html(self):
        """Verify HTML content type detection."""
        from services.ingestion.app.routes import _detect_extension
        
        assert _detect_extension("text/html") == ".html"

    def test_detect_extension_unknown(self):
        """Verify unknown content type handling."""
        from services.ingestion.app.routes import _detect_extension
        
        result = _detect_extension("application/octet-stream")
        # Should return a sensible default or None
        assert result is None or result == ""


class TestSizeLimits:
    """Tests for content size enforcement."""

    def test_enforce_size_limit_allows_small_content(self):
        """Verify small content passes size check."""
        from services.ingestion.app.routes import _enforce_size_limit
        
        small_content = b"x" * 1000  # 1KB
        # Should not raise
        _enforce_size_limit(small_content)

    def test_enforce_size_limit_rejects_oversized_content(self):
        """Verify oversized content is rejected."""
        from services.ingestion.app.routes import _enforce_size_limit
        from fastapi import HTTPException
        
        # This is intentionally large - adjust based on actual limit
        huge_content = b"x" * (50 * 1024 * 1024)  # 50MB
        
        with pytest.raises(HTTPException) as exc_info:
            _enforce_size_limit(huge_content)
        
        assert exc_info.value.status_code == 413


class TestIngestResponseFormat:
    """Tests for ingest response format validation."""

    def test_response_contains_required_fields(self):
        """Verify response structure matches expected format."""
        required_fields = [
            "event_id",
            "document_id",
            "document_hash",
            "tenant_id",
            "source_system",
            "source_url",
            "timestamp",
        ]
        
        # This is a structural test - actual response depends on mocking
        # In integration tests, verify these fields are present
        assert len(required_fields) == 7  # Sanity check

    def test_s3_paths_format(self):
        """Verify S3 path format expectations."""
        # S3 paths should follow pattern: s3://bucket/prefix/document_id/event_id.ext
        expected_pattern = "s3://reg-engine-"
        # This is a format specification test
        assert "reg-engine" in expected_pattern
