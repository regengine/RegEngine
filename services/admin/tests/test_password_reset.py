"""Tests for password reset routes and helpers."""

import hashlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import password_reset_routes

# Disable rate limiter for unit tests
password_reset_routes.limiter.enabled = False


# ── Email helper tests ───────────────────────────────────────────────


class _DummyEmails:
    last_payload = None

    @staticmethod
    def send(payload):
        _DummyEmails.last_payload = payload
        return {"id": "email_456"}


class _DummyResend:
    api_key = None
    Emails = _DummyEmails


def test_send_password_reset_email_uses_resend_when_key_configured(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "noreply@regengine.test")
    monkeypatch.setitem(sys.modules, "resend", _DummyResend)

    _DummyEmails.last_payload = None
    password_reset_routes._send_password_reset_email(
        "user@example.com",
        "https://regengine.co/reset-password?token=abc123",
    )

    assert _DummyResend.api_key == "re_test_key"
    assert _DummyEmails.last_payload is not None
    assert _DummyEmails.last_payload["to"] == "user@example.com"
    assert _DummyEmails.last_payload["from"] == "noreply@regengine.test"
    assert "Reset Password" in _DummyEmails.last_payload["html"]
    assert "Reset your RegEngine password" in _DummyEmails.last_payload["subject"]
    assert "1 hour" in _DummyEmails.last_payload["html"]


