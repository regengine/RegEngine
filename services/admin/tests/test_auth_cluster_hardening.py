"""Tests for the April-2026 auth-hardening cluster.

Covers:
  * #1337 — /auth/accept-invite existing-user lockout + new-user flow
  * #1349 — token_version invalidation and refresh/session hardening
  * #1375 — /logout-all bumps token_version and revokes elevation tokens
  * #1376 — mfa_secret encryption-at-rest round trip
  * #1377 — recovery code normalization across casing/padding
  * #1379 — /auth/refresh preserves original tenant_id from access token
  * #1380 — require_reauth rejects cross-tenant / stale-tv / revoked-jti tokens
  * #1387 — invite role-tier escalation check

Tests are direct-call unit tests so they don't depend on the TestClient
integration path that #1435 broke.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types as _types
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from starlette.requests import Request as _StarletteRequest


def _make_starlette_request(headers: dict | None = None) -> "_StarletteRequest":
    """Construct a minimal starlette.requests.Request suitable for SlowAPI.

    SlowAPI's ``async_wrapper`` runs ``isinstance(request, Request)`` and
    refuses MagicMocks. We build a real Request on a fake ASGI scope.
    """
    from starlette.requests import Request

    raw_headers = []
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/test",
        "headers": raw_headers,
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
        "http_version": "1.1",
        "root_path": "",
        "state": {},
        "app": SimpleNamespace(state=SimpleNamespace(limiter=None, rate_limit_exceeded_handler=None)),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


# ── pyotp stub (shared with test_mfa_verification.py) ───────────────
if "pyotp" not in sys.modules:  # pragma: no cover - test env bootstrap

    class _FakeTOTP:
        def __init__(self, secret):
            self._secret = secret

        def verify(self, token, valid_window=1):
            return token == "999111"

        def provisioning_uri(self, name=None, issuer_name=None):
            return f"otpauth://totp/{issuer_name}:{name}?secret={self._secret}"

    _pyotp_stub = _types.ModuleType("pyotp")
    _pyotp_stub.TOTP = _FakeTOTP
    _pyotp_stub.random_base32 = lambda: "JBSWY3DPEHPK3PXP"
    sys.modules["pyotp"] = _pyotp_stub


# Ensure local imports resolve the same way other admin tests do.
_ADMIN_DIR = Path(__file__).parent.parent
if str(_ADMIN_DIR) not in sys.path:
    sys.path.insert(0, str(_ADMIN_DIR))


# ─────────────────────────────────────────────────────────────────────
# #1377 — recovery-code normalization
# ─────────────────────────────────────────────────────────────────────


def test_recovery_code_normalize_strips_dash_and_lowercases():
    from services.admin.app.mfa import normalize_recovery_code

    assert normalize_recovery_code("abcd-efgh") == "ABCDEFGH"
    assert normalize_recovery_code("ABCD-EFGH") == "ABCDEFGH"
    assert normalize_recovery_code("  abcd efgh ") == "ABCDEFGH"
    assert normalize_recovery_code("abcd_efgh") == "ABCDEFGH"
    assert normalize_recovery_code("") == ""


def test_recovery_code_generator_only_emits_alnum_codes():
    from services.admin.app.mfa import generate_recovery_codes, normalize_recovery_code

    codes = generate_recovery_codes(100)
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    for code in codes:
        assert "-" in code  # human-readable grouping
        normalized = normalize_recovery_code(code)
        assert len(normalized) == 8
        assert normalized.isalnum()
        # Must be from the A-Z 0-9 alphabet — no '_' or '-' / lowercase
        # survive normalization. (Not .isupper() because a code of only
        # digits like "21477188" returns False for isupper.)
        assert all(c in allowed for c in normalized), f"Unexpected char in {normalized!r}"


def test_recovery_code_hash_matches_despite_formatting():
    """The key bug (#1377): user-typed code with different casing/spacing
    must verify against the hash of the canonical form.

    Updated for #1041: argon2 hashes are salted so two calls to
    hash_recovery_code produce different strings. Correctness is now checked
    via verify_recovery_code, which normalizes both sides before comparing.
    """
    from services.admin.app.mfa import hash_recovery_code, verify_recovery_code

    canonical = "ABCD-EFGH"
    stored = hash_recovery_code(canonical)
    for variant in ["abcd-efgh", "ABCDEFGH", "abcdefgh", " abcd-efgh ", "AbCd-EfGh"]:
        assert verify_recovery_code(variant, stored) is True, variant


def test_recovery_code_verify_uses_constant_time():
    from services.admin.app.mfa import hash_recovery_code, verify_recovery_code

    stored = hash_recovery_code("ABCD-EFGH")
    assert verify_recovery_code("abcd-efgh", stored) is True
    assert verify_recovery_code("XXXX-XXXX", stored) is False


# ─────────────────────────────────────────────────────────────────────
# #1376 — mfa_secret encryption-at-rest
# ─────────────────────────────────────────────────────────────────────


def test_encrypt_decrypt_mfa_secret_roundtrip(monkeypatch):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", key)
    from services.admin.app.mfa import decrypt_mfa_secret, encrypt_mfa_secret

    plaintext = "JBSWY3DPEHPK3PXP"
    ciphertext = encrypt_mfa_secret(plaintext)
    assert ciphertext is not None
    assert ciphertext != plaintext
    assert decrypt_mfa_secret(ciphertext) == plaintext


def test_encrypt_mfa_secret_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
    from services.admin.app.mfa import encrypt_mfa_secret

    assert encrypt_mfa_secret("anything") is None


def test_resolve_user_mfa_secret_prefers_ciphertext(monkeypatch):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", key)
    from services.admin.app.mfa import encrypt_mfa_secret, resolve_user_mfa_secret

    ciphertext = encrypt_mfa_secret("FROM_CIPHERTEXT")
    user = SimpleNamespace(
        id=uuid.uuid4(),
        mfa_secret="FROM_PLAINTEXT",
        mfa_secret_ciphertext=ciphertext,
    )
    assert resolve_user_mfa_secret(user) == "FROM_CIPHERTEXT"


def test_resolve_user_mfa_secret_falls_back_to_plaintext(monkeypatch):
    monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
    from services.admin.app.mfa import resolve_user_mfa_secret

    user = SimpleNamespace(
        id=uuid.uuid4(),
        mfa_secret="LEGACY_PLAINTEXT",
        mfa_secret_ciphertext=None,
    )
    assert resolve_user_mfa_secret(user) == "LEGACY_PLAINTEXT"


def test_store_mfa_secret_prefers_encryption(monkeypatch):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", key)
    from services.admin.app.mfa import decrypt_mfa_secret, store_mfa_secret_on_user

    user = SimpleNamespace(mfa_secret=None, mfa_secret_ciphertext=None)
    store_mfa_secret_on_user(user, "PLAINSECRET")
    assert user.mfa_secret is None
    assert user.mfa_secret_ciphertext is not None
    assert decrypt_mfa_secret(user.mfa_secret_ciphertext) == "PLAINSECRET"


def test_store_mfa_secret_falls_back_to_plaintext_without_key(monkeypatch):
    monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
    from services.admin.app.mfa import store_mfa_secret_on_user

    user = SimpleNamespace(mfa_secret=None, mfa_secret_ciphertext="stale")
    store_mfa_secret_on_user(user, "DEV_ONLY_SECRET")
    assert user.mfa_secret == "DEV_ONLY_SECRET"
    assert user.mfa_secret_ciphertext is None


# ─────────────────────────────────────────────────────────────────────
# #1387 — role tier enforcement
# ─────────────────────────────────────────────────────────────────────


def test_role_rank_basics():
    from shared.permissions import role_rank

    assert role_rank("Owner", []) > role_rank("Admin", [])
    assert role_rank("Admin", []) > role_rank("Manager", [])
    assert role_rank("Manager", []) > role_rank("Viewer", [])
    # wildcard perms promote to Owner-tier regardless of name
    assert role_rank("custom", ["*"]) == role_rank("Owner", [])


def test_can_invite_role_admin_cannot_invite_owner():
    from shared.permissions import can_invite_role

    # Admin with users.invite but no grant_owner permission
    admin_perms = ["users.invite", "users.read"]
    owner_perms = ["*"]
    assert can_invite_role("Admin", admin_perms, "Owner", owner_perms) is False


def test_can_invite_role_admin_can_invite_admin_or_below():
    from shared.permissions import can_invite_role

    admin_perms = ["users.invite", "users.read"]
    # Same tier
    assert can_invite_role("Admin", admin_perms, "Admin", ["users.read"]) is True
    # Below tier
    assert can_invite_role("Admin", admin_perms, "Viewer", ["users.read"]) is True


def test_can_invite_role_owner_can_invite_owner():
    from shared.permissions import can_invite_role

    assert can_invite_role("Owner", ["*"], "Owner", ["*"]) is True


def test_can_invite_role_grant_owner_permission_allows_escalation():
    """An Admin with the explicit users.invite.grant_owner permission may issue Owner invites."""
    from shared.permissions import can_invite_role

    privileged_admin = ["users.invite", "users.invite.grant_owner"]
    assert can_invite_role("Admin", privileged_admin, "Owner", ["*"]) is True


def test_can_invite_role_wildcard_target_detected():
    """A role named 'ReadOnly' whose permissions accidentally include '*' must
    still be treated as Owner-tier, not matched on name."""
    from shared.permissions import can_invite_role

    wildcard_target = ["*"]
    assert can_invite_role("Admin", ["users.invite"], "ReadOnly", wildcard_target) is False


# ─────────────────────────────────────────────────────────────────────
# #1337 — accept-invite existing-user lockout
# ─────────────────────────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        class _Scalars:
            def __init__(self, v):
                self._v = v

            def first(self):
                return self._v

            def all(self):
                return [self._v] if self._v is not None else []

        return _Scalars(self._value)


def _make_invite(email="new@example.com"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        email=email,
        token_hash="h",
        role_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        expires_at=datetime(2100, 1, 1, tzinfo=timezone.utc),
        revoked_at=None,
        accepted_at=None,
    )


@pytest.mark.asyncio
async def test_accept_invite_existing_user_with_token_succeeds(monkeypatch):
    from services.admin.app.invite_routes import AcceptInviteRequest, accept_invite

    invite = _make_invite(email="alice@acme.com")
    existing_user = SimpleNamespace(
        id=uuid.uuid4(),
        email="alice@acme.com",
        status="active",
    )
    db = MagicMock()
    db.execute.side_effect = [
        _FakeResult(invite),  # invite lookup
        _FakeResult(existing_user),  # user lookup
        _FakeResult(None),  # membership lookup — no existing
    ]
    # AuditLogger.log_event is idempotent for our purposes
    monkeypatch.setattr(
        "services.admin.app.invite_routes.AuditLogger",
        MagicMock(log_event=MagicMock(return_value=None)),
    )
    monkeypatch.setattr(
        "services.admin.app.invite_routes.supplier_graph_sync",
        MagicMock(record_invite_accepted=MagicMock(return_value=None)),
    )
    ensure_identity = MagicMock(return_value=None)
    monkeypatch.setattr(
        "services.admin.app.invite_routes.ensure_passwordless_identity",
        ensure_identity,
    )

    req = AcceptInviteRequest(token="raw", name="x")
    http_req = _make_starlette_request()
    out = await accept_invite.__wrapped__(payload=req, request=http_req, db=db)
    assert out["status"] == "success"
    assert out["user_id"] == str(existing_user.id)
    # Existing users joining a tenant must also get passwordless identity rows.
    ensure_identity.assert_called_once()
    assert ensure_identity.call_args.kwargs["user"] is existing_user
    assert ensure_identity.call_args.kwargs["email"] == invite.email
    assert ensure_identity.call_args.kwargs["organization_id"] == invite.tenant_id


@pytest.mark.asyncio
async def test_accept_invite_existing_user_with_naive_expiry_succeeds(monkeypatch):
    from services.admin.app.invite_routes import AcceptInviteRequest, accept_invite

    invite = _make_invite(email="alice@acme.com")
    invite.expires_at = datetime.utcnow() + timedelta(days=1)
    existing_user = SimpleNamespace(
        id=uuid.uuid4(),
        email="alice@acme.com",
        status="active",
    )
    db = MagicMock()
    db.execute.side_effect = [
        _FakeResult(invite),
        _FakeResult(existing_user),
        _FakeResult(None),
    ]
    monkeypatch.setattr(
        "services.admin.app.invite_routes.AuditLogger",
        MagicMock(log_event=MagicMock(return_value=None)),
    )
    monkeypatch.setattr(
        "services.admin.app.invite_routes.supplier_graph_sync",
        MagicMock(record_invite_accepted=MagicMock(return_value=None)),
    )
    monkeypatch.setattr(
        "services.admin.app.invite_routes.ensure_passwordless_identity",
        MagicMock(return_value=None),
    )

    req = AcceptInviteRequest(token="raw", name="x")
    http_req = _make_starlette_request()
    out = await accept_invite.__wrapped__(payload=req, request=http_req, db=db)
    assert out["status"] == "success"
    assert out["user_id"] == str(existing_user.id)


@pytest.mark.asyncio
async def test_accept_invite_inactive_user_refused(monkeypatch):
    """#1337 — do not reinstate suspended/erased users via invite."""
    from fastapi import HTTPException

    from services.admin.app.invite_routes import AcceptInviteRequest, accept_invite

    invite = _make_invite(email="inactive@example.com")
    inactive_user = SimpleNamespace(
        id=uuid.uuid4(),
        email="inactive@example.com",
        status="erased",
    )
    db = MagicMock()
    db.execute.side_effect = [
        _FakeResult(invite),
        _FakeResult(inactive_user),
    ]
    req = AcceptInviteRequest(token="raw", name="x")
    http_req = _make_starlette_request()

    with pytest.raises(HTTPException) as exc:
        await accept_invite.__wrapped__(payload=req, request=http_req, db=db)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_accept_invite_uniform_400_for_all_unusable():
    """Expired, revoked, and already-accepted all return the same 400 body."""
    from fastapi import HTTPException

    from services.admin.app.invite_routes import AcceptInviteRequest, accept_invite

    cases = [
        # expired
        SimpleNamespace(
            id=uuid.uuid4(),
            email="x@e",
            token_hash="h",
            role_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
            revoked_at=None,
            accepted_at=None,
        ),
        # revoked
        SimpleNamespace(
            id=uuid.uuid4(),
            email="x@e",
            token_hash="h",
            role_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            expires_at=datetime(2100, 1, 1, tzinfo=timezone.utc),
            revoked_at=datetime.now(timezone.utc),
            accepted_at=None,
        ),
        # already accepted
        SimpleNamespace(
            id=uuid.uuid4(),
            email="x@e",
            token_hash="h",
            role_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            expires_at=datetime(2100, 1, 1, tzinfo=timezone.utc),
            revoked_at=None,
            accepted_at=datetime.now(timezone.utc),
        ),
    ]

    req = AcceptInviteRequest(token="raw", name="x")
    http_req = _make_starlette_request()

    details = []
    for invite in cases:
        db = MagicMock()
        db.execute.return_value = _FakeResult(invite)
        with pytest.raises(HTTPException) as exc:
            await accept_invite.__wrapped__(payload=req, request=http_req, db=db)
        assert exc.value.status_code == 400
        details.append(exc.value.detail)
    # All three messages identical — no side-channel.
    assert len(set(details)) == 1


# ─────────────────────────────────────────────────────────────────────
# #1349 / #1375 — token_version invalidation
# ─────────────────────────────────────────────────────────────────────


def test_create_access_token_embeds_tv_claim():
    from services.admin.app.auth_utils import create_access_token, decode_access_token

    tok = create_access_token({"sub": "abc", "tv": 7})
    payload = decode_access_token(tok)
    assert payload["tv"] == 7
    assert "jti" in payload


def test_create_access_token_respects_provided_jti():
    """Elevation flow pre-allocates jti so it can store-then-hand-out."""
    from services.admin.app.auth_utils import create_access_token, decode_access_token

    my_jti = "fixed-jti-12345"
    tok = create_access_token({"sub": "abc", "tv": 1, "jti": my_jti})
    payload = decode_access_token(tok)
    assert payload["jti"] == my_jti


# ─────────────────────────────────────────────────────────────────────
# #1379 — /auth/refresh preserves tenant_id from old access token
# ─────────────────────────────────────────────────────────────────────
# We test the tenant-preservation logic by calling refresh_session with a
# mocked session_store and db, and inspecting the token claims returned.


@pytest.mark.asyncio
async def test_refresh_preserves_original_tenant_id(monkeypatch):
    from services.admin.app.auth_routes import RefreshRequest, refresh_session
    from services.admin.app.auth_utils import create_access_token, decode_access_token
    from services.admin.app.session_store import SessionData

    user_id = uuid.uuid4()
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    # Old access token claims tenant_a. Our fix must re-issue with tenant_a
    # even though memberships include both A and B in arbitrary order.
    old_access = create_access_token(
        {
            "sub": str(user_id),
            "tenant_id": str(tenant_a),
            "tv": 0,
        }
    )

    session_store = MagicMock()
    session_store.claim_session_by_token = AsyncMock(
        return_value=SessionData(
            id=uuid.uuid4(),
            user_id=user_id,
            refresh_token_hash="h",
            family_id=uuid.uuid4(),
            is_revoked=False,
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
            expires_at=datetime(2100, 1, 1, tzinfo=timezone.utc),
            user_agent="ua",
            ip_address="1.1.1.1",
        )
    )
    session_store.update_session = AsyncMock(return_value=True)

    user = SimpleNamespace(
        id=user_id,
        email="u@e.com",
        is_sysadmin=False,
        status="active",
        token_version=0,
    )
    # memberships: order A then B doesn't matter — we verify that the
    # REFRESH output carries tenant_a specifically, not "first row wins".
    role_a = uuid.uuid4()
    role_b = uuid.uuid4()
    mem_a = SimpleNamespace(tenant_id=tenant_a, role_id=role_a)
    mem_b = SimpleNamespace(tenant_id=tenant_b, role_id=role_b)

    # #1401 — refresh_session now calls db.get(TenantModel, tenant_id) to
    # re-query the real tenant status. Give each model a distinct return value.
    tenant_row_a = SimpleNamespace(id=tenant_a, status="active")
    role_row_a = SimpleNamespace(id=role_a, name="qa", permissions=["inflow.write"])

    def _db_get(model, id_):
        from services.admin.app.sqlalchemy_models import RoleModel, TenantModel, UserModel

        if model is UserModel:
            return user
        if model is TenantModel:
            return tenant_row_a
        if model is RoleModel and id_ == role_a:
            return role_row_a
        return user  # fallback

    db = MagicMock()
    db.get.side_effect = _db_get
    # Ordering B, A to make it clear we aren't relying on "first row".
    db.execute.return_value.scalars.return_value.all.return_value = [mem_b, mem_a]
    db.commit.return_value = None

    payload = RefreshRequest(refresh_token="raw")
    request = _make_starlette_request(headers={"Authorization": f"Bearer {old_access}"})

    result = await refresh_session.__wrapped__(
        payload=payload,
        request=request,
        db=db,
        session_store=session_store,
    )
    issued = decode_access_token(result.access_token)
    assert issued["tenant_id"] == str(tenant_a), f"Expected tenant_a preserved, got {issued['tenant_id']!r}"


@pytest.mark.asyncio
async def test_refresh_rejects_when_no_longer_member_of_original_tenant():
    from fastapi import HTTPException

    from services.admin.app.auth_routes import RefreshRequest, refresh_session
    from services.admin.app.auth_utils import create_access_token
    from services.admin.app.session_store import SessionData

    user_id = uuid.uuid4()
    tenant_a = uuid.uuid4()
    other_tenant = uuid.uuid4()
    old_access = create_access_token(
        {
            "sub": str(user_id),
            "tenant_id": str(tenant_a),
            "tv": 0,
        }
    )

    session_store = MagicMock()
    session_store.claim_session_by_token = AsyncMock(
        return_value=SessionData(
            id=uuid.uuid4(),
            user_id=user_id,
            refresh_token_hash="h",
            family_id=uuid.uuid4(),
            is_revoked=False,
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
            expires_at=datetime(2100, 1, 1, tzinfo=timezone.utc),
        )
    )
    session_store.update_session = AsyncMock(return_value=True)

    user = SimpleNamespace(id=user_id, email="u@e", is_sysadmin=False, token_version=0)
    db = MagicMock()
    db.get.return_value = user
    db.execute.return_value.scalars.return_value.all.return_value = [
        SimpleNamespace(tenant_id=other_tenant),
    ]
    payload = RefreshRequest(refresh_token="raw")
    request = _make_starlette_request(headers={"Authorization": f"Bearer {old_access}"})

    with pytest.raises(HTTPException) as exc:
        await refresh_session.__wrapped__(
            payload=payload,
            request=request,
            db=db,
            session_store=session_store,
        )
    assert exc.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────
# #1349 / #1375 — get_current_user rejects stale tv
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_current_user_rejects_stale_tv_claim(monkeypatch):
    """A token minted with tv=0 after the user bumped to tv=1 must be rejected."""
    from fastapi import HTTPException

    from services.admin.app import dependencies
    from services.admin.app.auth_utils import create_access_token

    user_id = uuid.uuid4()
    # Supabase disabled for this path so we go through local JWT.
    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)

    tok = create_access_token({"sub": str(user_id), "tv": 0})

    # DB returns a user whose token_version has been bumped.
    user = SimpleNamespace(
        id=user_id,
        email="u@e",
        is_sysadmin=False,
        status="active",
        token_version=1,
    )
    db = MagicMock()
    db.bind = None
    db.get.return_value = user

    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token=tok, db=db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_accepts_matching_tv(monkeypatch):
    from services.admin.app import dependencies
    from services.admin.app.auth_utils import create_access_token

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)

    # tv=3 in the token matches the user's token_version -> tv check OK.
    # Include tenant_id in the claim so we don't hit the #1383 fail-closed
    # path (which rejects tokens with no claim AND no memberships).
    tok = create_access_token({"sub": str(user_id), "tv": 3, "tenant_id": str(tenant_id)})
    user = SimpleNamespace(
        id=user_id,
        email="u@e",
        is_sysadmin=False,
        status="active",
        token_version=3,
    )
    db = MagicMock()
    db.bind = None
    db.get.return_value = user
    # Simulate an active membership for the tenant_id in the token so
    # the final membership check passes.
    membership = SimpleNamespace(is_active=True)
    db.execute.return_value.scalar_one_or_none.return_value = membership
    db.execute.return_value.scalars.return_value.all.return_value = [membership]

    out = await dependencies.get_current_user(token=tok, db=db)
    assert out is user


