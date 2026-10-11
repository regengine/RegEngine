"""QA5: webhook timestamp boundaries for shared/webhook_security.py."""

import time

import pytest
from shared.webhook_security import (
    WebhookTimestampError,
    generate_signature,
    verify_signature,
)

SECRET = "qa5-webhook-secret"
PAYLOAD = b'{"event": "test"}'


def test_signature_from_near_future_rejected() -> None:
    future_header = generate_signature(PAYLOAD, SECRET, timestamp=int(time.time()) + 299)
    with pytest.raises(WebhookTimestampError):
        verify_signature(PAYLOAD, future_header, secret=SECRET)


def test_signature_from_small_future_skew_accepted() -> None:
    header = generate_signature(PAYLOAD, SECRET, timestamp=int(time.time()) + 30)
    assert verify_signature(PAYLOAD, header, secret=SECRET) is True


def test_signature_within_age_tolerance_accepted() -> None:
    header = generate_signature(PAYLOAD, SECRET, timestamp=int(time.time()) - 299)
    assert verify_signature(PAYLOAD, header, secret=SECRET) is True


def test_stale_signature_rejected() -> None:
    header = generate_signature(PAYLOAD, SECRET, timestamp=int(time.time()) - 301)
    with pytest.raises(WebhookTimestampError):
        verify_signature(PAYLOAD, header, secret=SECRET)
