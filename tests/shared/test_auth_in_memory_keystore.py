"""Dedicated coverage for ``shared.auth.APIKeyStore`` — #1338.

``services/shared/auth.py`` exposes two key stores side-by-side:

- ``DatabaseAPIKeyStore`` (in ``shared.api_key_store``) — exercised by
  ``tests/shared/test_api_key_store.py``, production default.
- ``APIKeyStore`` (in ``shared.auth``, lines 91-227) — the in-memory
  fallback used whenever ``REGENGINE_ENV != "production"`` and
  ``ENABLE_DB_API_KEYS`` is unset. This is what local dev, most of CI,
  and the initial on-prem footprint actually hit.

Prior to this test file the in-memory path had **zero** dedicated
coverage despite guarding authentication for every non-prod
environment. #1338 calls it out as one of the shared-kernel gaps
where a regression in a 200-line thread-safe store could silently
open up every downstream service.

These tests pin down:

  1. ``create_key`` — ID format, uniqueness, jurisdiction default,
     metadata echoed back, raw key structure.
  2. ``validate_key`` — every rejection branch (empty / bad prefix /
     no separator / unknown id / hash mismatch / disabled / expired)
     plus happy-path that stamps ``last_used_at``.
  3. ``check_rate_limit`` — 60-second sliding window, off-by-one at
     the limit, cleanup of stale timestamps.
  4. ``revoke_key`` — no-op on unknown id, flips ``enabled=False`` on
     known id so subsequent ``validate_key`` returns None.
  5. ``list_keys`` — returns a snapshot (mutating the return value
     does not corrupt internal state).
  6. ``_hash_key`` — deterministic SHA-256.

Pure Python, no DB, no network.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import threading
from datetime import datetime, timedelta, timezone
from typing import Tuple

import pytest

from shared.auth import APIKey, APIKeyStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> APIKeyStore:
    """Fresh in-memory keystore per test — no state bleed across cases."""
    return APIKeyStore()


@pytest.fixture
def raw_and_key(store: APIKeyStore) -> Tuple[str, APIKey]:
    """Pre-create one API key and hand back (raw_key, metadata)."""
    return store.create_key(name="fixture-key")


# ---------------------------------------------------------------------------
# 1. create_key
# ---------------------------------------------------------------------------


class TestCreateKey:
    def test_returns_raw_key_and_metadata(self, store: APIKeyStore):
        raw, key = store.create_key(name="integration-test")
        assert isinstance(raw, str) and raw.startswith("rge_")
        assert "." in raw, "raw key must have {key_id}.{secret} shape"
        assert isinstance(key, APIKey)
        assert key.key_id == raw.split(".", 1)[0]

    def test_generates_unique_ids(self, store: APIKeyStore):
        """100 consecutive keys must all have distinct IDs and hashes —
        catches a regression where the token RNG was fed a fixed seed."""
        raws = [store.create_key(name=f"k{i}")[0] for i in range(100)]
        ids = {r.split(".", 1)[0] for r in raws}
        assert len(ids) == 100
        hashes = {store._hash_key(r) for r in raws}
        assert len(hashes) == 100

    def test_default_jurisdiction_is_us(self, store: APIKeyStore):
        _, key = store.create_key(name="no-juris")
        assert key.allowed_jurisdictions == ["US"]

    def test_respects_explicit_jurisdiction_list(self, store: APIKeyStore):
        _, key = store.create_key(name="j", allowed_jurisdictions=["US-NY", "EU"])
        assert key.allowed_jurisdictions == ["US-NY", "EU"]

    def test_echoes_metadata(self, store: APIKeyStore):
        now = datetime.now(timezone.utc)
        _, key = store.create_key(
            name="meta",
            tenant_id="11111111-1111-1111-1111-111111111111",
            rate_limit_per_minute=120,
            expires_at=now + timedelta(days=30),
            scopes=["read:regulations", "write:events"],
            billing_tier="ENTERPRISE",
        )
        assert key.name == "meta"
        assert key.tenant_id == "11111111-1111-1111-1111-111111111111"
        assert key.rate_limit_per_minute == 120
        assert key.billing_tier == "ENTERPRISE"
        assert sorted(key.scopes) == ["read:regulations", "write:events"]
        assert key.enabled is True
        assert key.last_used_at is None

    def test_key_is_registered_in_store(
        self, store: APIKeyStore, raw_and_key: Tuple[str, APIKey]
    ):
        _, key = raw_and_key
        assert store.list_keys() == [key]


# ---------------------------------------------------------------------------
# 2. validate_key — each rejection branch + happy path
# ---------------------------------------------------------------------------


class TestValidateKey:
    def test_rejects_empty(self, store: APIKeyStore):
        assert store.validate_key("") is None
        assert store.validate_key(None) is None  # type: ignore[arg-type]

    def test_rejects_missing_prefix(self, store: APIKeyStore):
        assert store.validate_key("whatever.payload") is None

    def test_rejects_no_separator(self, store: APIKeyStore):
        # Starts with rge_ but has no `.` — ValueError path.
        assert store.validate_key("rge_nopunctuation") is None

    def test_rejects_unknown_key_id(self, store: APIKeyStore):
        assert store.validate_key("rge_bogusid.bogussecret") is None

    def test_rejects_hash_mismatch(
        self, store: APIKeyStore, raw_and_key: Tuple[str, APIKey]
    ):
        """A correct key_id with a forged secret must be rejected — this is
        the branch ``hmac.compare_digest`` defends. Without it, an
        attacker who knows the key_id (leaked in logs) could walk the
        secret via timing."""
        raw, _ = raw_and_key
        key_id = raw.split(".", 1)[0]
        forged = f"{key_id}.forged-secret-xxxxxxxxxxxxxxxxxxxx"
        assert store.validate_key(forged) is None

    def test_rejects_disabled(
        self, store: APIKeyStore, raw_and_key: Tuple[str, APIKey]
    ):
        raw, key = raw_and_key
        assert store.revoke_key(key.key_id) is True
        assert store.validate_key(raw) is None

    def test_rejects_expired(self, store: APIKeyStore):
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        raw, _ = store.create_key(name="expired", expires_at=past)
        assert store.validate_key(raw) is None

    def test_happy_path_returns_metadata_and_stamps_last_used(
        self, store: APIKeyStore, raw_and_key: Tuple[str, APIKey]
    ):
        raw, key = raw_and_key
        assert key.last_used_at is None
        got = store.validate_key(raw)
        assert got is key
        # last_used_at is stamped on successful validate.
        assert got.last_used_at is not None
        assert got.last_used_at.tzinfo is not None, "must be timezone-aware UTC"

    def test_does_not_bump_last_used_on_rejection(
        self, store: APIKeyStore, raw_and_key: Tuple[str, APIKey]
    ):
        raw, key = raw_and_key
        # Poison with a hash-mismatch call before the happy path.
        key_id = raw.split(".", 1)[0]
        store.validate_key(f"{key_id}.forged-secret-xxxxxxxxxxxxxxxxxxxx")
        assert key.last_used_at is None, (
            "hash-mismatch must NOT stamp last_used_at — would let an "
            "attacker with a leaked key_id update the timestamp and muddy "
            "audit trails"
        )


# ---------------------------------------------------------------------------
# 3. check_rate_limit — sliding 60s window
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_allows_under_limit(self, store: APIKeyStore):
        for _ in range(5):
            assert store.check_rate_limit("k1", limit_per_minute=10) is True

    def test_blocks_at_limit(self, store: APIKeyStore):
        """The check must return False on the 11th call when limit=10 —
        off-by-one guard. The implementation uses ``>=`` so the caller
        who sees True has already been counted."""
        limit = 10
        allowed = sum(
            1 for _ in range(limit + 5)
            if store.check_rate_limit("k1", limit_per_minute=limit)
        )
        assert allowed == limit, f"expected exactly {limit} allowed, got {allowed}"

    def test_evicts_stale_timestamps(self, store: APIKeyStore, monkeypatch):
        """Timestamps older than 60s must drop out of the window —
        otherwise a quiet key would be permanently rate-limited after
        spiking once."""
        import shared.auth as auth_mod
        fake_now = [1_000_000.0]
        monkeypatch.setattr(auth_mod.time, "time", lambda: fake_now[0])

        # Burn the budget at t=0.
        for _ in range(10):
            store.check_rate_limit("k1", limit_per_minute=10)
        # Still at limit right now.
        assert store.check_rate_limit("k1", limit_per_minute=10) is False

        # Jump 61s into the future — stale entries must evict.
        fake_now[0] += 61
        assert store.check_rate_limit("k1", limit_per_minute=10) is True

    def test_isolates_keys_from_each_other(self, store: APIKeyStore):
        """k1 burning its budget must not affect k2 — shared dict but
        separate per-key lists."""
        for _ in range(10):
            store.check_rate_limit("k1", limit_per_minute=10)
        assert store.check_rate_limit("k1", limit_per_minute=10) is False
        assert store.check_rate_limit("k2", limit_per_minute=10) is True


# ---------------------------------------------------------------------------
# 4. revoke_key
# ---------------------------------------------------------------------------


class TestRevokeKey:
    def test_returns_false_for_unknown(self, store: APIKeyStore):
        assert store.revoke_key("rge_never-existed") is False

    def test_flips_enabled_false_on_known(
        self, store: APIKeyStore, raw_and_key: Tuple[str, APIKey]
    ):
        _, key = raw_and_key
        assert key.enabled is True
        assert store.revoke_key(key.key_id) is True
        assert key.enabled is False

    def test_idempotent(
        self, store: APIKeyStore, raw_and_key: Tuple[str, APIKey]
    ):
        _, key = raw_and_key
        assert store.revoke_key(key.key_id) is True
        # Second revoke still returns True (key still exists in store)
        # but has no observable effect — idempotent from a caller's
        # standpoint. If this ever flips to False we want a conscious
        # reason in the git log.
        assert store.revoke_key(key.key_id) is True
        assert key.enabled is False


# ---------------------------------------------------------------------------
# 5. list_keys — snapshot semantics
# ---------------------------------------------------------------------------


class TestListKeys:
    def test_returns_all_keys(self, store: APIKeyStore):
        _, a = store.create_key(name="a")
        _, b = store.create_key(name="b")
        listed = store.list_keys()
        assert {k.key_id for k in listed} == {a.key_id, b.key_id}

    def test_returns_snapshot_not_live_view(
        self, store: APIKeyStore, raw_and_key: Tuple[str, APIKey]
    ):
        """Mutating the returned list must not corrupt internal state —
        callers are admin dashboards, we can't trust they'll be
        careful."""
        snapshot = store.list_keys()
        snapshot.clear()
        assert len(store.list_keys()) == 1, (
            "list_keys must return a fresh list each call"
        )


# ---------------------------------------------------------------------------
# 6. _hash_key — deterministic SHA-256
# ---------------------------------------------------------------------------


class TestHashKey:
    def test_deterministic(self):
        assert APIKeyStore._hash_key("anything") == APIKeyStore._hash_key("anything")

    def test_matches_sha256(self):
        expected = hashlib.sha256(b"input").hexdigest()
        assert APIKeyStore._hash_key("input") == expected

    def test_distinct_inputs_distinct_hashes(self):
        assert APIKeyStore._hash_key("a") != APIKeyStore._hash_key("b")


# ---------------------------------------------------------------------------
# Thread safety — the store documents itself as thread-safe so exercise
# the claim. If the lock were removed, concurrent create_key would lose
# writes under load (dict assignment isn't atomic from Python's perspective
# in all interpreter builds).
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_create_no_lost_writes(self, store: APIKeyStore):
        n = 200
        barrier = threading.Barrier(n)

        def _worker(i: int) -> str:
            barrier.wait()
            raw, _ = store.create_key(name=f"t-{i}")
            return raw

        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
            raws = list(pool.map(_worker, range(n)))

        # Every worker got a unique key AND every key is discoverable in
        # the store — if the lock were removed, some writes would vanish
        # under a dict-resize race.
        assert len({r.split(".", 1)[0] for r in raws}) == n
        assert len(store.list_keys()) == n

    def test_concurrent_rate_limit_exact_budget(self, store: APIKeyStore):
        """Under a hot storm of 100 concurrent calls with limit=50, the
        store must allow *exactly* 50 through. No lock → oversubscription
        because the read-check-append dance isn't atomic."""
        limit = 50
        n = 100
        results: list[bool] = []
        lock = threading.Lock()
        barrier = threading.Barrier(n)

        def _worker() -> None:
            barrier.wait()
            allowed = store.check_rate_limit("hot-key", limit_per_minute=limit)
            with lock:
                results.append(allowed)

        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(lambda _: _worker(), range(n)))

        assert sum(1 for r in results if r) == limit, (
            f"rate limiter oversubscribed — got {sum(results)} allowed, "
            f"budget was {limit}"
        )
