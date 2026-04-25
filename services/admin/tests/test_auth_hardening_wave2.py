"""Auth hardening wave 2 — tests for issues #1400, #1090, #1404, #1401, #1088, #1089.

Each test class maps to one GitHub issue:
  * TestSignupEmailOracle      — #1400: existing-email signup returns 202 not 409
  * TestSignupRace             — #1090: Supabase provisioned after db.flush, cleanup helper
  * TestRateLimitOracle        — #1404: rate-limit returns 401 not 429, no Retry-After
  * TestRefreshTenantStatus    — #1401: refresh re-queries tenant_status, never hardcodes
  * TestChangePasswordRevoke   — #1088: change-password revokes other sessions, keeps current
  * TestSupabaseSyncFail       — #1089: Supabase sync failure → 503, no DB commit
"""

from __future__ import annotations

import uuid as uuid_mod
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ── Shared helpers ─────────────────────────────────────────────────────────────


def _make_request(headers=None, client_host="127.0.0.1"):
    from starlette.requests import Request

    raw_headers = []
    for k, v in (headers or {"user-agent": "pytest"}).items():
        raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/test",
        "headers": raw_headers,
        "client": (client_host, 0),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
        "http_version": "1.1",
        "root_path": "",
        "state": {},
        "app": SimpleNamespace(
            state=SimpleNamespace(limiter=None, rate_limit_exceeded_handler=None),
        ),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def _valid_password() -> str:
    return "Correct-Horse-Battery-Staple-9!"


def _make_db_no_existing_user() -> MagicMock:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    db.add.return_value = None
    db.flush.return_value = None
    return db


def _make_session_store(*, fail_rate_limit: bool = False) -> MagicMock:
    ss = MagicMock()
    ss.create_session = AsyncMock(return_value=None)
    ss.delete_session = AsyncMock(return_value=None)
    ss.revoke_all_user_sessions = AsyncMock(return_value=0)
    ss.revoke_all_for_user = AsyncMock(return_value=0)

    # Redis client mock for rate-limit / lockout helpers
    redis_client = AsyncMock()
    if fail_rate_limit:
        # Return count >= EMAIL_ATTEMPT_LIMIT (5)
        redis_client.get = AsyncMock(return_value="5")
    else:
        redis_client.get = AsyncMock(return_value=None)
    redis_client.ttl = AsyncMock(return_value=0)
    redis_client.pipeline.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
    redis_client.pipeline.return_value.__aexit__ = AsyncMock(return_value=None)
    ss._get_client = AsyncMock(return_value=redis_client)
    return ss


# ── #1400 — Signup email enumeration oracle ───────────────────────────────────


class TestSignupEmailOracle:
    """Existing-email signup must return 202, not 409."""

    @pytest.mark.asyncio
    async def test_existing_email_returns_202(self, monkeypatch):
        from services.admin.app import auth_routes

        monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
        monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
        monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

        # Simulate an existing user found in DB
        db = MagicMock()
        existing_user = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = existing_user

        ss = _make_session_store()

        payload = auth_routes.RegisterRequest(
            email="existing@example.com",
            password=_valid_password(),
            tenant_name="AcmeCo",
        )
        result = await auth_routes.signup.__wrapped__(
            payload=payload,
            request=_make_request(),
            db=db,
            session_store=ss,
        )

        # Must be a JSONResponse (202) — NOT a TokenResponse or HTTPException
        from starlette.responses import JSONResponse
        assert isinstance(result, JSONResponse), (
            f"Expected JSONResponse for existing email, got {type(result)}"
        )
        assert result.status_code == 202

    @pytest.mark.asyncio
    async def test_existing_email_response_body_identical_to_new_email(self, monkeypatch):
        """The 202 body message must be a generic 'check your inbox' to avoid leakage."""
        from services.admin.app import auth_routes
        import json as json_mod

        monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
        monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
        monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = MagicMock()

        result = await auth_routes.signup.__wrapped__(
            payload=auth_routes.RegisterRequest(
                email="taken@example.com",
                password=_valid_password(),
                tenant_name="AcmeCo",
            ),
            request=_make_request(),
            db=db,
            session_store=_make_session_store(),
        )

        body = json_mod.loads(result.body)
        # Must contain a neutral message, not mention "already exists" or "taken"
        detail = body.get("detail", "").lower()
        assert "already exists" not in detail, "Response leaks email existence"
        assert "taken" not in detail, "Response leaks email existence"
        assert "inbox" in detail or "confirmation" in detail, (
            f"Expected neutral 'check inbox/confirmation' message, got: {detail}"
        )

    @pytest.mark.asyncio
    async def test_new_email_signup_returns_same_generic_body(self, monkeypatch):
        """A new email gets the same response shape as an existing email."""
        from services.admin.app import auth_routes
        import json as json_mod

        monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
        monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
        monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

        db = _make_db_no_existing_user()
        ss = _make_session_store()

        result = await auth_routes.signup.__wrapped__(
            payload=auth_routes.RegisterRequest(
                email="brand-new@example.com",
                password=_valid_password(),
                tenant_name="NewCo",
            ),
            request=_make_request(),
            db=db,
            session_store=ss,
        )

        from starlette.responses import JSONResponse
        assert isinstance(result, JSONResponse)
        assert result.status_code == 202
        assert set(json_mod.loads(result.body).keys()) == {"detail"}


