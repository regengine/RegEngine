"""Regression tests for issue #1138 — FDA scraper HTTP retry/backoff.

Before the fix, all three FDA scrapers (``fda_recalls``, ``fda_warning_letters``,
``fda_import_alerts``) issued a single ``self.session.get(...)`` with no retry.
A transient 502/503 from openFDA or a slow TCP handshake aborted the whole
scrape; the next attempt happened on the next interval, often 30+ minutes later.
For Class I recalls that's a real 24-hour-window compliance delay.

These tests exercise ``fetch_with_retry``:

1. 5xx responses are retried; a 200 after retries succeeds.
2. Transport errors (timeout, connect) are retried.
3. 4xx responses pass through without retry.
4. Exhausting all attempts re-raises.
5. ``Retry-After`` header is honored — we don't sleep less than the server asked.
6. 4xx / 5xx distinction: a 500 → 200 sequence is exactly 2 requests.
"""
from __future__ import annotations

from typing import List, Optional

import httpx
import pytest

from app.scrapers.base import (
    _compute_backoff,
    _parse_retry_after,
    fetch_with_retry,
)


# ---------------------------------------------------------------------------
# Test transport: scripted responses + observable attempt count.
# ---------------------------------------------------------------------------


class _ScriptedTransport(httpx.BaseTransport):
    """Returns a predefined sequence of (response_or_exception) to each
    GET request, in order. Test asserts on both the outcome and on how
    many attempts actually ran."""

    def __init__(self, script: List):
        # Each entry is either a tuple (status_code, headers_dict) or an
        # exception to raise when the transport is invoked.
        self._script = list(script)
        self.attempts = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.attempts += 1
        if not self._script:
            raise AssertionError("scripted transport exhausted but another request arrived")
        entry = self._script.pop(0)
        if isinstance(entry, BaseException):
            raise entry
        status_code, headers = entry
        return httpx.Response(
            status_code=status_code,
            headers=headers or {},
            content=b'{"ok": true}',
            request=request,
        )


def _client(script) -> tuple[httpx.Client, _ScriptedTransport]:
    transport = _ScriptedTransport(script)
    client = httpx.Client(transport=transport, base_url="https://example.test")
    return client, transport


