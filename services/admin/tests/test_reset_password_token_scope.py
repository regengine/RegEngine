"""Regression tests for #1087: /auth/reset-password token-scope enforcement.

Context
-------
Before this fix, ``/auth/reset-password`` validated the caller's Supabase
token via ``sb.auth.get_user(token)`` and — if Supabase said the token
was valid — immediately updated the user's password_hash. But
``get_user()`` accepts ANY valid Supabase user session token: regular
password-login access tokens, magic-link tokens, recovery tokens. The
endpoint never checked that the token was issued specifically for
password recovery.

That meant an attacker who obtained a user's Supabase access token (via
XSS on any site sharing the Supabase project, exposed browser storage,
cross-origin token leak, etc.) could POST to /auth/reset-password with
that token and silently reset the victim's password.

The fix adds two defense layers AFTER the existing ``get_user()`` call:

1. ``_enforce_recovery_token_scope`` — decodes the JWT (unverified
   claims; signature was already verified by Supabase) and checks:
   * ``amr`` claim contains a method in ``{"otp", "recovery"}``.
     Regular password logins have ``amr.method == "password"``, so
     those tokens are now rejected.
   * ``iat`` is within the last 15 minutes. A stolen token, even if
     originally obtained via OTP, can't be replayed hours later.
2. ``_claim_recovery_token_single_use`` — marks the token's ``jti``
   (or ``session_id``) in Redis so the same token can't be consumed
   twice even within the 15-minute window.

These tests verify every branch of both gates.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import jwt as _jwt
import pytest
from fastapi import HTTPException, status

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services" / "admin"))

# Defer import until env is set up to avoid picking up bad module state.
from services.admin.app import auth_routes as ar  # noqa: E402


# ── Helpers ─────────────────────────────────────────────────────────────────


def _mint_unsigned_supabase_token(
    *,
    amr_methods: list[str] | None = None,
    iat_offset_seconds: int = 0,
    jti: str | None = "test-jti-1",
    session_id: str | None = None,
) -> str:
    """Build a Supabase-shape JWT. Signature is irrelevant — the code
    under test only decodes unverified claims."""
    now = int(time.time())
    payload: dict = {
        "sub": "sb-user-1",
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now + iat_offset_seconds,
        "exp": now + 3600,
    }
    if amr_methods is not None:
        payload["amr"] = [{"method": m, "timestamp": now} for m in amr_methods]
    if jti is not None:
        payload["jti"] = jti
    if session_id is not None:
        payload["session_id"] = session_id
    # HS256 with any key — we only decode unverified.
    return _jwt.encode(payload, "irrelevant-test-key", algorithm="HS256")


# ── 1. _enforce_recovery_token_scope: amr check ─────────────────────────────


def test_enforce_rejects_password_session_token():
    """#1087 THE regression test: a regular password-login session token
    must NOT pass the recovery-scope gate. Before the fix, this token
    would happily reset the victim's password."""
    token = _mint_unsigned_supabase_token(amr_methods=["password"])
    with pytest.raises(HTTPException) as exc:
        ar._enforce_recovery_token_scope(token, user_id="sb-user-1")
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc.value.detail == "Invalid or expired recovery token"


def test_enforce_rejects_oauth_session_token():
    """OAuth/SSO logins don't prove email ownership for password reset."""
    token = _mint_unsigned_supabase_token(amr_methods=["oauth"])
    with pytest.raises(HTTPException) as exc:
        ar._enforce_recovery_token_scope(token)
    assert exc.value.status_code == 401


def test_enforce_rejects_saml_session_token():
    token = _mint_unsigned_supabase_token(amr_methods=["saml"])
    with pytest.raises(HTTPException):
        ar._enforce_recovery_token_scope(token)


def test_enforce_rejects_missing_amr():
    """Tokens with NO amr claim (legacy / malformed) are refused."""
    token = _mint_unsigned_supabase_token(amr_methods=None)
    with pytest.raises(HTTPException):
        ar._enforce_recovery_token_scope(token)


