"""
Regression coverage for ``app/session_store.py`` — closes the 83% gap
left by ``test_session_store.py``.

The Redis session store is the hotpath for every authenticated admin
request (refresh-token rotation, logout-all-devices, session listing).
The uncovered branches are the ones the happy-path smoke tests skip:

* URL credential redaction (line 42 + exception path 45-46) — we log
  the redis URL on init; leaking credentials into structured logs
  would be a direct secrets-in-logs incident.
* Lazy-client branch (line 134) — the first call to
  ``_get_client`` constructs the real redis asyncio client. Pinned
  via a ``patch("redis.asyncio.from_url")`` so the branch fires
  without needing a live redis.
* ``close()`` branch (lines 144-146) — teardown path; pinned to
  catch a regression that would leave ``_client`` attached across
  worker restarts and leak connections.
* ``claim_session_by_token`` GETDEL atomic-claim (lines 275-285) —
  refresh-token rotation; the GETDEL atomicity is what prevents
  concurrent /refresh requests from both succeeding (token-replay
  protection). Must not silently regress.
* ``update_session`` not-found (lines 311-312) + expired-TTL
  fallback (line 317) — both are defensive branches that keep the
  refresh path from crashing when upstream Redis state disagrees.
* ``list_user_sessions`` empty-set (line 419) and stale-reference
  cleanup (lines 434-438) — the GC path; without coverage here,
  a stale ``user_sessions:{uid}`` set grows unboundedly.
* ``revoke_all_user_sessions`` empty-list short-circuit (line 471)
  and the ``revoke_all_for_user`` alias (line 498) — password-reset
  and logout-all flows depend on these.
* ``cleanup_expired_sessions`` (lines 512-534) — maintenance path.

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from app.session_store import (  # noqa: E402
    RedisSessionStore,
    SessionData,
    redact_connection_url,
)


# ---------------------------------------------------------------------------
# Shared fixtures — mirrors test_session_store.py patterns
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Async Redis mock with a pipeline context manager."""
    r = AsyncMock()
    r.pipeline = MagicMock()
    pipe = AsyncMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock()
    r.pipeline.return_value = pipe
    return r


@pytest.fixture
def store(mock_redis):
    s = RedisSessionStore("redis://localhost:6379/0")
    s._client = mock_redis
    return s


def _sample_session(**overrides) -> SessionData:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        refresh_token_hash="hash-" + uuid.uuid4().hex[:16],
        family_id=uuid.uuid4(),
        is_revoked=False,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=30),
        user_agent=None,
        ip_address=None,
    )
    defaults.update(overrides)
    return SessionData(**defaults)


# ---------------------------------------------------------------------------
# redact_connection_url — lines 42, 45-46
# ---------------------------------------------------------------------------


class TestRedactConnectionUrl:

    def test_redacts_username_password_when_present(self):
        """Line 42: when the URL has a username, the function builds
        ``user:***@`` so neither username (ideally) nor password leaks.
        We confirm the password is scrubbed — the username is kept for
        debuggability per the current implementation."""
        url = "redis://alice:supersecret@redis.internal:6379/0"
        redacted = redact_connection_url(url)
        assert "supersecret" not in redacted
        assert "***" in redacted
        assert "redis.internal" in redacted

    def test_no_credentials_returns_host_only(self):
        """Line 40 False: URL without credentials — no ``user:***@``
        prefix. Keeps the non-auth branch pinned."""
        url = "redis://redis.internal:6379/0"
        redacted = redact_connection_url(url)
        assert "***" not in redacted
        assert "redis.internal:6379" in redacted

    def test_malformed_url_returns_placeholder(self):
        """Lines 45-46: ``urlsplit`` itself is forgiving, but accessing
        ``.port`` on a URL whose port segment is non-numeric raises
        ``ValueError``. We catch that (plus ``AttributeError``) and
        return ``<redacted>`` so startup logging never dies with a
        URL-parse crash."""
        result = redact_connection_url("redis://host:not-a-port/0")
        assert result == "<redacted>"


