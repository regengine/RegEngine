"""Tests for SSRF guard + response body cap on outbound webhook delivery (#1084).

Covers:
  - SSRF-blocked URL → DeliveryResult(success=False, error="SSRF blocked: ...")
    without making any HTTP call.
  - Response body > 1 MB → truncated to cap, warning logged, success/failure
    determined by HTTP status code.
  - Normal 200 response → passes through correctly.
  - validate_webhook_url is mocked so tests don't require network access.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from datetime import datetime, timezone

from app.models import EnforcementItem, EnforcementSeverity, SourceType, WebhookPayload
from app.notifications import DeliveryResult, WebhookNotifier
from app.webhook_security import CappedBody, WebhookURLBlocked


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_notifier(**kwargs) -> WebhookNotifier:
    """Return a notifier with test defaults (no disk outbox, no settings I/O)."""
    urls = kwargs.pop("urls", ["https://example.com/hook"])
    with patch("app.notifications.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            webhook_url_list=urls,
            webhook_timeout_seconds=10,
            webhook_max_retries=1,
        )
        notifier = WebhookNotifier(urls=urls, timeout=10, max_retries=1, **kwargs)
    return notifier


def _make_payload() -> WebhookPayload:
    item = EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id="test-recall-001",
        title="Test recall",
        severity=EnforcementSeverity.HIGH,
        url="https://fda.gov/test",
        published_date=datetime(2026, 4, 20, tzinfo=timezone.utc),
    )
    return WebhookPayload(items=[item], summary="1 HIGH")


# ---------------------------------------------------------------------------
# 1. SSRF-blocked URL — no HTTP call made
# ---------------------------------------------------------------------------

class TestSSRFBlocked:
    def test_blocked_url_returns_failure_without_http_call(self):
        """validate_webhook_url raises → DeliveryResult(success=False, error~SSRF)."""
        notifier = _make_notifier(urls=["http://169.254.169.254/latest/meta-data/"])
        payload = _make_payload()

        with patch(
            "app.notifications.validate_webhook_url",
            side_effect=WebhookURLBlocked("link_local"),
        ) as mock_validate, patch.object(
            notifier, "_post_with_body_cap"
        ) as mock_post:
            result = notifier._deliver_with_retry(
                "http://169.254.169.254/latest/meta-data/", payload
            )

        mock_validate.assert_called_once_with("http://169.254.169.254/latest/meta-data/")
        mock_post.assert_not_called()
        assert result.success is False
        assert "SSRF blocked" in (result.error or "")

    def test_blocked_url_attempts_is_zero(self):
        notifier = _make_notifier()
        payload = _make_payload()

        with patch(
            "app.notifications.validate_webhook_url",
            side_effect=WebhookURLBlocked("loopback"),
        ):
            result = notifier._deliver_with_retry("http://127.0.0.1/hook", payload)

        assert result.attempts == 0
        assert result.status_code is None

    def test_private_ip_url_blocked(self):
        notifier = _make_notifier()
        payload = _make_payload()

        with patch(
            "app.notifications.validate_webhook_url",
            side_effect=WebhookURLBlocked("private"),
        ), patch.object(notifier, "_post_with_body_cap") as mock_post:
            result = notifier._deliver_with_retry("http://10.0.0.1/hook", payload)

        mock_post.assert_not_called()
        assert result.success is False


# ---------------------------------------------------------------------------
# 2. Response body > 1 MB → truncated, success/failure per status code
# ---------------------------------------------------------------------------

class TestResponseBodyCap:
    def _make_capped_body(self, truncated: bool, size: int = 1_048_576) -> CappedBody:
        data = b"x" * min(size, 1_048_576)
        return CappedBody(data=data, truncated=truncated, byte_count=len(data))

    def test_large_body_truncated_success_on_200(self):
        """A 200 response with > 1 MB body → success=True, body truncated."""
        notifier = _make_notifier()
        payload = _make_payload()
        capped = self._make_capped_body(truncated=True)

        with patch("app.notifications.validate_webhook_url"):
            with patch.object(
                notifier,
                "_post_with_body_cap",
                return_value=(200, capped, {}),
            ):
                result = notifier._deliver_with_retry(
                    "https://example.com/hook", payload
                )

        assert result.success is True
        assert result.status_code == 200

    def test_large_body_truncated_failure_on_500(self):
        """A 500 response with > 1 MB body → success=False, body truncated."""
        notifier = _make_notifier()
        payload = _make_payload()
        capped = self._make_capped_body(truncated=True)

        with patch("app.notifications.validate_webhook_url"):
            with patch.object(
                notifier,
                "_post_with_body_cap",
                return_value=(500, capped, {}),
            ):
                result = notifier._deliver_with_retry(
                    "https://example.com/hook", payload
                )

        assert result.success is False
        assert result.status_code == 500

    def test_read_response_capped_truncates_at_limit(self):
        """read_response_capped stops reading after the cap."""
        from app.webhook_security import read_response_capped

        limit = 100
        # 5 chunks of 40 bytes each = 200 bytes total, cap is 100.
        chunks = [b"A" * 40] * 5
        result = read_response_capped(iter(chunks), limit=limit)

        assert result.truncated is True
        assert len(result.data) <= limit
        assert result.byte_count <= limit

    def test_read_response_capped_full_body_under_limit(self):
        """read_response_capped returns all bytes when body < cap."""
        from app.webhook_security import read_response_capped

        chunks = [b"hello ", b"world"]
        result = read_response_capped(iter(chunks), limit=1_048_576)

        assert result.truncated is False
        assert result.data == b"hello world"

    def test_read_response_capped_exactly_at_limit(self):
        """Exactly cap bytes: not truncated."""
        from app.webhook_security import read_response_capped

        limit = 50
        chunks = [b"B" * 50]
        result = read_response_capped(iter(chunks), limit=limit)

        assert result.truncated is False
        assert len(result.data) == 50


# ---------------------------------------------------------------------------
# 3. Normal 200 response → passes through
# ---------------------------------------------------------------------------

class TestNormalDelivery:
    def test_200_response_success(self):
        notifier = _make_notifier()
        payload = _make_payload()
        capped = CappedBody(data=b'{"ok": true}', truncated=False, byte_count=12)

        with patch("app.notifications.validate_webhook_url"):
            with patch.object(
                notifier,
                "_post_with_body_cap",
                return_value=(200, capped, {}),
            ):
                result = notifier._deliver_with_retry(
                    "https://example.com/hook", payload
                )

        assert result.success is True
        assert result.status_code == 200
        assert result.attempts == 1

    def test_201_response_success(self):
        notifier = _make_notifier()
        payload = _make_payload()
        capped = CappedBody(data=b"created", truncated=False, byte_count=7)

        with patch("app.notifications.validate_webhook_url"):
            with patch.object(
                notifier,
                "_post_with_body_cap",
                return_value=(201, capped, {}),
            ):
                result = notifier._deliver_with_retry(
                    "https://example.com/hook", payload
                )

        assert result.success is True

    def test_404_response_no_retry(self):
        """4xx (non-429) → fail immediately, no retry."""
        # max_retries=3 to confirm it only calls once
        notifier = _make_notifier()
        with patch("app.notifications.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                webhook_url_list=["https://example.com/hook"],
                webhook_timeout_seconds=10,
                webhook_max_retries=3,
            )
            notifier3 = WebhookNotifier(
                urls=["https://example.com/hook"], timeout=10, max_retries=3
            )
        payload = _make_payload()
        capped = CappedBody(data=b"not found", truncated=False, byte_count=9)

        with patch("app.notifications.validate_webhook_url"):
            with patch.object(
                notifier3,
                "_post_with_body_cap",
                return_value=(404, capped, {}),
            ) as mock_post:
                result = notifier3._deliver_with_retry(
                    "https://example.com/hook", payload
                )

        # Should only call once (no retry on 4xx)
        assert mock_post.call_count == 1
        assert result.success is False
        assert result.status_code == 404


# ---------------------------------------------------------------------------
# 4. validate_webhook_url integration tests (no network)
# ---------------------------------------------------------------------------

class TestValidateWebhookURLIntegration:
    """Minimal integration tests for webhook_security.validate_webhook_url."""

    def test_empty_url_raises(self):
        from app.webhook_security import validate_webhook_url

        with pytest.raises(WebhookURLBlocked, match="empty"):
            validate_webhook_url("")

    def test_file_scheme_raises(self):
        from app.webhook_security import validate_webhook_url

        # file:// has no host, so it triggers "no host" or "scheme" — both
        # are correct rejections. Use ftp:// which does have a host.
        with pytest.raises(WebhookURLBlocked, match="scheme"):
            validate_webhook_url("ftp://attacker.com/payload")

    def test_loopback_ip_raises(self):
        import os
        from app.webhook_security import validate_webhook_url

        with patch.dict(os.environ, {"WEBHOOK_ALLOW_PRIVATE": "false", "WEBHOOK_ALLOW_HTTP": "true"}):
            with pytest.raises(WebhookURLBlocked):
                validate_webhook_url("http://127.0.0.1/hook")

    def test_metadata_ip_raises(self):
        import os
        from app.webhook_security import validate_webhook_url

        with patch.dict(os.environ, {"WEBHOOK_ALLOW_PRIVATE": "false", "WEBHOOK_ALLOW_HTTP": "true"}):
            with pytest.raises(WebhookURLBlocked):
                validate_webhook_url("http://169.254.169.254/latest")

    def test_http_blocked_by_default(self):
        """http:// is blocked unless WEBHOOK_ALLOW_HTTP=true."""
        import os
        from app.webhook_security import validate_webhook_url

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WEBHOOK_ALLOW_HTTP", None)
            with pytest.raises(WebhookURLBlocked, match="http"):
                validate_webhook_url("http://example.com/hook")

    def test_private_network_blocked(self):
        import os
        from app.webhook_security import validate_webhook_url

        with patch.dict(os.environ, {"WEBHOOK_ALLOW_PRIVATE": "false"}):
            with pytest.raises(WebhookURLBlocked):
                validate_webhook_url("https://10.0.0.1/hook")

    def test_rfc1918_172_blocked(self):
        import os
        from app.webhook_security import validate_webhook_url

        with patch.dict(os.environ, {"WEBHOOK_ALLOW_PRIVATE": "false"}):
            with pytest.raises(WebhookURLBlocked):
                validate_webhook_url("https://172.16.0.1/hook")
