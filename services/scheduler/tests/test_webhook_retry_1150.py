"""Regression tests for issue #1150 — scheduler webhook notification retry.

Before the fix, ``WebhookNotifier`` gave up after 3 attempts over ~3 seconds
(1s + 2s backoff) and appended to an IN-MEMORY dead-letter list that was
lost on restart. Customer webhook endpoints routinely have transient issues
(cold starts, deploys, rate limits) that last longer than 3 seconds — so
every such blip dropped a HIGH-severity alert permanently.

These tests cover:
  - Retry-After honored on 429 and 503
  - 429 IS retried (not treated as a permanent 4xx)
  - Longer in-thread backoff schedule (1s, 5s, 30s)
  - Persistent on-disk outbox roundtrip
  - ``retry_outbox_once()`` respects ``next_retry_at``
  - Successful retry removes entry from outbox
  - Exhausted entries park with a 30-day next_retry_at
  - Corrupt JSONL lines tolerated
  - Atomic outbox rewrite
  - Per-URL failure-streak counter increments + resets on success
"""

import json
import os
import sys
import time
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
import httpx  # noqa: E402

from app.models import EnforcementItem, EnforcementSeverity, SourceType  # noqa: E402
from app.notifications import (  # noqa: E402
    OutboxEntry,
    WebhookNotifier,
    _IN_THREAD_BACKOFF_SCHEDULE_SECONDS,
    _MAX_OUTBOX_ATTEMPTS,
    _OUTBOX_BACKOFF_SCHEDULE_SECONDS,
    _RETRY_AFTER_CAP_SECONDS,
    _parse_retry_after,
)


def _make_item(severity: EnforcementSeverity = EnforcementSeverity.HIGH) -> EnforcementItem:
    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id="recall-1150",
        title="Issue 1150 test recall",
        url="https://fda.gov/recalls/1150",
        published_date=datetime(2026, 4, 18, tzinfo=timezone.utc),
        severity=severity,
    )


def _make_response(status_code: int, headers: dict = None, text: str = "") -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.headers = headers or {}
    r.text = text
    return r


@pytest.fixture(autouse=True)
def _allow_mock_webhook_urls(monkeypatch):
    monkeypatch.setattr("app.notifications.validate_url", lambda _url: None)


# ── Retry-After header parsing ───────────────────────────────────────────────


class TestParseRetryAfter_Issue1150:
    def test_valid_integer_seconds(self):
        assert _parse_retry_after("30") == 30.0

    def test_valid_float_seconds(self):
        assert _parse_retry_after("2.5") == 2.5

    def test_none_returns_none(self):
        assert _parse_retry_after(None) is None

    def test_empty_returns_none(self):
        assert _parse_retry_after("") is None

    def test_http_date_format_returns_none(self):
        # RFC 7231 also allows HTTP-date; we don't support it and fall
        # back to the computed backoff.
        assert _parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None

    def test_negative_rejected(self):
        assert _parse_retry_after("-5") is None

    def test_capped_at_60s(self):
        # Misbehaving server sending huge values must not block the worker.
        assert _parse_retry_after("3600") == _RETRY_AFTER_CAP_SECONDS
        assert _parse_retry_after("999999") == _RETRY_AFTER_CAP_SECONDS

    def test_whitespace_tolerated(self):
        assert _parse_retry_after("  12 ") == 12.0


# ── In-thread retry: Retry-After on 503 / 429 ────────────────────────────────


