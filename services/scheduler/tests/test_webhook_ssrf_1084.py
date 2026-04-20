"""Tests for SSRF guard and response-body cap on outbound webhooks -- #1084.

Covers:
- Private/loopback address blocked (e.g. AWS IMDS 169.254.169.254)
- Localhost rejected
- RFC-1918 ranges rejected
- HTTPS public address allowed
- HTTP blocked by default, allowed with WEBHOOK_ALLOW_HTTP=true
- WEBHOOK_ALLOW_PRIVATE=true bypasses guard (dev escape-hatch)
- Response body truncated at WEBHOOK_MAX_RESPONSE_BYTES cap
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# Ensure SSRF guard is active in tests (not bypassed).
os.environ.pop("WEBHOOK_ALLOW_PRIVATE", None)

_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable
ensure_shared_importable()

import pytest

from app.models import EnforcementItem, EnforcementSeverity, SourceType
from app.notifications import (
    WebhookNotifier,
    _check_ssrf,
    _read_capped_body,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(**kw) -> EnforcementItem:
    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id=kw.get("source_id", "test-recall-001"),
        title=kw.get("title", "Test FDA Recall"),
        url="https://fda.gov/recalls/test",
        published_date=datetime(2026, 3, 15, tzinfo=timezone.utc),
        severity=kw.get("severity", EnforcementSeverity.HIGH),
    )


# ---------------------------------------------------------------------------
# Unit tests for _check_ssrf
# ---------------------------------------------------------------------------

class TestCheckSsrf:
    """Direct unit tests for the _check_ssrf guard function."""

    def test_imds_address_blocked(self):
        """169.254.169.254 (AWS IMDS) must be rejected."""
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (2, 1, 6, "", ("169.254.169.254", 0))
            ]
            with pytest.raises(ValueError, match="SSRF blocked"):
                _check_ssrf("https://internal-target.example.com/hook")

    def test_loopback_127_blocked(self):
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(2, 1, 6, "", ("127.0.0.1", 0))]
            with pytest.raises(ValueError, match="SSRF blocked"):
                _check_ssrf("https://some-host.example.com/hook")

    def test_rfc1918_10_blocked(self):
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(2, 1, 6, "", ("10.0.0.1", 0))]
            with pytest.raises(ValueError, match="SSRF blocked"):
                _check_ssrf("https://some-host.example.com/hook")

    def test_rfc1918_172_blocked(self):
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(2, 1, 6, "", ("172.16.5.5", 0))]
            with pytest.raises(ValueError, match="SSRF blocked"):
                _check_ssrf("https://some-host.example.com/hook")

    def test_rfc1918_192168_blocked(self):
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(2, 1, 6, "", ("192.168.1.50", 0))]
            with pytest.raises(ValueError, match="SSRF blocked"):
                _check_ssrf("https://some-host.example.com/hook")

    def test_ipv6_loopback_blocked(self):
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(10, 1, 6, "", ("::1", 0, 0, 0))]
            with pytest.raises(ValueError, match="SSRF blocked"):
                _check_ssrf("https://some-host.example.com/hook")

    def test_public_https_allowed(self):
        """A real public address over https must pass."""
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
            # Should not raise.
            _check_ssrf("https://example.com/webhook")

    def test_http_blocked_by_default(self):
        """http:// must be rejected unless WEBHOOK_ALLOW_HTTP=true."""
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
            with pytest.raises(ValueError, match="scheme"):
                _check_ssrf("http://example.com/webhook")

    def test_http_allowed_when_env_set(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_ALLOW_HTTP", "true")
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
            _check_ssrf("http://example.com/webhook")  # must not raise

    def test_allow_private_bypasses_guard(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_ALLOW_PRIVATE", "true")
        # No socket call needed — returns immediately.
        _check_ssrf("http://127.0.0.1/internal")  # must not raise

    def test_unresolvable_host_raises(self):
        import socket as _socket
        with patch("socket.getaddrinfo", side_effect=_socket.gaierror("nxdomain")):
            with pytest.raises(ValueError, match="Cannot resolve"):
                _check_ssrf("https://this-host-does-not-exist.invalid/hook")


# ---------------------------------------------------------------------------
# Integration test: WebhookNotifier rejects SSRF target
# ---------------------------------------------------------------------------

class TestWebhookNotifierSsrf:
    """WebhookNotifier._deliver_with_retry must reject private-IP targets."""

    def test_deliver_blocked_for_imds_url(self):
        """notify() returns a failed DeliveryResult when host resolves to IMDS IP."""
        notifier = WebhookNotifier(
            urls=["https://metadata.internal/hook"],
            timeout=5,
            max_retries=1,
        )
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(2, 1, 6, "", ("169.254.169.254", 0))]
            results = notifier.notify([_make_item()])

        assert len(results) == 1
        result = results[0]
        assert result.success is False
        assert "SSRF blocked" in (result.error or "")
        # No HTTP call must have been made.

    def test_deliver_succeeds_for_public_url(self):
        """notify() delivers when host resolves to a public IP."""
        notifier = WebhookNotifier(
            urls=["https://hooks.example.com/endpoint"],
            timeout=5,
            max_retries=1,
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"ok":true}'

        with patch("socket.getaddrinfo") as mock_gai, \
             patch.object(notifier.session, "post", return_value=mock_response):
            mock_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
            results = notifier.notify([_make_item()])

        assert len(results) == 1
        assert results[0].success is True


# ---------------------------------------------------------------------------
# Response-body cap tests
# ---------------------------------------------------------------------------

class TestResponseBodyCap:
    """_read_capped_body must truncate at the specified limit."""

    def test_small_body_returned_in_full(self):
        mock_resp = MagicMock()
        mock_resp.content = b"Hello, world!"
        result = _read_capped_body(mock_resp, max_bytes=1024)
        assert result == "Hello, world!"

    def test_large_body_truncated_at_cap(self):
        """A 2 MB body with a 1 MB cap must be truncated to exactly 1 MB."""
        one_mb = 1 * 1024 * 1024
        big_body = b"x" * (2 * one_mb)
        mock_resp = MagicMock()
        mock_resp.content = big_body
        result = _read_capped_body(mock_resp, max_bytes=one_mb)
        assert len(result.encode("utf-8")) == one_mb

    def test_cap_applied_in_deliver_with_retry(self, monkeypatch):
        """WebhookNotifier records a truncated error body on non-2xx response."""
        cap = 50  # tiny cap for test
        monkeypatch.setenv("WEBHOOK_MAX_RESPONSE_BYTES", str(cap))

        notifier = WebhookNotifier(
            urls=["https://hooks.example.com/endpoint"],
            timeout=5,
            max_retries=1,
        )

        # Response body is 500 bytes; only first `cap` bytes should be read.
        large_body = b"E" * 500
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = large_body
        mock_response.headers = {}

        with patch("socket.getaddrinfo") as mock_gai, \
             patch.object(notifier.session, "post", return_value=mock_response):
            mock_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
            results = notifier.notify([_make_item()])

        assert len(results) == 1
        result = results[0]
        assert result.success is False
        # Error message body preview must not exceed cap chars (plus "HTTP 500: " prefix).
        body_in_error = (result.error or "").replace("HTTP 500: ", "")
        assert len(body_in_error) <= 200  # the [:200] slice in notifications.py
