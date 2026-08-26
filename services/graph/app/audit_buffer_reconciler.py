"""Reconciliation/replay job for ``audit_log_buffer`` (closes #2257 follow-up).

When the primary KDE_READ audit-log backend is unavailable, the buffered
failure policy in :mod:`audit_failure_policy` writes events to the durable
``audit_log_buffer`` Postgres table. This module replays those events to the
primary backend on a schedule.

Design
------
* Read up to ``batch_size`` rows where ``replayed_at IS NULL`` ordered by the
  partial index ``idx_audit_log_buffer_unreplayed`` (oldest first).
* For each row attempt to write to the primary audit log via a pluggable
  ``primary_writer`` callable. The default writer calls the global
  :class:`FSMAAuditLog` from :mod:`services.graph.app.fsma_audit` with
  ``require_persistence=True``.
* On *confirmed* success -> ``UPDATE ... SET replayed_at = now()``
  (idempotent: rows already stamped are filtered by the WHERE clause).
  A writer signals failure by raising or by returning ``False``; a
  plain return (legacy ``None``) still counts as success. #2829: the
  default writer used to return normally even when nothing reached
  Postgres, so rows were stamped replayed and the buffered evidence was
  lost with every counter reading clean.
* On failure AND ``replay_attempts < max_attempts`` -> ``UPDATE ... SET
  replay_attempts = replay_attempts + 1``; the row stays unreplayed and will
  be reattempted next run (exponential backoff is implicit in cron cadence).
* On failure AND ``replay_attempts >= max_attempts`` -> emit a structured
  ``audit_buffer_event_dead_lettered`` ERROR log with full context and
  *increment* the attempt counter so subsequent passes know it's been
  shelved. The row is NEVER deleted: forensic retention is the entire point
  of the buffer.
* If a row's age exceeds ``max_age_hours`` -> emit
  ``audit_buffer_age_warning`` WARNING regardless of replay outcome.

Idempotency
-----------
Running the reconciler twice on the same input is safe: the WHERE clause
``replayed_at IS NULL`` excludes already-replayed rows, the per-row UPDATE
runs in its own transaction with the row id as predicate, and the primary
audit-log path is itself best-effort/idempotent on event_id.

Operational runbook
-------------------
* Watch the ``audit_buffer_unreplayed_count`` log line emitted at end of
  every scan. Steady-state value should trend to zero.
* On ``audit_buffer_event_dead_lettered`` ERROR: pull the row by id from
  the buffer table, inspect ``payload`` + ``primary_error``, and either
  manually replay or document the loss.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import structlog
from sqlalchemy import text

logger = structlog.get_logger("audit_buffer_reconciler")

# Env knobs
ENV_INTERVAL_SECONDS = "AUDIT_BUFFER_RECONCILE_INTERVAL_SECONDS"
DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes
DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_MAX_AGE_HOURS = 24


@dataclass
class ReconcileResult:
    """Counts emitted by a single reconciler pass."""

    scanned: int = 0
    replayed: int = 0
    failed_will_retry: int = 0
    dead_lettered: int = 0
    aged_warnings: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "replayed": self.replayed,
            "failed_will_retry": self.failed_will_retry,
            "dead_lettered": self.dead_lettered,
            "aged_warnings": self.aged_warnings,
        }


# ----------------------------------------------------------------------------
# Default primary writer
# ----------------------------------------------------------------------------


def _default_primary_writer(
    *,
    tenant_id: str,
    actor: str,
    event_type: str,
    payload: dict[str, Any],
    originally_failed_at: datetime,
) -> bool:
    """Default replay path: write to the FSMA audit log.

    The buffered events were generated from KDE_READ failures; we replay
    them as SYSTEM-actor entries tagged with the original
    ``originally_failed_at`` so the chain is auditable.

    #2829: this asks the audit log to *confirm* the write
    (``require_persistence=True``). Without it the call returned
    normally whether or not anything reached Postgres — an unconfigured
    engine returned immediately, and an exhausted retry budget only
    logged — so the reconciler stamped ``replayed_at`` on events that
    were never written and the buffer's whole purpose (forensic
    retention until the primary catches up) was defeated. If the primary
    is still unavailable this now raises and the caller increments the
    attempt counter / dead-letters.
    """
    # Imported lazily so importing this module does not require the
    # graph app's full dependency tree.
    from services.graph.app.fsma_audit import (  # type: ignore
        FSMAAuditAction,
        FSMAAuditActorType,
        get_audit_log,
    )

    target_type = str(payload.get("target_type") or event_type)
    target_id = str(payload.get("target_id") or payload.get("resource_id") or payload.get("kde_id") or "unknown")
    correlation_id = payload.get("correlation_id")

    # Map our generic event_type onto the closest FSMAAuditAction.
    # FSMAAuditAction has no ACCESSED member, so the old
    # ``ACCESSED if hasattr(...) else EXTRACTED`` guard ALWAYS fell
    # through and relabelled every replayed KDE_READ event as EXTRACTED
    # — an extraction event in the FDA-facing trail that never happened.
    # Everything in this buffer comes from KDE_READ failures
    # (audit_failure_policy is the only producer), so KDE_READ is the
    # honest default; a future producer whose event_type names a real
    # action ("exported", "traced", ...) keeps that action.
    action = getattr(
        FSMAAuditAction,
        str(event_type or "").strip().upper(),
        FSMAAuditAction.KDE_READ,
    )

    get_audit_log().log(
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor=actor,
        actor_type=FSMAAuditActorType.SYSTEM,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        # #2829: fail loudly rather than pretending the replay landed.
        require_persistence=True,
        # Stash the replay metadata so an investigator can correlate.
        replayed_from_buffer=True,
        originally_failed_at=originally_failed_at.isoformat(),
        replayed_payload=payload,
    )
    return True


# ----------------------------------------------------------------------------
# DB session helper (overridable for tests)
# ----------------------------------------------------------------------------


def _open_session():
    """Return a SQLAlchemy session, or raise RuntimeError if unavailable."""
    from shared.database import get_db_safe  # type: ignore

    session = get_db_safe()
    if session is None:
        raise RuntimeError("audit_buffer_reconciler: no DB session available")
    return session


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


def reconcile_audit_buffer(
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_attempts_per_event: int = DEFAULT_MAX_ATTEMPTS,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    primary_writer: Optional[Callable[..., Any]] = None,
    session_factory: Optional[Callable[[], Any]] = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ReconcileResult:
    """Replay unreplayed ``audit_log_buffer`` rows to the primary backend.

    See module docstring for full semantics.

    Returns a :class:`ReconcileResult` with the per-pass counts; safe to
    invoke from a scheduler tick or from tests.
    """
    writer = primary_writer or _default_primary_writer
    open_session = session_factory or _open_session
    result = ReconcileResult()
    now = now_fn()
    age_threshold = now - timedelta(hours=max_age_hours)

    logger.info(
        "audit_buffer_reconcile_started",
        batch_size=batch_size,
        max_attempts_per_event=max_attempts_per_event,
        max_age_hours=max_age_hours,
    )

    session = open_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT id, tenant_id, actor, event_type, payload,
                       originally_failed_at, primary_error, replay_attempts,
                       created_at
                FROM audit_log_buffer
                WHERE replayed_at IS NULL
                ORDER BY created_at ASC
                LIMIT :limit
                """
            ),
            {"limit": batch_size},
        ).fetchall()

        result.scanned = len(rows)

        # Probe the unreplayed gauge while we're here — useful for
        # operators even when the batch doesn't drain it fully.
        unreplayed_total_row = session.execute(
            text("SELECT COUNT(*) FROM audit_log_buffer WHERE replayed_at IS NULL")
        ).fetchone()
        unreplayed_total = int(unreplayed_total_row[0]) if unreplayed_total_row else 0

        for row in rows:
            (
                row_id,
                tenant_id,
                actor,
                event_type,
                payload,
                originally_failed_at,
                primary_error,
                replay_attempts,
                _created_at,
            ) = row

            # Normalise originally_failed_at to a tz-aware datetime for
            # arithmetic (Postgres timestamptz already is, but a SQLite
            # test backend may hand back naive datetimes or even ISO
            # strings).
            ofa = originally_failed_at
            if isinstance(ofa, str):
                try:
                    ofa = datetime.fromisoformat(ofa)
                except ValueError:
                    ofa = None
            if isinstance(ofa, datetime) and ofa.tzinfo is None:
                ofa = ofa.replace(tzinfo=timezone.utc)

            if isinstance(ofa, datetime) and ofa < age_threshold:
                result.aged_warnings += 1
                logger.warning(
                    "audit_buffer_age_warning",
                    row_id=str(row_id),
                    tenant_id=tenant_id,
                    event_type=event_type,
                    age_hours=round((now - ofa).total_seconds() / 3600.0, 2),
                    replay_attempts=replay_attempts,
                )

            # Coerce payload to dict (jsonb -> dict in psycopg2; str on SQLite).
            payload_dict = payload
            if isinstance(payload_dict, str):
                import json

                try:
                    payload_dict = json.loads(payload_dict)
                except Exception:
                    payload_dict = {"_raw": payload_dict}
            if not isinstance(payload_dict, dict):
                payload_dict = {"_value": payload_dict}

            # #2829: a return is not proof of a write. The writer either
            # raises or reports its outcome; anything that is not an
            # explicit ``False`` (including the legacy ``None``) counts
            # as success, so custom writers keep working while the
            # default writer now confirms durability.
            replay_error: Optional[BaseException] = None
            try:
                outcome = writer(
                    tenant_id=tenant_id,
                    actor=actor,
                    event_type=event_type,
                    payload=payload_dict,
                    originally_failed_at=ofa,
                )
                if outcome is False:
                    replay_error = RuntimeError("primary writer reported an unconfirmed write")
            except Exception as exc:
                replay_error = exc

            if replay_error is not None:
                exc = replay_error
                # Failure: bump the attempt counter; dead-letter if exhausted.
                new_attempts = (replay_attempts or 0) + 1
                _update_attempts(session, row_id, new_attempts)

                if new_attempts >= max_attempts_per_event:
                    result.dead_lettered += 1
                    logger.error(
                        "audit_buffer_event_dead_lettered",
                        row_id=str(row_id),
                        tenant_id=tenant_id,
                        actor=actor,
                        event_type=event_type,
                        replay_attempts=new_attempts,
                        primary_error=primary_error,
                        replay_error=str(exc),
                        replay_error_type=type(exc).__name__,
                        originally_failed_at=(ofa.isoformat() if isinstance(ofa, datetime) else str(ofa)),
                        operator_action=(
                            "Inspect audit_log_buffer row by id; manually "
                            "replay or document loss. Row is retained for "
                            "forensics."
                        ),
                    )
                else:
                    result.failed_will_retry += 1
                    logger.warning(
                        "audit_buffer_event_replay_failed",
                        row_id=str(row_id),
                        tenant_id=tenant_id,
                        event_type=event_type,
                        replay_attempts=new_attempts,
                        replay_error=str(exc),
                    )
                continue

            # Success: stamp replayed_at.
            _stamp_replayed(session, row_id, now)
            result.replayed += 1
            logger.debug(
                "audit_buffer_event_replayed",
                row_id=str(row_id),
                tenant_id=tenant_id,
                event_type=event_type,
            )

        # Emit the final unreplayed gauge AFTER the batch's effects.
        post_unreplayed = max(0, unreplayed_total - result.replayed)

        logger.info(
            "audit_buffer_reconcile_finished",
            **result.as_dict(),
            unreplayed_remaining=post_unreplayed,
        )
        return result
    finally:
        try:
            session.close()
        except Exception:  # pragma: no cover — close best-effort
            pass


