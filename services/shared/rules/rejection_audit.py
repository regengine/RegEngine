"""Durable rejection-audit helper for the rules engine.

Why this exists
---------------
The pre-eval reject paths in EPCIS and the webhook routers all run with
``persist=False`` and then either raise an ``HTTPException(422)`` or call
``savepoint.rollback()`` to discard the in-flight transaction. As a
result, NO row is written to ``fsma.rule_evaluations`` for a rejected
event — the only trace of "we rejected event X for reason Y at time Z"
lives in stdout logs, which do not survive a process restart and do not
satisfy compliance defensibility.

This helper writes a single row to ``fsma.rule_rejections`` in a
separate, short-lived session that commits independently of the main
ingest transaction. The audit row survives even when the caller raises
``HTTPException(422)`` or rolls the outer savepoint back.

Compliance-defensibility contract
---------------------------------
Callers MUST invoke ``record_rejection`` BEFORE raising the 422 (or
before rolling back the outer savepoint) so the audit row reaches the
DB even if the request connection dies mid-rejection. The helper never
raises — a failed audit-write logs at error level and is captured to
Sentry, but does not block the reject decision. The product behavior
(reject the event) is more important than the audit row; without the
audit row we still hold an exception-log trail.

The helper is idempotent on ``(tenant_id, event_id, rule_id, created_at)``
via the table's UNIQUE constraint so retries do not duplicate rows.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def record_rejection(
    *,
    tenant_id: str,
    rule_id: Optional[str],
    rule_version: Optional[int],
    reasons: list[dict] | dict | str,
    event_id: Optional[str] = None,
    source: str = "preeval",
    enforcement_mode: Optional[str] = None,
) -> None:
    """Insert one durable rejection-audit row.

    Uses its own ``SessionLocal()`` session so the write commits
    independently of the caller's transaction. Caller's outer
    ``rollback()`` or ``HTTPException`` cannot wipe this row.

    Never raises — all exceptions are caught, logged, and reported to
    Sentry. The caller's reject decision is more important than the
    audit row; failing the audit must not turn a reject into an accept
    or a 500.

    The schema is intentionally minimal (see V080 migration):
    ``(id, tenant_id, event_id, rule_id, rule_version, result='rejected',
    reasons jsonb, source, enforcement_mode, created_at)``.
    """
    try:
        # Local import so test environments that stub out
        # ``shared.database`` (and SQLite-only test runs that monkey-patch
        # ``SessionLocal``) pick up the active value at call time.
        from shared.database import SessionLocal  # noqa: PLC0415
    except Exception:  # pragma: no cover  # noqa: BLE001
        # Two-package layout: ``services.shared`` vs ``shared``.
        try:
            from services.shared.database import SessionLocal  # type: ignore[no-redef]  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            logger.error("rule_rejection_audit_no_session_factory")
            _capture_sentry("rule_rejection_audit_no_session_factory", {})
            return

    if isinstance(reasons, (dict, list)):
        reasons_json = json.dumps(reasons, default=str)
    else:
        reasons_json = json.dumps({"reason": str(reasons)})

    session = None
    try:
        session = SessionLocal()
        from sqlalchemy import text  # noqa: PLC0415

        session.execute(
            text(
                """
                INSERT INTO fsma.rule_rejections (
                    id, tenant_id, event_id, rule_id, rule_version,
                    result, reasons, source, enforcement_mode, created_at
                ) VALUES (
                    :id, :tenant_id, :event_id, :rule_id, :rule_version,
                    'rejected', CAST(:reasons AS JSONB), :source,
                    :enforcement_mode, NOW()
                )
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "tenant_id": str(tenant_id),
                "event_id": _opt_str(event_id),
                "rule_id": _opt_str(rule_id),
                "rule_version": rule_version,
                "reasons": reasons_json,
                "source": source,
                "enforcement_mode": enforcement_mode
                or os.getenv(
                    "RULES_ENGINE_ENFORCE",
                    "off",
                ),
            },
        )
        session.commit()
    except Exception as err:  # noqa: BLE001
        # Best-effort: never fail the request because the audit row failed.
        try:
            if session is not None:
                session.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.error(
            "rule_rejection_audit_failed tenant=%s rule=%s err=%s",
            tenant_id,
            rule_id,
            err,
        )
        _capture_sentry(
            "rule_rejection_audit_failed",
            {
                "tenant_id": str(tenant_id),
                "rule_id": str(rule_id) if rule_id else None,
                "error": str(err),
            },
        )
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass


def _capture_sentry(message: str, extras: dict) -> None:
    try:
        import sentry_sdk  # noqa: PLC0415

        sentry_sdk.capture_message(
            message,
            level="error",
            extras=extras,
            tags={"subsystem": "rules_engine", "component": "rejection_audit"},
        )
    except Exception:  # noqa: BLE001
        # Sentry is best-effort. The structured log line above is the
        # durable record when Sentry itself is unavailable.
        logger.debug("sentry_capture_failed component=rejection_audit")


def reasons_from_summary(summary: Any) -> list[dict]:
    """Render an ``EvaluationSummary`` to a JSON-friendly reasons list.

    Defensive: tolerates duck-typed shapes so a future ``EvaluationSummary``
    refactor doesn't break the audit row.
    """
    out: list[dict] = []
    results = (
        getattr(summary, "critical_failures", None)
        or getattr(
            summary,
            "results",
            None,
        )
        or []
    )
    for r in results:
        result_value = getattr(r, "result", None)
        if result_value not in ("fail", "error"):
            continue
        out.append(
            {
                "rule_id": getattr(r, "rule_id", None),
                "rule_version": getattr(r, "rule_version", None),
                "severity": getattr(r, "severity", None),
                "result": result_value,
                "why_failed": getattr(r, "why_failed", None),
            }
        )
    if not out:
        out.append({"reason": "rule_violation"})
    return out
