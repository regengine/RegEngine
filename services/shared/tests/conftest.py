"""Reusable webhook-auth fixtures for shared-connector tests.

Any test module under ``services/shared/tests/`` can request these:

- ``webhook_secret``: a fixed non-empty signing secret.
- ``webhook_payload``: a fixed raw JSON body (bytes).
- ``sign_webhook``: factory ``(payload, secret, *, timestamp=None)``
  returning a provider-style signature header value.
- ``signed_webhook``: factory ``(payload=None, secret=None, *,
  timestamp=None)`` returning ``(payload, header)`` ready for
  ``verify_webhook_signature``.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import pytest
from shared.webhook_auth import sign_webhook_payload

FIXED_WEBHOOK_SECRET = "test-webhook-secret-abc123"
FIXED_WEBHOOK_PAYLOAD = b'{"event_type": "INSPECTION_COMPLETED", "audit_id": "aud_123"}'


@pytest.fixture
def webhook_secret() -> str:
    """Fixed signing secret for webhook tests."""
    return FIXED_WEBHOOK_SECRET


@pytest.fixture
def webhook_payload() -> bytes:
    """Fixed raw webhook body for webhook tests."""
    return FIXED_WEBHOOK_PAYLOAD


@pytest.fixture
def sign_webhook() -> Callable[..., str]:
    """Factory returning a provider-style signature header value."""

    def _sign(payload: bytes, secret: str, *, timestamp: Optional[int] = None) -> str:
        return sign_webhook_payload(payload, secret, timestamp=timestamp)

    return _sign


@pytest.fixture
def signed_webhook() -> Callable[..., tuple[bytes, str]]:
    """Factory returning a ``(payload, signature_header)`` pair.

    Defaults to the fixed payload and secret with the provider clock set
    to now, so timestamped signatures pass the tolerance window.
    """

    def _make(
        payload: Optional[bytes] = None,
        secret: Optional[str] = None,
        *,
        timestamp: Optional[int] = None,
        use_timestamp: bool = True,
    ) -> tuple[bytes, str]:
        body = FIXED_WEBHOOK_PAYLOAD if payload is None else payload
        key = FIXED_WEBHOOK_SECRET if secret is None else secret
        ts = int(time.time()) if (use_timestamp and timestamp is None) else timestamp
        return body, sign_webhook_payload(body, key, timestamp=ts)

    return _make
