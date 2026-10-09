"""Regression tests for the in-memory fallback of ``BulkUploadSessionStore``.

The audit found the fallback kept a lock entry per session ever seen
(``_memory_locks`` was never pruned) and let a session that was touched
often live forever (``update_session`` refreshed the sliding TTL with no
upper bound). Each test below fails on the pre-fix implementation:

- lock map assertions fail because expired sessions left their locks
  behind;
- the lifetime-cap assertions fail because every update pushed the expiry
  a full TTL into the future.
"""

from __future__ import annotations

import types

import app.bulk_upload.session_store as store_module
import pytest
from app.bulk_upload.session_store import BulkUploadSessionStore


class _Clock:
    """Manually advanced clock standing in for ``time.time``."""

    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def store(monkeypatch) -> BulkUploadSessionStore:
    """Store forced onto the in-memory fallback with a controllable clock."""
    clock = _Clock()
    monkeypatch.setattr(store_module, "time", types.SimpleNamespace(time=clock))
    s = BulkUploadSessionStore(ttl_seconds=100)
    s._redis_available = False  # type: ignore[attr-defined]
    s._clock = clock  # type: ignore[attr-defined]
    return s


async def test_memory_locks_pruned_when_sessions_expire(store: BulkUploadSessionStore):
    payloads = {"status": "validated"}
    ids = [await store.create_session("t1", "u1", dict(payloads)) for _ in range(3)]
    for session_id in ids:
        claimed = await store.try_claim_commit("t1", "u1", session_id)
        assert claimed is not None
    assert len(store._memory_locks) == 3

    # Move past the sliding TTL and touch the store so cleanup runs.
    store._clock.now += 101  # type: ignore[attr-defined]
    assert await store.get_session("t1", "u1", ids[0]) is None

    assert store._memory_store == {}
    assert store._memory_locks == {}
    assert store._memory_created_at == {}


async def test_memory_lock_held_during_claim_is_not_pruned(store: BulkUploadSessionStore):
    key = store._session_key("t1", "u1", "ghost")
    lock = store._memory_lock(key)
    await lock.acquire()
    try:
        store._cleanup_memory()
        # The held lock must survive: a concurrent claimant created its
        # waiter on this same object before cleanup ran.
        assert key in store._memory_locks
    finally:
        lock.release()

    store._cleanup_memory()
    assert key not in store._memory_locks


async def test_update_session_capped_by_absolute_lifetime(store: BulkUploadSessionStore):
    session_id = await store.create_session("t1", "u1", {"status": "validated"})
    key = store._session_key("t1", "u1", session_id)
    cap = 1_000_000.0 + 8 * 100

    # Touches every 90s keep refreshing the sliding TTL (which alone
    # would let the session live forever) ...
    now = 1_000_000.0
    for _ in range(8):
        now += 90
        store._clock.now = now  # type: ignore[attr-defined]
        await store.update_session("t1", "u1", session_id, {"status": "validated"})

    # ... but the expiry never passes the absolute cap.
    assert store._memory_store[key][0] == pytest.approx(cap)

    # Past the cap the session is gone despite continuous updates.
    store._clock.now = cap + 1  # type: ignore[attr-defined]
    assert await store.get_session("t1", "u1", session_id) is None
    assert store._memory_store == {}
