"""Deep QA coverage for admin auth, session, MFA-adjacent, and key-policy code.

Fills gaps the existing per-finding tests do not reach. Every test is
fast and deterministic: in-memory stores only, no sleeps, no network.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.auth import session_helpers as session_helpers_mod
from app.auth.challenges_router import (
    _browser_binding_matches,
    _browser_nonce_for_request,
    _challenge_is_pending,
)
from app.auth.elevation_helpers import _revoke_all_elevation_tokens_for_user
from app.auth.session_helpers import _persist_session
from app.auth.sessions_router import _remaining_token_ttl_seconds
from app.auth_crypto import AuthCryptoService
from app.session_store import InMemorySessionStore, SessionData
from fastapi import HTTPException

TEST_SECRET = "test-auth-otp-hmac-secret-32-bytes-minimum"  # pragma: allowlist secret


def _crypto() -> AuthCryptoService:
    return AuthCryptoService(hmac_secret=TEST_SECRET)


def _make_session(user_id=None, family_id=None, token_hash=None) -> SessionData:
    now = datetime.now(timezone.utc)
    return SessionData(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        refresh_token_hash=token_hash or uuid.uuid4().hex,
        family_id=family_id or uuid.uuid4(),
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=30),
    )


def _cookie_request(cookies: dict[str, str]):
    from starlette.requests import Request

    cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
    raw_headers = [(b"cookie", cookie_header.encode())] if cookie_header else []
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/challenges/verify",
            "headers": raw_headers,
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 443),
            "scheme": "https",
            "query_string": b"",
            "http_version": "1.1",
            "root_path": "",
            "state": {},
        }
    )


# --- _persist_session -------------------------------------------------------


async def test_persist_session_succeeds_first_try_without_retry():
    store = AsyncMock()
    session = _make_session()

    await _persist_session(store, session, context="login", user_id=session.user_id)

    store.create_session.assert_awaited_once_with(session)


async def test_persist_session_retries_once_then_succeeds(monkeypatch):
    store = AsyncMock()
    store.create_session.side_effect = [ConnectionError("down"), None]
    sleep = AsyncMock()
    monkeypatch.setattr(session_helpers_mod.asyncio, "sleep", sleep)
    session = _make_session()

    await _persist_session(store, session, context="login", user_id=session.user_id)

    assert store.create_session.await_count == 2
    sleep.assert_awaited_once()


async def test_persist_session_raises_503_after_two_failures(monkeypatch):
    store = AsyncMock()
    store.create_session.side_effect = ConnectionError("down")
    monkeypatch.setattr(session_helpers_mod.asyncio, "sleep", AsyncMock())
    session = _make_session()

    with pytest.raises(HTTPException) as exc_info:
        await _persist_session(store, session, context="signup", user_id=session.user_id)

    assert exc_info.value.status_code == 503
    assert store.create_session.await_count == 2


# --- elevation-token cleanup helper -----------------------------------------


async def test_elevation_revoke_removes_only_matching_user_entries():
    from app.session_store import InMemorySessionStore

    store = InMemorySessionStore()
    user_id = uuid.uuid4()
    other_id = uuid.uuid4()
    client = await store._get_client()
    await client.set("elevation_jti:aaa", str(user_id), ex=300)
    await client.set("elevation_jti:bbb", str(other_id), ex=300)
    await client.set("unrelated:key", str(user_id), ex=300)

    revoked = await _revoke_all_elevation_tokens_for_user(store, user_id)

    assert revoked == 1
    assert await client.get("elevation_jti:aaa") is None
    assert await client.get("elevation_jti:bbb") == str(other_id)
    assert await client.get("unrelated:key") == str(user_id)


async def test_elevation_revoke_empty_keyspace_returns_zero():
    store = InMemorySessionStore()

    assert await _revoke_all_elevation_tokens_for_user(store, uuid.uuid4()) == 0


# --- remaining access-token TTL ---------------------------------------------


def test_remaining_ttl_returns_none_without_exp():
    assert _remaining_token_ttl_seconds({}) is None
    assert _remaining_token_ttl_seconds({"exp": None}) is None
    assert _remaining_token_ttl_seconds({"exp": "not-a-number"}) is None


def test_remaining_ttl_floors_at_one_second_for_expired_token():
    import time

    assert _remaining_token_ttl_seconds({"exp": int(time.time()) - 60}) == 1


def test_remaining_ttl_accepts_datetime_and_numeric_string_exp():
    import time

    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    ttl_dt = _remaining_token_ttl_seconds({"exp": future})
    assert 295 <= ttl_dt <= 301

    ttl_str = _remaining_token_ttl_seconds({"exp": str(int(time.time()) + 300)})
    assert 299 <= ttl_str <= 301


# --- auth crypto gaps -------------------------------------------------------


def test_email_fingerprint_normalizes_case_and_whitespace():
    service = _crypto()

    assert service.fingerprint_email("User@Example.COM ") == service.fingerprint_email("user@example.com")


def test_email_fingerprint_differs_across_secrets():
    other = AuthCryptoService(hmac_secret="other-auth-otp-hmac-secret-32-bytes-minimum")

    assert _crypto().fingerprint_email("user@example.com") != other.fingerprint_email("user@example.com")


def test_verify_otp_hash_rejects_cross_secret_digest():
    service = _crypto()
    other = AuthCryptoService(hmac_secret="other-auth-otp-hmac-secret-32-bytes-minimum")
    challenge_id = uuid.uuid4()
    digest = service.hash_otp(challenge_id, "sign_in", "fp", "012345")

    assert other.verify_otp_hash(digest, challenge_id, "sign_in", "fp", "012345") is False


def test_hmac_secret_accepts_bytes_and_rejects_wrong_types():
    service = AuthCryptoService(hmac_secret=b"x" * 32)
    assert service.fingerprint_email("a@b.test")

    with pytest.raises(TypeError):
        AuthCryptoService(hmac_secret=12345)


def test_generated_session_tokens_are_unique():
    tokens = {AuthCryptoService.generate_opaque_session_token() for _ in range(10)}

    assert len(tokens) == 10


# --- refresh-token tombstones and family revocation -------------------------


async def test_token_reuse_tombstone_roundtrip_and_unknown():
    store = InMemorySessionStore()
    session_id = uuid.uuid4()

    assert await store.check_token_reuse("never-seen") is None

    await store.mark_token_used("consumed-hash", session_id, ttl_seconds=3600)
    assert await store.check_token_reuse("consumed-hash") == session_id


async def test_token_reuse_with_corrupt_value_returns_none():
    store = InMemorySessionStore()
    client = await store._get_client()
    await client.set(store._used_token_key("corrupt-hash"), "not-a-uuid", ex=3600)

    assert await store.check_token_reuse("corrupt-hash") is None


async def test_revoke_all_for_family_scopes_to_matching_family():
    store = InMemorySessionStore()
    user_id = uuid.uuid4()
    family = uuid.uuid4()
    session_a = _make_session(user_id=user_id, family_id=family, token_hash="hash-a")
    session_b = _make_session(user_id=user_id, family_id=family, token_hash="hash-b")
    session_c = _make_session(user_id=user_id, token_hash="hash-c")
    for session in (session_a, session_b, session_c):
        await store.create_session(session)

    revoked = await store.revoke_all_for_family(family)

    assert revoked == 2
    assert (await store.get_session(session_a.id)).is_revoked is True
    assert (await store.get_session(session_b.id)).is_revoked is True
    assert await store.get_session_by_token("hash-a") is None
    assert await store.get_session_by_token("hash-b") is None
    survivor = await store.get_session(session_c.id)
    assert survivor is not None and survivor.is_revoked is False
    assert (await store.get_session_by_token("hash-c")).id == session_c.id


async def test_revoke_all_for_family_skips_already_revoked():
    store = InMemorySessionStore()
    family = uuid.uuid4()
    session = _make_session(family_id=family)
    await store.create_session(session)
    await store.revoke_session(session.id)

    assert await store.revoke_all_for_family(family) == 0


async def test_revoke_all_user_sessions_honors_except_session_id():
    store = InMemorySessionStore()
    user_id = uuid.uuid4()
    mine = _make_session(user_id=user_id)
    theirs = _make_session(user_id=user_id)
    await store.create_session(mine)
    await store.create_session(theirs)

    revoked = await store.revoke_all_user_sessions(user_id, except_session_id=mine.id)

    assert revoked == 1
    assert (await store.get_session(mine.id)).is_revoked is False
    assert (await store.get_session(theirs.id)).is_revoked is True


async def test_revoke_update_and_delete_unknown_session():
    store = InMemorySessionStore()
    unknown = uuid.uuid4()

    assert await store.revoke_session(unknown) is False
    assert await store.update_session(unknown, {"is_revoked": "true"}) is False
    assert await store.delete_session(unknown) is False


async def test_delete_session_removes_row_set_member_and_token_mapping():
    store = InMemorySessionStore()
    session = _make_session()
    await store.create_session(session)

    assert await store.delete_session(session.id) is True
    assert await store.get_session(session.id) is None
    assert await store.get_session_by_token(session.refresh_token_hash) is None
    assert await store.list_user_sessions(session.user_id) == []


def test_session_data_token_version_defaults_to_zero_and_roundtrips():
    session = _make_session()
    assert session.token_version == 0

    restored = SessionData.from_redis_hash(session.id, session.to_redis_hash())
    assert restored.token_version == 0
    assert restored == session


# --- challenge helpers ------------------------------------------------------


def _challenge(status="pending", expires_in=timedelta(minutes=5), failed_attempts=0, naive=False):
    expires_at = datetime.now(timezone.utc) + expires_in
    if naive:
        expires_at = expires_at.replace(tzinfo=None)
    return SimpleNamespace(status=status, expires_at=expires_at, failed_attempts=failed_attempts)


def test_challenge_pending_matrix():
    assert _challenge_is_pending(_challenge(), datetime.now(timezone.utc)) is True
    assert _challenge_is_pending(_challenge(failed_attempts=4), datetime.now(timezone.utc)) is True
    assert _challenge_is_pending(_challenge(failed_attempts=5), datetime.now(timezone.utc)) is False
    assert _challenge_is_pending(_challenge(status="consumed"), datetime.now(timezone.utc)) is False
    assert _challenge_is_pending(_challenge(status="locked"), datetime.now(timezone.utc)) is False
    assert _challenge_is_pending(_challenge(expires_in=timedelta(seconds=-1)), datetime.now(timezone.utc)) is False


def test_challenge_pending_tolerates_naive_expires_at():
    assert _challenge_is_pending(_challenge(naive=True), datetime.now(timezone.utc)) is True
    assert (
        _challenge_is_pending(
            _challenge(naive=True, expires_in=timedelta(seconds=-1)),
            datetime.now(timezone.utc),
        )
        is False
    )


def test_browser_nonce_reuses_well_formed_cookie_and_regenerates_overlong():
    service = _crypto()
    well_formed = "A" * 43

    assert (
        _browser_nonce_for_request(_cookie_request({"regengine_auth_browser_nonce": well_formed}), service)
        == well_formed
    )

    fresh = _browser_nonce_for_request(_cookie_request({"regengine_auth_browser_nonce": "n" * 300}), service)
    assert fresh != "n" * 300
    assert len(fresh) > 20


def test_browser_binding_requires_matching_cookie():
    service = _crypto()
    nonce = service.generate_opaque_session_token()
    challenge = SimpleNamespace(browser_binding_hash=service.hash_session_token(nonce))

    assert (
        _browser_binding_matches(
            request=_cookie_request({"regengine_auth_browser_nonce": nonce}),
            challenge=challenge,
            crypto_service=service,
        )
        is True
    )
    assert (
        _browser_binding_matches(
            request=_cookie_request({"regengine_auth_browser_nonce": "wrong"}),
            challenge=challenge,
            crypto_service=service,
        )
        is False
    )
    assert _browser_binding_matches(request=_cookie_request({}), challenge=challenge, crypto_service=service) is False


# --- workload key policy and throttle subjects ------------------------------


def _workload_key_response(**overrides):
    from app import privileged_auth as privileged_mod
    from shared.api_key_store import APIKeyResponse

    now = datetime.now(timezone.utc)
    values = {
        "key_id": "rge_live_workload",
        "key_prefix": "rge_live_wor",
        "name": "stripe-tenant-provisioner",
        "tenant_id": None,
        "scopes": [privileged_mod.TENANT_PROVISIONER_SCOPE],
        "rate_limit_per_minute": 10,
        "created_at": now,
        "expires_at": now + timedelta(days=30),
    }
    values.update(overrides)
    return APIKeyResponse(**values)


def test_valid_workload_key_passes_policy():
    from app import privileged_auth as privileged_mod

    assert privileged_mod._workload_key_policy_error(_workload_key_response()) is None


def test_expired_workload_key_is_rejected_by_policy():
    from app import privileged_auth as privileged_mod

    now = datetime.now(timezone.utc)
    key = _workload_key_response(created_at=now - timedelta(days=40), expires_at=now - timedelta(seconds=1))

    assert privileged_mod._workload_key_policy_error(key) == "expired"


def test_workload_key_at_exact_90_day_lifetime_is_allowed():
    from app import privileged_auth as privileged_mod

    created = datetime.now(timezone.utc)
    key = _workload_key_response(created_at=created, expires_at=created + timedelta(days=90))

    assert privileged_mod._workload_key_policy_error(key) is None


def test_workload_key_over_90_day_lifetime_is_rejected():
    from app import privileged_auth as privileged_mod

    created = datetime.now(timezone.utc)
    key = _workload_key_response(created_at=created, expires_at=created + timedelta(days=91))

    assert privileged_mod._workload_key_policy_error(key) == "expiry_exceeds_90_days"


def test_workload_key_policy_tolerates_naive_datetimes():
    from app import privileged_auth as privileged_mod

    created = datetime.now(timezone.utc).replace(tzinfo=None)
    key = _workload_key_response(created_at=created, expires_at=created + timedelta(days=30))

    assert privileged_mod._workload_key_policy_error(key) is None


@pytest.mark.parametrize("rate", [0, -1, 11, 100])
def test_workload_key_policy_rejects_out_of_range_rate_limit(rate):
    from app import privileged_auth as privileged_mod

    assert (
        privileged_mod._workload_key_policy_error(_workload_key_response(rate_limit_per_minute=rate))
        == "rate_limit_configuration_invalid"
    )


def _privileged_request(ip="203.0.113.50"):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/admin/keys",
            "headers": [],
            "client": (ip, 12345),
            "server": ("testserver", 443),
            "scheme": "https",
            "query_string": b"",
            "http_version": "1.1",
            "root_path": "",
            "state": {},
        }
    )


def test_throttle_subjects_isolate_realms_and_hide_the_ip():
    from app import privileged_auth as privileged_mod

    request = _privileged_request()
    human = privileged_mod._throttle_subject(request, realm="human-admin")
    workload = privileged_mod._throttle_subject(request, realm="workload-tenant-provisioner")

    assert human != workload
    assert "203.0.113.50" not in privileged_mod.PrivilegedAuthThrottle._key(human)


async def test_memory_throttle_limits_after_five_failures_and_resets(monkeypatch):
    from app import privileged_auth as privileged_mod

    monkeypatch.setenv("REGENGINE_ENV", "test")
    for name in privileged_mod.CLOUD_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    throttle = privileged_mod.PrivilegedAuthThrottle(redis_client=None)

    assert await throttle.is_limited("subject-a") is False
    for _ in range(privileged_mod.PRIVILEGED_AUTH_MAX_FAILURES):
        await throttle.record_failure("subject-a")

    assert await throttle.is_limited("subject-a") is True
    assert await throttle.is_limited("subject-b") is False

    await throttle.reset("subject-a")
    assert await throttle.is_limited("subject-a") is False


# --- refresh rotation persistence -------------------------------------------


def _refresh_harness(*, update_result=True):
    from unittest.mock import MagicMock

    from app.session_store import SessionData

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    role_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    store = MagicMock()
    store.claim_session_by_token = AsyncMock(
        return_value=SessionData(
            id=uuid.uuid4(),
            user_id=user_id,
            refresh_token_hash="claimed-hash",
            family_id=uuid.uuid4(),
            token_version=0,
            is_revoked=False,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=7),
        )
    )
    store.update_session = AsyncMock(return_value=update_result)
    store.mark_token_used = AsyncMock(return_value=None)

    user = SimpleNamespace(id=user_id, email="u@example.test", is_sysadmin=False, status="active", token_version=0)
    db = MagicMock()
    db.get.side_effect = lambda model, id_: {
        "UserModel": user,
        "TenantModel": SimpleNamespace(id=tenant_id, status="active"),
        "RoleModel": SimpleNamespace(id=role_id, name="owner", permissions=["admin.read"]),
    }.get(model.__name__, user)
    db.execute.return_value.scalars.return_value.all.return_value = [
        SimpleNamespace(tenant_id=tenant_id, role_id=role_id)
    ]
    return store, db


def _refresh_request():
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/refresh",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 443),
            "scheme": "https",
            "query_string": b"",
            "http_version": "1.1",
            "root_path": "",
            "state": {},
        }
    )


async def test_refresh_fails_closed_when_rotation_write_is_lost():
    from app.auth.refresh_router import RefreshRequest, refresh_session

    store, db = _refresh_harness(update_result=False)

    with pytest.raises(HTTPException) as exc_info:
        await refresh_session.__wrapped__(
            payload=RefreshRequest(refresh_token="raw-refresh-token"),
            request=_refresh_request(),
            db=db,
            session_store=store,
        )

    assert exc_info.value.status_code == 401
    store.mark_token_used.assert_not_awaited()


async def test_refresh_still_rotates_when_rotation_write_succeeds():
    from app.auth.refresh_router import RefreshRequest, refresh_session

    store, db = _refresh_harness(update_result=True)

    result = await refresh_session.__wrapped__(
        payload=RefreshRequest(refresh_token="raw-refresh-token"),
        request=_refresh_request(),
        db=db,
        session_store=store,
    )

    assert result.refresh_token
    assert result.refresh_token != "raw-refresh-token"
    store.mark_token_used.assert_awaited_once()
