"""Rules-engine pre-evaluation gate (enforcement, #1919/#1926) and the
canonical-event + rule-evaluation persistence helpers (#1929, #1335).

Code moved verbatim from the original ``webhook_router_v2.py``.
``normalize_webhook_event`` and sibling helpers are resolved through
the package namespace (``_pkg``) at call time so tests that monkeypatch
``app.webhook_router_v2.normalize_webhook_event`` keep working.
"""

from __future__ import annotations

import sys
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from ..webhook_models import IngestEvent

_pkg = sys.modules[__package__]


class _CanonicalPersistenceError(Exception):
    """Raised when required canonical persistence cannot complete."""


def _get_persistence(db_session=None):
    """Get CTEPersistence instance, or None if DB unavailable."""
    if db_session is None:
        return None
    try:
        from shared.cte_persistence import CTEPersistence

        return CTEPersistence(db_session)
    except ImportError:
        _pkg.logger.warning("cte_persistence module not available")
        return None


def _rules_preeval_reject(event: IngestEvent, db_session, tenant_id: str):
    """Pre-evaluate rules to decide whether the event should be rejected
    under the current ``RULES_ENGINE_ENFORCE`` policy.

    Runs ``engine.evaluate_event(persist=False)`` so the decision is made
    without writing eval rows — a reject can exclude the event from the
    batch without polluting the transaction. Canonical normalization or
    rule evaluation errors fail loud under active enforcement. A completed
    evaluation with no verdict is rejected by the shared policy gate.

    Short-circuits on OFF mode — skips normalization + eval entirely
    so the default production path pays no added latency. Without this
    guard every webhook ingest would re-normalize and re-evaluate even
    though ``should_reject`` would always return ``(False, None)``;
    the threaded post-commit block still does its own eval with
    ``persist=True``, so under enforcement we pay for the double eval
    intentionally. Under OFF we must not.

    Returns ``(reject, reason, summary)``:
      * ``reject``: True when the caller must reject the event.
      * ``reason``: short string suitable for ``EventResult.errors``,
        or None when not rejecting.
      * ``summary``: the ``EvaluationSummary`` produced by pre-eval, or
        None when pre-eval was skipped (OFF mode short-circuit, or
        canonical/eval errored). Returned so callers can hand it back
        to the post-commit persistence path via
        ``engine.persist_summary`` and avoid re-evaluating the rules —
        eliminates the double-eval that otherwise lands when
        ``RULES_ENGINE_ENFORCE != off``.

    All three branches return a 3-tuple. PR #1919 (OFF short-circuit)
    and PR #1926 (3-tuple signature) were composed by hand during a
    botched merge and one branch got left at the old 2-tuple shape;
    every webhook ingest under the prod-default ``OFF`` mode crashed
    at the call-site destructure with ``ValueError: not enough values
    to unpack``. Restored consistent 3-tuple here. See spawned task.
    """
    from shared.rules.enforcement import (  # noqa: PLC0415
        EnforcementMode,
        current_mode,
        handle_preeval_exception,
        should_reject,
    )

    if current_mode() == EnforcementMode.OFF:
        return False, None, None

    canonical = None
    try:
        canonical = _pkg.normalize_webhook_event(event, tenant_id)
        from shared.rules_engine import RulesEngine  # noqa: PLC0415

        engine = RulesEngine(db_session)
        event_data = {
            "event_id": str(canonical.event_id),
            "event_type": canonical.event_type.value,
            "traceability_lot_code": canonical.traceability_lot_code,
            "product_reference": canonical.product_reference,
            "quantity": canonical.quantity,
            "unit_of_measure": canonical.unit_of_measure,
            "from_facility_reference": canonical.from_facility_reference,
            "to_facility_reference": canonical.to_facility_reference,
            "from_entity_reference": canonical.from_entity_reference,
            "to_entity_reference": canonical.to_entity_reference,
            "kdes": canonical.kdes,
        }
        summary = engine.evaluate_event(event_data, persist=False, tenant_id=tenant_id)
    except (ImportError, SQLAlchemyError, ValueError, TypeError, RuntimeError, AttributeError, KeyError) as err:
        # Finding A — fail loud under cte_only/all; HTTPException(500)
        # bubbles up to ingest_events and the route returns 5xx instead
        # of silently accepting because a rule crashed.
        handle_preeval_exception(err, where="webhook_router_v2")
        # If we reach here, mode was OFF (handle_preeval_exception
        # returned). Treat as no-verdict.
        return False, None, None

    reject, reason = should_reject(summary)
    if reject:
        # Finding B — durable audit row BEFORE the caller marks the
        # event rejected. Independent session = survives outer rollback.
        try:
            from shared.rules.rejection_audit import (  # noqa: PLC0415
                reasons_from_summary,
                record_rejection,
            )

            _first_crit = (summary.critical_failures or [None])[0]
            record_rejection(
                tenant_id=tenant_id,
                rule_id=getattr(_first_crit, "rule_id", None),
                rule_version=getattr(_first_crit, "rule_version", None),
                event_id=str(canonical.event_id) if canonical is not None else None,
                reasons=reasons_from_summary(summary, rejection_reason=reason),
                source="webhook_router_v2_preeval",
                enforcement_mode=current_mode(),
            )
        except Exception:  # noqa: BLE001
            _pkg.logger.error("webhook_v2_rejection_audit_inline_error")
            raise HTTPException(status_code=503, detail="Rejection audit storage is unavailable") from None
    return reject, reason, summary


