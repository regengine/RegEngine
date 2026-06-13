"""Regression test for the API-key usage write-throttle (#2449).

``validate_key`` used to do an ORM read-modify-write of
``last_used_at`` / ``total_requests`` on every authenticated request — a
per-request row write on the hot auth path, and a lost-update race on the
counter under concurrency.

``_record_key_usage`` replaces that: increments are buffered in-process and
flushed via a single atomic SQL UPDATE at most once per
``_USAGE_FLUSH_INTERVAL_SECONDS`` per key, so the count stays accurate (the
flush adds the buffered delta) while DB writes drop sharply. These tests pin:

* the first request for a key flushes immediately (sets last_used_at promptly)
* subsequent requests within the window buffer instead of writing
* the flush is a single atomic ``total_requests = total_requests + :delta``
  UPDATE carrying the accumulated delta — never an ORM read-modify-write
"""

from unittest.mock import patch

import pytest
from shared.api_key_store import DatabaseAPIKeyStore


def _make_store(monkeypatch) -> DatabaseAPIKeyStore:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:6543/d")
    with patch("shared.api_key_store.create_async_engine") as _e, patch("shared.api_key_store.sessionmaker") as _s:
        _e.return_value = object()
        _s.return_value = lambda: None
        return DatabaseAPIKeyStore()


class _RecordingSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params or {}))


@pytest.mark.asyncio
async def test_first_request_flushes_immediately(monkeypatch):
    store = _make_store(monkeypatch)
    session = _RecordingSession()

    await store._record_key_usage("key-abc", session)

    assert len(session.calls) == 1
    sql, params = session.calls[0]
    # Atomic increment, not a read-modify-write.
    assert "total_requests = COALESCE(total_requests, 0) + :delta" in sql
    assert params["delta"] == 1
    assert params["kid"] == "key-abc"


@pytest.mark.asyncio
async def test_requests_within_window_buffer_without_writing(monkeypatch):
    store = _make_store(monkeypatch)
    session = _RecordingSession()

    # Freeze monotonic time so all calls fall inside one flush window.
    with patch("shared.api_key_store.time.monotonic", return_value=1000.0):
        await store._record_key_usage("key-abc", session)  # flush (delta=1)
        await store._record_key_usage("key-abc", session)  # buffer
        await store._record_key_usage("key-abc", session)  # buffer

    # Only the first call wrote; the other two are buffered.
    assert len(session.calls) == 1
    assert store._pending_usage["key-abc"] == 2


@pytest.mark.asyncio
async def test_next_window_flushes_accumulated_delta(monkeypatch):
    store = _make_store(monkeypatch)
    session = _RecordingSession()

    with patch("shared.api_key_store.time.monotonic", return_value=1000.0):
        await store._record_key_usage("key-abc", session)  # flush delta=1
        await store._record_key_usage("key-abc", session)  # buffer (pending=2)

    # Advance past the flush interval — the accumulated delta must be written.
    later = 1000.0 + 60.0
    with patch("shared.api_key_store.time.monotonic", return_value=later):
        await store._record_key_usage("key-abc", session)

    assert len(session.calls) == 2
    _, params = session.calls[1]
    # 1 buffered (the second call) + 1 for this third call = delta of 2.
    # Across both flushes: 1 + 2 = 3, matching the three calls exactly.
    assert params["delta"] == 2
    assert "key-abc" not in store._pending_usage


@pytest.mark.asyncio
async def test_keys_are_throttled_independently(monkeypatch):
    store = _make_store(monkeypatch)
    session = _RecordingSession()

    with patch("shared.api_key_store.time.monotonic", return_value=500.0):
        await store._record_key_usage("key-a", session)
        await store._record_key_usage("key-b", session)

    # Each distinct key flushes on its own first request.
    assert len(session.calls) == 2
    assert {params["kid"] for _, params in session.calls} == {"key-a", "key-b"}