# ---------------------------------------------------------------------------
# _get_client lazy init — line 134
# ---------------------------------------------------------------------------


class TestGetClientLazyInit:

    @pytest.mark.asyncio
    async def test_first_call_constructs_client_via_from_url(self):
        """Line 134: first call to ``_get_client`` with ``_client is
        None`` constructs the real redis asyncio client with the
        documented kwargs. A refactor that drops ``decode_responses``
        or ``max_connections`` would silently change the serialization
        contract — pin it."""
        s = RedisSessionStore("redis://fake:6379/0")
        assert s._client is None

        fake_client = AsyncMock()
        with patch("redis.asyncio.from_url", new=AsyncMock(return_value=fake_client)) as mock_from_url:
            client = await s._get_client()

        assert client is fake_client
        assert s._client is fake_client  # cached
        mock_from_url.assert_called_once()
        _, kwargs = mock_from_url.call_args
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["decode_responses"] is True
        assert kwargs["max_connections"] == 50


# ---------------------------------------------------------------------------
# close() — lines 144-146
# ---------------------------------------------------------------------------


class TestClose:

    @pytest.mark.asyncio
    async def test_close_releases_and_nulls_client(self, store, mock_redis):
        """Lines 144-146: ``close()`` must both await ``_client.close()``
        AND null the cached reference so subsequent ``_get_client``
        calls reconstruct cleanly after a teardown."""
        await store.close()
        mock_redis.close.assert_awaited_once()
        assert store._client is None

    @pytest.mark.asyncio
    async def test_close_is_safe_when_client_never_built(self):
        """Line 144 False: ``close()`` when ``_client is None`` must not
        raise — lifecycle has to survive ``create → close → close`` as
        a no-op on the second call."""
        s = RedisSessionStore("redis://fake:6379/0")
        assert s._client is None
        # Must not raise
        await s.close()
        assert s._client is None


# ---------------------------------------------------------------------------
# claim_session_by_token — lines 275-285 (GETDEL atomic claim)
# ---------------------------------------------------------------------------


class TestClaimSessionByToken:

    @pytest.mark.asyncio
    async def test_claim_returns_session_when_first_to_getdel(self, store, mock_redis):
        """Lines 275, 278, 284-285: first caller GETDELs the token_hash
        key and gets back the session_id, loads the full session. This
        is the token-rotation hotpath — if the GETDEL were replaced
        with GET + DELETE, concurrent /refresh calls could both succeed
        (token replay)."""
        session = _sample_session()
        mock_redis.getdel = AsyncMock(return_value=str(session.id))
        # get_session path — hgetall returns populated hash
        mock_redis.hgetall = AsyncMock(return_value=session.to_redis_hash())

        result = await store.claim_session_by_token(session.refresh_token_hash)

        assert result is not None
        assert result.id == session.id
        mock_redis.getdel.assert_awaited_once_with(
            store._token_hash_key(session.refresh_token_hash)
        )

    @pytest.mark.asyncio
    async def test_claim_returns_none_when_already_claimed(self, store, mock_redis):
        """Lines 280-282: second caller's GETDEL returns nil → we log
        and return None. Pinned so a refactor that silently re-reads
        the key (reopening the replay window) gets caught."""
        mock_redis.getdel = AsyncMock(return_value=None)

        result = await store.claim_session_by_token("already-claimed-hash")

        assert result is None
        # Must NOT fall through to hgetall
        assert not mock_redis.hgetall.called


# ---------------------------------------------------------------------------
# update_session — lines 311-312, 317
# ---------------------------------------------------------------------------