def test_enforce_rejects_empty_amr_array():
    token = _mint_unsigned_supabase_token(amr_methods=[])
    with pytest.raises(HTTPException):
        ar._enforce_recovery_token_scope(token)


def test_enforce_accepts_otp_amr():
    """Magic-link and recovery flows emit amr.method == 'otp' in older
    Supabase versions. These must pass the scope gate."""
    token = _mint_unsigned_supabase_token(amr_methods=["otp"])
    # Should NOT raise.
    ar._enforce_recovery_token_scope(token)


def test_enforce_accepts_recovery_amr():
    """Newer Supabase versions emit amr.method == 'recovery' specifically
    for password-recovery flows."""
    token = _mint_unsigned_supabase_token(amr_methods=["recovery"])
    ar._enforce_recovery_token_scope(token)


def test_enforce_accepts_mixed_amr_with_one_recovery_method():
    """A token with multiple amr entries is accepted if ANY entry is a
    recovery-flow method. (Defensive — Supabase occasionally adds
    audit entries beyond the primary method.)"""
    token = _mint_unsigned_supabase_token(amr_methods=["password", "otp"])
    ar._enforce_recovery_token_scope(token)


# ── 2. _enforce_recovery_token_scope: iat freshness ─────────────────────────


def test_enforce_rejects_stale_token_older_than_15min():
    """A recovery token issued 20 minutes ago must be refused even if
    the amr claim is correct — limits the blast radius of a stolen
    token obtained via a legitimate OTP flow."""
    token = _mint_unsigned_supabase_token(
        amr_methods=["otp"],
        iat_offset_seconds=-20 * 60,  # 20 minutes ago
    )
    with pytest.raises(HTTPException) as exc:
        ar._enforce_recovery_token_scope(token)
    assert exc.value.status_code == 401


def test_enforce_accepts_token_within_15min_window():
    """Fresh recovery tokens (e.g. 5 min old) are accepted."""
    token = _mint_unsigned_supabase_token(
        amr_methods=["otp"],
        iat_offset_seconds=-5 * 60,
    )
    ar._enforce_recovery_token_scope(token)


def test_enforce_accepts_just_under_15min_boundary():
    """Boundary: 14m59s must pass."""
    token = _mint_unsigned_supabase_token(
        amr_methods=["otp"],
        iat_offset_seconds=-(15 * 60 - 1),
    )
    ar._enforce_recovery_token_scope(token)


def test_enforce_rejects_future_iat_beyond_clock_skew():
    """A token with iat far in the future is a tampering signal."""
    token = _mint_unsigned_supabase_token(
        amr_methods=["otp"],
        iat_offset_seconds=3600,  # 1h in the future — well beyond 5m skew
    )
    with pytest.raises(HTTPException):
        ar._enforce_recovery_token_scope(token)


def test_enforce_tolerates_small_negative_skew():
    """Clocks drift; +30s into the future is acceptable."""
    token = _mint_unsigned_supabase_token(
        amr_methods=["otp"],
        iat_offset_seconds=30,
    )
    ar._enforce_recovery_token_scope(token)


def test_enforce_rejects_missing_iat():
    """A recovery-scoped token without an iat claim can't be freshness-
    checked, so refuse it (#1087 fail-closed)."""
    # Directly construct to omit iat.
    payload = {
        "sub": "sb-user-1",
        "aud": "authenticated",
        "amr": [{"method": "otp"}],
        "jti": "no-iat-1",
    }
    token = _jwt.encode(payload, "key", algorithm="HS256")
    with pytest.raises(HTTPException):
        ar._enforce_recovery_token_scope(token)


# ── 3. Malformed tokens ─────────────────────────────────────────────────────


def test_enforce_rejects_unparseable_token():
    """Garbage token yields empty claims dict → no amr → reject."""
    with pytest.raises(HTTPException):
        ar._enforce_recovery_token_scope("not.a.jwt")


def test_enforce_rejects_empty_token():
    with pytest.raises(HTTPException):
        ar._enforce_recovery_token_scope("")