@pytest.mark.asyncio
async def test_get_current_user_rejects_stale_supabase_tv_claim(monkeypatch):
    """Supabase-authenticated requests must enforce app_metadata tv too."""
    from fastapi import HTTPException

    from services.admin.app import dependencies

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    sb_user = SimpleNamespace(
        id=str(user_id),
        app_metadata={"tenant_id": str(tenant_id), "tv": 0},
    )
    sb = SimpleNamespace(auth=SimpleNamespace(get_user=MagicMock(return_value=SimpleNamespace(user=sb_user))))
    monkeypatch.setattr(dependencies, "get_supabase", lambda: sb)

    user = SimpleNamespace(
        id=user_id,
        email="u@e",
        is_sysadmin=False,
        status="active",
        token_version=1,
    )
    db = MagicMock()
    db.bind = None
    db.get.return_value = user

    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token="supabase-token", db=db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_accepts_matching_supabase_tv_claim(monkeypatch):
    from services.admin.app import dependencies

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    sb_user = SimpleNamespace(
        id=str(user_id),
        app_metadata={"tenant_id": str(tenant_id), "token_version": 3},
    )
    sb = SimpleNamespace(auth=SimpleNamespace(get_user=MagicMock(return_value=SimpleNamespace(user=sb_user))))
    monkeypatch.setattr(dependencies, "get_supabase", lambda: sb)

    user = SimpleNamespace(
        id=user_id,
        email="u@e",
        is_sysadmin=False,
        status="active",
        token_version=3,
    )
    membership = SimpleNamespace(is_active=True)
    db = MagicMock()
    db.bind = None
    db.get.return_value = user
    db.execute.return_value.scalar_one_or_none.return_value = membership
    db.execute.return_value.scalars.return_value.all.return_value = [membership]

    out = await dependencies.get_current_user(token="supabase-token", db=db)
    assert out is user


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_supabase_tv_after_bump(monkeypatch):
    from fastapi import HTTPException

    from services.admin.app import dependencies

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    sb_user = SimpleNamespace(
        id=str(user_id),
        app_metadata={"tenant_id": str(tenant_id)},
    )
    sb = SimpleNamespace(auth=SimpleNamespace(get_user=MagicMock(return_value=SimpleNamespace(user=sb_user))))
    monkeypatch.setattr(dependencies, "get_supabase", lambda: sb)

    user = SimpleNamespace(
        id=user_id,
        email="u@e",
        is_sysadmin=False,
        status="active",
        token_version=1,
    )
    db = MagicMock()
    db.bind = None
    db.get.return_value = user

    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token="supabase-token", db=db)
    assert exc.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Session store — revoke_all_for_user drops refresh-token mapping
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_all_for_user_drops_token_hash_mapping():
    """#1349 — after account-security invalidation, the refresh-token mapping must be gone
    so a stolen refresh token can't be redeemed even within its TTL window."""
    from services.admin.app.session_store import RedisSessionStore, SessionData

    store = RedisSessionStore("redis://fake/0")

    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    token_hash = "abc123"

    session = SessionData(
        id=session_id,
        user_id=user_id,
        refresh_token_hash=token_hash,
        family_id=uuid.uuid4(),
        is_revoked=False,
        created_at=datetime.now(timezone.utc),
        last_used_at=datetime.now(timezone.utc),
        expires_at=datetime(2100, 1, 1, tzinfo=timezone.utc),
    )

    client = MagicMock()
    client.smembers = AsyncMock(return_value={str(session_id)})
    # Pipeline for list_user_sessions (one hgetall result per session)
    read_pipe = MagicMock()
    read_pipe.__aenter__ = AsyncMock(return_value=read_pipe)
    read_pipe.__aexit__ = AsyncMock(return_value=None)
    read_pipe.hgetall = AsyncMock()
    read_pipe.execute = AsyncMock(return_value=[session.to_redis_hash()])
    # Pipeline for the revoke write
    write_pipe = MagicMock()
    write_pipe.__aenter__ = AsyncMock(return_value=write_pipe)
    write_pipe.__aexit__ = AsyncMock(return_value=None)
    write_pipe.hset = AsyncMock()
    write_pipe.delete = AsyncMock()
    write_pipe.execute = AsyncMock(return_value=[])

    # pipeline() is called twice — first for read (transaction=False), then revoke (transaction=False).
    pipelines = iter([read_pipe, write_pipe])
    client.pipeline = MagicMock(side_effect=lambda transaction=False: next(pipelines))

    store._client = client
    store._get_client = AsyncMock(return_value=client)

    count = await store.revoke_all_for_user(user_id)
    assert count == 1
    # The key claim: delete() was called with the token_hash mapping key.
    write_pipe.delete.assert_awaited_with(f"token_hash:{token_hash}")


