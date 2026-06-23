"""Tests for the one-off email fingerprint backfill script."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.admin.scripts.backfill_email_fingerprints import backfill_email_fingerprints

from app.auth_crypto import AuthCryptoService
from app.sqlalchemy_models import Base, UserEmailModel, UserModel


def test_backfill_email_fingerprints_uses_auth_crypto_keyed_fingerprint():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine, tables=[UserModel.__table__, UserEmailModel.__table__])
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    crypto = AuthCryptoService(hmac_secret="x" * 32)

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

    count = backfill_email_fingerprints(
        batch_size=10,
        session_factory=session_factory,
        crypto_service=crypto,
    )

    assert count == 1
    with session_factory() as session:
        rows = session.execute(select(UserEmailModel).order_by(UserEmailModel.email)).scalars().all()

    assert rows[0].email == "User@Example.com"
    assert rows[0].email_fingerprint == crypto.fingerprint_email("User@Example.com")
    assert rows[1].email == "done@example.com"
    assert rows[1].email_fingerprint == "already-set"