def test_parse_claims_survives_malformed_token():
    """_parse_supabase_token_claims should NEVER raise — it returns {}
    and lets the downstream gate fail closed."""
    assert ar._parse_supabase_token_claims("not-a-jwt") == {}
    assert ar._parse_supabase_token_claims("") == {}


# ── 4. Single-use enforcement ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_single_use_first_call_allows():
    """First call with a given jti claims the dedup key and returns."""
    session_store = MagicMock()
    client = MagicMock()
    client.set = AsyncMock(return_value=True)
    session_store._get_client = AsyncMock(return_value=client)

    token = _mint_unsigned_supabase_token(
        amr_methods=["otp"], jti="fresh-jti-42"
    )
    # Should not raise.
    await ar._claim_recovery_token_single_use(
        session_store, token, user_id="u1"
    )
    # Verified: set was called with SET NX EX semantics.
    args, kwargs = client.set.call_args
    assert args[0] == "auth:recovery:used:fresh-jti-42"
    assert kwargs.get("nx") is True
    assert kwargs.get("ex") is not None and kwargs["ex"] > 0


@pytest.mark.asyncio
async def test_claim_single_use_replay_rejected():
    """Second call with the same jti must raise 401."""
    session_store = MagicMock()
    client = MagicMock()
    # SET NX returns None when key already exists (redis-py contract).
    client.set = AsyncMock(return_value=None)
    session_store._get_client = AsyncMock(return_value=client)

    token = _mint_unsigned_supabase_token(
        amr_methods=["otp"], jti="replay-jti-1"
    )
    with pytest.raises(HTTPException) as exc:
        await ar._claim_recovery_token_single_use(session_store, token)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_claim_single_use_fails_open_on_redis_error():
    """Redis outage must NOT block legitimate resets — amr+iat gates
    are the primary defense; single-use is defense-in-depth."""
    session_store = MagicMock()
    client = MagicMock()
    client.set = AsyncMock(side_effect=RuntimeError("redis down"))
    session_store._get_client = AsyncMock(return_value=client)

    token = _mint_unsigned_supabase_token(
        amr_methods=["otp"], jti="outage-jti"
    )
    # Should not raise — fail open.
    await ar._claim_recovery_token_single_use(session_store, token)


@pytest.mark.asyncio
async def test_claim_single_use_falls_back_to_session_id():
    """If jti is absent, fall back to session_id as the dedup key."""
    session_store = MagicMock()
    client = MagicMock()
    client.set = AsyncMock(return_value=True)
    session_store._get_client = AsyncMock(return_value=client)

    token = _mint_unsigned_supabase_token(
        amr_methods=["otp"], jti=None, session_id="sess-1"
    )
    await ar._claim_recovery_token_single_use(session_store, token)
    args, _ = client.set.call_args
    assert args[0] == "auth:recovery:used:sess-1"


@pytest.mark.asyncio
async def test_claim_single_use_no_dedup_id_fails_open():
    """No jti AND no session_id: log and fail open. Can't dedup
    without a stable id."""
    session_store = MagicMock()
    client = MagicMock()
    client.set = AsyncMock(return_value=True)
    session_store._get_client = AsyncMock(return_value=client)

    payload = {
        "sub": "sb-1",
        "aud": "authenticated",
        "iat": int(time.time()),
        "amr": [{"method": "otp"}],
    }
    token = _jwt.encode(payload, "k", algorithm="HS256")
    # Should not raise — nothing to dedup on.
    await ar._claim_recovery_token_single_use(session_store, token)
    # Redis never called.
    client.set.assert_not_called()


