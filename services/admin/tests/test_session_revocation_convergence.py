"""Logout-everywhere convergence: cleanups must not miss state minted mid-run.

A single list-then-act pass over sessions, or a single SCAN pass over the
elevation-jti keyspace, misses entries created concurrently with the cleanup,
so those credentials survive logout-everywhere. Both cleanups repeat in
bounded passes until a pass finds nothing left, and these tests pin that by
minting one entry mid-cleanup and asserting nothing usable remains.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from services.admin.app.auth.elevation_helpers import _revoke_all_elevation_tokens_for_user
from services.admin.app.session_store import InMemorySessionStore, SessionData


def _session(user_id, refresh_suffix: str) -> SessionData:
    now = datetime.now(timezone.utc)
    return SessionData(
        id=uuid.uuid4(),
        user_id=user_id,
        refresh_token_hash=f"hash-{refresh_suffix}",
        family_id=uuid.uuid4(),
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_revoke_all_user_sessions_catches_session_minted_mid_cleanup():
    store = InMemorySessionStore()
    user_id = uuid.uuid4()
    first = _session(user_id, "first")
    await store.create_session(first)

    # Simulate a concurrent login landing between the revoke's list and write.
    orig_list = store.list_user_sessions
    calls = 0

    async def listing(uid, active_only=True):
        nonlocal calls
        result = await orig_list(uid, active_only=active_only)
        calls += 1
        if calls == 1:
            await store.create_session(_session(user_id, "late"))
        return result

    store.list_user_sessions = listing  # type: ignore[method-assign]

    revoked = await store.revoke_all_user_sessions(user_id)

    assert revoked == 2
    assert await store.list_user_sessions(user_id, active_only=True) == []
    assert await store.claim_session_by_token("hash-first") is None
    assert await store.claim_session_by_token("hash-late") is None


@pytest.mark.asyncio
async def test_revoke_all_user_sessions_respects_except_session_id():
    store = InMemorySessionStore()
    user_id = uuid.uuid4()
    keep = _session(user_id, "keep")
    drop = _session(user_id, "drop")
    await store.create_session(keep)
    await store.create_session(drop)

    revoked = await store.revoke_all_user_sessions(user_id, except_session_id=keep.id)

    assert revoked == 1
    remaining = await store.list_user_sessions(user_id, active_only=True)
    assert [s.id for s in remaining] == [keep.id]


@pytest.mark.asyncio
async def test_elevation_cleanup_catches_token_minted_mid_cleanup():
    store = InMemorySessionStore()
    user_id = uuid.uuid4()
    other_id = uuid.uuid4()
    client = await store._get_client()
    await client.set("elevation_jti:seed", str(user_id), ex=300)
    await client.set("elevation_jti:other", str(other_id), ex=300)

    # Simulate a step-up mint landing after the cleanup's scan page is read.
    orig_scan = client.scan
    calls = 0

    async def scan_and_mint(*args, **kwargs):
        nonlocal calls
        result = await orig_scan(*args, **kwargs)
        calls += 1
        if calls == 1:
            await client.set("elevation_jti:late", str(user_id), ex=300)
        return result

    client.scan = scan_and_mint  # type: ignore[method-assign]

    revoked = await _revoke_all_elevation_tokens_for_user(store, user_id)

    assert revoked == 2
    assert await client.get("elevation_jti:seed") is None
    assert await client.get("elevation_jti:late") is None
    assert await client.get("elevation_jti:other") == str(other_id)