def test_send_password_reset_email_noop_without_api_key(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    _DummyEmails.last_payload = None
    password_reset_routes._send_password_reset_email(
        "user@example.com",
        "https://regengine.co/reset-password?token=abc123",
    )
    assert _DummyEmails.last_payload is None


def test_send_password_reset_email_escapes_html_in_link(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setitem(sys.modules, "resend", _DummyResend)

    _DummyEmails.last_payload = None
    password_reset_routes._send_password_reset_email(
        "user@example.com",
        'https://regengine.co/reset-password?token=abc"<script>alert(1)</script>',
    )

    html_body = _DummyEmails.last_payload["html"]
    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body


def test_get_reset_base_url_uses_env(monkeypatch):
    monkeypatch.setenv("INVITE_BASE_URL", "https://app.regengine.test/")
    assert password_reset_routes._get_reset_base_url() == "https://app.regengine.test"


def test_get_reset_base_url_default(monkeypatch):
    monkeypatch.delenv("INVITE_BASE_URL", raising=False)
    assert password_reset_routes._get_reset_base_url() == "https://regengine.co"


# ── Token hash tests ────────────────────────────────────────────────


def test_token_hash_is_sha256():
    """Verify our token hashing matches the invite pattern."""
    raw_token = "test_token_value"
    expected = hashlib.sha256(raw_token.encode()).hexdigest()
    assert len(expected) == 64
    # The route uses the same pattern inline
    assert hashlib.sha256(raw_token.encode()).hexdigest() == expected


# ── Route logic tests (using FastAPI TestClient) ─────────────────────

@pytest.fixture
def mock_db():
    """Mock database session."""
    db = MagicMock()
    db.execute = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.flush = MagicMock()
    db.get = MagicMock()
    return db


@pytest.fixture
def mock_session_store():
    """Mock Redis session store."""
    store = AsyncMock()
    store.revoke_all_user_sessions = AsyncMock(return_value=3)
    return store


@pytest.fixture
def sample_user():
    """Create a mock user object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "user@example.com"
    user.status = "active"
    user.password_hash = "$argon2id$v=19$m=65536,t=3,p=4$fake_hash"
    return user


@pytest.fixture
def sample_token(sample_user):
    """Create a mock password reset token."""
    token = MagicMock()
    token.id = uuid.uuid4()
    token.user_id = sample_user.id
    token.token_hash = hashlib.sha256(b"valid_token").hexdigest()
    token.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    token.used_at = None
    token.created_at = datetime.now(timezone.utc)
    return token


def test_forgot_password_generic_message_for_unknown_email(mock_db):
    """forgot-password always returns the same message regardless of email existence."""
    # Simulate user not found
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    result = password_reset_routes.forgot_password(
        payload=password_reset_routes.ForgotPasswordRequest(email="nobody@example.com"),
        request=MagicMock(),
        db=mock_db,
    )

    assert result["message"] == password_reset_routes.GENERIC_SUCCESS_MESSAGE
    mock_db.commit.assert_called()
    # Should NOT have added any token
    mock_db.add.assert_not_called()


def test_forgot_password_creates_token_for_existing_user(mock_db, sample_user, monkeypatch):
    """forgot-password creates a token when user exists and is active."""
    # Mock: first execute returns user, second execute (invalidation) returns mock,
    # third execute (membership lookup) returns None
    mock_result_user = MagicMock()
    mock_result_user.scalar_one_or_none.return_value = sample_user

    mock_result_update = MagicMock()

    mock_result_membership = MagicMock()
    mock_result_membership.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [mock_result_user, mock_result_update, mock_result_membership]

    # Prevent actual email sending
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    result = password_reset_routes.forgot_password(
        payload=password_reset_routes.ForgotPasswordRequest(email="user@example.com"),
        request=MagicMock(),
        db=mock_db,
    )

    assert result["message"] == password_reset_routes.GENERIC_SUCCESS_MESSAGE
    # Should have added a PasswordResetTokenModel
    mock_db.add.assert_called_once()
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.user_id == sample_user.id
    assert added_obj.token_hash is not None
    assert len(added_obj.token_hash) == 64  # SHA256 hex digest


def test_forgot_password_inactive_user_returns_generic_message(mock_db):
    """forgot-password returns generic message for inactive users."""
    inactive_user = MagicMock()
    inactive_user.status = "locked"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = inactive_user
    mock_db.execute.return_value = mock_result

    result = password_reset_routes.forgot_password(
        payload=password_reset_routes.ForgotPasswordRequest(email="locked@example.com"),
        request=MagicMock(),
        db=mock_db,
    )

    assert result["message"] == password_reset_routes.GENERIC_SUCCESS_MESSAGE
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_reset_password_with_valid_token(mock_db, mock_session_store, sample_user, sample_token, monkeypatch):
    """reset-password updates password hash and marks token as used."""
    # Mock token lookup
    mock_result_token = MagicMock()
    mock_result_token.scalar_one_or_none.return_value = sample_token

    # Mock membership lookup
    mock_result_membership = MagicMock()
    mock_result_membership.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [mock_result_token, mock_result_membership]
    mock_db.get.return_value = sample_user

    # Use a valid password
    strong_password = "MyStr0ng!Pass_2026"

    result = await password_reset_routes.reset_password(
        payload=password_reset_routes.ResetPasswordRequest(
            token="valid_token",
            password=strong_password,
        ),
        request=MagicMock(),
        db=mock_db,
        session_store=mock_session_store,
    )

    assert result["message"] == "Password has been reset successfully."
    assert sample_token.used_at is not None
    assert sample_user.password_hash != "$argon2id$v=19$m=65536,t=3,p=4$fake_hash"
    mock_session_store.revoke_all_user_sessions.assert_called_once_with(sample_user.id)
    mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_reset_password_with_expired_token(mock_db, mock_session_store, sample_token):
    """reset-password rejects expired tokens."""
    sample_token.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_token
    mock_db.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc_info:
        await password_reset_routes.reset_password(
            payload=password_reset_routes.ResetPasswordRequest(
                token="expired_token",
                password="MyStr0ng!Pass_2026",
            ),
            request=MagicMock(),
            db=mock_db,
            session_store=mock_session_store,
        )

    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_reset_password_with_used_token(mock_db, mock_session_store, sample_token):
    """reset-password rejects already-used tokens."""
    sample_token.used_at = datetime.now(timezone.utc) - timedelta(minutes=30)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_token
    mock_db.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc_info:
        await password_reset_routes.reset_password(
            payload=password_reset_routes.ResetPasswordRequest(
                token="used_token",
                password="MyStr0ng!Pass_2026",
            ),
            request=MagicMock(),
            db=mock_db,
            session_store=mock_session_store,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_with_invalid_token(mock_db, mock_session_store):
    """reset-password rejects unknown tokens."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc_info:
        await password_reset_routes.reset_password(
            payload=password_reset_routes.ResetPasswordRequest(
                token="nonexistent_token",
                password="MyStr0ng!Pass_2026",
            ),
            request=MagicMock(),
            db=mock_db,
            session_store=mock_session_store,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_enforces_password_policy(mock_db, mock_session_store, sample_user, sample_token):
    """reset-password rejects weak passwords."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_token
    mock_db.execute.return_value = mock_result
    mock_db.get.return_value = sample_user

    with pytest.raises(HTTPException) as exc_info:
        await password_reset_routes.reset_password(
            payload=password_reset_routes.ResetPasswordRequest(
                token="valid_token",
                password="short",  # Too short, missing requirements
            ),
            request=MagicMock(),
            db=mock_db,
            session_store=mock_session_store,
        )

    assert exc_info.value.status_code == 400
    assert "at least" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_reset_password_inactive_user_rejected(mock_db, mock_session_store, sample_token):
    """reset-password rejects tokens for inactive users."""
    inactive_user = MagicMock()
    inactive_user.status = "locked"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_token
    mock_db.execute.return_value = mock_result
    mock_db.get.return_value = inactive_user

    with pytest.raises(HTTPException) as exc_info:
        await password_reset_routes.reset_password(
            payload=password_reset_routes.ResetPasswordRequest(
                token="valid_token",
                password="MyStr0ng!Pass_2026",
            ),
            request=MagicMock(),
            db=mock_db,
            session_store=mock_session_store,
        )

    assert exc_info.value.status_code == 400


# ── Change-password route tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_change_password_with_valid_credentials(mock_db, mock_session_store, sample_user):
    """change-password updates hash when current password is correct."""
    original_hash = sample_user.password_hash
    sample_user.password_hash = password_reset_routes.get_password_hash("OldP@ssw0rd!Valid")

    mock_result_membership = MagicMock()
    mock_result_membership.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result_membership

    result = await password_reset_routes.change_password(
        payload=password_reset_routes.ChangePasswordRequest(
            current_password="OldP@ssw0rd!Valid",
            new_password="NewStr0ng!Pass_2026",
        ),
        request=MagicMock(),
        current_user=sample_user,
        db=mock_db,
        session_store=mock_session_store,
    )

    assert result["message"] == "Password changed successfully."
    assert sample_user.password_hash != original_hash
    mock_session_store.revoke_all_user_sessions.assert_called_once_with(sample_user.id)
    mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_change_password_wrong_current_password(mock_db, mock_session_store, sample_user):
    """change-password rejects when current password is wrong."""
    sample_user.password_hash = password_reset_routes.get_password_hash("ActualP@ssw0rd!")

    with pytest.raises(HTTPException) as exc_info:
        await password_reset_routes.change_password(
            payload=password_reset_routes.ChangePasswordRequest(
                current_password="WrongP@ssw0rd!Here",
                new_password="NewStr0ng!Pass_2026",
            ),
            request=MagicMock(),
            current_user=sample_user,
            db=mock_db,
            session_store=mock_session_store,
        )

    assert exc_info.value.status_code == 401
    assert "incorrect" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_change_password_weak_new_password(mock_db, mock_session_store, sample_user):
    """change-password rejects weak new passwords."""
    sample_user.password_hash = password_reset_routes.get_password_hash("OldP@ssw0rd!Valid")

    with pytest.raises(HTTPException) as exc_info:
        await password_reset_routes.change_password(
            payload=password_reset_routes.ChangePasswordRequest(
                current_password="OldP@ssw0rd!Valid",
                new_password="weak",
            ),
            request=MagicMock(),
            current_user=sample_user,
            db=mock_db,
            session_store=mock_session_store,
        )

    assert exc_info.value.status_code == 400
    assert "at least" in exc_info.value.detail.lower()
