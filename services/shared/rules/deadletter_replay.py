"""Replay pass for ``fsma.rule_evaluation_deadletter`` (WS-8, #2709).

Rows land in the dead-letter when an evaluation record could not be
written even by the row-level salvage path (see ``engine._salvage_rows``).
This module re-attempts them into ``fsma.rule_evaluations``:

* Idempotent: the insert is ``ON CONFLICT (evaluation_id, tenant_id) DO
  NOTHING`` (the v079 unique index), so a row whose original insert
  actually landed is simply marked replayed.
* Bounded: ``replay_attempts`` increments per failed attempt; rows at
  ``_MAX_REPLAY_ATTEMPTS`` are parked (skipped by the query) with an
  error log so operators can repair them manually.
* Tenant-scoped: ``fsma.rule_evaluation_deadletter`` is FORCE RLS, so
  the all-tenants entry point iterates ``public.tenants`` and seeds the
  tenant GUC per tenant — the ``drain_all_tenants`` pattern (#2461).
"""

from __future__ import annotations

import json
import logging
from typing import Dict

from sqlalchemy import text

logger = logging.getLogger("rules-engine")

_MAX_REPLAY_ATTEMPTS = 10

_REPLAY_INSERT = text(
    "INSERT INTO fsma.rule_evaluations ("
    "    evaluation_id, tenant_id, event_id,"
    "    rule_id, rule_version, result,"
    "    why_failed, evidence_fields_inspected, confidence"
    ") VALUES ("
    "    :eval_id, :tenant_id, :event_id,"
    "    :rule_id, :rule_version, :result,"
    "    :why_failed, CAST(:evidence AS jsonb), :confidence"
    ") ON CONFLICT (evaluation_id, tenant_id) DO NOTHING"
)


def replay_deadletter_for_tenant(session, tenant_id: str, *, batch_size: int = 200) -> Dict[str, int]:
    """Attempt every pending dead-letter row for one tenant.

    Returns counters: ``attempted`` / ``replayed`` / ``failed`` /
    ``parked`` (rows that just exhausted their attempt budget).
    """
    rows = session.execute(
        text(
            "SELECT id, evaluation_id, event_id, rule_id, rule_version,"
            "       result, why_failed, evidence, confidence, replay_attempts"
            " FROM fsma.rule_evaluation_deadletter"
            " WHERE tenant_id = CAST(:tid AS uuid)"
            "   AND replayed_at IS NULL"
            "   AND replay_attempts < :max_attempts"
            " ORDER BY created_at"
            " LIMIT :lim"
        ),
        {"tid": tenant_id, "max_attempts": _MAX_REPLAY_ATTEMPTS, "lim": batch_size},
    ).fetchall()

    counters = {"attempted": 0, "replayed": 0, "failed": 0, "parked": 0}
    for row in rows:
        (dl_id, eval_id, event_id, rule_id, rule_version, result, why_failed, evidence, confidence, attempts) = row
        counters["attempted"] += 1
        savepoint = session.begin_nested()
        try:
            session.execute(
                _REPLAY_INSERT,
                {
                    "eval_id": eval_id,
                    "tenant_id": tenant_id,
                    "event_id": event_id,
                    "rule_id": rule_id,
                    "rule_version": rule_version,
                    "result": result,
                    "why_failed": why_failed,
                    "evidence": evidence if isinstance(evidence, str) else json.dumps(evidence, default=str),
                    "confidence": confidence,
                },
            )
            session.execute(
                text("UPDATE fsma.rule_evaluation_deadletter SET replayed_at = now() WHERE id = :id"),
                {"id": dl_id},
            )
            counters["replayed"] += 1
        except Exception as exc:
            savepoint.rollback()
            counters["failed"] += 1
            new_attempts = int(attempts) + 1
            try:
                session.execute(
                    text("UPDATE fsma.rule_evaluation_deadletter SET replay_attempts = :attempts WHERE id = :id"),
                    {"attempts": new_attempts, "id": dl_id},
                )
            except Exception as bump_err:
                logger.error(
                    "deadletter_attempt_bump_failed",
                    extra={"deadletter_id": str(dl_id), "error": str(bump_err)},
                )
            if new_attempts >= _MAX_REPLAY_ATTEMPTS:
                counters["parked"] += 1
                logger.error(
                    "deadletter_row_parked",
                    extra={
                        "deadletter_id": str(dl_id),
                        "event_id": event_id,
                        "rule_id": rule_id,
                        "attempts": new_attempts,
                        "error": str(exc),
                    },
                )
            else:
                logger.warning(
                    "deadletter_replay_failed",
                    extra={
                        "deadletter_id": str(dl_id),
                        "event_id": event_id,
                        "attempts": new_attempts,
                        "error": str(exc),
                    },
                )
    return counters


def replay_all_tenants(session, *, batch_size: int = 200) -> Dict[str, int]:
    """Tenant-iterating entry point for the scheduler job.

    ``public.tenants`` is the discovery table (infra table, permissive
    policy) because the RLS-forced dead-letter cannot be scanned
    cross-tenant (#2461) — mirrors ``remediation.delivery.drain_all_tenants``.
    """
    from shared.tenant_context import set_tenant_guc, tenant_scope

    tenant_rows = session.execute(text("SELECT id FROM public.tenants")).fetchall()
    totals = {"attempted": 0, "replayed": 0, "failed": 0, "parked": 0}
    for (tenant_id,) in tenant_rows:
        tid = str(tenant_id)
        try:
            with tenant_scope(tid):
                set_tenant_guc(session, tid)
                summary = replay_deadletter_for_tenant(session, tid, batch_size=batch_size)
            session.commit()
        except Exception:  # noqa: BLE001 — one tenant must not poison the tick
            session.rollback()
            logger.exception("deadletter_replay_tenant_failed tenant_id=%s", tid)
            continue
        for key, value in summary.items():
            totals[key] += value
    return totals