# ── 5. End-to-end via the route ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reset_password_rejects_password_session_token(monkeypatch):
    """End-to-end: a caller sending a password-session access token
    receives 401 and the password is NOT updated."""
    from services.admin.app import auth_routes
    from services.admin.app.auth_routes import ResetPasswordRequest

    # Supabase returns a valid user for this token (signature OK).
    fake_user = SimpleNamespace(id="sb-user-1", email="victim@example.com")
    fake_user_response = SimpleNamespace(user=fake_user)
    fake_sb = SimpleNamespace(
        auth=SimpleNamespace(get_user=lambda _t: fake_user_response)
    )
    monkeypatch.setattr(auth_routes, "get_supabase", lambda: fake_sb)

    password_token = _mint_unsigned_supabase_token(amr_methods=["password"])

    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None

    session_store = MagicMock()

    request = MagicMock()
    request.headers.get = MagicMock(return_value=f"Bearer {password_token}")

    with pytest.raises(HTTPException) as exc:
        await auth_routes.reset_password.__wrapped__(
            payload=ResetPasswordRequest(new_password="NewStrongPass-123"),
            request=request,
            db=db,
            session_store=session_store,
        )
    assert exc.value.status_code == 401
    # CRITICAL: the DB was never touched to update password_hash.
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_reset_password_accepts_fresh_otp_token(monkeypatch):
    """Happy path: a freshly-minted OTP/recovery token passes all gates
    and the password update proceeds."""
    from services.admin.app import auth_routes
    from services.admin.app.auth_routes import ResetPasswordRequest

    fake_user = SimpleNamespace(id="sb-user-1", email="legit@example.com")
    fake_user_response = SimpleNamespace(user=fake_user)
    # Stub out admin.update_user_by_id (supabase sync call).
    admin_ns = SimpleNamespace(
        update_user_by_id=lambda _uid, _body: None,
    )
    fake_sb = SimpleNamespace(
        auth=SimpleNamespace(
            get_user=lambda _t: fake_user_response,
            admin=admin_ns,
        )
    )
    monkeypatch.setattr(auth_routes, "get_supabase", lambda: fake_sb)

    recovery_token = _mint_unsigned_supabase_token(amr_methods=["otp"])

    # DB returns an active user with the matching email.
    user_row = SimpleNamespace(
        id="user-1",
        email="legit@example.com",
        password_hash="old-hash",
        status="active",
        token_version=0,
    )
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = user_row

    # Session store: single-use claim succeeds; revoke_all_for_user mock.
    session_store = MagicMock()
    client = MagicMock()
    client.set = AsyncMock(return_value=True)
    session_store._get_client = AsyncMock(return_value=client)
    session_store.revoke_all_for_user = AsyncMock(return_value=0)

    # Elevation revocation helper — make it a no-op.
    monkeypatch.setattr(
        auth_routes,
        "_revoke_all_elevation_tokens_for_user",
        AsyncMock(return_value=0),
    )

    request = MagicMock()
    request.headers.get = MagicMock(return_value=f"Bearer {recovery_token}")

    result = await auth_routes.reset_password.__wrapped__(
        payload=ResetPasswordRequest(new_password="FreshPass-1234"),
        request=request,
        db=db,
        session_store=session_store,
    )

    assert result == {"status": "success"}
    # Password was actually updated.
    assert user_row.password_hash != "old-hash"
    # token_version bumped.
    assert user_row.token_version == 1
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_reset_password_rejects_stale_otp_token(monkeypatch):
    """A recovery token issued 30 minutes ago is rejected even with
    correct amr."""
    from services.admin.app import auth_routes
    from services.admin.app.auth_routes import ResetPasswordRequest

    fake_user = SimpleNamespace(id="sb-user-1", email="u@e.com")
    fake_sb = SimpleNamespace(
        auth=SimpleNamespace(
            get_user=lambda _t: SimpleNamespace(user=fake_user)
        )
    )
    monkeypatch.setattr(auth_routes, "get_supabase", lambda: fake_sb)

    stale_token = _mint_unsigned_supabase_token(
        amr_methods=["otp"],
        iat_offset_seconds=-30 * 60,
    )

    db = MagicMock()
    session_store = MagicMock()
    request = MagicMock()
    request.headers.get = MagicMock(return_value=f"Bearer {stale_token}")

    with pytest.raises(HTTPException) as exc:
        await auth_routes.reset_password.__wrapped__(
            payload=ResetPasswordRequest(new_password="NewPassword-1234"),
            request=request,
            db=db,
            session_store=session_store,
        )
    assert exc.value.status_code == 401
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_reset_password_rejects_replayed_otp_token(monkeypatch):
    """Same recovery token used twice: second call is rejected with 401
    (single-use enforced via Redis jti dedup)."""
    from services.admin.app import auth_routes
    from services.admin.app.auth_routes import ResetPasswordRequest

    fake_user = SimpleNamespace(id="sb-user-1", email="u@e.com")
    fake_sb = SimpleNamespace(
        auth=SimpleNamespace(
            get_user=lambda _t: SimpleNamespace(user=fake_user)
        )
    )
    monkeypatch.setattr(auth_routes, "get_supabase", lambda: fake_sb)

    recovery_token = _mint_unsigned_supabase_token(
        amr_methods=["otp"], jti="single-use-test-jti"
    )

    db = MagicMock()
    session_store = MagicMock()
    client = MagicMock()
    # First call claims the key; second call gets None (already claimed).
    client.set = AsyncMock(side_effect=[True, None])
    session_store._get_client = AsyncMock(return_value=client)
    session_store.revoke_all_for_user = AsyncMock(return_value=0)

    user_row = SimpleNamespace(
        id="user-1",
        email="u@e.com",
        password_hash="old",
        status="active",
        token_version=0,
    )
    db.execute.return_value.scalar_one_or_none.return_value = user_row

    # Supabase admin sync call.
    admin_ns = SimpleNamespace(update_user_by_id=lambda _a, _b: None)
    fake_sb.auth.admin = admin_ns

    monkeypatch.setattr(
        auth_routes,
        "_revoke_all_elevation_tokens_for_user",
        AsyncMock(return_value=0),
    )

    request = MagicMock()
    request.headers.get = MagicMock(return_value=f"Bearer {recovery_token}")

    # First call succeeds.
    result = await auth_routes.reset_password.__wrapped__(
        payload=ResetPasswordRequest(new_password="NewPass1-1234"),
        request=request,
        db=db,
        session_store=session_store,
    )
    assert result == {"status": "success"}

    # Reset mock call counts for second attempt.
    db.commit.reset_mock()

    # Second call with the SAME token: 401.
    with pytest.raises(HTTPException) as exc:
        await auth_routes.reset_password.__wrapped__(
            payload=ResetPasswordRequest(new_password="NewPass2-1234"),
            request=request,
            db=db,
            session_store=session_store,
        )
    assert exc.value.status_code == 401
    db.commit.assert_not_called()


