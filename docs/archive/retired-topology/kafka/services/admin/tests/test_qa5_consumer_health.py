"""QA5: a review consumer that never started must not report healthy.

``get_consumer_health`` derived ``healthy`` from ``is_alive`` (stop
never requested) and poll freshness, but a consumer that crashed or
was skipped at boot has ``started_at=None`` and was never stale by
construction, so ``/health/consumer`` returned 200 green forever.
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

import app.review_consumer as consumer  # noqa: E402


class TestNeverStartedUnhealthy:
    def test_never_started_reports_unhealthy(self, monkeypatch):
        monkeypatch.setattr(consumer, "_shutdown_event", threading.Event())
        monkeypatch.setattr(consumer, "_consumer_started_at", None)
        monkeypatch.setattr(consumer, "_last_poll_time", None)

        health = consumer.get_consumer_health()

        assert health["started_at"] is None
        assert health["healthy"] is False

    def test_started_and_fresh_reports_healthy(self, monkeypatch):
        now = datetime.now(timezone.utc)
        monkeypatch.setattr(consumer, "_shutdown_event", threading.Event())
        monkeypatch.setattr(consumer, "_consumer_started_at", now - timedelta(seconds=60))
        monkeypatch.setattr(consumer, "_last_poll_time", now)

        health = consumer.get_consumer_health()

        assert health["healthy"] is True

    def test_stale_poll_still_unhealthy(self, monkeypatch):
        now = datetime.now(timezone.utc)
        monkeypatch.setattr(consumer, "_shutdown_event", threading.Event())
        monkeypatch.setattr(
            consumer,
            "_consumer_started_at",
            now - timedelta(seconds=consumer.CONSUMER_STALE_THRESHOLD_SECONDS + 120),
        )
        monkeypatch.setattr(
            consumer,
            "_last_poll_time",
            now - timedelta(seconds=consumer.CONSUMER_STALE_THRESHOLD_SECONDS + 60),
        )

        health = consumer.get_consumer_health()

        assert health["poll_stale"] is True
        assert health["healthy"] is False
