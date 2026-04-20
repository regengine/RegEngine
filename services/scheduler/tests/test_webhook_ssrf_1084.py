"""Regression tests for issue #1084 — webhook SSRF guard and response-body cap.

Covers:
  - SSRF guard blocks private IP addresses (127.x, 192.168.x)
  - SSRF guard allows public external URLs
  - Response body is capped at _RESPONSE_BODY_MAX_BYTES even if server sends more
  - _retry_one_entry also applies SSRF guard
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable  # noqa: E402
ensure_shared_importable()

import pytest  # noqa: E402

from app.models import EnforcementItem, EnforcementSeverity, SourceType  # noqa: E402
from app.notifications import (  # noqa: E402
    OutboxEntry,
    WebhookNotifier,
    _RESPONSE_BODY_MAX_BYTES,
)


def _make_item() -> EnforcementItem:
    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id="recall-1084",
        title="Issue 1084 test recall",
        url="https://fda.gov/recalls/1084",
        published_date=datetime(2026, 4, 20, tzinfo=timezone.utc),
        severity=EnforcementSeverity.HIGH,
    )


def _make_notifier(url: str) -> WebhookNotifier:
    return WebhookNotifier(urls=[url], timeout=5, max_retries=1)


def _make_response(status_code: int, content: bytes = b"ok") -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.content = content
    r.headers = {}
    return r


# ── SSRF guard: _deliver_with_retry ──────────────────────────────────────────


class TestSSRFGuard_Issue1084:
    def test_blocks_loopback(self):
        notifier = _make_notifier("http://127.0.0.1:8200/admin")
        result = notifier._deliver_with_retry("http://127.0.0.1:8200/admin", MagicMock())
        assert not result.success
        assert "SSRF blocked" in result.error

    def test_blocks_private_class_c(self):
        notifier = _make_notifier("http://192.168.1.100/hook")
        result = notifier._deliver_with_retry("http://192.168.1.100/hook", MagicMock())
        assert not result.success
        assert "SSRF blocked" in result.error

    def test_blocks_localhost_hostname(self):
        notifier = _make_notifier("http://localhost/hook")
        result = notifier._deliver_with_retry("http://localhost/hook", MagicMock())
        assert not result.success
        assert "SSRF blocked" in result.error

    def test_allows_public_url(self):
        notifier = _make_notifier("https://hooks.example.com/webhook")
        mock_response = _make_response(200, b'{"ok": true}')
        with patch("shared.url_validation.socket.gethostbyname", return_value="93.184.216.34"):
            with patch.object(notifier.session, "post", return_value=mock_response):
                result = notifier._deliver_with_retry(
                    "https://hooks.example.com/webhook", MagicMock(to_dict=lambda: {})
                )
        assert result.success

    def test_blocks_imds(self):
        notifier = _make_notifier("http://169.254.169.254/latest/meta-data")
        result = notifier._deliver_with_retry(
            "http://169.254.169.254/latest/meta-data", MagicMock()
        )
        assert not result.success
        assert "SSRF blocked" in result.error


# ── SSRF guard: _retry_one_entry ─────────────────────────────────────────────


class TestSSRFGuardOutbox_Issue1084:
    def _make_entry(self, url: str) -> OutboxEntry:
        return OutboxEntry(url=url, payload={})

    def test_outbox_blocks_private_ip(self):
        notifier = WebhookNotifier(urls=[], timeout=5, max_retries=1)
        entry = self._make_entry("http://10.0.0.1/admin")
        result = notifier._retry_one_entry(entry)
        assert result is False
        assert "SSRF blocked" in entry.last_error

    def test_outbox_allows_public_url(self):
        notifier = WebhookNotifier(urls=[], timeout=5, max_retries=1)
        entry = self._make_entry("https://hooks.example.com/webhook")
        entry.payload = {}
        mock_response = _make_response(200, b"ok")
        with patch("shared.url_validation.socket.gethostbyname", return_value="93.184.216.34"):
            with patch.object(notifier.session, "post", return_value=mock_response):
                result = notifier._retry_one_entry(entry)
        assert result is True


# ── Response-body cap ─────────────────────────────────────────────────────────


class TestResponseBodyCap_Issue1084:
    def test_deliver_caps_response_body(self):
        """A 500 response with a large body must not materialize more than
        _RESPONSE_BODY_MAX_BYTES bytes.
        """
        large_body = b"X" * (_RESPONSE_BODY_MAX_BYTES + 100_000)
        # httpx Response.content returns the full bytes; our code slices it
        mock_response = _make_response(500, large_body)
        notifier = _make_notifier("https://hooks.example.com/webhook")
        with patch("shared.url_validation.socket.gethostbyname", return_value="93.184.216.34"):
            with patch.object(notifier.session, "post", return_value=mock_response):
                result = notifier._deliver_with_retry(
                    "https://hooks.example.com/webhook",
                    MagicMock(to_dict=lambda: {}),
                )
        assert not result.success
        # The error string must be short (capped preview, not multi-MB)
        assert len(result.error) < 500

    def test_response_body_constant_is_one_mb(self):
        assert _RESPONSE_BODY_MAX_BYTES == 1024 * 1024

    def test_outbox_caps_error_preview(self):
        """_retry_one_entry must also cap the response body."""
        large_body = b"E" * (_RESPONSE_BODY_MAX_BYTES + 50_000)
        mock_response = _make_response(503, large_body)
        notifier = WebhookNotifier(urls=[], timeout=5, max_retries=1)
        entry = OutboxEntry(url="https://hooks.example.com/webhook", payload={})
        with patch("shared.url_validation.socket.gethostbyname", return_value="93.184.216.34"):
            with patch.object(notifier.session, "post", return_value=mock_response):
                result = notifier._retry_one_entry(entry)
        assert result is False
        assert len(entry.last_error) < 500