class TestInThreadRetryAfter_Issue1150:
    @patch("app.notifications.time.sleep")
    def test_retry_after_honored_on_503(self, mock_sleep):
        """503 with Retry-After: 7 → second attempt sleeps for max(7, 1)=7."""
        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=2,
            max_workers=1,
        )
        fail = _make_response(503, headers={"Retry-After": "7"}, text="Service Unavailable")
        success = _make_response(200)
        with patch.object(n.session, "post", side_effect=[fail, success]):
            results = n.notify([_make_item()])
        assert results[0].success is True
        assert results[0].attempts == 2
        # First retry sleep should use the Retry-After value since 7 > 1 (base)
        mock_sleep.assert_called_with(7.0)
        n.close()

    @patch("app.notifications.time.sleep")
    def test_429_is_retried_with_retry_after(self, mock_sleep):
        """429 used to be treated as a non-retryable 4xx; now it IS retried
        with Retry-After honored."""
        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=3,
            max_workers=1,
        )
        rate_limited = _make_response(429, headers={"Retry-After": "2"}, text="Rate limit")
        success = _make_response(200)
        with patch.object(n.session, "post", side_effect=[rate_limited, success]) as mock_post:
            results = n.notify([_make_item()])
        assert results[0].success is True
        assert results[0].attempts == 2
        assert mock_post.call_count == 2
        n.close()

    @patch("app.notifications.time.sleep")
    def test_non_429_4xx_still_not_retried(self, mock_sleep):
        """400 and 404 remain non-retryable — those are real client bugs."""
        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=3,
            max_workers=1,
        )
        bad = _make_response(400, text="Bad Request")
        with patch.object(n.session, "post", return_value=bad) as mock_post:
            results = n.notify([_make_item()])
        assert results[0].success is False
        assert results[0].attempts == 1
        assert mock_post.call_count == 1
        n.close()

    @patch("app.notifications.time.sleep")
    def test_retry_after_capped_at_60s(self, mock_sleep):
        """Misbehaving server sending Retry-After: 99999 gets capped."""
        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=2,
            max_workers=1,
        )
        fail = _make_response(503, headers={"Retry-After": "99999"})
        success = _make_response(200)
        with patch.object(n.session, "post", side_effect=[fail, success]):
            n.notify([_make_item()])
        mock_sleep.assert_called_with(_RETRY_AFTER_CAP_SECONDS)
        n.close()

    @patch("app.notifications.time.sleep")
    def test_longer_backoff_schedule(self, mock_sleep):
        """Without Retry-After, the in-thread schedule is 1s / 5s / 30s."""
        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=3,
            max_workers=1,
        )
        fail = _make_response(500, text="Server error")
        success = _make_response(200)
        with patch.object(n.session, "post", side_effect=[fail, fail, success]):
            n.notify([_make_item()])
        # Two sleeps before the third (successful) attempt.
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [
            _IN_THREAD_BACKOFF_SCHEDULE_SECONDS[0],  # 1s after attempt 1
            _IN_THREAD_BACKOFF_SCHEDULE_SECONDS[1],  # 5s after attempt 2
        ]
        n.close()


# ── Persistent outbox ────────────────────────────────────────────────────────


