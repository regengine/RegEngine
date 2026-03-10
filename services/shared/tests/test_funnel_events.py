"""Tests for shared funnel event tracking utilities."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.shared.funnel_events import emit_funnel_event, get_funnel_stage_metrics


def _session():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    session.execute(
        text(
            """
            CREATE TABLE funnel_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                event_name TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (tenant_id, event_name)
            )
            """
        )
    )
    session.commit()
    return session


def test_emit_funnel_event_is_idempotent_per_tenant() -> None:
    session = _session()
    try:
        inserted_first = emit_funnel_event(
            tenant_id="tenant-a",
            event_name="first_ingest",
            metadata={"source": "webhook"},
            db_session=session,
        )
        inserted_second = emit_funnel_event(
            tenant_id="tenant-a",
            event_name="first_ingest",
            metadata={"source": "webhook"},
            db_session=session,
        )
        session.commit()

        total = session.execute(text("SELECT COUNT(*) FROM funnel_events")).scalar_one()
        assert inserted_first is True
        assert inserted_second is False
        assert total == 1
    finally:
        session.close()


def test_get_funnel_stage_metrics_reports_counts_and_conversion() -> None:
    session = _session()
    try:
        emit_funnel_event("tenant-1", "signup_completed", db_session=session)
        emit_funnel_event("tenant-2", "signup_completed", db_session=session)
        emit_funnel_event("tenant-1", "first_ingest", db_session=session)
        emit_funnel_event("tenant-1", "first_scan", db_session=session)
        session.commit()

        stages = get_funnel_stage_metrics(db_session=session)
        by_name = {stage["name"]: stage for stage in stages}

        assert by_name["signup_completed"]["count"] == 2
        assert by_name["signup_completed"]["conversion_from_previous_pct"] == 100.0

        assert by_name["first_ingest"]["count"] == 1
        assert by_name["first_ingest"]["conversion_from_previous_pct"] == 50.0

        assert by_name["first_scan"]["count"] == 1
        assert by_name["first_scan"]["conversion_from_previous_pct"] == 100.0

        assert by_name["first_nlp_query"]["count"] == 0
        assert by_name["first_nlp_query"]["conversion_from_previous_pct"] == 0.0
    finally:
        session.close()