class _SleepRecorder:
    """Captures calls to sleep so tests can assert on delay magnitudes
    without actually waiting."""

    def __init__(self):
        self.calls: List[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


# ---------------------------------------------------------------------------
# Retry-After header parser
# ---------------------------------------------------------------------------


class TestRetryAfterParser_Issue1138:
    def test_integer_seconds(self):
        assert _parse_retry_after("7") == 7.0

    def test_float_seconds(self):
        assert _parse_retry_after("2.5") == 2.5

    def test_whitespace_trimmed(self):
        assert _parse_retry_after("  5 ") == 5.0

    def test_missing_header_returns_none(self):
        assert _parse_retry_after(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_retry_after("") is None

    def test_negative_rejected(self):
        assert _parse_retry_after("-5") is None

    def test_http_date_unsupported_returns_none(self):
        # RFC 7231 also allows HTTP-date. We don't parse that form —
        # fall back to computed backoff.
        assert _parse_retry_after("Fri, 31 Dec 1999 23:59:59 GMT") is None

    def test_capped_at_maximum(self):
        # Obnoxiously large server values get capped so a misbehaving
        # upstream can't stall the scraper for an hour.
        assert _parse_retry_after("99999") == 60.0


# ---------------------------------------------------------------------------
# fetch_with_retry: 5xx retry + success
# ---------------------------------------------------------------------------


class Test5xxRetry_Issue1138:
    def test_500_then_200_succeeds_after_one_retry(self):
        client, transport = _client([
            (500, {}),
            (200, {}),
        ])
        sleeper = _SleepRecorder()

        resp = fetch_with_retry(
            client, "/test",
            sleep=sleeper,
            base_delay_seconds=0.01,
        )

        assert resp.status_code == 200
        assert transport.attempts == 2
        assert len(sleeper.calls) == 1

    def test_503_twice_then_200_succeeds_after_two_retries(self):
        client, transport = _client([
            (503, {}),
            (503, {}),
            (200, {}),
        ])
        sleeper = _SleepRecorder()

        resp = fetch_with_retry(
            client, "/test",
            sleep=sleeper,
            base_delay_seconds=0.01,
        )

        assert resp.status_code == 200
        assert transport.attempts == 3
        assert len(sleeper.calls) == 2

    def test_502_502_502_exhausts_and_raises(self):
        client, transport = _client([
            (502, {}),
            (502, {}),
            (502, {}),
        ])
        sleeper = _SleepRecorder()

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            fetch_with_retry(
                client, "/test",
                sleep=sleeper,
                base_delay_seconds=0.01,
            )

        assert exc_info.value.response.status_code == 502
        assert transport.attempts == 3
        # Final attempt doesn't sleep after it — only between attempts.
        assert len(sleeper.calls) == 2


# ---------------------------------------------------------------------------
# Transport errors (timeouts, connect)
# ---------------------------------------------------------------------------


class TestTransportErrorRetry_Issue1138:
    def test_read_timeout_then_200_retries_and_succeeds(self):
        req = httpx.Request("GET", "https://example.test/test")
        client, transport = _client([
            httpx.ReadTimeout("read timed out", request=req),
            (200, {}),
        ])
        sleeper = _SleepRecorder()

        resp = fetch_with_retry(
            client, "/test",
            sleep=sleeper,
            base_delay_seconds=0.01,
        )

        assert resp.status_code == 200
        assert transport.attempts == 2

    def test_connect_error_exhausts_and_raises(self):
        req = httpx.Request("GET", "https://example.test/test")
        client, transport = _client([
            httpx.ConnectError("boom", request=req),
            httpx.ConnectError("boom", request=req),
            httpx.ConnectError("boom", request=req),
        ])
        sleeper = _SleepRecorder()

        with pytest.raises(httpx.ConnectError):
            fetch_with_retry(
                client, "/test",
                sleep=sleeper,
                base_delay_seconds=0.01,
            )

        assert transport.attempts == 3
        assert len(sleeper.calls) == 2


# ---------------------------------------------------------------------------
# 4xx pass-through: 404 etc. are NOT retried.
# ---------------------------------------------------------------------------


class Test4xxNotRetried_Issue1138:
    def test_404_returns_immediately_without_retry(self):
        client, transport = _client([(404, {})])
        sleeper = _SleepRecorder()

        resp = fetch_with_retry(
            client, "/test",
            sleep=sleeper,
            base_delay_seconds=0.01,
        )

        assert resp.status_code == 404
        assert transport.attempts == 1
        assert sleeper.calls == []

    def test_400_passthrough_when_allowed(self):
        client, transport = _client([(400, {})])
        sleeper = _SleepRecorder()

        resp = fetch_with_retry(
            client, "/test",
            sleep=sleeper,
            allow_404_passthrough=True,
            base_delay_seconds=0.01,
        )

        assert resp.status_code == 400
        assert transport.attempts == 1

    def test_400_raises_when_passthrough_disabled(self):
        client, transport = _client([(400, {})])
        sleeper = _SleepRecorder()

        with pytest.raises(httpx.HTTPStatusError):
            fetch_with_retry(
                client, "/test",
                sleep=sleeper,
                allow_404_passthrough=False,
                base_delay_seconds=0.01,
            )

        assert transport.attempts == 1


# ---------------------------------------------------------------------------
# Retry-After header honoring
# ---------------------------------------------------------------------------


class TestRetryAfterHonored_Issue1138:
    def test_retry_after_larger_than_backoff_wins(self):
        # Server says "wait 5s" — we must sleep >= 5s even though our
        # computed backoff at attempt 1 is up to 1s.
        client, transport = _client([
            (503, {"Retry-After": "5"}),
            (200, {}),
        ])
        sleeper = _SleepRecorder()

        resp = fetch_with_retry(
            client, "/test",
            sleep=sleeper,
            base_delay_seconds=1.0,
            max_delay_seconds=1.0,
        )

        assert resp.status_code == 200
        assert len(sleeper.calls) == 1
        assert sleeper.calls[0] >= 5.0

    def test_retry_after_ignored_if_missing(self):
        client, transport = _client([
            (503, {}),
            (200, {}),
        ])
        sleeper = _SleepRecorder()

        fetch_with_retry(
            client, "/test",
            sleep=sleeper,
            base_delay_seconds=0.01,
            max_delay_seconds=0.01,
        )

        assert len(sleeper.calls) == 1
        # With no header, delay comes from computed backoff only — small.
        assert sleeper.calls[0] <= 0.02


# ---------------------------------------------------------------------------
# Backoff math
# ---------------------------------------------------------------------------


class TestBackoffMath_Issue1138:
    def test_attempt_1_caps_at_base(self):
        # Seed RNG for determinism — _compute_backoff uses random.uniform.
        import random
        random.seed(42)
        # attempt=1 → cap = min(max_delay, base * 2^0) = min(10, 1) = 1.
        delay = _compute_backoff(1, base=1.0, max_delay=10.0)
        assert 0.0 <= delay <= 1.0

    def test_attempt_3_caps_at_max(self):
        # attempt=3 → base * 2^2 = 4; under max_delay 10, so cap = 4.
        delays = [_compute_backoff(3, base=1.0, max_delay=10.0) for _ in range(100)]
        assert all(0.0 <= d <= 4.0 for d in delays)

    def test_attempt_10_clamped_by_max(self):
        # 2^9 = 512, but max_delay=10 so cap stays at 10.
        delays = [_compute_backoff(10, base=1.0, max_delay=10.0) for _ in range(100)]
        assert all(0.0 <= d <= 10.0 for d in delays)


# ---------------------------------------------------------------------------
# Regression: full flow from FDA recalls scraper (end-to-end).
# ---------------------------------------------------------------------------


class TestFDARecallsScraperE2E_Issue1138:
    """Exercise FDARecallsScraper with a 503-then-200 transport and
    verify the scrape succeeds after retry."""

    def test_scraper_survives_single_503(self, monkeypatch):
        from app.scrapers.fda_recalls import FDARecallsScraper

        scraper = FDARecallsScraper(limit=5)
        # Replace the httpx client with a scripted one.
        transport = _ScriptedTransport([
            (503, {"Retry-After": "0"}),  # server says don't wait, just retry
            (200, {}),
        ])
        scraper.session.close()
        scraper.session = httpx.Client(transport=transport)
        scraper.session.headers.update({
            "User-Agent": "RegEngine/1.0",
            "Accept": "application/json",
        })

        # Monkeypatch sleep inside base module so the test doesn't
        # actually wait. The scraper calls fetch_with_retry without an
        # explicit sleep kwarg, so it uses the default time.sleep.
        monkeypatch.setattr(
            "app.scrapers.base.time.sleep",
            lambda s: None,
        )

        result = scraper.scrape()
        assert result.success is True
        assert transport.attempts == 2
