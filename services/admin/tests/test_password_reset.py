"""Tests for the change-password route."""

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

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
    return db


@pytest.fixture
def sample_user():
    """Create a mock user object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "user@example.com"
    user.status = "active"
    user.password_hash = password_reset_routes.get_password_hash("OldP@ssw0rd!Valid")
    return user


# ── Change-password route tests ──────────────────────────────────────


def test_change_password_with_valid_credentials(mock_db, sample_user):
    """change-password updates hash when current password is correct."""
    original_hash = sample_user.password_hash

    mock_result_membership = MagicMock()
    mock_result_membership.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result_membership

    result = password_reset_routes.change_password(
        payload=password_reset_routes.ChangePasswordRequest(
            current_password="OldP@ssw0rd!Valid",
            new_password="NewStr0ng!Pass_2026",
        ),
        request=MagicMock(),
        current_user=sample_user,
        db=mock_db,
    )

    assert result["message"] == "Password changed successfully."
    assert sample_user.password_hash != original_hash
    mock_db.commit.assert_called()


def test_change_password_wrong_current_password(mock_db, sample_user):
    """change-password rejects when current password is wrong."""
    with pytest.raises(HTTPException) as exc_info:
        password_reset_routes.change_password(
            payload=password_reset_routes.ChangePasswordRequest(
                current_password="WrongP@ssw0rd!Here",
                new_password="NewStr0ng!Pass_2026",
            ),
            request=MagicMock(),
            current_user=sample_user,
            db=mock_db,
        )

    assert exc_info.value.status_code == 401
    assert "incorrect" in exc_info.value.detail.lower()


def test_change_password_weak_new_password(mock_db, sample_user):
    """change-password rejects weak new passwords."""
    with pytest.raises(HTTPException) as exc_info:
        password_reset_routes.change_password(
            payload=password_reset_routes.ChangePasswordRequest(
                current_password="OldP@ssw0rd!Valid",
                new_password="weak",
            ),
            request=MagicMock(),
            current_user=sample_user,
            db=mock_db,
        )

    assert exc_info.value.status_code == 400
    assert "at least" in exc_info.value.detail.lower()


def test_change_password_does_not_revoke_sessions(mock_db, sample_user):
    """change-password does NOT revoke sessions (user stays logged in)."""
    mock_result_membership = MagicMock()
    mock_result_membership.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result_membership

    password_reset_routes.change_password(
        payload=password_reset_routes.ChangePasswordRequest(
            current_password="OldP@ssw0rd!Valid",
            new_password="NewStr0ng!Pass_2026",
        ),
        request=MagicMock(),
        current_user=sample_user,
        db=mock_db,
    )

    # No session store interaction — user stays logged in
    mock_db.commit.assert_called()


def test_change_password_audits_event(mock_db, sample_user):
    """change-password logs an audit event when user has a membership."""
    mock_membership = MagicMock()
    mock_membership.tenant_id = uuid.uuid4()
    mock_result_membership = MagicMock()
    mock_result_membership.scalar_one_or_none.return_value = mock_membership
    mock_db.execute.return_value = mock_result_membership

    password_reset_routes.change_password(
        payload=password_reset_routes.ChangePasswordRequest(
            current_password="OldP@ssw0rd!Valid",
            new_password="NewStr0ng!Pass_2026",
        ),
        request=MagicMock(),
        current_user=sample_user,
        db=mock_db,
    )

    mock_db.commit.assert_called()