# ── #1090 — Signup race: Supabase after flush ─────────────────────────────────


class TestSignupRace:
    """Supabase must be provisioned AFTER db.flush(), not before."""

    @pytest.mark.asyncio
    async def test_supabase_called_after_db_flush(self, monkeypatch):
        from services.admin.app import auth_routes
        from services.admin.app.auth import signup_router as _sr

        monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
        monkeypatch.setattr(_sr, "emit_funnel_event", lambda **k: None)

        call_order: list[str] = []

        db = _make_db_no_existing_user()
        original_flush = db.flush.side_effect
        db.flush.side_effect = lambda: call_order.append("db.flush")

        fake_sb_user = SimpleNamespace(id=str(uuid_mod.uuid4()))
        fake_sb_response = SimpleNamespace(user=fake_sb_user)
        fake_sb = MagicMock()

        def _create_user(data):
            call_order.append("supabase.create_user")
            return fake_sb_response

        fake_sb.auth.admin.create_user = _create_user
        monkeypatch.setattr(_sr, "get_supabase", lambda: fake_sb)

        ss = _make_session_store()

        await auth_routes.signup.__wrapped__(
            payload=auth_routes.RegisterRequest(
                email="race@example.com",
                password=_valid_password(),
                tenant_name="RaceCo",
            ),
            request=_make_request(),
            db=db,
            session_store=ss,
        )

        # First db.flush must appear before supabase.create_user
        assert "db.flush" in call_order, "db.flush was never called"
        assert "supabase.create_user" in call_order, "supabase.create_user was never called"
        first_flush_idx = next(i for i, s in enumerate(call_order) if s == "db.flush")
        sb_idx = call_order.index("supabase.create_user")
        assert first_flush_idx < sb_idx, (
            f"Supabase must be called AFTER db.flush; call order was {call_order}"
        )

    @pytest.mark.asyncio
    async def test_concurrent_signup_same_email_no_500(self, monkeypatch):
        """Second signup for same email returns 202, not 500."""
        from services.admin.app import auth_routes

        monkeypatch.setattr(auth_routes, "get_supabase", lambda: None)
        monkeypatch.setattr(auth_routes.AuditLogger, "log_event", lambda *a, **k: None)
        monkeypatch.setattr(auth_routes, "emit_funnel_event", lambda **k: None)

        # Simulate DB having an existing user (as if the first signup committed)
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = MagicMock()

        result = await auth_routes.signup.__wrapped__(
            payload=auth_routes.RegisterRequest(
                email="dup@example.com",
                password=_valid_password(),
                tenant_name="DupCo",
            ),
            request=_make_request(),
            db=db,
            session_store=_make_session_store(),
        )

        from starlette.responses import JSONResponse
        assert isinstance(result, JSONResponse)
        assert result.status_code == 202, (
            f"Concurrent signup should return 202, got {result.status_code}"
        )

    @pytest.mark.asyncio
    async def test_cleanup_supabase_user_swallows_errors(self, monkeypatch):
        """_cleanup_supabase_user must not raise even when Supabase errors."""
        from services.admin.app import auth_routes

        fake_sb = MagicMock()
        fake_sb.auth.admin.delete_user.side_effect = RuntimeError("supabase down")
        monkeypatch.setattr(auth_routes, "get_supabase", lambda: fake_sb)

        # Should not raise
        user_id = uuid_mod.uuid4()
        await auth_routes._cleanup_supabase_user(user_id)


