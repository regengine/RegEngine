"""Unit suite for the shared fail-closed webhook verifier.

Every test here pins one fail-closed property: anything missing or
wrong (secret, signature, scheme, timestamp) is a rejection, and only
a correctly signed payload verifies. Uses the reusable fixtures from
``services/shared/tests/conftest.py``.
"""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest
from fastapi import HTTPException
from shared.external_connectors.base import ConnectorConfig, IntegrationConnector
from shared.webhook_auth import (
    VerifiedWebhook,
    WebhookSecretMissingError,
    WebhookSignatureInvalidError,
    WebhookSignatureMissingError,
    WebhookTimestampError,
    require_webhook_secret,
    sign_webhook_payload,
    verification_http_exception,
    verify_webhook_or_401,
    verify_webhook_signature,
    webhook_accepted_response,
)


class _StubConnector(IntegrationConnector):
    async def test_connection(self) -> bool:
        return True

    async def fetch_events(self, since=None, cursor=None, limit=100):  # type: ignore[no-untyped-def]
        return [], None

    def normalize_event(self, raw_event):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def get_connector_info(self):  # type: ignore[no-untyped-def]
        return {}


class TestRequireWebhookSecret:
    def test_valid_secret_returned(self, webhook_secret: str) -> None:
        assert require_webhook_secret(webhook_secret) == webhook_secret

    def test_missing_secret_refused(self) -> None:
        with pytest.raises(WebhookSecretMissingError):
            require_webhook_secret(None)

    def test_blank_secret_refused(self) -> None:
        with pytest.raises(WebhookSecretMissingError):
            require_webhook_secret("   ")

    def test_empty_secret_refused(self) -> None:
        with pytest.raises(WebhookSecretMissingError):
            require_webhook_secret("")


class TestVerifyFailClosed:
    def test_missing_secret_rejects_valid_signature(self, signed_webhook) -> None:  # type: ignore[no-untyped-def]
        payload, header = signed_webhook()
        with pytest.raises(WebhookSecretMissingError):
            verify_webhook_signature(payload, header, None)

    def test_blank_secret_rejects_valid_signature(self, signed_webhook) -> None:  # type: ignore[no-untyped-def]
        payload, header = signed_webhook()
        with pytest.raises(WebhookSecretMissingError):
            verify_webhook_signature(payload, header, "  ")

    def test_missing_header_rejected(self, webhook_payload: bytes, webhook_secret: str) -> None:
        with pytest.raises(WebhookSignatureMissingError):
            verify_webhook_signature(webhook_payload, None, webhook_secret)

    def test_blank_header_rejected(self, webhook_payload: bytes, webhook_secret: str) -> None:
        with pytest.raises(WebhookSignatureMissingError):
            verify_webhook_signature(webhook_payload, "  ", webhook_secret)

    def test_wrong_signature_rejected(self, webhook_payload: bytes, webhook_secret: str) -> None:
        with pytest.raises(WebhookSignatureInvalidError):
            verify_webhook_signature(webhook_payload, "sha256=" + "0" * 64, webhook_secret)

    def test_tampered_payload_rejected(self, webhook_secret: str, signed_webhook) -> None:  # type: ignore[no-untyped-def]
        _, header = signed_webhook()
        with pytest.raises(WebhookSignatureInvalidError):
            verify_webhook_signature(b'{"event_type": "FORGED"}', header, webhook_secret)

    def test_wrong_secret_rejected(self, webhook_secret: str, sign_webhook) -> None:  # type: ignore[no-untyped-def]
        payload = b'{"event_type": "x"}'
        header = sign_webhook(payload, "other-secret")
        with pytest.raises(WebhookSignatureInvalidError):
            verify_webhook_signature(payload, header, webhook_secret)

    def test_unknown_scheme_rejected(self, webhook_payload: bytes, webhook_secret: str) -> None:
        with pytest.raises(WebhookSignatureInvalidError):
            verify_webhook_signature(webhook_payload, "md5=abcdef", webhook_secret)

    def test_malformed_header_rejected(self, webhook_payload: bytes, webhook_secret: str) -> None:
        with pytest.raises(WebhookSignatureInvalidError):
            verify_webhook_signature(webhook_payload, "t=abc,v1=def", webhook_secret)