def _persist_canonical_and_eval(
    db_session,
    event: IngestEvent,
    tenant_id: str,
    precomputed_summary,
    source: str = "webhook_api",
    canonical_event_id: str | None = None,
) -> None:
    """Persist canonical event + write rule eval rows + create exception
    queue entries for non-compliant verdicts.

    Module-level so the happy-path batch block and the fallback path
    can share a single implementation, AND so the
    routing logic (use ``persist_summary`` when the pre-computed summary
    is available, else fall back to ``evaluate_event(persist=True)``)
    can be unit-tested without mounting the full ``ingest_events`` route.

    Routing rules (verified by ``test_webhook_router_v2_canonical_helper``):
      - ``precomputed_summary`` is non-None AND has results →
        ``RulesEngine.persist_summary`` writes the eval rows. No
        re-evaluation. Fast path under
        ``RULES_ENGINE_ENFORCE=cte_only|all``.
      - ``precomputed_summary`` is None OR has empty ``.results`` →
        ``RulesEngine.evaluate_event(persist=True)`` re-runs and
        persists. Default production path under ``OFF`` mode and
        fallback for no-verdict / pre-eval-error cases.
      - In both paths, ``not summary.compliant`` triggers
        ``ExceptionQueueService.create_exceptions_from_evaluation``
        for non-blocking failure visibility.

    Anchors the eval rows on the canonical event_id we just persisted
    (``str(canonical.event_id)``), not on whatever ID the pre-eval
    canonical happened to have. ``normalize_webhook_event`` mints a
    fresh UUID per call.

    Caller is responsible for catching exceptions raised by this
    function — the helper does not swallow errors so the caller can
    decide between "abort the request" and "log and continue".

    History: this helper was originally supposed to land in PR #1929,
    but only the test file made it through the merge — the source
    change was dropped during conflict resolution. Restored here.
    """
    from shared.canonical_persistence import CanonicalEventStore  # noqa: PLC0415
    from shared.rules_engine import RulesEngine  # noqa: PLC0415

    canonical = _pkg.normalize_webhook_event(event, tenant_id, source=source)
    if canonical_event_id is not None:
        # Reuse the legacy fsma.cte_events UUID for the canonical row and
        # rule-evaluation anchor. The legacy CTEPersistence path already
        # writes fsma.hash_chain for this event; canonical persistence must
        # not append a second chain row to the same shared ledger.
        canonical.event_id = UUID(str(canonical_event_id))
        canonical.prepare_for_persistence()
    store = CanonicalEventStore(db_session, dual_write=False, skip_chain_write=True)
    persist_result = store.persist_event(canonical)
    persisted_event_id = str(getattr(persist_result, "event_id", None) or canonical.event_id)
    engine = RulesEngine(db_session)

    if precomputed_summary is not None and precomputed_summary.results:
        engine.persist_summary(
            precomputed_summary,
            tenant_id=tenant_id,
            event_id=persisted_event_id,
        )
        summary = precomputed_summary
    else:
        event_data = {
            "event_id": persisted_event_id,
            "event_type": canonical.event_type.value,
            "traceability_lot_code": canonical.traceability_lot_code,
            "product_reference": canonical.product_reference,
            "quantity": canonical.quantity,
            "unit_of_measure": canonical.unit_of_measure,
            "from_facility_reference": canonical.from_facility_reference,
            "to_facility_reference": canonical.to_facility_reference,
            "from_entity_reference": canonical.from_entity_reference,
            "to_entity_reference": canonical.to_entity_reference,
            "kdes": canonical.kdes,
        }
        summary = engine.evaluate_event(event_data, persist=True, tenant_id=tenant_id)

    # ExceptionQueueService links cases from summary.event_id; idempotent
    # canonical persistence may return an existing row whose id differs from
    # the freshly normalized/pre-evaluated candidate.
    summary.event_id = persisted_event_id

    if not summary.compliant:
        from shared.exception_queue import ExceptionQueueService  # noqa: PLC0415

        ExceptionQueueService(db_session).create_exceptions_from_evaluation(tenant_id, summary)


def _persist_required_canonical_and_eval(
    db_session,
    event: IngestEvent,
    tenant_id: str,
    precomputed_summary,
    source: str = "webhook_api",
    canonical_event_id: str | None = None,
) -> None:
    """Persist canonical evidence or fail the ingest transaction."""
    try:
        _pkg._persist_canonical_and_eval(
            db_session,
            event,
            tenant_id,
            precomputed_summary,
            source=source,
            canonical_event_id=canonical_event_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise _CanonicalPersistenceError(
            f"Canonical persistence failed for TLC {event.traceability_lot_code}: {exc}"
        ) from exc
