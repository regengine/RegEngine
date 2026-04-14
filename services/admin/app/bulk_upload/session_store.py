from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import structlog
import redis.asyncio as redis


logger = structlog.get_logger("bulk_upload.session_store")


class BulkUploadSessionStore:
    def __init__(self, redis_url: str | None = None, ttl_seconds: int = 3600):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "rediss://redis:6379/0")
        self.ttl_seconds = ttl_seconds
        self._client: redis.Redis | None = None
        self._redis_available: bool | None = None
        # In-memory fallback — ephemeral upload session data. Redis is primary store when available.
        self._memory_store: dict[str, tuple[float, dict[str, Any]]] = {}

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


session_store = BulkUploadSessionStore()
