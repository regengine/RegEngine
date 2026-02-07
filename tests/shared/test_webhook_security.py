"""Tests for webhook security utilities."""

import os
import time
from unittest import mock

import pytest

from shared.webhook_security import (
    DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
    WebhookSignatureError,
    WebhookTimestampError,
    generate_signature,
    get_signature_header_name,
    get_webhook_secret,
    get_webhook_secrets,
    parse_signature_header,
    verify_signature,
    verify_stripe_signature,
)


class TestGenerateSignature:
    """Tests for signature generation."""

    def test_generate_signature_basic(self):
        """Test basic signature generation."""
        payload = b'{"event": "test"}'
        secret = "test-secret-key"
        
        sig = generate_signature(payload, secret=secret)
        
        assert sig.startswith("t=")
        assert ",v1=" in sig

    def test_generate_signature_with_timestamp(self):
        """Test signature with explicit timestamp."""
        payload = b'{"event": "test"}'
        secret = "test-secret-key"
        timestamp = 1700000000
        
        sig = generate_signature(payload, secret=secret, timestamp=timestamp)
        
        assert f"t={timestamp}" in sig

    def test_generate_signature_deterministic(self):
        """Test same inputs produce same signature."""
        payload = b'{"event": "test"}'
        secret = "test-secret-key"
        timestamp = 1700000000
        
        sig1 = generate_signature(payload, secret=secret, timestamp=timestamp)
        sig2 = generate_signature(payload, secret=secret, timestamp=timestamp)
        
        assert sig1 == sig2

    def test_generate_signature_different_payloads(self):
        """Test different payloads produce different signatures."""
        secret = "test-secret-key"
        timestamp = 1700000000
        
        sig1 = generate_signature(b'{"event": "test1"}', secret=secret, timestamp=timestamp)
        sig2 = generate_signature(b'{"event": "test2"}', secret=secret, timestamp=timestamp)
        
        assert sig1 != sig2

    def test_generate_signature_from_env(self, monkeypatch):
        """Test signature generation using environment variable."""
        monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", "env-secret-key")
        
        payload = b'{"event": "test"}'
        sig = generate_signature(payload)
        
        assert sig.startswith("t=")

    def test_generate_signature_no_secret_raises(self, monkeypatch):
        """Test error when no secret available."""
        monkeypatch.delenv("WEBHOOK_SIGNING_SECRET", raising=False)
        
        with pytest.raises(ValueError, match="not configured"):
            generate_signature(b'{"event": "test"}')


class TestParseSignatureHeader:
    """Tests for signature header parsing."""

    def test_parse_valid_header(self):
        """Test parsing valid signature header."""
        header = "t=1700000000,v1=abc123def456"
        
        parsed = parse_signature_header(header)
        
        assert parsed.timestamp == 1700000000
        assert parsed.signature == "abc123def456"
        assert parsed.version == "v1"

    def test_parse_header_with_spaces(self):
        """Test parsing header with spaces."""
        header = "t=1700000000, v1=abc123def456"
        
        parsed = parse_signature_header(header)
        
        assert parsed.timestamp == 1700000000
        assert parsed.signature == "abc123def456"

    def test_parse_empty_header_raises(self):
        """Test error on empty header."""
        with pytest.raises(WebhookSignatureError, match="Missing signature header"):
            parse_signature_header("")

    def test_parse_missing_timestamp_raises(self):
        """Test error when timestamp missing."""
        with pytest.raises(WebhookSignatureError, match="Missing timestamp"):
            parse_signature_header("v1=abc123")

    def test_parse_missing_signature_raises(self):
        """Test error when signature missing."""
        with pytest.raises(WebhookSignatureError, match="Missing v1 signature"):
            parse_signature_header("t=1700000000")

    def test_parse_invalid_timestamp_raises(self):
        """Test error on invalid timestamp format."""
        with pytest.raises(WebhookSignatureError, match="Invalid timestamp"):
            parse_signature_header("t=not-a-number,v1=abc123")