# ── #1404 — Rate-limit oracle ─────────────────────────────────────────────────


class TestRateLimitOracle:
    """_check_email_rate_limit must return 401 (not 429) with no Retry-After."""

    @pytest.mark.asyncio
    async def test_rate_limited_email_returns_401(self, monkeypatch):
        from services.admin.app import auth_routes
        import asyncio

        # Suppress the artificial sleep so tests run fast
        monkeypatch.setattr(auth_routes.asyncio, "sleep", AsyncMock(return_value=None))

        ss = _make_session_store(fail_rate_limit=True)

        with pytest.raises(HTTPException) as exc_info:
            await auth_routes._check_email_rate_limit(ss, "victim@company.com")

        assert exc_info.value.status_code == 401, (
            f"Expected 401 for rate-limited email, got {exc_info.value.status_code}"
        )

    @pytest.mark.asyncio
    async def test_rate_limited_email_no_retry_after_header(self, monkeypatch):
        from services.admin.app import auth_routes

        monkeypatch.setattr(auth_routes.asyncio, "sleep", AsyncMock(return_value=None))

        ss = _make_session_store(fail_rate_limit=True)

        with pytest.raises(HTTPException) as exc_info:
            await auth_routes._check_email_rate_limit(ss, "victim@company.com")

        headers = exc_info.value.headers or {}
        assert "Retry-After" not in headers, (
            "Retry-After header must not be present (leaks rate-limit state)"
        )

    @pytest.mark.asyncio
    async def test_rate_limited_same_status_as_wrong_password(self, monkeypatch):
        """401 response detail must be indistinguishable from wrong-password."""
        from services.admin.app import auth_routes

        monkeypatch.setattr(auth_routes.asyncio, "sleep", AsyncMock(return_value=None))

        ss = _make_session_store(fail_rate_limit=True)

        with pytest.raises(HTTPException) as exc_info:
            await auth_routes._check_email_rate_limit(ss, "victim@company.com")

        # Same detail as wrong-password 401 in the login handler
        assert "Incorrect" in exc_info.value.detail or "password" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_non_rate_limited_email_passes_through(self):
        """Email below the limit must not raise."""
        from services.admin.app import auth_routes

        ss = _make_session_store(fail_rate_limit=False)
        # Should not raise
        await auth_routes._check_email_rate_limit(ss, "fine@example.com")


# ── #1401 — Refresh re-queries tenant_status ─────────────────────────────────