class TestPersistentOutbox_Issue1150:
    @patch("app.notifications.time.sleep")
    def test_failed_delivery_writes_to_outbox(self, mock_sleep, tmp_path):
        outbox = tmp_path / "webhook_outbox.jsonl"
        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=2,
            max_workers=1,
            outbox_path=str(outbox),
        )
        fail = _make_response(500, text="boom")
        with patch.object(n.session, "post", return_value=fail):
            n.notify([_make_item()])
        n.close()

        assert outbox.exists()
        lines = outbox.read_text().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["url"] == "https://hook.example.com"
        assert entry["attempt_count"] == 0
        assert entry["last_status_code"] == 500
        assert "payload" in entry

    def test_outbox_entry_roundtrip(self):
        now = time.time()
        entry = OutboxEntry(
            url="https://hook.example.com",
            payload={"event_type": "test", "items": []},
            attempt_count=2,
            first_attempted_at=now - 100,
            last_attempted_at=now - 50,
            next_retry_at=now + 300,
            last_error="HTTP 503",
            last_status_code=503,
        )
        round_tripped = OutboxEntry.from_dict(entry.to_dict())
        assert round_tripped.url == entry.url
        assert round_tripped.attempt_count == 2
        assert round_tripped.last_status_code == 503
        assert round_tripped.last_error == "HTTP 503"

    def test_retry_outbox_once_with_no_outbox_is_noop(self, tmp_path):
        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=1,
            max_workers=1,
            outbox_path=None,  # not configured
        )
        counter = n.retry_outbox_once()
        assert counter == {"attempted": 0, "delivered": 0, "rescheduled": 0, "exhausted": 0}
        n.close()

    def test_retry_outbox_once_skips_not_yet_due(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        future_entry = OutboxEntry(
            url="https://hook.example.com",
            payload={"items": []},
            attempt_count=1,
            next_retry_at=time.time() + 1000,  # well in the future
        )
        outbox.write_text(json.dumps(future_entry.to_dict()) + "\n")

        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=1,
            max_workers=1,
            outbox_path=str(outbox),
        )
        with patch.object(n.session, "post") as mock_post:
            counter = n.retry_outbox_once()
        # Should not have attempted.
        assert mock_post.call_count == 0
        assert counter["attempted"] == 0
        # Entry still in the file.
        assert len(outbox.read_text().splitlines()) == 1
        n.close()

    def test_retry_outbox_once_success_removes_entry(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        due_entry = OutboxEntry(
            url="https://hook.example.com",
            payload={"items": []},
            attempt_count=1,
            next_retry_at=time.time() - 1,  # due now
        )
        outbox.write_text(json.dumps(due_entry.to_dict()) + "\n")

        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=1,
            max_workers=1,
            outbox_path=str(outbox),
        )
        success = _make_response(200)
        with patch.object(n.session, "post", return_value=success):
            counter = n.retry_outbox_once()
        assert counter["attempted"] == 1
        assert counter["delivered"] == 1
        # Outbox should now be empty.
        assert outbox.read_text().strip() == ""
        n.close()

    def test_retry_outbox_once_failure_reschedules(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        due_entry = OutboxEntry(
            url="https://hook.example.com",
            payload={"items": []},
            attempt_count=0,
            next_retry_at=time.time() - 1,
        )
        outbox.write_text(json.dumps(due_entry.to_dict()) + "\n")

        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=1,
            max_workers=1,
            outbox_path=str(outbox),
        )
        fail = _make_response(500)
        with patch.object(n.session, "post", return_value=fail):
            counter = n.retry_outbox_once()
        assert counter["attempted"] == 1
        assert counter["rescheduled"] == 1
        # Entry still in file, attempt_count bumped.
        lines = outbox.read_text().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["attempt_count"] == 1
        # next_retry_at should be ~60s in the future (first outbox backoff slot).
        assert parsed["next_retry_at"] > time.time()
        n.close()

    def test_retry_outbox_once_exhausts_after_max_attempts(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        # Entry that already used 4/5 attempts — next failure exhausts it.
        due_entry = OutboxEntry(
            url="https://hook.example.com",
            payload={"items": []},
            attempt_count=_MAX_OUTBOX_ATTEMPTS - 1,
            next_retry_at=time.time() - 1,
        )
        outbox.write_text(json.dumps(due_entry.to_dict()) + "\n")

        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=1,
            max_workers=1,
            outbox_path=str(outbox),
        )
        fail = _make_response(500)
        with patch.object(n.session, "post", return_value=fail):
            counter = n.retry_outbox_once()
        assert counter["attempted"] == 1
        assert counter["exhausted"] == 1
        # Entry still present for operator inspection.
        lines = outbox.read_text().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["attempt_count"] == _MAX_OUTBOX_ATTEMPTS
        # Next retry pushed ~30 days out.
        assert parsed["next_retry_at"] > time.time() + 29 * 24 * 60 * 60
        n.close()

    def test_retry_outbox_tolerates_corrupt_line(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        good = OutboxEntry(
            url="https://hook.example.com",
            payload={"items": []},
            attempt_count=0,
            next_retry_at=time.time() - 1,
        )
        outbox.write_text(
            json.dumps(good.to_dict()) + "\n"
            "{not valid json\n"
            "\n"  # empty line
        )

        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=1,
            max_workers=1,
            outbox_path=str(outbox),
        )
        success = _make_response(200)
        with patch.object(n.session, "post", return_value=success):
            counter = n.retry_outbox_once()
        # Good line was attempted and delivered; corrupt line was skipped.
        assert counter["attempted"] == 1
        assert counter["delivered"] == 1
        n.close()

    def test_atomic_rewrite_uses_tmp_then_rename(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        entries = [
            OutboxEntry(
                url=f"https://hook{i}.example.com",
                payload={"items": []},
                attempt_count=i,
                next_retry_at=time.time() + 1000,  # not due
            )
            for i in range(3)
        ]
        outbox.write_text(
            "\n".join(json.dumps(e.to_dict()) for e in entries) + "\n"
        )

        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=1,
            max_workers=1,
            outbox_path=str(outbox),
        )
        n.retry_outbox_once()  # nothing due — should rewrite with same entries
        n.close()

        # File still there, not .tmp.
        assert outbox.exists()
        assert not (tmp_path / "outbox.jsonl.tmp").exists()
        reparsed = [json.loads(line) for line in outbox.read_text().splitlines()]
        assert len(reparsed) == 3
        assert {e["url"] for e in reparsed} == {
            f"https://hook{i}.example.com" for i in range(3)
        }


