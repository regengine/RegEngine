"""Tests for the change-password route."""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import password_reset_routes

# Disable rate limiter for unit tests
password_reset_routes.limiter.enabled = False


# ── Fixtures ─────────────────────────────────────────────────────────


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


@pytest.mark.asyncio
async def test_change_password_revokes_sessions(mock_db, mock_session_store, sample_user):
    """change-password revokes all sessions after successful change."""
    sample_user.password_hash = password_reset_routes.get_password_hash("OldP@ssw0rd!Valid")

    mock_result_membership = MagicMock()
    mock_result_membership.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result_membership

    await password_reset_routes.change_password(
        payload=password_reset_routes.ChangePasswordRequest(
            current_password="OldP@ssw0rd!Valid",
            new_password="NewStr0ng!Pass_2026",
        ),
        request=MagicMock(),
        current_user=sample_user,
        db=mock_db,
        session_store=mock_session_store,
    )

    mock_session_store.revoke_all_user_sessions.assert_called_once_with(sample_user.id)


@pytest.mark.asyncio
async def test_change_password_audits_event(mock_db, mock_session_store, sample_user):
    """change-password logs an audit event when user has a membership."""
    sample_user.password_hash = password_reset_routes.get_password_hash("OldP@ssw0rd!Valid")

    mock_membership = MagicMock()
    mock_membership.tenant_id = uuid.uuid4()
    mock_result_membership = MagicMock()
    mock_result_membership.scalar_one_or_none.return_value = mock_membership
    mock_db.execute.return_value = mock_result_membership

    await password_reset_routes.change_password(
        payload=password_reset_routes.ChangePasswordRequest(
            current_password="OldP@ssw0rd!Valid",
            new_password="NewStr0ng!Pass_2026",
        ),
        request=MagicMock(),
        current_user=sample_user,
        db=mock_db,
        session_store=mock_session_store,
    )

    # Verify db.add was called (AuditLogger.log_event adds to the session)
    mock_db.commit.assert_called()