class TestRefreshTenantStatus:
    """refresh_session must re-query real tenant_status, never hardcode 'active'."""

    def _make_refresh_db(self, tenant_status: str = "suspended") -> MagicMock:
        db = MagicMock()

        user = MagicMock()
        user.id = uuid_mod.uuid4()
        user.email = "user@example.com"
        user.is_sysadmin = False
        user.token_version = 1
        db.get.side_effect = lambda model, id_: (
            user if model.__name__ == "UserModel" or str(model).endswith("UserModel") else None
        )

        tenant_id = uuid_mod.uuid4()
        membership = MagicMock()
        membership.tenant_id = tenant_id
        membership.is_active = True

        tenant_row = MagicMock()
        tenant_row.id = tenant_id
        tenant_row.status = tenant_status

        db.execute.return_value.scalars.return_value.all.return_value = [membership]
        db.commit.return_value = None
        return db, user, tenant_id, tenant_row

    @pytest.mark.asyncio
    async def test_refresh_uses_real_tenant_status_not_hardcoded(self, monkeypatch):
        from services.admin.app import auth_routes
        from services.admin.app.auth import refresh_router as _rr
        from services.admin.app.auth_utils import create_refresh_token, hash_token

        db, user, tenant_id, tenant_row = self._make_refresh_db(tenant_status="suspended")

        # Make db.get return the right object depending on what's requested
        def _db_get(model, id_):
            model_name = getattr(model, "__name__", str(model))
            if "User" in model_name:
                return user
            if "Tenant" in model_name:
                return tenant_row
            return None

        db.get.side_effect = _db_get

        raw_rt = create_refresh_token()
        token_hash = hash_token(raw_rt)
        session = MagicMock()
        session.id = uuid_mod.uuid4()
        session.user_id = user.id
        session.is_revoked = False
        from datetime import datetime, timezone, timedelta
        session.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        session.refresh_token_hash = token_hash

        ss = MagicMock()
        ss.claim_session_by_token = AsyncMock(return_value=session)
        ss.update_session = AsyncMock(return_value=None)

        # Patch create_access_token to capture what was passed
        captured: list[dict] = []

        def _capture_token(data, **kwargs):
            captured.append(dict(data))
            return "fake.access.token"

        monkeypatch.setattr(_rr, "create_access_token", _capture_token)

        payload = auth_routes.RefreshRequest(refresh_token=raw_rt)
        req = _make_request(headers={"authorization": "Bearer old.jwt.token"})

        await auth_routes.refresh_session.__wrapped__(
            payload=payload,
            request=req,
            db=db,
            session_store=ss,
        )

        assert captured, "create_access_token was never called"
        token_data = captured[-1]
        assert "tenant_status" in token_data, "tenant_status missing from token"
        assert token_data["tenant_status"] == "suspended", (
            f"Expected real tenant_status='suspended', got {token_data['tenant_status']!r}. "
            "Hardcoded 'active' detected!"
        )

    @pytest.mark.asyncio
    async def test_refresh_tenant_status_active_when_tenant_is_active(self, monkeypatch):
        from services.admin.app import auth_routes
        from services.admin.app.auth import refresh_router as _rr
        from services.admin.app.auth_utils import create_refresh_token, hash_token

        db, user, tenant_id, tenant_row = self._make_refresh_db(tenant_status="active")

        def _db_get(model, id_):
            model_name = getattr(model, "__name__", str(model))
            if "User" in model_name:
                return user
            if "Tenant" in model_name:
                return tenant_row
            return None

        db.get.side_effect = _db_get

        raw_rt = create_refresh_token()
        from datetime import datetime, timezone, timedelta
        session = MagicMock()
        session.id = uuid_mod.uuid4()
        session.user_id = user.id
        session.is_revoked = False
        session.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        session.refresh_token_hash = hash_token(raw_rt)

        ss = MagicMock()
        ss.claim_session_by_token = AsyncMock(return_value=session)
        ss.update_session = AsyncMock(return_value=None)

        captured: list[dict] = []

        def _capture_token(data, **kwargs):
            captured.append(dict(data))
            return "fake.access.token"

        monkeypatch.setattr(_rr, "create_access_token", _capture_token)

        await auth_routes.refresh_session.__wrapped__(
            payload=auth_routes.RefreshRequest(refresh_token=raw_rt),
            request=_make_request(headers={"authorization": "Bearer old.jwt.token"}),
            db=db,
            session_store=ss,
        )

        assert captured[-1]["tenant_status"] == "active"


# ── #1088 — Change-password revokes other sessions ────────────────────────────


