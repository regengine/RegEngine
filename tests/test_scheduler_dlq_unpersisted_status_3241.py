"""#3241 — /v1/scheduler/status must reflect live unpersisted webhook loss.

Before the fix, ``webhook_dlq.at_risk`` derived only from settings (URLs
configured + outbox path empty). A deploy WITH a configured outbox path
whose append failed (disk error), or any tick that added an unpersisted
dead letter, still reported ``persistence_enabled: true`` and
``at_risk: false``: the success signal operators watch stayed green while
the alert died with the process.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from server.routes_scheduler_status import _webhook_dlq_status


class _Settings:
    def __init__(self, urls, outbox_path):
        self.webhook_url_list = urls
        self.webhook_outbox_path = outbox_path


class _Service:
    def __init__(self, settings, unpersisted=0, with_notifier=True):
        self.settings = settings
        if with_notifier:
            notifier = MagicMock()
            notifier.unpersisted_dead_letter_count.return_value = unpersisted
            self.notifier = notifier


def test_at_risk_when_outbox_append_failed_despite_configured_path():
    """Configured path + nonzero live loss still reports at risk."""
    svc = _Service(_Settings(["https://hook.example.com/alerts"], "/data/webhook_outbox.jsonl"), unpersisted=2)
    status = _webhook_dlq_status(svc)
    assert status["persistence_enabled"] is True
    assert status["unpersisted_dead_letter_count"] == 2
    assert status["at_risk"] is True


def test_not_at_risk_when_durable_and_nothing_lost():
    svc = _Service(_Settings(["https://hook.example.com/alerts"], "/data/webhook_outbox.jsonl"), unpersisted=0)
    status = _webhook_dlq_status(svc)
    assert status["unpersisted_dead_letter_count"] == 0
    assert status["at_risk"] is False


def test_service_without_notifier_stays_quiet():
    """Older or fake service objects without a notifier report zero loss."""
    svc = _Service(_Settings([], ""), with_notifier=False)
    status = _webhook_dlq_status(svc)
    assert status["unpersisted_dead_letter_count"] == 0
    assert status["at_risk"] is False
