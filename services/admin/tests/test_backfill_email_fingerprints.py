"""Tests for the one-off email fingerprint backfill script."""

from __future__ import annotations

import uuid

from app.auth_crypto import AuthCryptoService
from app.sqlalchemy_models import Base, UserEmailModel, UserModel
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.admin.scripts.backfill_email_fingerprints import backfill_email_fingerprints


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


def _make_backfill_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine, tables=[UserModel.__table__, UserEmailModel.__table__])
    return engine


def test_backfill_dry_run_counts_every_batch_without_writing():
    engine = _make_backfill_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    crypto = AuthCryptoService(hmac_secret="x" * 32)

    user_id = uuid.UUID("77777777-7777-4777-8777-777777777777")
    with session_factory() as session:
        session.add(UserModel(id=user_id, email="owner@example.com"))
        for i in range(3):
            session.add(
                UserEmailModel(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    email=f"pending{i}@example.com",
                    is_verified=True,
                )
            )
        session.commit()

    count = backfill_email_fingerprints(
        batch_size=1,
        dry_run=True,
        session_factory=session_factory,
        crypto_service=crypto,
    )

    # Three rows need fingerprints but batch_size is 1, so a dry run that
    # stops after the first batch would report 1 instead of 3.
    assert count == 3
    with session_factory() as session:
        rows = session.execute(select(UserEmailModel)).scalars().all()
    assert len(rows) == 3
    assert all(row.email_fingerprint is None for row in rows)
