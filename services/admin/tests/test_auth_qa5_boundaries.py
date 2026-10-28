"""QA5 deep-pass boundary tests for services/admin/app/auth/.

Covers real behavior that had no direct tests: the WebAuthn fake-options
anti-enumeration shape, scoped session context arm/disarm/bind ordering,
high-assurance fail-closed default, session persist retry contract, token
TTL helper edges, browser nonce handling, challenge pending predicate,
elevation revocation paging, and sign-count resolution.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from services.admin.app.auth import challenges_router as cr, session_auth, sessions_router, webauthn_router as wr
from services.admin.app.auth.elevation_helpers import _revoke_all_elevation_tokens_for_user
from services.admin.app.auth.session_helpers import _persist_session
from services.admin.app.session_store import SessionData


def _request(*, path: str = "/auth/webauthn/login/verify", cookie: str | None = None) -> Request:
    raw_headers = []
    if cookie is not None:
        raw_headers.append((b"cookie", f"{cr.AUTH_BROWSER_NONCE_COOKIE}={cookie}".encode("latin-1")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": raw_headers,
        "client": ("203.0.113.50", 12345),
        "server": ("testserver", 443),
        "scheme": "https",
        "query_string": b"",
        "http_version": "1.1",
        "root_path": "",
        "state": {},
        "app": SimpleNamespace(state=SimpleNamespace()),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def _is_security_guc(statement) -> bool:
    return "set_config('regengine.is_sysadmin'" in str(statement)


class _NullResult:
    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return []

    def first(self):
        return None


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value if isinstance(self._value, list) else [self._value]


class _FakeDb:
    """Minimal stand-in for a SQLAlchemy session."""

    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0

    def execute(self, statement):
        if _is_security_guc(statement):
            return _NullResult()
        if not self._results:
            raise AssertionError(f"unexpected execute: {statement}")
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.rollback_count += 1
        else:
            self.commit_count += 1
        return False


# ---------------------------------------------------------------------------
# WebAuthn fake login options must be shape-identical to real options.
# ---------------------------------------------------------------------------


def test_fake_login_options_contain_a_plausible_credential_descriptor():
    first = wr._fake_authentication_options()
    second = wr._fake_authentication_options()

    assert set(first) == {"challenge", "timeout", "rpId", "allowCredentials", "userVerification"}
    assert first["timeout"] == 60000
    assert first["userVerification"] == "required"
    assert first["rpId"]

    descriptors = first["allowCredentials"]
    assert isinstance(descriptors, list) and len(descriptors) == 1
    assert descriptors[0]["type"] == "public-key"
    assert isinstance(descriptors[0]["id"], str) and descriptors[0]["id"]

    # Fresh randomness per call so responses cannot be fingerprinted or replayed.
    assert first["challenge"] != second["challenge"]
    assert descriptors[0]["id"] != second["allowCredentials"][0]["id"]


@pytest.mark.asyncio
async def test_unknown_and_credentialless_users_get_indistinguishable_options():
    unknown_db = _FakeDb([_ScalarResult(None)])
    unknown = await wr.generate_webauthn_login_options(
        payload=wr.WebAuthnLoginOptionsRequest(email="missing@example.com"),
        db=unknown_db,
    )

    user = SimpleNamespace(id=uuid.uuid4())
    no_creds_db = _FakeDb([_ScalarResult(user), _ScalarResult([])])
    no_creds = await wr.generate_webauthn_login_options(
        payload=wr.WebAuthnLoginOptionsRequest(email="plain@example.com"),
        db=no_creds_db,
    )

    assert set(unknown) == set(no_creds)
    for options in (unknown, no_creds):
        assert options["allowCredentials"]
        assert options["userVerification"] == "required"
    assert unknown_db.added == [] and no_creds_db.added == []
    assert unknown_db.commit_count == 0 and no_creds_db.commit_count == 0


@pytest.mark.asyncio
async def test_login_verify_with_fake_challenge_fails_closed():
    import base64
    import json

    fake = wr._fake_authentication_options()
    client_data = (
        base64.urlsafe_b64encode(json.dumps({"challenge": fake["challenge"]}).encode()).rstrip(b"=").decode("ascii")
    )
    payload = wr.WebAuthnCredentialPayload(
        credential={
            "id": fake["allowCredentials"][0]["id"],
            "rawId": fake["allowCredentials"][0]["id"],
            "type": "public-key",
            "response": {"clientDataJSON": client_data},
        }
    )
    db = _FakeDb([_NullResult(), _NullResult()])
    response = Response()

    with pytest.raises(HTTPException) as exc_info:
        await wr.verify_webauthn_login(
            payload=payload,
            request=_request(),
            response=response,
            db=db,
            crypto_service=MagicMock(),
        )

    assert exc_info.value.status_code == 401
    assert "set-cookie" not in response.headers
    assert db.added == []


# ---------------------------------------------------------------------------
# Scoped session context: global arm must never leak past the lookup.
# ---------------------------------------------------------------------------


def test_scoped_context_arms_disarms_then_binds_user(monkeypatch):
    calls: list[str] = []
    user = SimpleNamespace(id=uuid.uuid4())
    context = session_auth.ActiveSessionContext(user=user, session=SimpleNamespace(id=1))
    monkeypatch.setattr(session_auth, "arm_global_admin_context", lambda db: calls.append("arm"))
    monkeypatch.setattr(session_auth, "disarm_global_admin_context", lambda db: calls.append("disarm"))
    monkeypatch.setattr(session_auth, "bind_authenticated_user_context", lambda db, uid: calls.append(f"bind:{uid}"))
    monkeypatch.setattr(
        session_auth, "get_current_active_session_context", lambda **kwargs: calls.append("lookup") or context
    )
    db, crypto = MagicMock(), MagicMock()

    assert session_auth.get_scoped_active_session_context(request=_request(), db=db, crypto_service=crypto) is context
    assert calls == ["arm", "lookup", "disarm", f"bind:{user.id}"]


def test_scoped_context_disarms_without_binding_on_auth_failure(monkeypatch):
    calls: list[str] = []

    def _fail(**kwargs):
        calls.append("lookup")
        raise HTTPException(status_code=401, detail="Authentication required.")

    monkeypatch.setattr(session_auth, "arm_global_admin_context", lambda db: calls.append("arm"))
    monkeypatch.setattr(session_auth, "disarm_global_admin_context", lambda db: calls.append("disarm"))
    monkeypatch.setattr(session_auth, "bind_authenticated_user_context", lambda db, uid: calls.append("bind"))
    monkeypatch.setattr(session_auth, "get_current_active_session_context", _fail)

    with pytest.raises(HTTPException) as exc_info:
        session_auth.get_scoped_active_session_context(request=_request(), db=MagicMock(), crypto_service=MagicMock())

    assert exc_info.value.status_code == 401
    assert calls == ["arm", "lookup", "disarm"]


# ---------------------------------------------------------------------------
# High-assurance gate fails closed on missing auth method.
# ---------------------------------------------------------------------------


def test_step_up_required_when_auth_method_is_none():
    user = SimpleNamespace(id="user-id")
    context = session_auth.ActiveSessionContext(user=user, session=SimpleNamespace(auth_method=None))

    with pytest.raises(HTTPException) as exc_info:
        session_auth.require_high_assurance_session(context=context)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "requires_step_up"
    assert exc_info.value.detail["auth_method"] is None


def test_step_up_required_when_session_has_no_auth_method_attribute():
    user = SimpleNamespace(id="user-id")
    context = session_auth.ActiveSessionContext(user=user, session=SimpleNamespace())

    with pytest.raises(HTTPException) as exc_info:
        session_auth.require_high_assurance_session(context=context)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "requires_step_up"


# ---------------------------------------------------------------------------
# Session persist retry contract.
# ---------------------------------------------------------------------------


def _session_data() -> SessionData:
    now = datetime.now(timezone.utc)
    return SessionData(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        refresh_token_hash="hash",
        family_id=uuid.uuid4(),
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_persist_session_succeeds_first_try():
    store = MagicMock()
    store.create_session = AsyncMock(return_value=None)
    data = _session_data()

    await _persist_session(store, data, context="login", user_id=data.user_id)

    store.create_session.assert_awaited_once_with(data)


@pytest.mark.asyncio
async def test_persist_session_retries_once_then_succeeds():
    store = MagicMock()
    store.create_session = AsyncMock(side_effect=[ConnectionError("down"), None])
    data = _session_data()

    await _persist_session(store, data, context="login", user_id=data.user_id)

    assert store.create_session.await_count == 2


@pytest.mark.asyncio
async def test_persist_session_raises_503_after_two_failures():
    store = MagicMock()
    store.create_session = AsyncMock(side_effect=ConnectionError("down"))
    data = _session_data()

    with pytest.raises(HTTPException) as exc_info:
        await _persist_session(store, data, context="login", user_id=data.user_id)

    assert exc_info.value.status_code == 503
    assert store.create_session.await_count == 2


# ---------------------------------------------------------------------------
# Token TTL helper edges.
# ---------------------------------------------------------------------------


def test_remaining_ttl_from_datetime_exp():
    exp = datetime.now(timezone.utc) + timedelta(seconds=120)
    ttl = sessions_router._remaining_token_ttl_seconds({"exp": exp})

    assert 115 <= ttl <= 120


def test_remaining_ttl_from_numeric_exp():
    import time

    ttl = sessions_router._remaining_token_ttl_seconds({"exp": int(time.time()) + 300})

    assert 295 <= ttl <= 300


def test_remaining_ttl_missing_or_invalid_exp_is_none():
    assert sessions_router._remaining_token_ttl_seconds({}) is None
    assert sessions_router._remaining_token_ttl_seconds({"exp": "soon"}) is None
    assert sessions_router._remaining_token_ttl_seconds({"exp": None}) is None


def test_remaining_ttl_floor_is_one_second_for_expired_tokens():
    import time

    assert sessions_router._remaining_token_ttl_seconds({"exp": int(time.time()) - 60}) == 1


# ---------------------------------------------------------------------------
# Browser nonce handling.
# ---------------------------------------------------------------------------


class _NonceCrypto:
    def __init__(self):
        self.minted = 0

    def generate_opaque_session_token(self):
        self.minted += 1
        return "fresh-nonce"


def test_browser_nonce_helper_always_mints_fresh():
    """Never echo the client cookie into Set-Cookie (CodeQL py/cookie-injection)."""
    crypto = _NonceCrypto()

    well_formed = "x" * 43  # token_urlsafe(32) shape
    assert cr._browser_nonce_for_request(_request(cookie=well_formed), crypto) == "fresh-nonce"
    assert crypto.minted == 1

    assert cr._browser_nonce_for_request(_request(), crypto) == "fresh-nonce"
    assert crypto.minted == 2

    assert cr._browser_nonce_for_request(_request(cookie="n" * 257), crypto) == "fresh-nonce"
    assert crypto.minted == 3


# ---------------------------------------------------------------------------
# Challenge pending predicate.
# ---------------------------------------------------------------------------


def _pending_challenge(**overrides):
    values = {
        "status": "pending",
        "failed_attempts": 0,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_pending_challenge_is_accepted():
    assert cr._challenge_is_pending(_pending_challenge(), datetime.now(timezone.utc)) is True


def test_expired_or_locked_or_consumed_challenges_are_rejected():
    now = datetime.now(timezone.utc)
    assert cr._challenge_is_pending(_pending_challenge(expires_at=now - timedelta(seconds=1)), now) is False
    assert cr._challenge_is_pending(_pending_challenge(expires_at=now), now) is False
    assert cr._challenge_is_pending(_pending_challenge(failed_attempts=5), now) is False
    assert cr._challenge_is_pending(_pending_challenge(status="consumed"), now) is False
    assert cr._challenge_is_pending(_pending_challenge(status="locked"), now) is False


def test_naive_expiry_is_read_as_utc():
    naive_future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)

    assert cr._challenge_is_pending(_pending_challenge(expires_at=naive_future), datetime.now(timezone.utc)) is True


# ---------------------------------------------------------------------------
# Elevation revocation scans every page and only touches this user's keys.
# ---------------------------------------------------------------------------


class _PagedRedis:
    def __init__(self, pages, values):
        self._pages = pages
        self._values = values
        self.deleted: list[str] = []

    async def scan(self, cursor=0, match=None, count=None):
        assert match == "elevation_jti:*"
        return self._pages[cursor]

    async def get(self, key):
        return self._values.get(key)

    async def delete(self, key):
        self.deleted.append(key)


def _elevation_store(client) -> SimpleNamespace:
    return SimpleNamespace(_get_client=AsyncMock(return_value=client))


@pytest.mark.asyncio
async def test_elevation_revocation_walks_all_pages_and_spares_other_users():
    user_id = uuid.uuid4()
    other_id = uuid.uuid4()
    client = _PagedRedis(
        pages={
            0: (7, ["elevation_jti:a", "elevation_jti:other"]),
            7: (0, ["elevation_jti:b", "elevation_jti:gone"]),
        },
        values={
            "elevation_jti:a": str(user_id),
            "elevation_jti:other": str(other_id),
            "elevation_jti:b": str(user_id),
            "elevation_jti:gone": None,
        },
    )

    revoked = await _revoke_all_elevation_tokens_for_user(_elevation_store(client), user_id)

    assert revoked == 2
    assert sorted(client.deleted) == ["elevation_jti:a", "elevation_jti:b"]


@pytest.mark.asyncio
async def test_elevation_revocation_with_empty_keyspace_returns_zero():
    client = _PagedRedis(pages={0: (0, [])}, values={})

    assert await _revoke_all_elevation_tokens_for_user(_elevation_store(client), uuid.uuid4()) == 0
    assert client.deleted == []


# ---------------------------------------------------------------------------
# Sign-count resolution.
# ---------------------------------------------------------------------------


def test_sign_count_accepts_first_and_increasing_counts():
    assert wr._resolve_new_sign_count(0, SimpleNamespace(new_sign_count=0)) == 0
    assert wr._resolve_new_sign_count(2, SimpleNamespace(new_sign_count=5)) == 5


def test_sign_count_rejects_stale_or_replayed_counts():
    with pytest.raises(HTTPException) as equal_exc:
        wr._resolve_new_sign_count(5, SimpleNamespace(new_sign_count=5))
    assert equal_exc.value.status_code == 401

    with pytest.raises(HTTPException) as lower_exc:
        wr._resolve_new_sign_count(5, SimpleNamespace(new_sign_count=3))
    assert lower_exc.value.status_code == 401