class TestChangePasswordRevoke:
    """change_password must revoke all OTHER sessions; the caller's stays alive."""

    def _make_user(self, user_id=None) -> MagicMock:
        u = MagicMock()
        u.id = user_id or uuid_mod.uuid4()
        u.email = "user@example.com"
        u.status = "active"
        u.password_hash = "$argon2id$v=19$m=65536,t=3,p=4$test$test"
        u.token_version = 0
        return u

    @pytest.mark.asyncio
    async def test_change_password_revokes_other_sessions(self, monkeypatch):
        from services.admin.app import auth_routes
        from services.admin.app.auth import change_password_router as _cpr

        user = self._make_user()

        db = MagicMock()
        db.get.return_value = user
        db.commit.return_value = None

        monkeypatch.setattr(_cpr, "verify_password", lambda pw, h: True)
        monkeypatch.setattr(_cpr, "validate_password", lambda pw, user_context=None: None)
        monkeypatch.setattr(_cpr, "get_password_hash", lambda pw: "new_hash")
        # Supabase succeeds
        fake_sb = MagicMock()
        fake_sb.auth.admin.update_user_by_id.return_value = None
        monkeypatch.setattr(_cpr, "get_supabase", lambda: fake_sb)
        monkeypatch.setattr(_cpr, "_revoke_all_elevation_tokens_for_user", AsyncMock(return_value=0))

        ss = MagicMock()
        ss.revoke_all_user_sessions = AsyncMock(return_value=3)

        await auth_routes.change_password.__wrapped__(
            payload=auth_routes.ChangePasswordRequest(
                current_password="OldPass1!",
                new_password=_valid_password(),
            ),
            request=_make_request(),
            db=db,
            current_user=user,
            session_store=ss,
        )

        ss.revoke_all_user_sessions.assert_awaited_once()
        call_kwargs = ss.revoke_all_user_sessions.call_args
        # Check that except_session_id keyword arg was passed (may be None if no sid in token)
        assert "except_session_id" in (call_kwargs.kwargs or {}), (
            "revoke_all_user_sessions must be called with except_session_id kwarg"
        )

    @pytest.mark.asyncio
    async def test_change_password_keeps_current_session_when_sid_in_token(self, monkeypatch):
        """If the access token carries a 'sid' claim, that session must be excluded."""
        from services.admin.app import auth_routes
        from services.admin.app.auth import change_password_router as _cpr

        user = self._make_user()
        current_sid = uuid_mod.uuid4()

        db = MagicMock()
        db.get.return_value = user
        db.commit.return_value = None

        monkeypatch.setattr(_cpr, "verify_password", lambda pw, h: True)
        monkeypatch.setattr(_cpr, "validate_password", lambda pw, user_context=None: None)
        monkeypatch.setattr(_cpr, "get_password_hash", lambda pw: "new_hash")
        fake_sb = MagicMock()
        monkeypatch.setattr(_cpr, "get_supabase", lambda: fake_sb)
        monkeypatch.setattr(_cpr, "_revoke_all_elevation_tokens_for_user", AsyncMock(return_value=0))

        # decode_access_token returns a payload with 'sid'
        monkeypatch.setattr(
            _cpr,
            "decode_access_token",
            lambda token: {"sub": str(user.id), "sid": str(current_sid)},
        )

        ss = MagicMock()
        ss.revoke_all_user_sessions = AsyncMock(return_value=2)

        await auth_routes.change_password.__wrapped__(
            payload=auth_routes.ChangePasswordRequest(
                current_password="OldPass1!",
                new_password=_valid_password(),
            ),
            request=_make_request(headers={"authorization": "Bearer my.access.token"}),
            db=db,
            current_user=user,
            session_store=ss,
        )

        call_kwargs = ss.revoke_all_user_sessions.call_args
        passed_except = (call_kwargs.kwargs or {}).get("except_session_id")
        assert passed_except == current_sid, (
            f"Expected except_session_id={current_sid}, got {passed_except}"
        )


# ── #1089 — Supabase sync failure → 503, no DB commit ────────────────────────