def _stamp_replayed(session: Any, row_id: Any, now: datetime) -> None:
    """Mark a row as successfully replayed.

    Each UPDATE runs in its own implicit transaction (we commit per row)
    so a failure on row N doesn't roll back rows 0..N-1. The
    ``replayed_at IS NULL`` predicate makes the operation idempotent: a
    concurrent reconciler that already stamped this row is a no-op here.
    """
    session.execute(
        text(
            """
            UPDATE audit_log_buffer
            SET replayed_at = :now,
                replay_attempts = replay_attempts + 1
            WHERE id = :id AND replayed_at IS NULL
            """
        ),
        {"now": now, "id": row_id},
    )
    session.commit()


def _update_attempts(session: Any, row_id: Any, new_attempts: int) -> None:
    """Increment ``replay_attempts`` after a failed replay."""
    session.execute(
        text(
            """
            UPDATE audit_log_buffer
            SET replay_attempts = :attempts
            WHERE id = :id AND replayed_at IS NULL
            """
        ),
        {"attempts": new_attempts, "id": row_id},
    )
    session.commit()


# ----------------------------------------------------------------------------
# Scheduler entrypoint
# ----------------------------------------------------------------------------


def get_interval_seconds() -> int:
    """Return the configured reconcile interval (seconds).

    Reads :data:`AUDIT_BUFFER_RECONCILE_INTERVAL_SECONDS` from env; falls
    back to :data:`DEFAULT_INTERVAL_SECONDS` (5 min). Invalid values
    fall back to the default with a WARNING.
    """
    raw = os.getenv(ENV_INTERVAL_SECONDS, "").strip()
    if not raw:
        return DEFAULT_INTERVAL_SECONDS
    try:
        n = int(raw)
        if n <= 0:
            raise ValueError("must be positive")
        return n
    except ValueError:
        logger.warning(
            "audit_buffer_reconcile_interval_invalid",
            value=raw,
            defaulting_to=DEFAULT_INTERVAL_SECONDS,
        )
        return DEFAULT_INTERVAL_SECONDS


def run_reconcile_tick() -> None:
    """Scheduler-friendly wrapper: never raises.

    Designed to be registered with APScheduler. Any exception is logged
    (so the job appears as EXECUTED rather than ERROR in the
    ``scheduler_job_runs`` table) and swallowed; the next tick will
    re-attempt.
    """
    try:
        reconcile_audit_buffer()
    except Exception as exc:  # noqa: BLE001 — telemetry must not crash
        logger.exception("audit_buffer_reconcile_tick_failed", error=str(exc))
