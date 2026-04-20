"""Focused coverage for ``app/stripe_billing/state.py`` — #1342.

Companion to ``test_stripe_webhook_idempotency.py``, which exercises
``_mark_event_seen`` / ``_event_dedup_key`` end-to-end but does not
reach:

- ``_redis_client()``       — the raw ``redis.from_url`` wiring
  (tests elsewhere all monkeypatch ``_redis_client``).
- ``_buffer_pending_subscription_update`` (#1196 out-of-order buffer).
  Handler code paths buffer these but no existing test probes every
  branch of the ordering/TTL logic.
- ``_pop_pending_subscription_update`` — the ``GETDEL`` → pipeline
  fallback path and JSON-decode failure path.
- Edge cases for ``_buffer_pending_subscription_update`` write-write
  races and malformed existing-buffer recovery.

This file is narrow and deterministic: one in-memory Redis fake per
test, no network, no live ``get_settings`` beyond a direct unit test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
import redis

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.stripe_billing import state as state_mod  # noqa: E402


# ── Test double: in-memory Redis ────────────────────────────────────────────


class _FakeRedis:
    """Minimal in-memory Redis covering every call site in state.py.

    Methods wired:
    - ``set(key, value, nx=..., ex=...)`` with first-writer-wins NX
    - ``get(key)``
    - ``getdel(key)``
    - ``delete(key)``
    - ``hset(key, mapping=...)``
    - ``hgetall(key)``
    - ``pipeline()`` returning a fake pipeline with ``get``/``delete``/``execute``
    """

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []
        self.set_calls: list[tuple[str, str, dict[str, Any]]] = []

    def set(
        self,
        key: str,
        value: str,
        nx: bool = False,
        ex: Optional[int] = None,
    ) -> Any:
        self.set_calls.append((key, value, {"nx": nx, "ex": ex}))
        if nx and key in self.values:
            return None
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def get(self, key: str) -> Optional[str]:
        return self.values.get(key)

    def getdel(self, key: str) -> Optional[str]:
        return self.values.pop(key, None)

    def delete(self, key: str) -> int:
        self.deleted.append(key)
        existed = key in self.values
        self.values.pop(key, None)
        self.hashes.pop(key, None)
        return 1 if existed else 0

    def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.hashes.setdefault(key, {}).update(mapping)

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    def pipeline(self) -> "_FakePipeline":
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, parent: _FakeRedis) -> None:
        self._parent = parent
        self._ops: list[tuple[str, str]] = []

    def get(self, key: str) -> "_FakePipeline":
        self._ops.append(("get", key))
        return self

    def delete(self, key: str) -> "_FakePipeline":
        self._ops.append(("delete", key))
        return self

    def execute(self) -> list[Any]:
        results: list[Any] = []
        for op, key in self._ops:
            if op == "get":
                results.append(self._parent.values.get(key))
            elif op == "delete":
                existed = key in self._parent.values
                self._parent.values.pop(key, None)
                results.append(1 if existed else 0)
        return results


@pytest.fixture()
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)
    return fake


# ── _redis_client(): the one path the other tests monkeypatch past ─────────


class TestRedisClient:
    """_redis_client itself builds the connection; other tests stub it.

    Verified contract (#1076 / #1196 depend on this wiring):
    - reads ``redis_url`` from settings
    - passes ``decode_responses=True`` so all other helpers can treat
      values as ``str`` rather than ``bytes``
    """

    def test_calls_redis_from_url_with_decoded_responses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        fake_settings = MagicMock()
        fake_settings.redis_url = "redis://unit-test:6379/0"

        def _fake_get_settings() -> Any:
            return fake_settings

        def _fake_from_url(url: str, **kwargs: Any) -> Any:
            captured["url"] = url
            captured["kwargs"] = kwargs
            return MagicMock(name="fake-redis-conn")

        monkeypatch.setattr(state_mod, "get_settings", _fake_get_settings)
        monkeypatch.setattr(state_mod.redis, "from_url", _fake_from_url)

        client = state_mod._redis_client()
        assert client is not None
        assert captured["url"] == "redis://unit-test:6379/0"
        # decode_responses MUST be True; otherwise ``client.get()`` returns
        # bytes and string comparisons / JSON decoding downstream break.
        assert captured["kwargs"].get("decode_responses") is True


# ── _buffer_pending_subscription_update (#1196) ────────────────────────────


class TestBufferPendingSubscriptionUpdate:
    """#1196: buffer late-arriving subscription updates until the
    ``checkout.session.completed`` event creates the tenant mapping."""

    def _payload(self, **overrides: Any) -> dict[str, Any]:
        base = {
            "event_created": 1_700_000_000,
            "status": "active",
            "current_period_end": 1_800_000_000,
        }
        base.update(overrides)
        return base

    def test_missing_subscription_id_returns_false_without_write(
        self, fake_redis: _FakeRedis
    ) -> None:
        result = state_mod._buffer_pending_subscription_update(
            "",
            self._payload(),
        )
        assert result is False
        # No write, not even a set_calls entry — the guard short-circuits
        # BEFORE touching Redis.
        assert fake_redis.set_calls == []

    def test_first_update_writes_payload_with_ttl(
        self, fake_redis: _FakeRedis
    ) -> None:
        result = state_mod._buffer_pending_subscription_update(
            "sub_fresh",
            self._payload(),
        )
        assert result is True

        key = "billing:pending_sub_update:sub_fresh"
        raw = fake_redis.values[key]
        decoded = json.loads(raw)
        assert decoded["status"] == "active"
        # TTL must match the module constant — 72h, covering Stripe's
        # ~3 day retry window.
        assert fake_redis.ttls[key] == state_mod._PENDING_SUB_UPDATE_TTL_SECONDS

    def test_newer_event_overwrites_buffered_older(
        self, fake_redis: _FakeRedis
    ) -> None:
        state_mod._buffer_pending_subscription_update(
            "sub_1",
            self._payload(event_created=100, status="past_due"),
        )
        result = state_mod._buffer_pending_subscription_update(
            "sub_1",
            self._payload(event_created=200, status="active"),
        )
        assert result is True

        decoded = json.loads(fake_redis.values["billing:pending_sub_update:sub_1"])
        # The newer status wins.
        assert decoded["status"] == "active"
        assert decoded["event_created"] == 200

    def test_older_event_is_ignored_when_newer_already_buffered(
        self, fake_redis: _FakeRedis
    ) -> None:
        state_mod._buffer_pending_subscription_update(
            "sub_1",
            self._payload(event_created=500, status="active"),
        )
        result = state_mod._buffer_pending_subscription_update(
            "sub_1",
            self._payload(event_created=100, status="past_due"),
        )
        # Returns False — we discarded the older one.
        assert result is False

        decoded = json.loads(fake_redis.values["billing:pending_sub_update:sub_1"])
        assert decoded["status"] == "active"
        assert decoded["event_created"] == 500

    def test_equal_timestamp_overwrites(self, fake_redis: _FakeRedis) -> None:
        """Equal timestamps fall into the ``>`` comparison: existing is NOT
        strictly greater, so the new payload is written. This keeps the
        handler's last-write-wins semantics for ties (documented since
        Stripe ``event.created`` is second-granular and ties are possible)."""
        state_mod._buffer_pending_subscription_update(
            "sub_tie",
            self._payload(event_created=100, status="old"),
        )
        result = state_mod._buffer_pending_subscription_update(
            "sub_tie",
            self._payload(event_created=100, status="new"),
        )
        assert result is True
        decoded = json.loads(fake_redis.values["billing:pending_sub_update:sub_tie"])
        assert decoded["status"] == "new"

    def test_event_created_zero_is_treated_as_zero(
        self, fake_redis: _FakeRedis
    ) -> None:
        """Missing ``event_created`` coerces to 0 (defensive). A later
        non-zero timestamp must overwrite."""
        state_mod._buffer_pending_subscription_update(
            "sub_zero",
            {"status": "queued"},  # no event_created key
        )
        # Re-issuing with a concrete timestamp wins because 0 < 1.
        result = state_mod._buffer_pending_subscription_update(
            "sub_zero",
            self._payload(event_created=1, status="active"),
        )
        assert result is True
        decoded = json.loads(fake_redis.values["billing:pending_sub_update:sub_zero"])
        assert decoded["status"] == "active"

    def test_corrupt_existing_buffer_is_treated_as_zero(
        self, fake_redis: _FakeRedis
    ) -> None:
        """If the existing buffered value is not valid JSON (external
        mutation / bad deploy), we treat its event_created as 0 and
        overwrite. Prevents a permanent poison-pill buffer."""
        key = "billing:pending_sub_update:sub_corrupt"
        fake_redis.values[key] = "not-json{"
        result = state_mod._buffer_pending_subscription_update(
            "sub_corrupt",
            self._payload(event_created=100, status="active"),
        )
        assert result is True
        decoded = json.loads(fake_redis.values[key])
        assert decoded["status"] == "active"

    def test_non_integer_event_created_in_existing_buffer_falls_back(
        self, fake_redis: _FakeRedis
    ) -> None:
        """If the existing buffer has ``event_created`` as a non-integer
        string, ``int(...)`` raises ValueError — we treat as 0."""
        key = "billing:pending_sub_update:sub_nonint"
        fake_redis.values[key] = json.dumps(
            {"event_created": "not-an-int", "status": "old"}
        )
        result = state_mod._buffer_pending_subscription_update(
            "sub_nonint",
            self._payload(event_created=50, status="new"),
        )
        assert result is True
        decoded = json.loads(fake_redis.values[key])
        assert decoded["status"] == "new"

    def test_redis_error_on_get_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Boom:
            def get(self, *a: Any, **k: Any) -> Any:
                raise redis.RedisError("nope")

            def set(self, *a: Any, **k: Any) -> Any:  # pragma: no cover - defense
                return True

        monkeypatch.setattr(state_mod, "_redis_client", lambda: _Boom())
        result = state_mod._buffer_pending_subscription_update(
            "sub_err", {"event_created": 1}
        )
        # Fail-open: return False so the caller knows the buffer was NOT
        # safely written — but don't raise.
        assert result is False

    def test_redis_error_on_set_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _BoomOnSet:
            def get(self, *a: Any, **k: Any) -> Optional[str]:
                return None

            def set(self, *a: Any, **k: Any) -> Any:
                raise redis.RedisError("write refused")

        monkeypatch.setattr(state_mod, "_redis_client", lambda: _BoomOnSet())
        result = state_mod._buffer_pending_subscription_update(
            "sub_write_err", {"event_created": 1}
        )
        assert result is False

    def test_payload_serialization_is_compact(
        self, fake_redis: _FakeRedis
    ) -> None:
        """JSON uses ``(",", ":")`` separators to save Redis memory. Verify
        the stored value has no extraneous whitespace."""
        state_mod._buffer_pending_subscription_update(
            "sub_compact",
            {"event_created": 1, "a": 1, "b": 2},
        )
        raw = fake_redis.values["billing:pending_sub_update:sub_compact"]
        assert ", " not in raw
        assert ": " not in raw


# ── _pop_pending_subscription_update ───────────────────────────────────────


class TestPopPendingSubscriptionUpdate:
    """#1196 drain side: atomic fetch-and-delete of the buffered payload."""

    def test_missing_subscription_id_returns_none(
        self, fake_redis: _FakeRedis
    ) -> None:
        # Empty sub_id short-circuits before any Redis call.
        assert state_mod._pop_pending_subscription_update("") is None
        assert fake_redis.deleted == []

    def test_no_buffered_entry_returns_none(self, fake_redis: _FakeRedis) -> None:
        assert state_mod._pop_pending_subscription_update("sub_never") is None

    def test_happy_path_returns_and_deletes(self, fake_redis: _FakeRedis) -> None:
        state_mod._buffer_pending_subscription_update(
            "sub_1", {"event_created": 1, "status": "active"}
        )
        popped = state_mod._pop_pending_subscription_update("sub_1")
        assert popped is not None
        assert popped["status"] == "active"
        # The second pop returns None (value was atomically deleted).
        assert state_mod._pop_pending_subscription_update("sub_1") is None

    def test_pipeline_fallback_when_getdel_is_missing(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        """Older redis-py versions don't expose ``getdel``. Cover the
        fallback path that builds a pipeline and executes GET+DELETE."""
        state_mod._buffer_pending_subscription_update(
            "sub_pipe", {"event_created": 1, "status": "active"}
        )

        # Swap the getdel method with one that raises AttributeError —
        # this is exactly what happens on older redis-py.
        def _no_getdel(*a: Any, **k: Any) -> Any:
            raise AttributeError("no getdel on old redis-py")

        fake_redis.getdel = _no_getdel  # type: ignore[assignment]

        popped = state_mod._pop_pending_subscription_update("sub_pipe")
        assert popped is not None
        assert popped["status"] == "active"
        # The pipeline fallback DELETEd the key.
        assert "billing:pending_sub_update:sub_pipe" not in fake_redis.values

    def test_pipeline_fallback_when_getdel_raises_response_error(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        """Redis servers older than 6.2 answer GETDEL with ERR unknown
        command — redis-py surfaces that as ``redis.ResponseError``.
        Same recovery path as the AttributeError case above."""
        state_mod._buffer_pending_subscription_update(
            "sub_old_server", {"event_created": 1, "status": "past_due"}
        )

        def _response_err(*a: Any, **k: Any) -> Any:
            raise redis.ResponseError("ERR unknown command 'GETDEL'")

        fake_redis.getdel = _response_err  # type: ignore[assignment]

        popped = state_mod._pop_pending_subscription_update("sub_old_server")
        assert popped is not None
        assert popped["status"] == "past_due"
        assert "billing:pending_sub_update:sub_old_server" not in fake_redis.values

    def test_pipeline_fallback_with_empty_results_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the pipeline returns an empty list (defensive — real redis-py
        always returns one element per queued op), we should not crash and
        should return None."""

        class _OddRedis:
            def getdel(self, *a: Any, **k: Any) -> Any:
                raise AttributeError("forced fallback")

            def pipeline(self) -> Any:
                class _EmptyPipe:
                    def get(self, *a: Any, **k: Any) -> Any:
                        return self

                    def delete(self, *a: Any, **k: Any) -> Any:
                        return self

                    def execute(self) -> list[Any]:
                        return []

                return _EmptyPipe()

        monkeypatch.setattr(state_mod, "_redis_client", lambda: _OddRedis())
        assert state_mod._pop_pending_subscription_update("sub_empty") is None

    def test_redis_error_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Boom:
            def getdel(self, *a: Any, **k: Any) -> Any:
                raise redis.RedisError("conn dropped")

        monkeypatch.setattr(state_mod, "_redis_client", lambda: _Boom())
        assert state_mod._pop_pending_subscription_update("sub_boom") is None

    def test_corrupt_json_returns_none(
        self, fake_redis: _FakeRedis
    ) -> None:
        """If the buffered value is not decodeable JSON, we log and
        return None — do NOT crash and do NOT leak the raw string."""
        fake_redis.values["billing:pending_sub_update:sub_bad"] = "<<<not json>>>"
        assert state_mod._pop_pending_subscription_update("sub_bad") is None

    def test_pipeline_fallback_corrupt_json_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        """Same poison-pill defense, but reached via the pipeline
        fallback path."""
        fake_redis.values["billing:pending_sub_update:sub_bad_old"] = "garbage"

        def _no_getdel(*a: Any, **k: Any) -> Any:
            raise AttributeError("force pipeline path")

        fake_redis.getdel = _no_getdel  # type: ignore[assignment]

        assert state_mod._pop_pending_subscription_update("sub_bad_old") is None


# ── _clear_customer_lookup / _clear_subscription_lookup smoke ───────────────
#
# These are already covered at 100% by the companion suites; the tests
# below lock in the "empty id is a no-op" branches since those are the
# first line of the functions and could regress silently.


class TestClearLookupNoops:
    def test_clear_customer_lookup_empty_id_is_noop(
        self, fake_redis: _FakeRedis
    ) -> None:
        state_mod._clear_customer_lookup("")
        assert fake_redis.deleted == []

    def test_clear_subscription_lookup_empty_id_is_noop(
        self, fake_redis: _FakeRedis
    ) -> None:
        state_mod._clear_subscription_lookup("")
        assert fake_redis.deleted == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
