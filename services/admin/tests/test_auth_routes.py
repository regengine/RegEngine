"""Tests for services/admin/app/auth_routes.py — issue #1333.

Covers the seven critical paths with FastAPI TestClient + mocked Supabase
and Redis so no live infrastructure is required.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — same pattern used by test_smoke_admin.py
# ---------------------------------------------------------------------------
_repo_root = Path(__file__).resolve().parents[3]
_service_dir = Path(__file__).resolve().parents[2]
for _p in (_repo_root, _service_dir):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Stub out heavy env-required imports before anything else loads.
import os
os.environ.setdefault("ADMIN_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-for-auth-routes-tests")
os.environ.setdefault("JWT_ALGORITHM", "HS256")

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(
    *,
    email: str = "alice@example.com",
    status: str = "active",
    is_sysadmin: bool = False,
    token_version: int = 0,
):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = email
    u.password_hash = "hashed"
    u.status = status
    u.is_sysadmin = is_sysadmin
    u.token_version = token_version
    u.last_login_at = None
    return u


def _make_tenant(*, tenant_id=None, name="Acme Corp"):
    t = MagicMock()
    t.id = tenant_id or uuid.uuid4()
    t.name = name
    t.slug = name.lower().replace(" ", "-")
    t.status = "active"
    return t


def _make_membership(user_id, tenant_id):
    m = MagicMock()
    m.user_id = user_id
    m.tenant_id = tenant_id
    return m


def _make_session_data(user_id):
    sd = MagicMock()
    sd.id = uuid.uuid4()
    sd.user_id = user_id
    sd.is_revoked = False
    from datetime import datetime, timedelta, timezone
    sd.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    return sd


# ---------------------------------------------------------------------------
# Shared mock-store fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_session_store():
    """Async-capable mock for RedisSessionStore."""
    store = MagicMock()
    # Rate-limit helpers — all return "no block"
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.ttl = AsyncMock(return_value=-1)
    redis_client.set = AsyncMock(return_value=True)
    redis_client.setex = AsyncMock(return_value=True)
    redis_client.delete = AsyncMock(return_value=1)
    mock_pipe = AsyncMock(
        execute=AsyncMock(return_value=[0, True]),
    )
    mock_pipe.incr = MagicMock()
    mock_pipe.expire = MagicMock()
    redis_client.pipeline = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_pipe),
        __aexit__=AsyncMock(return_value=False),
    ))
    store._get_client = AsyncMock(return_value=redis_client)
    store.create_session = AsyncMock(return_value=None)
    store.claim_session_by_token = AsyncMock()
    store.update_session = AsyncMock(return_value=None)
    store.mark_token_used = AsyncMock(return_value=None)
    store.check_token_reuse = AsyncMock(return_value=None)
    store.get_session = AsyncMock(return_value=None)
    store.revoke_all_for_family = AsyncMock(return_value=0)
    store.revoke_all_user_sessions = AsyncMock(return_value=0)
    store.delete_sessions_for_user = AsyncMock(return_value=0)
    store.get_sessions_for_user = AsyncMock(return_value=[])
    return store


# ---------------------------------------------------------------------------
# Test: 1 — Happy-path login
# ---------------------------------------------------------------------------

class TestLoginHappyPath:
    def test_login_returns_tokens(self, mock_session_store):
        user = _make_user()
        tenant = _make_tenant()
        mem = _make_membership(user.id, tenant.id)

        db_session = MagicMock()
        # First execute → user lookup; second execute → membership join
        db_session.execute.return_value.scalar_one_or_none.return_value = user
        db_session.execute.return_value.all.return_value = [(mem, tenant)]
        db_session.commit.return_value = None

        with (
            patch("services.admin.app.auth_routes.get_session", return_value=iter([db_session])),
            patch("services.admin.app.auth_routes.get_session_store", return_value=iter([mock_session_store])),
            patch("services.admin.app.auth_routes.verify_login", return_value=True),
            patch("services.admin.app.auth_routes.get_supabase", return_value=None),
            patch("services.admin.app.auth_routes.emit_funnel_event", new=AsyncMock()),
            patch("services.admin.app.auth_routes.AuditLogger.log_event", return_value=None),
        ):
            from services.admin.app.auth_routes import login
            import asyncio

            req = MagicMock()
            req.headers = {"User-Agent": "pytest"}
            req.client = MagicMock(host="127.0.0.1")
            req.state = MagicMock()

            payload = MagicMock()
            payload.email = "alice@example.com"
            payload.password = "correct-password"

            # Patch DB execute to return different things on successive calls
            call_count = [0]
            def side_effect(stmt):
                r = MagicMock()
                if call_count[0] == 0:
                    r.scalar_one_or_none.return_value = user
                    r.all.return_value = [(mem, tenant)]
                else:
                    r.scalar_one_or_none.return_value = user
                    r.all.return_value = [(mem, tenant)]
                call_count[0] += 1
                return r
            db_session.execute.side_effect = side_effect

            result = asyncio.get_event_loop().run_until_complete(
                login.__wrapped__(payload, req, db=db_session, session_store=mock_session_store)
            )
            assert result.access_token
            assert result.refresh_token
            assert result.user["email"] == user.email


# ---------------------------------------------------------------------------
# Test: 2 — Login with bad credentials → 401
# ---------------------------------------------------------------------------

class TestLoginBadCredentials:
    def test_wrong_password_returns_401(self, mock_session_store):
        from fastapi import HTTPException

        user = _make_user()
        db_session = MagicMock()
        db_session.execute.return_value.scalar_one_or_none.return_value = user

        with (
            patch("services.admin.app.auth_routes.verify_login", return_value=False),
            patch("services.admin.app.auth_routes.get_supabase", return_value=None),
        ):
            from services.admin.app.auth_routes import login
            import asyncio

            req = MagicMock()
            req.headers = {"User-Agent": "pytest"}
            req.client = MagicMock(host="127.0.0.1")

            payload = MagicMock()
            payload.email = "alice@example.com"
            payload.password = "wrong-password"

            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    login.__wrapped__(payload, req, db=db_session, session_store=mock_session_store)
                )
            assert exc_info.value.status_code == 401
            assert "Incorrect" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Test: 3 — Signup with existing email → 409
# ---------------------------------------------------------------------------

class TestSignupExistingEmail:
    def test_existing_email_returns_200_generic(self, mock_session_store):
        """Existing email returns 200 generic response (email enumeration guard).
        Uses __wrapped__ to bypass the SlowAPI rate-limit decorator."""
        import asyncio
        import services.admin.app.auth_routes as ar

        existing_user = _make_user()
        db_session = MagicMock()
        db_session.execute.return_value.scalar_one_or_none.return_value = existing_user

        with (
            patch("services.admin.app.auth_routes.get_supabase", return_value=None),
        ):
            req = MagicMock()
            req.headers = {"User-Agent": "pytest"}
            req.client = MagicMock(host="127.0.0.1")

            payload = MagicMock()
            payload.email = "alice@example.com"
            payload.password = "SomeP@ss1"
            payload.tenant_name = "Acme"
            payload.partner_tier = None

            result = asyncio.get_event_loop().run_until_complete(
                ar.signup.__wrapped__(payload, req, db=db_session, session_store=mock_session_store)
            )
            # Route returns generic JSONResponse(202) for existing emails (enumeration guard)
            assert result.status_code == 202


# ---------------------------------------------------------------------------
# Test: 3b — Signup duplicate-email race: DB flush fails → no Supabase call
# #1090: DB flush must happen BEFORE Supabase user creation so a concurrent
# duplicate email raises IntegrityError (→ 409) without creating an orphaned
# Supabase account.
# ---------------------------------------------------------------------------

class TestSignupDbFlushBeforeSupabase:
    def test_integrity_error_on_flush_returns_409_no_supabase_call(self, mock_session_store):
        """When db.flush() raises IntegrityError the route must return 409 and
        must NOT call supabase create_user.  Uses __wrapped__ to bypass the
        SlowAPI rate-limit decorator (same pattern as test_auth_cluster_hardening)."""
        import asyncio
        from fastapi import HTTPException
        from sqlalchemy.exc import IntegrityError
        import services.admin.app.auth_routes as ar

        db_session = MagicMock()
        # No existing user found by the pre-check query
        db_session.execute.return_value.scalar_one_or_none.return_value = None
        # flush raises IntegrityError (concurrent duplicate insert wins the race)
        db_session.flush.side_effect = IntegrityError("unique", {}, Exception())

        mock_sb = MagicMock()

        with (
            patch("services.admin.app.auth_routes.get_supabase", return_value=mock_sb),
            patch("services.admin.app.auth_routes.validate_password", return_value=None),
            patch("services.admin.app.auth_routes.get_password_hash", return_value="hashed"),
        ):
            req = MagicMock()
            req.headers = {"User-Agent": "pytest"}
            req.client = MagicMock(host="127.0.0.1")

            payload = MagicMock()
            payload.email = "race@example.com"
            payload.password = "SomeP@ss1"
            payload.tenant_name = "Acme"
            payload.partner_tier = None

            result = asyncio.get_event_loop().run_until_complete(
                ar.signup.__wrapped__(payload, req, db=db_session, session_store=mock_session_store)
            )

        assert result.status_code == 202
        # Supabase create_user must NOT have been called
        mock_sb.auth.admin.create_user.assert_not_called()


# ---------------------------------------------------------------------------
# Test: 4 — Password change revokes sessions
# ---------------------------------------------------------------------------

class TestChangePasswordRevokeSessions:
    def test_change_password_increments_token_version(self, mock_session_store):
        """change_password bumps token_version, which signals session revocation."""
        from fastapi import HTTPException

        user = _make_user(token_version=0)
        db_session = MagicMock()
        db_session.get.return_value = user
        db_session.commit.return_value = None

        with (
            patch("services.admin.app.auth_routes.verify_password", return_value=True),
            patch("services.admin.app.auth_routes.validate_password", return_value=None),
            patch("services.admin.app.auth_routes.get_password_hash", return_value="new-hash"),
            patch("services.admin.app.auth_routes.get_supabase", return_value=None),
            patch("services.admin.app.auth_routes._revoke_all_elevation_tokens_for_user", new=AsyncMock()),
        ):
            from services.admin.app.auth_routes import change_password
            import asyncio

            req = MagicMock()
            payload = MagicMock()
            payload.current_password = "OldPass1!"
            payload.new_password = "NewPass1!"

            asyncio.get_event_loop().run_until_complete(
                change_password.__wrapped__(
                    payload,
                    req,
                    db=db_session,
                    current_user=user,
                    session_store=mock_session_store,
                )
            )

            # token_version must have been incremented so old tokens are rejected
            assert user.token_version == 1
            assert user.password_hash == "new-hash"
            db_session.commit.assert_called()


# ---------------------------------------------------------------------------
# Test: 5 — Token refresh → 200 with new token
# ---------------------------------------------------------------------------

class TestTokenRefresh:
    def test_refresh_returns_new_access_token(self, mock_session_store):
        user = _make_user()
        tenant = _make_tenant()
        membership = _make_membership(user.id, tenant.id)
        sd = _make_session_data(user.id)

        mock_session_store.claim_session_by_token = AsyncMock(return_value=sd)
        mock_session_store.update_session = AsyncMock(return_value=None)

        db_session = MagicMock()
        db_session.get.return_value = user
        db_session.execute.return_value.scalars.return_value.all.return_value = [membership]

        with (
            patch("services.admin.app.auth_routes.decode_access_token", return_value={"tenant_id": None, "tid": None}),
            patch("services.admin.app.auth_routes.create_access_token", return_value="new-access-token"),
        ):
            from services.admin.app.auth_routes import refresh_session
            import asyncio

            req = MagicMock()
            req.headers = {"Authorization": "Bearer old-token", "User-Agent": "pytest"}
            req.client = MagicMock(host="127.0.0.1")

            payload = MagicMock()
            payload.refresh_token = "valid-refresh-token"

            result = asyncio.get_event_loop().run_until_complete(
                refresh_session.__wrapped__(payload, req, db=db_session, session_store=mock_session_store)
            )
            assert result.access_token == "new-access-token"


# ---------------------------------------------------------------------------
# Test: 6 — MFA verification happy path (TOTP)
# ---------------------------------------------------------------------------

class TestMFAVerificationHappyPath:
    def test_valid_totp_token_accepted(self, mock_session_store):
        """require_mfa accepts a TOTP token that pyotp verifies."""
        import sys
        import types as _types

        # Stub pyotp if not installed
        if "pyotp" not in sys.modules:
            stub = _types.ModuleType("pyotp")
            class _FakeTOTP:
                def __init__(self, secret): pass
                def verify(self, token, valid_window=1): return token == "888000"
            stub.TOTP = _FakeTOTP
            stub.random_base32 = lambda: "JBSWY3DPEHPK3PXP"
            sys.modules["pyotp"] = stub

        from services.admin.app.mfa import require_mfa
        import asyncio

        user = SimpleNamespace(id=uuid.uuid4(), email="alice@example.com", mfa_secret="TESTBASE32SECRET")
        with patch("services.admin.app.mfa.verify_totp", return_value=True):
            result = asyncio.get_event_loop().run_until_complete(
                require_mfa(
                    x_mfa_token="888000",
                    current_user=user,
                    db=MagicMock(),
                    session_store=mock_session_store,
                )
            )
        assert result == "888000"


# ---------------------------------------------------------------------------
# Test: 7 — MFA recovery code happy path
# ---------------------------------------------------------------------------

class TestMFARecoveryCodeHappyPath:
    def test_valid_recovery_code_accepted_and_consumed(self, mock_session_store):
        """require_mfa accepts XXXX-XXXX format recovery codes and marks them used."""
        import sys
        import types as _types

        if "pyotp" not in sys.modules:
            stub = _types.ModuleType("pyotp")
            class _FakeTOTP:
                def __init__(self, secret): pass
                def verify(self, token, valid_window=1): return False
            stub.TOTP = _FakeTOTP
            stub.random_base32 = lambda: "JBSWY3DPEHPK3PXP"
            sys.modules["pyotp"] = stub

        from services.admin.app.mfa import require_mfa
        import asyncio

        user = SimpleNamespace(id=uuid.uuid4(), email="alice@example.com", mfa_secret="TESTBASE32SECRET")

        from services.admin.app.mfa import hash_recovery_code

        recovery_row = MagicMock()
        recovery_row.used_at = None
        recovery_row.code_hash = hash_recovery_code("ABCD-EFGH")

        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = [recovery_row]

        result = asyncio.get_event_loop().run_until_complete(
            require_mfa(
                x_mfa_token="ABCD-EFGH",
                current_user=user,
                db=db,
                session_store=mock_session_store,
            )
        )
        assert result == "ABCD-EFGH"
        assert recovery_row.used_at is not None
        db.commit.assert_called_once()
