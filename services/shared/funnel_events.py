"""Shared funnel event tracking utilities."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from enum import Enum
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger("funnel-events")


class FunnelEventName(str, Enum):
    SIGNUP_COMPLETED = "signup_completed"
    FIRST_INGEST = "first_ingest"
    FIRST_SCAN = "first_scan"
    FIRST_NLP_QUERY = "first_nlp_query"
    CHECKOUT_STARTED = "checkout_started"
    PAYMENT_COMPLETED = "payment_completed"


FUNNEL_STAGE_ORDER: tuple[str, ...] = (
    FunnelEventName.SIGNUP_COMPLETED.value,
    FunnelEventName.FIRST_INGEST.value,
    FunnelEventName.FIRST_SCAN.value,
    FunnelEventName.FIRST_NLP_QUERY.value,
    FunnelEventName.CHECKOUT_STARTED.value,
    FunnelEventName.PAYMENT_COMPLETED.value,
)

_VALID_EVENTS = set(FUNNEL_STAGE_ORDER)


def _safe_metadata(metadata: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if not metadata:
        return {}
    return dict(metadata)


def _session_dialect_name(db_session: Any) -> str:
    bind = getattr(db_session, "bind", None)
    dialect = getattr(bind, "dialect", None)
    name = getattr(dialect, "name", "") if dialect is not None else ""
    return str(name or "").lower()


def _open_session():
    from shared.database import SessionLocal

    return SessionLocal()


def emit_funnel_event(
    tenant_id: Optional[str],
    event_name: str,
    metadata: Optional[Mapping[str, Any]] = None,
    *,
    db_session: Any = None,
) -> bool:
    """Insert a tenant-scoped funnel event once. Returns True only on first insert."""
    tenant = str(tenant_id or "").strip()
    if not tenant:
        return False

    normalized_event = str(event_name or "").strip().lower()
    if normalized_event not in _VALID_EVENTS:
        raise ValueError(f"Unsupported funnel event: {event_name}")

    payload = _safe_metadata(metadata)

    owns_session = db_session is None
    session = db_session
    if owns_session:
        try:
            session = _open_session()
        except Exception as exc:  # pragma: no cover - environment-specific
            logger.warning("funnel_event_session_open_failed error=%s", str(exc))
            return False

    try:
        dialect_name = _session_dialect_name(session)
        if dialect_name == "sqlite":
            result = session.execute(
                text(
                    """
                    INSERT OR IGNORE INTO funnel_events (tenant_id, event_name, metadata)
                    VALUES (:tenant_id, :event_name, :metadata)
                    """
                ),
                {
                    "tenant_id": tenant,
                    "event_name": normalized_event,
                    "metadata": json.dumps(payload, sort_keys=True),
                },
            )
            inserted = bool(getattr(result, "rowcount", 0) > 0)
        else:
            result = session.execute(
                text(
                    """
                    INSERT INTO funnel_events (tenant_id, event_name, metadata)
                    VALUES (CAST(:tenant_id AS uuid), :event_name, CAST(:metadata AS jsonb))
                    ON CONFLICT (tenant_id, event_name) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant,
                    "event_name": normalized_event,
                    "metadata": json.dumps(payload, sort_keys=True),
                },
            )
            inserted = result.fetchone() is not None

        if owns_session:
            session.commit()

        return inserted
    except Exception as exc:
        if owns_session and session is not None:
            session.rollback()
        logger.warning(
            "funnel_event_emit_failed tenant_id=%s event_name=%s error=%s",
            tenant,
            normalized_event,
            str(exc),
        )
        return False
    finally:
        if owns_session and session is not None:
            session.close()


def get_funnel_stage_metrics(*, db_session: Any = None) -> list[dict[str, Any]]:
    """
    Return ordered stage metrics:
    [{name, count, conversion_from_previous_pct}, ...]
    """
    owns_session = db_session is None
    session = db_session
    if owns_session:
        try:
            session = _open_session()
        except Exception as exc:  # pragma: no cover - environment-specific
            logger.warning("funnel_metrics_session_open_failed error=%s", str(exc))
            return [
                {"name": stage, "count": 0, "conversion_from_previous_pct": 0.0}
                for stage in FUNNEL_STAGE_ORDER
            ]

    try:
        rows = session.execute(
            text(
                """
                SELECT event_name, CAST(COUNT(*) AS INTEGER) AS tenant_count
                FROM funnel_events
                GROUP BY event_name
                """
            )
        ).fetchall()
    except Exception as exc:
        logger.warning("funnel_metrics_query_failed error=%s", str(exc))
        rows = []
    finally:
        if owns_session and session is not None:
            session.close()

    counts: dict[str, int] = {stage: 0 for stage in FUNNEL_STAGE_ORDER}
    for row in rows:
        name = str(getattr(row, "event_name", row[0]) or "").strip().lower()
        if name in counts:
            count_value = getattr(row, "tenant_count", row[1] if len(row) > 1 else 0)
            counts[name] = int(count_value or 0)

    stages: list[dict[str, Any]] = []
    previous = None
    for stage_name in FUNNEL_STAGE_ORDER:
        count = counts.get(stage_name, 0)
        if previous is None:
            conversion = 100.0 if count > 0 else 0.0
        elif previous <= 0:
            conversion = 0.0
        else:
            conversion = round((count / previous) * 100, 2)

        stages.append(
            {
                "name": stage_name,
                "count": count,
                "conversion_from_previous_pct": conversion,
            }
        )
        previous = count

    return stages
