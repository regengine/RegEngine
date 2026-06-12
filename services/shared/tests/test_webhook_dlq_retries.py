"""Regression tests for WebhookDLQ.process_retries (#2449 low).

The previous stub hardcoded ``success = False`` and always called
``mark_retry_attempt`` — silently burning every entry's retry budget and
marching it to 'dead' purely by the passage of time, with no delivery ever
attempted. The fix:

* No ``delivery_callback`` wired  -> entries are left pending (counted as
  'deferred'); neither mark_retry_attempt nor delete is called.
* Callback returns True          -> entry deleted, counted 'succeeded'.
* Callback returns False / raises -> mark_retry_attempt called (real retry).
"""

from unittest.mock import MagicMock

import pytest
from shared.webhook_dlq import WebhookDLQ

PENDING = [{"id": "wh-1"}, {"id": "wh-2"}]


def _dlq(**kwargs) -> WebhookDLQ:
    dlq = WebhookDLQ(db_session=MagicMock(), tenant_id="t-1", **kwargs)
    dlq.get_pending_retries = lambda limit=100: list(PENDING)
    dlq.delete_webhook = MagicMock(return_value=True)
    dlq.mark_retry_attempt = MagicMock(return_value=False)
    return dlq


@pytest.mark.asyncio
async def test_no_callback_leaves_entries_pending():
    dlq = _dlq()  # no delivery_callback
    stats = await dlq.process_retries()

    assert stats["deferred"] == 2
    assert stats["failed"] == 0 and stats["dead"] == 0 and stats["succeeded"] == 0
    # The destructive path is never taken.
    dlq.mark_retry_attempt.assert_not_called()
    dlq.delete_webhook.assert_not_called()


@pytest.mark.asyncio
async def test_successful_delivery_deletes_entry():
    dlq = _dlq(delivery_callback=lambda entry: True)
    stats = await dlq.process_retries()

    assert stats["succeeded"] == 2
    assert stats["deferred"] == 0
    assert dlq.delete_webhook.call_count == 2
    dlq.mark_retry_attempt.assert_not_called()


@pytest.mark.asyncio
async def test_failed_delivery_marks_retry():
    dlq = _dlq(delivery_callback=lambda entry: False)
    stats = await dlq.process_retries()

    assert stats["succeeded"] == 0
    assert dlq.mark_retry_attempt.call_count == 2
    dlq.delete_webhook.assert_not_called()


@pytest.mark.asyncio
async def test_callback_exception_is_treated_as_failure():
    def boom(entry):
        raise RuntimeError("delivery exploded")

    dlq = _dlq(delivery_callback=boom)
    stats = await dlq.process_retries()

    assert stats["succeeded"] == 0
    assert dlq.mark_retry_attempt.call_count == 2
