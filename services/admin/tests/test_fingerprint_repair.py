"""Tests for the v094 email-fingerprint startup repair (#2883)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.admin.app.auth.fingerprint_repair import repair_null_email_fingerprints
from services.admin.app.auth_crypto import AuthCryptoService
from services.admin.app.sqlalchemy_models import Base, UserEmailModel, UserModel

TEST_HMAC_SECRET = "unit-test-otp-hmac-secret-0123456789abcdef"  # pragma: allowlist secret


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine, tables=[UserModel.__table__, UserEmailModel.__table__])
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _seed_null_and_set_rows(session_factory):
    user_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    untouched_user_id = uuid.UUID("44444444-4444-4444-8444-444444444444")
    with session_factory() as session:
        session.add_all(
            [
                UserModel(id=user_id, email="User@Example.com"),
                UserModel(id=untouched_user_id, email="done@example.com"),
                UserEmailModel(
                    id=uuid.UUID("55555555-5555-4555-8555-555555555555"),
                    user_id=user_id,
                    email="User@Example.com",
                    is_verified=True,
                ),
                UserEmailModel(
                    id=uuid.UUID("66666666-6666-4666-8666-666666666666"),
                    user_id=untouched_user_id,
                    email="done@example.com",
                    email_fingerprint="already-set",
                    is_verified=True,
                ),
            ]
        )
        session.commit()
    return user_id


def test_repair_fills_null_fingerprints_when_secret_is_set(monkeypatch):
    monkeypatch.setenv("AUTH_OTP_HMAC_SECRET", TEST_HMAC_SECRET)
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)

    session_factory = _session_factory()
    _seed_null_and_set_rows(session_factory)
    crypto = AuthCryptoService(hmac_secret=TEST_HMAC_SECRET)

    count = repair_null_email_fingerprints(session_factory=session_factory)

    assert count == 1
    with session_factory() as session:
        rows = session.execute(select(UserEmailModel).order_by(UserEmailModel.email)).scalars().all()
    assert rows[0].email == "User@Example.com"
    assert rows[0].email_fingerprint == crypto.fingerprint_email("User@Example.com")
    assert rows[1].email_fingerprint == "already-set"

    # Re-run is a no-op once fingerprints exist.
    assert repair_null_email_fingerprints(session_factory=session_factory) == 0


def test_repair_is_noop_when_secret_unset_non_production(monkeypatch):
    monkeypatch.delenv("AUTH_OTP_HMAC_SECRET", raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)

    session_factory = _session_factory()
    _seed_null_and_set_rows(session_factory)

    count = repair_null_email_fingerprints(session_factory=session_factory)

    assert count == 0
    with session_factory() as session:
        rows = session.execute(select(UserEmailModel).order_by(UserEmailModel.email)).scalars().all()
    assert rows[0].email_fingerprint is None
    assert rows[1].email_fingerprint == "already-set"


def test_repair_raises_in_production_when_secret_unset(monkeypatch):
    monkeypatch.delenv("AUTH_OTP_HMAC_SECRET", raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)

    session_factory = _session_factory()
    _seed_null_and_set_rows(session_factory)

    with pytest.raises(RuntimeError, match="AUTH_OTP_HMAC_SECRET must be set in production"):
        repair_null_email_fingerprints(session_factory=session_factory)

    with session_factory() as session:
        rows = session.execute(select(UserEmailModel).order_by(UserEmailModel.email)).scalars().all()
    assert rows[0].email_fingerprint is None