class TestVerifySignature:
    """Tests for signature verification."""

    def test_verify_valid_signature(self):
        """Test verification of valid signature."""
        payload = b'{"event": "test"}'
        secret = "test-secret-key"
        timestamp = int(time.time())
        
        sig = generate_signature(payload, secret=secret, timestamp=timestamp)
        
        result = verify_signature(payload, sig, secret=secret)
        
        assert result is True

    def test_verify_invalid_signature_raises(self):
        """Test error on invalid signature."""
        payload = b'{"event": "test"}'
        secret = "test-secret-key"
        timestamp = int(time.time())
        
        # Generate with one secret, verify with another
        sig = generate_signature(payload, secret=secret, timestamp=timestamp)
        
        with pytest.raises(WebhookSignatureError, match="Invalid webhook signature"):
            verify_signature(payload, sig, secret="wrong-secret")

    def test_verify_tampered_payload_raises(self):
        """Test error when payload was tampered."""
        secret = "test-secret-key"
        timestamp = int(time.time())
        
        sig = generate_signature(b'{"event": "original"}', secret=secret, timestamp=timestamp)
        
        with pytest.raises(WebhookSignatureError, match="Invalid webhook signature"):
            verify_signature(b'{"event": "tampered"}', sig, secret=secret)

    def test_verify_old_timestamp_raises(self):
        """Test error on expired timestamp."""
        payload = b'{"event": "test"}'
        secret = "test-secret-key"
        old_timestamp = int(time.time()) - 600  # 10 minutes ago
        
        sig = generate_signature(payload, secret=secret, timestamp=old_timestamp)
        
        with pytest.raises(WebhookTimestampError, match="too old"):
            verify_signature(payload, sig, secret=secret, tolerance_seconds=300)

    def test_verify_future_timestamp_raises(self):
        """Test error on future timestamp."""
        payload = b'{"event": "test"}'
        secret = "test-secret-key"
        future_timestamp = int(time.time()) + 600  # 10 minutes in future
        
        sig = generate_signature(payload, secret=secret, timestamp=future_timestamp)
        
        with pytest.raises(WebhookTimestampError, match="too old or in future"):
            verify_signature(payload, sig, secret=secret, tolerance_seconds=300)

    def test_verify_with_secret_rotation(self, monkeypatch):
        """Test verification during secret rotation."""
        payload = b'{"event": "test"}'
        old_secret = "old-secret-key"
        new_secret = "new-secret-key"
        timestamp = int(time.time())
        
        # Configure both secrets
        monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", new_secret)
        monkeypatch.setenv("WEBHOOK_SIGNING_SECRET_PREVIOUS", old_secret)
        
        # Sign with old secret (simulating webhook from before rotation)
        sig = generate_signature(payload, secret=old_secret, timestamp=timestamp)
        
        # Should still verify using the previous secret
        result = verify_signature(payload, sig)
        
        assert result is True


class TestGetWebhookSecrets:
    """Tests for secret retrieval."""

    def test_get_single_secret(self, monkeypatch):
        """Test getting single configured secret."""
        monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", "current-secret")
        monkeypatch.delenv("WEBHOOK_SIGNING_SECRET_PREVIOUS", raising=False)
        
        secrets = get_webhook_secrets()
        
        assert secrets == ["current-secret"]

    def test_get_both_secrets(self, monkeypatch):
        """Test getting current and previous secrets."""
        monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", "current-secret")
        monkeypatch.setenv("WEBHOOK_SIGNING_SECRET_PREVIOUS", "previous-secret")
        
        secrets = get_webhook_secrets()
        
        assert secrets == ["current-secret", "previous-secret"]

    def test_get_no_secrets(self, monkeypatch):
        """Test when no secrets configured."""
        monkeypatch.delenv("WEBHOOK_SIGNING_SECRET", raising=False)
        monkeypatch.delenv("WEBHOOK_SIGNING_SECRET_PREVIOUS", raising=False)
        
        secrets = get_webhook_secrets()
        
        assert secrets == []


class TestStripeSignature:
    """Tests for Stripe-specific signature verification."""

    def test_verify_stripe_signature_valid(self, monkeypatch):
        """Test valid Stripe signature verification."""
        payload = b'{"type": "payment_intent.succeeded"}'
        secret = "whsec_test123"
        timestamp = int(time.time())
        
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
        
        sig = generate_signature(payload, secret=secret, timestamp=timestamp)
        
        result = verify_stripe_signature(payload, sig)
        
        assert result is True

    def test_verify_stripe_no_secret_raises(self, monkeypatch):
        """Test error when Stripe secret not configured."""
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        
        with pytest.raises(WebhookSignatureError, match="Stripe webhook secret"):
            verify_stripe_signature(b'{}', "t=123,v1=abc")


class TestSignatureHeaderNames:
    """Tests for signature header name retrieval."""

    def test_regengine_header(self):
        """Test RegEngine signature header name."""
        assert get_signature_header_name("regengine") == "X-RegEngine-Signature"

    def test_stripe_header(self):
        """Test Stripe signature header name."""
        assert get_signature_header_name("stripe") == "Stripe-Signature"

    def test_github_header(self):
        """Test GitHub signature header name."""
        assert get_signature_header_name("github") == "X-Hub-Signature-256"

    def test_unknown_provider_fallback(self):
        """Test fallback for unknown provider."""
        assert get_signature_header_name("unknown") == "X-Webhook-Signature"
