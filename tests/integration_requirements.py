"""Shared guards for integration tests with external dependencies."""

from __future__ import annotations

from typing import Any

import pytest


def sqlalchemy_session_or_skip(database_url: str | None, *, reason: str):
    """Return ``(engine, session)`` or skip when the configured DB is unreachable."""
    if not database_url:
        pytest.skip(f"{reason}: database URL is not set")

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"{reason}: {exc}")

    Session = sessionmaker(bind=engine)
    return engine, Session()


def psycopg_connect_or_skip(database_url: str | None, *, reason: str, **kwargs: Any):
    """Open a psycopg connection or skip when the configured DB is unreachable."""
    if not database_url:
        pytest.skip(f"{reason}: database URL is not set")

    import psycopg

    normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1).replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )
    try:
        return psycopg.connect(normalized, **kwargs)
    except (psycopg.OperationalError, psycopg.ProgrammingError) as exc:
        pytest.skip(f"{reason}: {exc}")


def start_container_or_skip(container: Any, *, reason: str):
    """Start a testcontainers container or skip when Docker is unavailable."""
    try:
        return container.start()
    except Exception as exc:
        pytest.skip(f"{reason}: {exc}")


def create_started_container_or_skip(container_cls: Any, *args: Any, reason: str, **kwargs: Any):
    """Construct and start a testcontainers container or skip when Docker is unavailable."""
    try:
        container = container_cls(*args, **kwargs)
        return container, container.start()
    except Exception as exc:
        pytest.skip(f"{reason}: {exc}")