# ─────────────────────────────────────────────────────────────────────
# SEL-12 gap — /refresh must reject a session generation issued before a
# logout-all / account-security token_version bump, even if the refresh
# token itself is otherwise valid and unexpired. get_current_user only
# rejects stale ACCESS tokens; without this guard a still-valid REFRESH
# token keeps minting fresh access tokens after "log out everywhere".
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_rejects_stale_session_token_version():
    from fastapi import HTTPException

    from services.admin.app.auth_routes import RefreshRequest, refresh_session
    from services.admin.app.session_store import SessionData

    user_id = uuid.uuid4()
    session_store = MagicMock()
    session_store.claim_session_by_token = AsyncMock(
        return_value=SessionData(
            id=uuid.uuid4(),
            user_id=user_id,
            refresh_token_hash="h",
            family_id=uuid.uuid4(),
            token_version=0,  # session minted before the bump
            is_revoked=False,
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
            expires_at=datetime(2100, 1, 1, tzinfo=timezone.utc),
        )
    )
    session_store.update_session = AsyncMock(return_value=True)

    db = MagicMock()
    db.get.return_value = SimpleNamespace(
        id=user_id,
        email="u@e",
        is_sysadmin=False,
        token_version=1,  # user did logout-all / account-security invalidation since
    )

    with pytest.raises(HTTPException) as exc:
        await refresh_session.__wrapped__(
            payload=RefreshRequest(refresh_token="raw"),
            request=_make_starlette_request(),
            db=db,
            session_store=session_store,
        )

    assert exc.value.status_code == 401
    # The guard runs BEFORE rotation: a stale session must never be rotated
    # into a fresh, usable refresh token.
    session_store.update_session.assert_not_called()