class TestVerifyAccepts:
    def test_timestamped_signature_accepted(self, signed_webhook, webhook_secret: str) -> None:  # type: ignore[no-untyped-def]
        payload, header = signed_webhook()
        result = verify_webhook_signature(payload, header, webhook_secret)
        assert isinstance(result, VerifiedWebhook)
        assert result.scheme == "v1"
        assert result.timestamp is not None

    def test_github_style_signature_accepted(
        self,
        webhook_payload: bytes,
        webhook_secret: str,
        sign_webhook,  # type: ignore[no-untyped-def]
    ) -> None:
        header = sign_webhook(webhook_payload, webhook_secret, timestamp=None)
        assert header.startswith("sha256=")
        result = verify_webhook_signature(webhook_payload, header, webhook_secret)
        assert result.scheme == "sha256"
        assert result.timestamp is None

    def test_bare_hex_signature_accepted(self, webhook_payload: bytes, webhook_secret: str) -> None:
        expected = hmac.new(webhook_secret.encode(), webhook_payload, hashlib.sha256).hexdigest()
        result = verify_webhook_signature(webhook_payload, expected, webhook_secret)
        assert result.scheme == "sha256"

    def test_no_timestamp_required_when_provider_sends_none(
        self,
        webhook_payload: bytes,
        webhook_secret: str,
        sign_webhook,  # type: ignore[no-untyped-def]
    ) -> None:
        header = sign_webhook(webhook_payload, webhook_secret, timestamp=None)
        result = verify_webhook_signature(webhook_payload, header, webhook_secret)
        assert result.timestamp is None


class TestTimestampTolerance:
    def test_stale_timestamp_rejected(self, webhook_secret: str) -> None:
        payload = b'{"event_type": "replay"}'
        old = int(time.time()) - 3600
        header = sign_webhook_payload(payload, webhook_secret, timestamp=old)
        with pytest.raises(WebhookTimestampError):
            verify_webhook_signature(payload, header, webhook_secret, timestamp_tolerance_seconds=300)

    def test_future_timestamp_rejected(self, webhook_secret: str) -> None:
        payload = b'{"event_type": "future"}'
        future = int(time.time()) + 3600
        header = sign_webhook_payload(payload, webhook_secret, timestamp=future)
        with pytest.raises(WebhookTimestampError):
            verify_webhook_signature(payload, header, webhook_secret, timestamp_tolerance_seconds=300)

    def test_timestamp_inside_window_accepted(self, webhook_secret: str) -> None:
        payload = b'{"event_type": "fresh"}'
        recent = int(time.time()) - 60
        header = sign_webhook_payload(payload, webhook_secret, timestamp=recent)
        result = verify_webhook_signature(payload, header, webhook_secret, timestamp_tolerance_seconds=300)
        assert result.timestamp == recent

    def test_custom_tolerance_honored(self, webhook_secret: str) -> None:
        payload = b'{"event_type": "edge"}'
        ts = int(time.time()) - 500
        header = sign_webhook_payload(payload, webhook_secret, timestamp=ts)
        with pytest.raises(WebhookTimestampError):
            verify_webhook_signature(payload, header, webhook_secret, timestamp_tolerance_seconds=60)
        result = verify_webhook_signature(payload, header, webhook_secret, timestamp_tolerance_seconds=900)
        assert result.timestamp == ts


