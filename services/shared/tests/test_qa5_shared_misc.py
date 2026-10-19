"""QA5: miscellaneous shared-module fixes (infra layer).

Covers canonical_event, rate_limit, metrics_auth, error_handling,
kafka_auth, kafka_compat, kafka_consumer_base, jwt_key_registry,
secrets_manager, resilient_http, safe_http, idempotency, and
api_key_store unit-level behavior. No live DB, Redis, or network.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# --- canonical_event: integral float schema_version -------------------------


def _minimal_event() -> dict:
    from shared.canonical_event import CTEType, IngestionSource

    return dict(
        tenant_id=uuid4(),
        source_system=IngestionSource.WEBHOOK_API,
        event_type=CTEType.RECEIVING,
        event_timestamp="2026-04-20T12:00:00Z",
        traceability_lot_code="TLC-QA5",
        quantity=10.0,
        unit_of_measure="each",
    )


def test_schema_version_integral_float_accepted_as_v1() -> None:
    from shared.canonical_event import parse_traceability_event

    payload = _minimal_event()
    payload["schema_version"] = 1.0
    assert parse_traceability_event(payload).schema_version == 1


def test_schema_version_non_integral_float_rejected() -> None:
    from shared.canonical_event import parse_traceability_event

    payload = _minimal_event()
    payload["schema_version"] = 1.5
    with pytest.raises(Exception):
        parse_traceability_event(payload)


# --- rate_limit: corrupt counter and stale-count pruning --------------------


def _limiter(**kwargs):
    from shared.rate_limit import BruteForceLimiter

    kwargs.setdefault("namespace", "qa5")
    kwargs.setdefault("max_failures", 3)
    kwargs.setdefault("window_seconds", 60)
    use_memory = kwargs.get("redis_client", None) is None
    kwargs.setdefault("redis_client", None)
    limiter = BruteForceLimiter(**kwargs)
    if use_memory:
        limiter._redis = None
    return limiter


class _FakeRedis:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw
        self.deleted: list = []

    def get(self, _key):
        return self._raw

    def delete(self, key):
        self.deleted.append(key)


def test_corrupt_redis_counter_resets_key_and_stays_open_by_default() -> None:
    fake = _FakeRedis(b"garbage")
    limiter = _limiter(redis_client=fake)
    assert limiter.is_limited("attacker") is False
    assert fake.deleted == [limiter._key("attacker")]


def test_corrupt_redis_counter_denies_in_closed_mode(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")
    fake = _FakeRedis(b"garbage")
    limiter = _limiter(redis_client=fake)
    assert limiter.is_limited("attacker") is True


def test_record_failure_prunes_expired_entries_first() -> None:
    limiter = _limiter()
    stale = time.time() - 3600
    limiter._mem_failures["s"] = [stale, stale, stale]
    assert limiter.record_failure("s") == 1


# --- metrics_auth: key read per call ----------------------------------------


def test_metrics_key_picks_up_rotated_env_value(monkeypatch) -> None:
    import shared.metrics_auth as metrics_auth

    monkeypatch.setenv("METRICS_API_KEY", "qa5-rotated")
    metrics_auth.require_metrics_key("qa5-rotated")


# --- error_handling: malformed sample-rate env ------------------------------


def test_init_sentry_tolerates_malformed_sample_rate(monkeypatch) -> None:
    from shared import error_handling

    monkeypatch.setenv("SENTRY_DSN", "https://abc123@example.com/1")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "not-a-float")
    monkeypatch.setenv("SENTRY_PROFILES_SAMPLE_RATE", "also-bad")
    error_handling.init_sentry()


# --- kafka_auth: non-positive max age ---------------------------------------


def test_negative_signature_age_falls_back_to_default(monkeypatch) -> None:
    from shared.kafka_auth import DEFAULT_MAX_SIGNATURE_AGE_SECONDS, _max_signature_age

    monkeypatch.setenv("KAFKA_MAX_SIGNATURE_AGE_SECONDS", "-1")
    assert _max_signature_age() == DEFAULT_MAX_SIGNATURE_AGE_SECONDS


# --- kafka_compat: tombstones and late callbacks ----------------------------


class _StubProducer:
    def __init__(self) -> None:
        self.produced: dict = {}

    def produce(self, topic, key=None, value=None, headers=None, on_delivery=None):
        self.produced = {"topic": topic, "key": key, "value": value}
        on_delivery(None, MagicMock(name="kafka-message"))

    def poll(self, _timeout):
        return None


def test_send_preserves_none_value_as_tombstone() -> None:
    from shared.kafka_compat import KafkaProducerCompat, _json_serializer, _optional_str_serializer

    producer = KafkaProducerCompat.__new__(KafkaProducerCompat)
    producer._producer = _StubProducer()
    producer._key_serializer = _optional_str_serializer
    producer._value_serializer = _json_serializer
    producer.send("compacted-topic", value=None)
    assert producer._producer.produced["value"] is None


def test_late_callback_receives_message_not_topic() -> None:
    from shared.kafka_compat import DeliveryHandle

    handle = DeliveryHandle("t")
    message = MagicMock(name="kafka-message")
    handle._on_delivery(None, message)
    received = []
    handle.add_callback(received.append)
    assert received == [message]


# --- kafka_consumer_base: started-but-never-polled --------------------------


def test_never_polled_consumer_reports_unhealthy_after_threshold() -> None:
    from shared.kafka_consumer_base import ConsumerHealthMonitor

    health = ConsumerHealthMonitor(stale_threshold_seconds=30)
    health.mark_started()
    health._started_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    status = health.get_status()
    assert status["healthy"] is False
    assert status["poll_stale"] is True


def test_freshly_started_consumer_reports_healthy() -> None:
    from shared.kafka_consumer_base import ConsumerHealthMonitor

    health = ConsumerHealthMonitor(stale_threshold_seconds=30)
    health.mark_started()
    assert health.get_status()["healthy"] is True


# --- jwt_key_registry: expiry filtering and listing redaction ---------------


def _registry_with(keys):
    from shared.jwt_key_registry import JWTKeyRegistry

    registry = JWTKeyRegistry(redis_client=None)
    registry._fallback_keys = list(keys)
    return registry


def test_verification_excludes_expired_keys() -> None:
    from shared.jwt_key_registry import SigningKey

    now = time.time()
    expired = SigningKey(kid="old", secret="s", created_at=now - 9999, expires_at=now - 10)
    current = SigningKey(kid="new", secret="s", created_at=now, expires_at=None)
    keys = asyncio.run(_registry_with([expired, current]).get_verification_keys())
    assert [k.kid for k in keys] == ["new"]


def test_admin_listing_keeps_kid_lifecycle_fields() -> None:
    from shared.jwt_key_registry import SigningKey

    key = SigningKey(kid="k1", secret="super-secret-value")
    keys = asyncio.run(_registry_with([key]).get_all_keys())
    assert keys[0].kid == "k1"
    assert keys[0].is_active is True
    assert keys[0].is_valid is True


# --- secrets_manager: cache invalidation ------------------------------------


def test_secret_cache_can_be_invalidated_after_rotation(monkeypatch) -> None:
    from shared.secrets_manager import SecretsManager

    manager = SecretsManager()
    monkeypatch.setenv("REGENGINE_SECRET_QA5_ROT", '{"token": "v1"}')
    assert manager.get_secret("qa5/rot") == {"token": "v1"}
    monkeypatch.setenv("REGENGINE_SECRET_QA5_ROT", '{"token": "v2"}')
    manager.invalidate_cache()
    assert manager.get_secret("qa5/rot") == {"token": "v2"}


# --- resilient_http: negative retries ---------------------------------------


def test_negative_retries_still_attempts_once() -> None:
    import httpx
    from shared.resilient_http import RetryTransport

    async def _run() -> httpx.Response:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": True})

        transport = RetryTransport(httpx.MockTransport(handler), retries=-1)
        async with httpx.AsyncClient(transport=transport) as client:
            return await client.get("https://example.com/x")

    assert asyncio.run(_run()).status_code == 200


# --- safe_http: pin tries next address --------------------------------------


def test_pin_skips_private_address_for_public_one(monkeypatch) -> None:
    import socket

    import shared.safe_http as safe_http

    monkeypatch.setattr(safe_http, "validate_url", lambda url: url)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, None, None, None, ("10.0.0.1", 0)),
            (socket.AF_INET, None, None, None, ("93.184.216.34", 0)),
        ],
    )
    pinned, host = safe_http._validate_and_pin("http://example.com/x")
    assert pinned == "93.184.216.34"


def test_pin_rejects_all_private_addresses(monkeypatch) -> None:
    import socket

    import shared.safe_http as safe_http
    from shared.url_validation import SSRFError

    monkeypatch.setattr(safe_http, "validate_url", lambda url: url)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, None, None, None, ("10.0.0.1", 0))],
    )
    with pytest.raises(SSRFError):
        safe_http._validate_and_pin("http://example.com/x")


# --- idempotency: naive expiry ----------------------------------------------


def test_idempotency_lookup_treats_naive_expiry_as_utc(monkeypatch) -> None:
    import shared.idempotency as idempotency

    naive_future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    # Current lookup shape: the key row carries revoked_at (#3242), and a
    # second query reads the key tenant's status (#3352).
    row = ("tenant-1", True, naive_future, "key-1", ["read"], ["US"], None)

    def execute(statement, *args, **kwargs):
        result = MagicMock()
        result.fetchone.return_value = ("active",) if "FROM tenants" in str(statement) else row
        return result

    session = MagicMock()
    session.execute.side_effect = execute
    monkeypatch.setattr("shared.database.SessionLocal", lambda: session)
    monkeypatch.setattr(
        "shared.api_key_store.set_api_key_lookup_context",
        lambda *a, **k: ("key-1", ["hash"]),
    )
    result = idempotency._lookup_api_key_context("rge_x.secret")
    assert result is not None
    assert result[0] == "tenant-1"


# --- api_key_store: usage failures and uuid validation ----------------------


def test_validate_uuid_rejects_non_string() -> None:
    from shared.api_key_store import DatabaseAPIKeyStore

    store = DatabaseAPIKeyStore.__new__(DatabaseAPIKeyStore)
    assert store._validate_uuid(None) is None
    with pytest.raises(ValueError):
        store._validate_uuid(123)
    with pytest.raises(ValueError):
        store._validate_uuid("not-a-uuid")


def test_db_usage_record_failure_returns_response(monkeypatch) -> None:
    """validate_key returns metadata even when the usage UPDATE fails."""
    import hashlib
    import hmac
    from contextlib import asynccontextmanager
    from datetime import datetime, timezone

    import shared.api_key_store as store_module
    from shared.api_key_store import DatabaseAPIKeyStore

    raw_secret = "s" * 40
    key_id = "rge_live_qa5usage"
    raw_key = f"{key_id}.{raw_secret}"
    current_hash = store_module.hash_api_key(raw_key)

    api_key = store_module.APIKeyModel(
        key_id=key_id,
        key_hash=current_hash,
        key_prefix=raw_key[:12],
        name="qa5",
        tenant_id=None,
        enabled=True,
        expires_at=None,
        revoked_at=None,
        created_at=datetime.now(timezone.utc),
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = api_key
    session = AsyncMock()
    session.execute.return_value = result

    store = DatabaseAPIKeyStore.__new__(DatabaseAPIKeyStore)
    store._arm_sysadmin_rls = False
    store._pending_usage = {}
    store._last_usage_flush = {}

    @asynccontextmanager
    async def _session_cm():
        yield session

    store._session = _session_cm  # noqa: SLF001
    store._set_key_lookup_context = AsyncMock(return_value=None)

    async def _boom(_key_id, _session):
        raise RuntimeError("usage table down")

    store._record_key_usage = _boom  # noqa: SLF001
    monkeypatch.setattr(
        store_module, "api_key_hash_candidates", lambda _raw: [current_hash]
    )

    response = asyncio.run(store.validate_key(raw_key))
    assert response is not None


def test_db_validate_key_accepts_naive_future_expiry(monkeypatch) -> None:
    """Naive datetimes from SQLite are treated as UTC, not a TypeError."""
    from contextlib import asynccontextmanager
    from datetime import datetime, timedelta, timezone

    import shared.api_key_store as store_module
    from shared.api_key_store import DatabaseAPIKeyStore

    raw_secret = "t" * 40
    key_id = "rge_live_qa5naive"
    raw_key = f"{key_id}.{raw_secret}"
    current_hash = store_module.hash_api_key(raw_key)

    api_key = store_module.APIKeyModel(
        key_id=key_id,
        key_hash=current_hash,
        key_prefix=raw_key[:12],
        name="qa5",
        tenant_id=None,
        enabled=True,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        revoked_at=None,
        created_at=datetime.now(timezone.utc),
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = api_key
    session = AsyncMock()
    session.execute.return_value = result

    store = DatabaseAPIKeyStore.__new__(DatabaseAPIKeyStore)
    store._arm_sysadmin_rls = False
    store._pending_usage = {}
    store._last_usage_flush = {}

    @asynccontextmanager
    async def _session_cm():
        yield session

    store._session = _session_cm  # noqa: SLF001
    store._set_key_lookup_context = AsyncMock(return_value=None)
    store._record_key_usage = AsyncMock(return_value=None)
    monkeypatch.setattr(
        store_module, "api_key_hash_candidates", lambda _raw: [current_hash]
    )

    assert asyncio.run(store.validate_key(raw_key)) is not None


def test_observability_metrics_key_picks_up_rotation(monkeypatch) -> None:
    import shared.observability.metrics_auth as obs_auth

    monkeypatch.setenv("METRICS_API_KEY", "qa5-obs-rotated")
    obs_auth.require_metrics_key("qa5-obs-rotated")


def test_record_failure_in_memory_counts_current_window_only() -> None:
    limiter = _limiter()
    limiter.record_failure("w")
    limiter.record_failure("w")
    assert limiter.is_limited("w") is False
    assert limiter.record_failure("w") == 3
    assert limiter.is_limited("w") is True
