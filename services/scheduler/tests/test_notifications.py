"""Tests for WebhookNotifier delivery system.

Covers:
- Successful delivery
- Retry with exponential backoff on 5xx
- No retry on 4xx
- Timeout and connection error handling
- Dead-letter queue
- Summary building
- Parallel delivery to multiple URLs
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable

ensure_shared_importable()

import app.notifications as notifications_mod
import httpx
import pytest
from app.models import EnforcementItem, EnforcementSeverity, SourceType

WebhookNotifier = notifications_mod.WebhookNotifier
DeliveryResult = notifications_mod.DeliveryResult


def _make_item(severity=EnforcementSeverity.MEDIUM, **kw) -> EnforcementItem:
    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id=kw.get("source_id", "test-recall-001"),
        title=kw.get("title", "Test FDA Recall"),
        url="https://fda.gov/recalls/test",
        published_date=datetime(2026, 3, 15, tzinfo=timezone.utc),
        severity=severity,
    )


@pytest.fixture
def notifier():
    """Create a WebhookNotifier with test URLs."""
    n = WebhookNotifier(
        urls=["https://hook1.example.com/webhook"],
        timeout=5,
        max_retries=3,
        max_workers=2,
    )
    yield n
    n.close()


@pytest.fixture(autouse=True)
def _allow_mock_webhook_urls(monkeypatch):
    monkeypatch.setattr(notifications_mod, "validate_url", lambda _url: None)


# ─── Successful delivery ────────────────────────────────────────────────


class TestSuccessfulDelivery:
    def test_200_response_is_success(self, notifier):
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch.object(notifier.session, "post", return_value=mock_response):
            results = notifier.notify([_make_item()])
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].status_code == 200

    def test_201_response_is_success(self, notifier):
        mock_response = MagicMock()
        mock_response.status_code = 201
        with patch.object(notifier.session, "post", return_value=mock_response):
            results = notifier.notify([_make_item()])
        assert results[0].success is True

    def test_empty_items_returns_empty(self, notifier):
        results = notifier.notify([])
        assert results == []

    def test_no_urls_returns_empty(self):
        n = WebhookNotifier(urls=[], max_retries=1)
        results = n.notify([_make_item()])
        assert results == []
        n.close()


# ─── Retry behavior ─────────────────────────────────────────────────────


class TestRetryBehavior:
    def test_4xx_does_not_retry(self, notifier):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        with patch.object(notifier.session, "post", return_value=mock_response) as mock_post:
            results = notifier.notify([_make_item()])
        assert results[0].success is False
        assert results[0].attempts == 1  # No retry
        assert mock_post.call_count == 1

    @patch.object(notifications_mod.time, "sleep")  # Avoid actual sleep in tests
    def test_5xx_retries(self, mock_sleep, notifier):
        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.text = "Internal Server Error"

        success_response = MagicMock()
        success_response.status_code = 200

        with patch.object(notifier.session, "post", side_effect=[fail_response, success_response]):
            results = notifier.notify([_make_item()])
        assert results[0].success is True
        assert results[0].attempts == 2

    @patch.object(notifications_mod.time, "sleep")
    def test_timeout_retries(self, mock_sleep, notifier):
        success_response = MagicMock()
        success_response.status_code = 200

        with patch.object(notifier.session, "post", side_effect=[httpx.TimeoutException("timeout"), success_response]):
            results = notifier.notify([_make_item()])
        assert results[0].success is True
        assert results[0].attempts == 2

    @patch.object(notifications_mod.time, "sleep")
    def test_connection_error_retries(self, mock_sleep, notifier):
        success_response = MagicMock()
        success_response.status_code = 200

        with patch.object(notifier.session, "post", side_effect=[httpx.ConnectError("refused"), success_response]):
            results = notifier.notify([_make_item()])
        assert results[0].success is True

    @patch.object(notifications_mod.time, "sleep")
    def test_all_retries_exhausted(self, mock_sleep, notifier):
        fail_response = MagicMock()
        fail_response.status_code = 503
        fail_response.text = "Service Unavailable"

        with patch.object(notifier.session, "post", return_value=fail_response):
            results = notifier.notify([_make_item()])
        assert results[0].success is False
        assert results[0].attempts == 3  # max_retries


# ─── Dead-letter queue ───────────────────────────────────────────────────


class TestDeadLetterQueue:
    @patch.object(notifications_mod.time, "sleep")
    def test_failed_delivery_added_to_dead_letter(self, mock_sleep, notifier):
        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.text = "Error"

        with patch.object(notifier.session, "post", return_value=fail_response):
            notifier.notify([_make_item()])

        dead = notifier.get_dead_letters()
        assert len(dead) == 1
        assert dead[0]["url"] == "https://hook1.example.com/webhook"

    def test_get_dead_letters_returns_copy(self, notifier):
        notifier._dead_letter.append({"url": "test", "payload": {}})
        dead = notifier.get_dead_letters()
        dead.clear()
        assert len(notifier._dead_letter) == 1

    def test_clear_dead_letters(self, notifier):
        notifier._dead_letter.append({"url": "test", "payload": {}})
        count = notifier.clear_dead_letters()
        assert count == 1
        assert len(notifier._dead_letter) == 0


class TestOutboxPersistence:
    """#2510 — the dead-letter queue must survive process restart when an
    outbox path is configured. Without it, failed HIGH/CRITICAL alert
    deliveries live only in process memory and are lost on every Railway
    restart/deploy."""

    @patch.object(notifications_mod.time, "sleep")
    def test_failed_delivery_persists_and_survives_restart(self, mock_sleep, tmp_path):
        outbox = tmp_path / "webhook_outbox.jsonl"

        # Notifier #1: configured with a durable outbox path.
        n1 = WebhookNotifier(
            urls=["https://hook1.example.com/webhook"],
            timeout=5,
            max_retries=2,
            max_workers=1,
            outbox_path=str(outbox),
        )
        assert n1._outbox_path is not None

        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.text = "Error"
        with patch.object(n1.session, "post", return_value=fail_response):
            n1.notify([_make_item(severity=EnforcementSeverity.CRITICAL)])

        # The on-disk JSONL file exists and holds one entry.
        assert outbox.exists()
        assert len([ln for ln in outbox.read_text().splitlines() if ln.strip()]) == 1

        # Notifier #2 simulates a fresh process after restart: it reads the
        # same path back and recovers the dead-letter (in-memory list is empty).
        n2 = WebhookNotifier(
            urls=["https://hook1.example.com/webhook"],
            outbox_path=str(outbox),
        )
        recovered = n2._read_outbox()
        assert len(recovered) == 1
        assert recovered[0].url == "https://hook1.example.com/webhook"

    def test_empty_outbox_path_selects_in_memory_only(self):
        """An empty outbox path -> in-memory-only mode (the unsafe legacy
        default the #2510 footgun warns about)."""
        n = WebhookNotifier(urls=["https://hook1.example.com/webhook"], outbox_path=None)
        assert n._outbox_path is None


# ─── Unpersisted dead letters are nacked, not silently kept ──────────


class TestUnpersistedNack:
    """Deliveries that fail with no outbox file die with the process.

    They must be nacked loudly (error log + counter + ``success=False``
    result) instead of sitting silently in the in-memory list.
    """

    @patch.object(notifications_mod.time, "sleep")
    def test_failed_delivery_without_outbox_counts_unpersisted(self, mock_sleep, notifier):
        assert notifier.outbox_durable is False
        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.text = "Error"

        with (
            patch.object(notifier.session, "post", return_value=fail_response),
            patch.object(notifications_mod.logger, "error") as log_error,
        ):
            results = notifier.notify([_make_item(severity=EnforcementSeverity.CRITICAL)])

        assert results[0].success is False
        assert notifier.unpersisted_dead_letter_count() == 1
        # Still visible in the legacy in-memory list for this process.
        assert len(notifier.get_dead_letters()) == 1
        # The nack must be a loud error log, not just a counter bump:
        # deleting the log line alone must turn this red.
        error_events = [call.args[0] for call in log_error.call_args_list if call.args]
        assert "webhook_dead_letter_unpersisted" in error_events

    @patch.object(notifications_mod.time, "sleep")
    def test_failed_delivery_with_outbox_stays_durable(self, mock_sleep, tmp_path):
        outbox = tmp_path / "webhook_outbox.jsonl"
        n = WebhookNotifier(
            urls=["https://hook1.example.com/webhook"],
            timeout=5,
            max_retries=2,
            max_workers=1,
            outbox_path=str(outbox),
        )
        try:
            assert n.outbox_durable is True
            fail_response = MagicMock()
            fail_response.status_code = 500
            fail_response.text = "Error"

            with patch.object(n.session, "post", return_value=fail_response):
                results = n.notify([_make_item(severity=EnforcementSeverity.CRITICAL)])

            assert results[0].success is False
            assert n.unpersisted_dead_letter_count() == 0
            assert len([ln for ln in outbox.read_text().splitlines() if ln.strip()]) == 1
        finally:
            n.close()

    @patch.object(notifications_mod.time, "sleep")
    def test_outbox_append_failure_counts_unpersisted(self, mock_sleep, tmp_path):
        """A disk failure keeps the scrape cycle alive but nacks durability."""
        outbox_dir = tmp_path / "outbox_is_a_directory"
        outbox_dir.mkdir()
        n = WebhookNotifier(
            urls=["https://hook1.example.com/webhook"],
            timeout=5,
            max_retries=1,
            max_workers=1,
            outbox_path=str(outbox_dir),  # open() for append raises OSError
        )
        try:
            fail_response = MagicMock()
            fail_response.status_code = 500
            fail_response.text = "Error"

            with (
                patch.object(n.session, "post", return_value=fail_response),
                patch.object(notifications_mod.logger, "error") as log_error,
            ):
                results = n.notify([_make_item()])

            assert results[0].success is False
            assert n.unpersisted_dead_letter_count() == 1
            error_events = [call.args[0] for call in log_error.call_args_list if call.args]
            assert "webhook_outbox_append_failed" in error_events
        finally:
            n.close()


# ─── Summary building ───────────────────────────────────────────────────


class TestBuildSummary:
    def test_empty_items_message(self, notifier):
        summary = notifier._build_summary([])
        assert "No new enforcement items" in summary

    def test_groups_by_severity(self, notifier):
        items = [
            _make_item(severity=EnforcementSeverity.CRITICAL),
            _make_item(severity=EnforcementSeverity.CRITICAL),
            _make_item(severity=EnforcementSeverity.HIGH),
            _make_item(severity=EnforcementSeverity.LOW),
        ]
        summary = notifier._build_summary(items)
        assert "4 enforcement item(s)" in summary
        assert "2 CRITICAL" in summary
        assert "1 HIGH" in summary
        assert "1 LOW" in summary

    def test_severity_order_is_descending(self, notifier):
        items = [
            _make_item(severity=EnforcementSeverity.LOW),
            _make_item(severity=EnforcementSeverity.CRITICAL),
        ]
        summary = notifier._build_summary(items)
        # CRITICAL should appear before LOW
        assert summary.index("CRITICAL") < summary.index("LOW")


# ─── Parallel delivery ──────────────────────────────────────────────────


class TestParallelDelivery:
    def test_delivers_to_multiple_urls(self):
        n = WebhookNotifier(
            urls=["https://hook1.example.com", "https://hook2.example.com"],
            max_retries=1,
            max_workers=2,
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch.object(n.session, "post", return_value=mock_response):
            results = n.notify([_make_item()])
        assert len(results) == 2
        urls = {r.url for r in results}
        hosts = {urlparse(u).hostname for u in urls}
        assert hosts == {"hook1.example.com", "hook2.example.com"}
        assert all(urlparse(u).scheme == "https" for u in urls)
        n.close()