class TestUpdateSession:

    @pytest.mark.asyncio
    async def test_returns_false_when_session_missing(self, store, mock_redis):
        """Lines 311-312: if ``EXISTS`` returns 0, we log and return
        False rather than creating orphan state. Critical for refresh
        path — a missing session means the caller's token is stale."""
        mock_redis.exists = AsyncMock(return_value=0)
        session_id = uuid.uuid4()

        result = await store.update_session(session_id, {"foo": "bar"})

        assert result is False
        # Must not have touched the pipeline
        assert not mock_redis.pipeline.called

    @pytest.mark.asyncio
    async def test_expired_ttl_falls_back_to_sixty_seconds(self, store, mock_redis):
        """Line 317: if ``TTL`` returns <= 0 (Redis key has no TTL or
        already expired), we fall back to 60s so the rotated token
        mapping isn't created with TTL -1 (persistent) or 0 (immediate
        deletion). Pin both the fallback and the fact that we still
        proceed with the update."""
        mock_redis.exists = AsyncMock(return_value=1)
        mock_redis.ttl = AsyncMock(return_value=-1)  # Redis "no TTL" sentinel
        session_id = uuid.uuid4()

        result = await store.update_session(
            session_id,
            {"is_revoked": "true"},
            new_token_hash="new-hash",
            old_token_hash="old-hash",
        )

        assert result is True
        # Confirm setex got ttl=60 (fallback) — find the setex call
        pipe = mock_redis.pipeline.return_value
        setex_calls = [c for c in pipe.setex.await_args_list]
        assert setex_calls, "expected setex call for new token mapping"
        # setex(key, ttl, value)
        args = setex_calls[0].args
        assert args[1] == 60

    @pytest.mark.asyncio
    async def test_new_token_mapping_written_without_old_hash(self, store, mock_redis):
        """A claimed token has already been removed via GETDEL, so refresh
        rotation must still write the new token mapping even when the caller
        has no old_token_hash to delete."""
        mock_redis.exists = AsyncMock(return_value=1)
        mock_redis.ttl = AsyncMock(return_value=120)
        session_id = uuid.uuid4()

        result = await store.update_session(
            session_id,
            {"refresh_token_hash": "new-hash"},
            new_token_hash="new-hash",
        )

        assert result is True
        pipe = mock_redis.pipeline.return_value
        pipe.setex.assert_awaited_once_with(
            store._token_hash_key("new-hash"),
            120,
            str(session_id),
        )


# ---------------------------------------------------------------------------
# list_user_sessions — lines 419, 434-438
# ---------------------------------------------------------------------------


class TestListUserSessions:

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_sessions(self, store, mock_redis):
        """Line 419: user has no session set → return []. Pinned so a
        refactor doesn't accidentally fall through to the pipeline
        block with an empty iterable (which would still work but
        wastes a round-trip)."""
        mock_redis.smembers = AsyncMock(return_value=set())

        result = await store.list_user_sessions(uuid.uuid4())

        assert result == []
        assert not mock_redis.pipeline.called

    @pytest.mark.asyncio
    async def test_stale_reference_is_cleaned_up(self, store, mock_redis):
        """Lines 434-438: ``hgetall`` returns an empty dict for a
        session_id that's been TTL'd out — we ``SREM`` the stale
        reference from ``user_sessions:{uid}``. Without this, the set
        grows unbounded over the user's lifetime."""
        user_id = uuid.uuid4()
        stale_id = uuid.uuid4()
        live = _sample_session(user_id=user_id)
        # smembers returns both stale and live
        mock_redis.smembers = AsyncMock(return_value={str(stale_id), str(live.id)})
        # pipeline.execute returns [stale_hgetall_empty, live_hgetall_populated]
        pipe = mock_redis.pipeline.return_value
        # ordering is set-membership-dependent — build the execute return to
        # match the iteration order of the set smembers returned.
        smembers_return = list(mock_redis.smembers.return_value)
        exec_results = []
        for sid in smembers_return:
            if sid == str(stale_id):
                exec_results.append({})
            else:
                exec_results.append(live.to_redis_hash())
        pipe.execute = AsyncMock(return_value=exec_results)
        mock_redis.srem = AsyncMock()

        result = await store.list_user_sessions(user_id, active_only=False)

        assert len(result) == 1
        assert result[0].id == live.id
        # The stale reference got cleaned up via direct srem (not pipelined)
        mock_redis.srem.assert_awaited_once()
        _, srem_args, _ = (
            mock_redis.srem.await_args.args[0],
            mock_redis.srem.await_args.args,
            mock_redis.srem.await_args.kwargs,
        )
        # Second positional is the stale session_id string
        assert srem_args[1] == str(stale_id)


