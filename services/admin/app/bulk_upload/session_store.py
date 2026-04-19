from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Any

import structlog
import redis.asyncio as redis
from redis.exceptions import WatchError


logger = structlog.get_logger("bulk_upload.session_store")


class BulkUploadSessionStore:
    def __init__(self, redis_url: str | None = None, ttl_seconds: int = 3600):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "rediss://redis:6379/0")
        self.ttl_seconds = ttl_seconds
        self._client: redis.Redis | None = None
        self._redis_available: bool | None = None
        # In-memory fallback — ephemeral upload session data. Redis is primary store when available.
        self._memory_store: dict[str, tuple[float, dict[str, Any]]] = {}
        # Per-key asyncio locks for the in-memory fallback. Only used by
        # ``try_claim_commit`` — simple ``get``/``update`` don't need
        # them because they're single-op. The map is never pruned by
        # hand (it grows O(sessions-seen)) but each entry is a tiny
        # Lock object and the process gets recycled periodically in
        # prod; don't bother with eviction.
        self._memory_locks: dict[str, asyncio.Lock] = {}

    async def _get_client(self) -> redis.Redis | None:
        if self._redis_available is False:
            return None
        if self._client is None:
            try:
                self._client = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=20,
                )
                await self._client.ping()
                self._redis_available = True
            except Exception as exc:  # pragma: no cover - environment specific
                logger.warning("bulk_upload_redis_unavailable", error=str(exc))
                self._redis_available = False
                self._client = None
        return self._client

    def _session_key(self, tenant_id: str, user_id: str, session_id: str) -> str:
        return f"bulk_upload:{tenant_id}:{user_id}:{session_id}"

    def _memory_lock(self, key: str) -> asyncio.Lock:
        lock = self._memory_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._memory_locks[key] = lock
        return lock

    def _cleanup_memory(self) -> None:
        now = time.time()
        expired = [key for key, (expiry, _value) in self._memory_store.items() if expiry <= now]
        for key in expired:
            self._memory_store.pop(key, None)

    async def create_session(self, tenant_id: str, user_id: str, payload: dict[str, Any]) -> str:
        session_id = str(uuid.uuid4())
        key = self._session_key(tenant_id, user_id, session_id)
        client = await self._get_client()
        if client is not None:
            await client.setex(key, self.ttl_seconds, json.dumps(payload))
            return session_id

        self._cleanup_memory()
        self._memory_store[key] = (time.time() + self.ttl_seconds, payload)
        return session_id

    async def get_session(self, tenant_id: str, user_id: str, session_id: str) -> dict[str, Any] | None:
        key = self._session_key(tenant_id, user_id, session_id)
        client = await self._get_client()
        if client is not None:
            raw_value = await client.get(key)
            if raw_value is None:
                return None
            return json.loads(raw_value)

        self._cleanup_memory()
        value = self._memory_store.get(key)
        if value is None:
            return None
        return value[1]

    async def update_session(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> None:
        key = self._session_key(tenant_id, user_id, session_id)
        client = await self._get_client()
        if client is not None:
            await client.setex(key, self.ttl_seconds, json.dumps(payload))
            return

        self._cleanup_memory()
        self._memory_store[key] = (time.time() + self.ttl_seconds, payload)

    async def try_claim_commit(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        *,
        from_status: str = "validated",
        to_status: str = "processing",
        mutations: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Atomically transition session status ``from_status → to_status``.

        Returns the updated payload on success, or ``None`` if the session
        is missing or its status doesn't match ``from_status`` (i.e. someone
        else claimed it first, or the session is in the wrong phase).

        This is a compare-and-swap operation. It replaces the non-atomic
        ``get → check → update`` pattern that let two concurrent commit
        requests both observe ``status=validated``, both pass the guard,
        and both call ``execute_bulk_commit`` — producing duplicate FSMA
        events and Merkle-hash divergence (issue #1074).

        On the Redis path the CAS is implemented with ``WATCH``/``MULTI``/
        ``EXEC``: if any other writer touches the key between our ``WATCH``
        and ``EXEC``, the transaction is aborted and we retry. On the
        in-memory fallback a per-session :class:`asyncio.Lock` serializes
        readers so only one claim proceeds.

        ``mutations`` (if provided) is merged into the payload as part of
        the same atomic write, so callers can set ``error=None``/
        ``updated_at=...`` in the same round trip that claims the status
        transition — preserving the current semantics of
        ``commit_bulk_upload`` without leaking the invariant.
        """
        key = self._session_key(tenant_id, user_id, session_id)
        client = await self._get_client()
        if client is not None:
            return await self._redis_try_claim(
                client=client,
                key=key,
                from_status=from_status,
                to_status=to_status,
                mutations=mutations,
            )
        return await self._memory_try_claim(
            key=key,
            from_status=from_status,
            to_status=to_status,
            mutations=mutations,
        )

    async def _redis_try_claim(
        self,
        *,
        client: redis.Redis,
        key: str,
        from_status: str,
        to_status: str,
        mutations: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        # Bound the retry count: if we're repeatedly losing the WATCH
        # race, something other than the intended two-client race is
        # happening (e.g. a rogue poller) and infinite-looping hides
        # the bug. 10 retries is generous for realistic traffic.
        max_retries = 10
        for _attempt in range(max_retries):
            async with client.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    if raw is None:
                        await pipe.unwatch()
                        return None
                    try:
                        data = json.loads(raw)
                    except (TypeError, ValueError):
                        # Corrupt session blob. Treat as unclaimable
                        # rather than raising — the endpoint will
                        # surface it as "wrong state" (400/409).
                        await pipe.unwatch()
                        return None
                    if not isinstance(data, dict) or data.get("status") != from_status:
                        await pipe.unwatch()
                        return None

                    data["status"] = to_status
                    if mutations:
                        data.update(mutations)

                    pipe.multi()
                    pipe.setex(key, self.ttl_seconds, json.dumps(data))
                    await pipe.execute()
                    return data
                except WatchError:
                    # Someone wrote to the key between our WATCH and
                    # EXEC — retry, re-read the current state, and
                    # re-evaluate the from_status guard.
                    continue
        logger.warning(
            "bulk_upload_try_claim_exhausted_retries",
            key=key,
            from_status=from_status,
            to_status=to_status,
        )
        return None

    async def _memory_try_claim(
        self,
        *,
        key: str,
        from_status: str,
        to_status: str,
        mutations: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        async with self._memory_lock(key):
            self._cleanup_memory()
            entry = self._memory_store.get(key)
            if entry is None:
                return None
            expiry, payload = entry
            if not isinstance(payload, dict) or payload.get("status") != from_status:
                return None
            payload["status"] = to_status
            if mutations:
                payload.update(mutations)
            self._memory_store[key] = (expiry, payload)
            return payload


session_store = BulkUploadSessionStore()