class TestSupabaseSyncFail:
    """change_password must return 503 and NOT commit the DB if Supabase sync fails."""

    def _make_user(self) -> MagicMock:
        u = MagicMock()
        u.id = uuid_mod.uuid4()
        u.email = "user@example.com"
        u.status = "active"
        u.password_hash = "$argon2id$v=19$m=65536,t=3,p=4$test$test"
        u.token_version = 0
        return u

    @pytest.mark.asyncio
    async def test_supabase_sync_fail_returns_503(self, monkeypatch):
        from services.admin.app import auth_routes
        from services.admin.app.auth import change_password_router as _cpr

        user = self._make_user()

        db = MagicMock()
        db.get.return_value = user

        monkeypatch.setattr(_cpr, "verify_password", lambda pw, h: True)
        monkeypatch.setattr(_cpr, "validate_password", lambda pw, user_context=None: None)
        monkeypatch.setattr(_cpr, "get_password_hash", lambda pw: "new_hash")

        fake_sb = MagicMock()
        fake_sb.auth.admin.update_user_by_id.side_effect = RuntimeError("Supabase unavailable")
        monkeypatch.setattr(_cpr, "get_supabase", lambda: fake_sb)

        ss = MagicMock()
        ss.revoke_all_user_sessions = AsyncMock(return_value=0)
        monkeypatch.setattr(_cpr, "_revoke_all_elevation_tokens_for_user", AsyncMock(return_value=0))

        with pytest.raises(HTTPException) as exc_info:
            await auth_routes.change_password.__wrapped__(
                payload=auth_routes.ChangePasswordRequest(
                    current_password="OldPass1!",
                    new_password=_valid_password(),
                ),
                request=_make_request(),
                db=db,
                current_user=user,
                session_store=ss,
            )

        assert exc_info.value.status_code == 503, (
            f"Expected 503 on Supabase sync failure, got {exc_info.value.status_code}"
        )

    @pytest.mark.asyncio
    async def test_supabase_sync_fail_no_db_commit(self, monkeypatch):
        """DB must NOT be committed when Supabase sync fails (#1089)."""
        from services.admin.app import auth_routes
        from services.admin.app.auth import change_password_router as _cpr

        user = self._make_user()

        db = MagicMock()
        db.get.return_value = user

        monkeypatch.setattr(_cpr, "verify_password", lambda pw, h: True)
        monkeypatch.setattr(_cpr, "validate_password", lambda pw, user_context=None: None)
        monkeypatch.setattr(_cpr, "get_password_hash", lambda pw: "new_hash")

        fake_sb = MagicMock()
        fake_sb.auth.admin.update_user_by_id.side_effect = ConnectionError("timeout")
        monkeypatch.setattr(_cpr, "get_supabase", lambda: fake_sb)

        ss = MagicMock()
        monkeypatch.setattr(_cpr, "_revoke_all_elevation_tokens_for_user", AsyncMock(return_value=0))

        with pytest.raises(HTTPException) as exc_info:
            await auth_routes.change_password.__wrapped__(
                payload=auth_routes.ChangePasswordRequest(
                    current_password="OldPass1!",
                    new_password=_valid_password(),
                ),
                request=_make_request(),
                db=db,
                current_user=user,
                session_store=ss,
            )

        assert exc_info.value.status_code == 503
        db.commit.assert_not_called(), (
            "db.commit must NOT be called when Supabase sync fails"
        )

    @pytest.mark.asyncio
    async def test_supabase_sync_success_commits_db(self, monkeypatch):
        """When Supabase sync succeeds, the DB commit must still happen."""
        from services.admin.app import auth_routes
        from services.admin.app.auth import change_password_router as _cpr

        user = self._make_user()

        db = MagicMock()
        db.get.return_value = user
        db.commit.return_value = None

        monkeypatch.setattr(_cpr, "verify_password", lambda pw, h: True)
        monkeypatch.setattr(_cpr, "validate_password", lambda pw, user_context=None: None)
        monkeypatch.setattr(_cpr, "get_password_hash", lambda pw: "new_hash")

        fake_sb = MagicMock()
        fake_sb.auth.admin.update_user_by_id.return_value = None  # success
        monkeypatch.setattr(_cpr, "get_supabase", lambda: fake_sb)
        monkeypatch.setattr(_cpr, "_revoke_all_elevation_tokens_for_user", AsyncMock(return_value=0))

        ss = MagicMock()
        ss.revoke_all_user_sessions = AsyncMock(return_value=0)

        result = await auth_routes.change_password.__wrapped__(
            payload=auth_routes.ChangePasswordRequest(
                current_password="OldPass1!",
                new_password=_valid_password(),
            ),
            request=_make_request(),
            db=db,
            current_user=user,
            session_store=ss,
        )

        db.commit.assert_called_once()
        assert result == {"status": "success"}