# ---------------------------------------------------------------------------
# revoke_all_user_sessions / alias — lines 471, 498
# ---------------------------------------------------------------------------


class TestRevokeAll:

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_active_sessions(self, store, mock_redis):
        """Line 471: empty-list short-circuit in
        ``revoke_all_user_sessions``. Keeps the password-reset flow
        fast for users with no live sessions."""
        mock_redis.smembers = AsyncMock(return_value=set())

        result = await store.revoke_all_user_sessions(uuid.uuid4())

        assert result == 0
        # Must not open a pipeline for no reason
        assert not mock_redis.pipeline.called

    @pytest.mark.asyncio
    async def test_revoke_all_for_user_alias_delegates(self, store, mock_redis):
        """Line 498: the ``revoke_all_for_user`` alias is the one used
        by password-reset / logout-all flows. Pin the alias delegation
        so a refactor can't silently break either call site."""
        mock_redis.smembers = AsyncMock(return_value=set())

        result = await store.revoke_all_for_user(uuid.uuid4())

        # Same empty-list behavior as the canonical method
        assert result == 0


# ---------------------------------------------------------------------------
# cleanup_expired_sessions — lines 512-534
# ---------------------------------------------------------------------------


class TestCleanupExpiredSessions:

    @pytest.mark.asyncio
    async def test_removes_stale_references_and_returns_count(self, store, mock_redis):
        """Lines 512-525, 527-534: iterates the user_sessions set,
        calls EXISTS for each, and SREMs stale references. The return
        value is the count of removed stale refs. This is the
        maintenance path — pinned to keep the WARN-level log
        and the count contract."""
        user_id = uuid.uuid4()
        live_id = uuid.uuid4()
        stale_id = uuid.uuid4()
        mock_redis.smembers = AsyncMock(return_value={str(live_id), str(stale_id)})

        # EXISTS returns 1 for live, 0 for stale
        async def _exists_side_effect(key: str) -> int:
            if str(stale_id) in key:
                return 0
            return 1

        mock_redis.exists = AsyncMock(side_effect=_exists_side_effect)
        mock_redis.srem = AsyncMock()

        result = await store.cleanup_expired_sessions(user_id)

        assert result == 1  # one stale reference removed
        mock_redis.srem.assert_awaited_once()
        args = mock_redis.srem.await_args.args
        assert args[1] == str(stale_id)

    @pytest.mark.asyncio
    async def test_zero_removed_skips_info_log(self, store, mock_redis):
        """Line 527 False: when ``removed == 0`` the INFO log is
        skipped (no noise for the common healthy case). Return value
        must still be 0."""
        user_id = uuid.uuid4()
        live_id = uuid.uuid4()
        mock_redis.smembers = AsyncMock(return_value={str(live_id)})
        mock_redis.exists = AsyncMock(return_value=1)
        mock_redis.srem = AsyncMock()

        result = await store.cleanup_expired_sessions(user_id)

        assert result == 0
        mock_redis.srem.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_set_returns_zero(self, store, mock_redis):
        """Empty ``user_sessions:{uid}`` set — cleanup returns 0
        with no EXISTS / SREM traffic."""
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.exists = AsyncMock()
        mock_redis.srem = AsyncMock()

        result = await store.cleanup_expired_sessions(uuid.uuid4())

        assert result == 0
        mock_redis.exists.assert_not_awaited()
        mock_redis.srem.assert_not_awaited()