class TestConstantTimeCompare:
    def test_compare_digest_used(
        self,
        monkeypatch: pytest.MonkeyPatch,
        webhook_payload: bytes,
        webhook_secret: str,
        sign_webhook,  # type: ignore[no-untyped-def]
    ) -> None:
        calls = []
        real_compare = hmac.compare_digest

        def _spy(a: str, b: str) -> bool:
            calls.append((a, b))
            return real_compare(a, b)

        monkeypatch.setattr(hmac, "compare_digest", _spy)
        header = sign_webhook(webhook_payload, webhook_secret, timestamp=None)
        verify_webhook_signature(webhook_payload, header, webhook_secret)
        assert len(calls) == 1

    def test_mismatch_still_compared_in_constant_time(
        self, monkeypatch: pytest.MonkeyPatch, webhook_payload: bytes, webhook_secret: str
    ) -> None:
        seen = []
        real_compare = hmac.compare_digest

        def _spy(a: str, b: str) -> bool:
            seen.append(True)
            return real_compare(a, b)

        monkeypatch.setattr(hmac, "compare_digest", _spy)
        with pytest.raises(WebhookSignatureInvalidError):
            verify_webhook_signature(webhook_payload, "sha256=" + "f" * 64, webhook_secret)
        assert seen, "mismatched signatures must still go through compare_digest"


class TestHttpMapping:
    def test_or_401_raises_401_with_error_body(self, webhook_payload: bytes, webhook_secret: str) -> None:
        with pytest.raises(HTTPException) as exc_info:
            verify_webhook_or_401(webhook_payload, None, webhook_secret)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "missing_webhook_signature"

    def test_or_401_accepts_valid(self, signed_webhook, webhook_secret: str) -> None:  # type: ignore[no-untyped-def]
        payload, header = signed_webhook()
        result = verify_webhook_or_401(payload, header, webhook_secret)
        assert isinstance(result, VerifiedWebhook)

    def test_verification_error_maps_to_401(self) -> None:
        exc = verification_http_exception(WebhookSignatureMissingError("Missing webhook signature."))
        assert exc.status_code == 401
        assert exc.detail["error"] == "missing_webhook_signature"

    def test_accepted_response_carries_count_only(self) -> None:
        assert webhook_accepted_response(3) == {"accepted": 3}


class TestConnectorAdoption:
    """Every connector inherits the fail-closed template from the base class."""

    def _connector(self, secret: str = "connector-secret") -> _StubConnector:
        return _StubConnector(
            ConnectorConfig(
                connector_id="stub",
                display_name="Stub",
                category="food_safety",
                webhook_secret=secret,
            )
        )

    def test_enable_time_gate_refuses_missing_secret(self) -> None:
        connector = self._connector(secret="")
        with pytest.raises(ValueError, match="without a signing secret"):
            connector.require_webhook_secret()

    def test_enable_time_gate_passes_with_secret(self) -> None:
        assert self._connector().require_webhook_secret() == "connector-secret"

    def test_connector_rejects_missing_secret(self, webhook_payload: bytes, sign_webhook) -> None:  # type: ignore[no-untyped-def]
        connector = self._connector(secret="")
        header = sign_webhook(webhook_payload, "connector-secret", timestamp=None)
        assert connector.verify_webhook_signature(webhook_payload, header) is False

    def test_connector_rejects_missing_signature(self) -> None:
        connector = self._connector()
        assert connector.verify_webhook_signature(b"{}", "") is False

    def test_connector_rejects_bad_signature(self, webhook_payload: bytes) -> None:
        connector = self._connector()
        assert connector.verify_webhook_signature(webhook_payload, "sha256=" + "0" * 64) is False

    def test_connector_accepts_valid_signature(self, webhook_payload: bytes, sign_webhook) -> None:  # type: ignore[no-untyped-def]
        connector = self._connector()
        header = sign_webhook(webhook_payload, "connector-secret", timestamp=None)
        assert connector.verify_webhook_signature(webhook_payload, header) is True

    def test_connector_accepts_timestamped_signature(self, signed_webhook) -> None:  # type: ignore[no-untyped-def]
        connector = self._connector(secret="test-webhook-secret-abc123")
        payload, header = signed_webhook()
        assert connector.verify_webhook_signature(payload, header) is True

    def test_connector_rejects_unknown_scheme(self, webhook_payload: bytes) -> None:
        connector = self._connector()
        assert connector.verify_webhook_signature(webhook_payload, "md5=abcdef") is False