# ── 6. Defense-in-depth: the bad detail string never changes ────────────────


def test_generic_401_detail_does_not_leak_failure_mode():
    """All rejection paths must emit the same generic detail so an
    attacker can't distinguish 'wrong scope' from 'stale token' etc.
    This is deliberately paranoid — token-type oracle attacks are
    real."""
    cases = [
        _mint_unsigned_supabase_token(amr_methods=["password"]),  # wrong scope
        _mint_unsigned_supabase_token(
            amr_methods=["otp"], iat_offset_seconds=-30 * 60
        ),  # stale
        "not-a-jwt",  # malformed
    ]
    details = set()
    for token in cases:
        try:
            ar._enforce_recovery_token_scope(token)
        except HTTPException as exc:
            details.add(exc.detail)
    assert details == {"Invalid or expired recovery token"}


# ── 7. Constants pinned ─────────────────────────────────────────────────────


def test_max_age_window_is_15_minutes():
    """If someone lengthens this window without review, it weakens the
    stolen-token blast-radius defense. Pin it here."""
    assert ar._RECOVERY_TOKEN_MAX_AGE_SECONDS == 15 * 60


def test_allowed_amr_methods_excludes_password():
    """'password' MUST NOT be in the allowed set, ever."""
    assert "password" not in ar._RECOVERY_ALLOWED_AMR_METHODS
    assert "oauth" not in ar._RECOVERY_ALLOWED_AMR_METHODS
    assert "saml" not in ar._RECOVERY_ALLOWED_AMR_METHODS
    # Positive assertions: the actual recovery flows are present.
    assert "otp" in ar._RECOVERY_ALLOWED_AMR_METHODS
    assert "recovery" in ar._RECOVERY_ALLOWED_AMR_METHODS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