# ── Per-URL failure-streak observability ─────────────────────────────────────


class TestFailureStreak_Issue1150:
    @patch("app.notifications.time.sleep")
    def test_streak_increments_on_consecutive_failures(self, mock_sleep):
        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=1,
            max_workers=1,
        )
        fail = _make_response(500)
        with patch.object(n.session, "post", return_value=fail):
            n.notify([_make_item()])
            n.notify([_make_item()])
            n.notify([_make_item()])
        streaks = n.get_failure_streaks()
        assert streaks["https://hook.example.com"] == 3
        n.close()

    @patch("app.notifications.time.sleep")
    def test_streak_resets_on_success(self, mock_sleep):
        n = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=1,
            max_workers=1,
        )
        fail = _make_response(500)
        success = _make_response(200)
        with patch.object(n.session, "post", side_effect=[fail, fail, success]):
            n.notify([_make_item()])
            n.notify([_make_item()])
            n.notify([_make_item()])
        streaks = n.get_failure_streaks()
        assert streaks["https://hook.example.com"] == 0
        n.close()

    def test_streaks_isolated_per_url(self):
        n = WebhookNotifier(
            urls=["https://hook1.example.com", "https://hook2.example.com"],
            max_retries=1,
            max_workers=2,
        )
        # hook1 fails, hook2 succeeds — streak only on hook1.
        def route(url, **kw):
            if "hook1" in url:
                return _make_response(500)
            return _make_response(200)
        with patch.object(n.session, "post", side_effect=lambda url, **kw: route(url, **kw)):
            n.notify([_make_item()])
        streaks = n.get_failure_streaks()
        assert streaks["https://hook1.example.com"] == 1
        assert streaks.get("https://hook2.example.com", 0) == 0
        n.close()


# ── Integration: scrape → fail → restart → outbox drain ──────────────────────


class TestOutboxSurvivesRestart_Issue1150:
    @patch("app.notifications.time.sleep")
    def test_fresh_notifier_picks_up_prior_outbox(self, mock_sleep, tmp_path):
        """End-to-end: a failed delivery from one WebhookNotifier instance
        is delivered on a subsequent ``retry_outbox_once()`` from a FRESH
        WebhookNotifier instance sharing the same outbox path."""
        outbox_path = tmp_path / "outbox.jsonl"

        # --- First notifier: delivery fails, writes to outbox. ---
        n1 = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=1,
            max_workers=1,
            outbox_path=str(outbox_path),
        )
        fail = _make_response(500, text="boom")
        with patch.object(n1.session, "post", return_value=fail):
            n1.notify([_make_item()])
        n1.close()
        assert outbox_path.exists()

        # --- Second notifier (simulating restart): drains outbox. ---
        # Rewrite entry's next_retry_at to be overdue.
        entries = [json.loads(ln) for ln in outbox_path.read_text().splitlines() if ln.strip()]
        assert len(entries) == 1
        entries[0]["next_retry_at"] = time.time() - 1
        outbox_path.write_text(json.dumps(entries[0]) + "\n")

        n2 = WebhookNotifier(
            urls=["https://hook.example.com"],
            max_retries=1,
            max_workers=1,
            outbox_path=str(outbox_path),
        )
        success = _make_response(200)
        with patch.object(n2.session, "post", return_value=success):
            counter = n2.retry_outbox_once()
        n2.close()

        assert counter["delivered"] == 1
        # Outbox now empty.
        assert outbox_path.read_text().strip() == ""
