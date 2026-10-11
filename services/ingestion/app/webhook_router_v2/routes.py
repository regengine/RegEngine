"""FastAPI router and endpoint handlers for webhook ingestion.

Code moved verbatim from the original ``webhook_router_v2.py``.

Dependency callables (``_verify_api_key``, ``_verify_webhook_signature``,
``get_db_session``, ...) are imported by object so
``app.dependency_overrides[...]`` keyed on the package re-exports keeps
matching — identical to the original module, where ``Depends(...)``
captured the function object at import time. Helpers invoked inside the
request handlers are resolved through the package namespace (``_pkg``)
at call time so monkeypatching ``app.webhook_router_v2.<name>``
(e.g. ``_check_rate_limit``, ``_publish_graph_sync``,
``emit_funnel_event``) keeps working exactly as before.
"""

from __future__ import annotations

import sys
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from shared.database import get_db_session
from shared.idempotency import IdempotencyDependency
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from ..authz import IngestionPrincipal, get_ingestion_principal, require_permission
from ..config import get_settings
from ..stripe_billing import charge_for_label
from ..subscription_gate import require_active_subscription
from ..webhook_models import (
    ChainVerifyResponse,
    EventResult,
    IngestResponse,
    RecentEventsResponse,
    WebhookPayload,
)
from .security import (
    _verify_api_key,
    _verify_api_key_present,
    _verify_webhook_signature,
)

_pkg = sys.modules[__package__]


def _failure_diagnostics(request: Request, exc: Exception) -> dict:
    """Structured fields for a 5xx log line on the ingest spine (#2868).

    These endpoints answer a 500 with "Check server logs for details", so the
    log line has to actually carry details: which tenant, which request, and
    what kind of failure. ``error_type`` matters because the batch handler
    catches bare ``Exception`` — without it a database outage and a
    programming error look identical in the logs.

    Deliberately **not** included: traceability lot codes, product
    descriptions, KDEs, or anything else from the request body. Those
    identify a specific customer's shipment, and this is a food-safety
    compliance platform — an over-eager log line is its own incident. The
    caller gets the correlation id in the response, and support joins the
    two on that.
    """
    correlation_id = getattr(request.state, "correlation_id", None)
    if not correlation_id:
        try:
            from shared.observability.correlation import get_correlation_id

            correlation_id = get_correlation_id()
        except Exception:  # pragma: no cover - correlation is best-effort
            correlation_id = None
    return {
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "error": str(exc),
        "error_type": type(exc).__name__,
    }


router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhook Ingestion"])


# ---------------------------------------------------------------------------
# Ingest Endpoint
# ---------------------------------------------------------------------------

# #1232 — enforce ``Idempotency-Key`` on all webhook ingest calls. The
# ``IdempotencyMiddleware`` mounted in ``main.py`` then caches the 2xx
# response for 24h, scoped per tenant (#1237).
_require_idempotency_key = IdempotencyDependency(strict=True)


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Ingest traceability events",
    description=(
        "Accept CTE events from external systems (IoT platforms, ERPs, manual entry). "
        "Each event is validated against FSMA 204 KDE requirements, SHA-256 hashed, "
        "chain-linked, and persisted to the compliance database. "
        "The ``Idempotency-Key`` header is REQUIRED — safe retries replay "
        "the cached response for 24 hours. Cache keys are tenant-scoped."
    ),
)
async def ingest_events(
    payload: WebhookPayload,
    request: Request,
    principal: IngestionPrincipal = Depends(require_permission("webhooks.ingest")),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    _auth: None = Depends(_verify_api_key),
    # #1243 / #3229: HMAC signature check runs in parallel with the
    # API-key check. A leaked key alone is no longer sufficient to forge
    # events: with ``WEBHOOK_HMAC_SECRET`` configured the body must be
    # signed, and on a closed gate (production or any strict/cloud
    # runtime) an unset secret rejects every ingest request instead of
    # skipping verification.
    _signature: None = Depends(_verify_webhook_signature),
    _subscription: None = Depends(require_active_subscription),
    _idempotency_key: Optional[str] = Depends(_require_idempotency_key),
    db_session=Depends(get_db_session),
) -> IngestResponse:
    """Process incoming webhook events with persistent storage."""
    ctx = await _pkg.resolve_tenant_context(request)
    tenant_id = ctx.tenant_id
    _pkg.validate_tenant_id(tenant_id)

    # Rate limiting (tenant-scoped)
    _pkg._check_rate_limit(tenant_id, request=request)

    results: list[EventResult] = []
    accepted = 0
    rejected = 0
    # Per-label FSMA 204 billing (v121) — event ids to charge once (and only
    # once) db_session.commit() below actually lands. Billing from inside
    # the loop, before that commit, would charge Stripe for a label whose
    # persistence row could still be rolled back by a later failure in this
    # same request -- a retry would then get a fresh event_id and bypass the
    # UNIQUE(tenant_id, cte_event_id) idempotency guarantee entirely.
    billable_event_ids: list[str] = []

    # Batch deduplication — detect identical events within the same payload
    seen_in_batch: set[str] = set()

    # Get persistence layer from injected db_session (Depends(get_db_session))
    persistence = None
    if db_session is None:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable — cannot accept events. Retry after service recovery.",
        )
    try:
        from shared.cte_persistence import CTEPersistence

        persistence = CTEPersistence(db_session)
    except (ImportError, SQLAlchemyError, RuntimeError, ConnectionError, OSError) as e:
        _pkg.logger.error("db_init_failed — rejecting ingest: %s", str(e))
        raise HTTPException(
            status_code=503,
            detail="Database unavailable — cannot accept events. Retry after service recovery.",
        )

    try:
        # --- Phase 1: Validate all events, collect valid ones for batch persist ---
        valid_events: list = []  # (event, alerts) tuples
        for event in payload.events:
            # Batch deduplication — skip identical events in same request
            dedup_key = f"{event.cte_type.value}|{event.traceability_lot_code}|{event.timestamp}|{event.location_gln or event.location_name or ''}"
            if dedup_key in seen_in_batch:
                results.append(
                    EventResult(
                        traceability_lot_code=event.traceability_lot_code,
                        cte_type=event.cte_type.value,
                        status="rejected",
                        errors=["Duplicate event in batch — same CTE type, TLC, timestamp, and location"],
                    )
                )
                rejected += 1
                continue
            seen_in_batch.add(dedup_key)

            # #1245: event-timestamp replay window. Signature-freshness
            # defends against immediate replay; this defends against a
            # captured payload re-ingested months later with freshly
            # computed signature.
            replay_error = _pkg._validate_event_timestamp_window(event.timestamp)
            if replay_error:
                _pkg.logger.warning(
                    "webhook_replay_window_rejected tenant=%s tlc=%s ts=%s",
                    tenant_id,
                    event.traceability_lot_code,
                    event.timestamp,
                )
                _pkg._record_replay_rejection(event.timestamp)
                results.append(
                    EventResult(
                        traceability_lot_code=event.traceability_lot_code,
                        cte_type=event.cte_type.value,
                        status="rejected",
                        errors=[replay_error],
                    )
                )
                rejected += 1
                continue

            # Validate KDEs
            errors = _pkg._validate_event_kdes(event)

            if errors:
                results.append(
                    EventResult(
                        traceability_lot_code=event.traceability_lot_code,
                        cte_type=event.cte_type.value,
                        status="rejected",
                        errors=errors,
                    )
                )
                rejected += 1
                continue

            # Generate alerts
            alerts = _pkg._generate_alerts(event)
            valid_events.append((event, alerts))

        # --- Phase 2a: Rules enforcement partition ---
        # Under RULES_ENGINE_ENFORCE=cte_only|all, exclude events whose
        # rules verdict says reject BEFORE they hit the batch store.
        # Runs a non-persisting eval per event; decision logic is in
        # ``shared.rules.enforcement.should_reject``. When ENFORCE=off
        # (default) every call returns (False, None) and the loop is a
        # no-op. No-verdict summaries (no rules loaded, non-FTL, etc.)
        # never reject — see EvaluationSummary.compliant docstring.
        # ``pre_eval_summaries`` is a parallel list to ``valid_events`` after
        # the filter — same length, same order, ``None`` entries for events
        # whose pre-eval skipped (OFF mode, canonical/eval error). The
        # threaded post-commit block uses the captured summary instead of
        # re-evaluating, eliminating the double-eval regression
        # (services/shared/rules/engine.py:persist_summary).
        pre_eval_summaries: list = []
        if valid_events:
            _filtered: list = []
            for _event, _alerts in valid_events:
                _reject, _reason, _summary = _pkg._rules_preeval_reject(_event, db_session, tenant_id)
                if _reject:
                    results.append(
                        EventResult(
                            traceability_lot_code=_event.traceability_lot_code,
                            cte_type=_event.cte_type.value,
                            status="rejected",
                            errors=[f"rule_violation: {_reason}"],
                        )
                    )
                    rejected += 1
                    continue
                _filtered.append((_event, _alerts))
                pre_eval_summaries.append(_summary)
            valid_events = _filtered

        # --- Phase 2: Batch persist all valid events ---
        if valid_events:
            batch_dicts = []
            event_objs = []
            for event, alerts in valid_events:
                batch_dicts.append(
                    {
                        "event_type": event.cte_type.value,
                        "traceability_lot_code": event.traceability_lot_code,
                        "product_description": event.product_description,
                        "quantity": event.quantity,
                        "unit_of_measure": event.unit_of_measure,
                        "event_timestamp": event.timestamp,
                        "location_gln": event.location_gln,
                        "location_name": event.location_name,
                        "kdes": event.kdes,
                        # One ledger entry serves both persisted projections.
                        # Construct its canonical content on the server; never
                        # accept a digest or projection from the request body.
                        "_canonical_event": _pkg.normalize_webhook_event(event, tenant_id, source=payload.source),
                        # #2902 — without this key ``store_events_batch`` reads an
                        # empty alert list, derives validation_status='valid' for
                        # every event and writes no compliance_alerts row, while
                        # the per-event fallback below persists both. Always pass
                        # the list (even when empty) so "no alerts" is stated
                        # rather than inferred from a missing key.
                        "alerts": alerts,
                    }
                )
                event_objs.append(event)

            # Snapshot so a partial-then-failed batch attempt (below) can be
            # undone precisely: on rollback we must discard only what THIS
            # attempt appended, not the pre-eval-rejected events already
            # recorded above.
            _pre_batch_results_len = len(results)
            _pre_batch_accepted = accepted

            try:
                store_results = persistence.store_events_batch(
                    tenant_id=tenant_id,
                    events=batch_dicts,
                    source=payload.source,
                )

                for store_result, event, precomputed_summary in zip(store_results, event_objs, pre_eval_summaries):
                    results.append(
                        EventResult(
                            traceability_lot_code=event.traceability_lot_code,
                            cte_type=event.cte_type.value,
                            status="accepted",
                            event_id=store_result.event_id,
                            sha256_hash=store_result.sha256_hash,
                            chain_hash=store_result.chain_hash,
                        )
                    )
                    accepted += 1
                    # Billed below, only after db_session.commit() succeeds.
                    billable_event_ids.append(store_result.event_id)

                    # Tenant-configured obligation-CTE rules (#2901). Runs
                    # after the store because it keys its fsma.compliance_alerts
                    # rows to the persisted event id. Its alerts are NOT merged
                    # into ``alerts`` above: a CRITICAL-risk obligation emits
                    # severity='critical', which _derive_validation_status
                    # treats as rejecting, so merging would silently turn
                    # accepted events into validation_status='rejected'.
                    # An unmet obligation is a detection signal, not an ingest
                    # gate — gating on it is a separate product decision.
                    _pkg._check_obligations(db_session, event, store_result.event_id, tenant_id)

                    # Canonical normalization + rule evaluation + exception creation.
                    # This is required evidence now: it runs synchronously in the
                    # request transaction so accepted legacy CTEs cannot diverge
                    # from canonical rows or persisted rule-evaluation evidence.
                    _pkg._persist_required_canonical_and_eval(
                        db_session,
                        event,
                        tenant_id,
                        precomputed_summary,
                        source=payload.source,
                        canonical_event_id=store_result.event_id,
                    )

                    # Post-ingest graph sync (non-blocking)
                    _pkg._publish_graph_sync(store_result.event_id, event, tenant_id)

                    # Auto-learn product catalog from confirmed scans
                    try:
                        from ..product_catalog import learn_from_event

                        learn_from_event(
                            tenant_id=tenant_id,
                            event={
                                "product_description": event.product_description,
                                "gtin": event.kdes.get("gtin") if event.kdes else None,
                                "kdes": event.kdes,
                                "location_name": event.location_name,
                            },
                        )
                    except (ImportError, SQLAlchemyError, ValueError, TypeError, RuntimeError, KeyError) as learn_err:
                        _pkg.logger.warning("catalog_learn_skipped: %s", str(learn_err))

            except (ValueError, TypeError, RuntimeError, AttributeError) as e:
                _pkg.logger.error(
                    "batch_persistence_failed",
                    extra={"error": str(e), "batch_size": len(valid_events)},
                )
                # The failed batch may have left flushed-but-doomed rows or an
                # aborted transaction on the shared session. Reset it so the
                # per-event retries below start clean — on Postgres a poisoned
                # transaction turns the final commit() into a silent no-op
                # that discards every event this loop reports as accepted.
                try:
                    db_session.rollback()
                except SQLAlchemyError as rb_err:
                    _pkg.logger.warning("fallback_pre_rollback_failed: %s", str(rb_err))
                # The batch loop above may have already recorded some of this
                # failed attempt's events as accepted (results/accepted) and
                # queued them for billing (billable_event_ids) before the
                # exception hit -- rows the rollback above just discarded.
                # The fallback below re-persists the ENTIRE valid_events list
                # from scratch, minting a fresh event_id per label and
                # appending its own EventResult, so anything from this
                # doomed attempt must be undone first: otherwise the response
                # double-counts every event that succeeded before the
                # failure, and billing would charge two different event_ids
                # for the same physical label -- bypassing the
                # UNIQUE(tenant_id, cte_event_id) idempotency guard entirely.
                del results[_pre_batch_results_len:]
                accepted = _pre_batch_accepted
                billable_event_ids.clear()
                # Fall back to per-event persistence
                for event, alerts in valid_events:
                    # Enforcement: same pre-eval gate as the happy path.
                    # Events that were pre-eval rejected above never
                    # reach this fallback (they were stripped from
                    # valid_events), but running the check again here
                    # is cheap insurance — if the batch path ever
                    # mutates valid_events in flight, the fallback
                    # still honors the enforcement policy.
                    _fb_reject, _fb_reason, _fb_summary = _pkg._rules_preeval_reject(event, db_session, tenant_id)
                    if _fb_reject:
                        results.append(
                            EventResult(
                                traceability_lot_code=event.traceability_lot_code,
                                cte_type=event.cte_type.value,
                                status="rejected",
                                errors=[f"rule_violation: {_fb_reason}"],
                            )
                        )
                        rejected += 1
                        continue
                    # Each event gets its own savepoint (same pattern as the
                    # webhook_compat v1 path) so one event's storage failure
                    # never poisons the shared transaction — without it, the
                    # events already accepted by this loop are silently
                    # discarded at the final commit while the response still
                    # reports them accepted with hashes.
                    savepoint = db_session.begin_nested()
                    try:
                        store_result = persistence.store_event(
                            tenant_id=tenant_id,
                            event_type=event.cte_type.value,
                            traceability_lot_code=event.traceability_lot_code,
                            product_description=event.product_description,
                            quantity=event.quantity,
                            unit_of_measure=event.unit_of_measure,
                            event_timestamp=event.timestamp,
                            source=payload.source,
                            location_gln=event.location_gln,
                            location_name=event.location_name,
                            kdes=event.kdes,
                            alerts=alerts,
                            canonical_event=_pkg.normalize_webhook_event(event, tenant_id, source=payload.source),
                        )

                        # Obligation-CTE rules (#2901) — same call as the batch
                        # path above, so the fallback is not a hole in
                        # obligation coverage. Inside the per-event savepoint,
                        # so an obligation-query failure cannot poison the
                        # shared transaction.
                        _pkg._check_obligations(db_session, event, store_result.event_id, tenant_id)

                        # Canonical normalization + rule evaluation. Required in
                        # the same transaction as the legacy fallback write.
                        _pkg._persist_required_canonical_and_eval(
                            db_session,
                            event,
                            tenant_id,
                            _fb_summary,
                            source=payload.source,
                            canonical_event_id=store_result.event_id,
                        )
                        savepoint.commit()

                        results.append(
                            EventResult(
                                traceability_lot_code=event.traceability_lot_code,
                                cte_type=event.cte_type.value,
                                status="accepted",
                                event_id=store_result.event_id,
                                sha256_hash=store_result.sha256_hash,
                                chain_hash=store_result.chain_hash,
                            )
                        )
                        accepted += 1
                        # Billed below, only after db_session.commit()
                        # succeeds -- a savepoint.commit() just above only
                        # releases the nested savepoint; it does not make
                        # this row durable against a later outer rollback.
                        billable_event_ids.append(store_result.event_id)

                        _pkg._publish_graph_sync(store_result.event_id, event, tenant_id)
                        try:
                            from ..product_catalog import learn_from_event

                            learn_from_event(
                                tenant_id=tenant_id,
                                event={
                                    "product_description": event.product_description,
                                    "gtin": event.kdes.get("gtin") if event.kdes else None,
                                    "kdes": event.kdes,
                                    "location_name": event.location_name,
                                },
                            )
                        except (ImportError, SQLAlchemyError, ValueError, TypeError, KeyError) as learn_err:
                            _pkg.logger.warning("catalog_learn_skipped: %s", str(learn_err))
                    except (SQLAlchemyError, ValueError, TypeError, RuntimeError, KeyError) as inner_e:
                        try:
                            savepoint.rollback()
                        except SQLAlchemyError as sp_err:
                            _pkg.logger.warning("fallback_savepoint_rollback_failed: %s", str(sp_err))
                        # F-3: don't leak SQL/bound-params from SQLAlchemyError.__str__
                        # to the API caller. Full detail goes to server logs with a
                        # correlation_id; the response carries only the correlation_id.
                        correlation_id = str(uuid.uuid4())
                        _pkg.logger.warning(
                            "storage_error_per_event_fallback",
                            correlation_id=correlation_id,
                            tlc=event.traceability_lot_code,
                            error=str(inner_e),
                            error_type=type(inner_e).__name__,
                        )
                        results.append(
                            EventResult(
                                traceability_lot_code=event.traceability_lot_code,
                                cte_type=event.cte_type.value,
                                status="rejected",
                                errors=[f"Internal storage error (correlation: {correlation_id})"],
                            )
                        )
                        rejected += 1

        if accepted > 0:
            _pkg.emit_funnel_event(
                tenant_id=tenant_id,
                event_name="first_ingest",
                metadata={
                    "accepted_events": accepted,
                    "source": payload.source,
                },
                db_session=db_session,
            )

        # Commit all events in a single transaction
        if db_session:
            db_session.commit()

    except Exception as e:
        if db_session:
            db_session.rollback()
        if isinstance(e, HTTPException) and e.status_code == 503:
            raise
        diagnostics = _failure_diagnostics(request, e)
        # ``.exception`` captures the traceback via the structlog chain's
        # ``format_exc_info`` processor — the old ``error(..., extra={...})``
        # emitted strictly less than the caller already had.
        _pkg.logger.exception(
            "ingest_batch_failed",
            tenant_id=tenant_id,
            event_count=len(payload.events),
            source=payload.source,
            accepted_before_failure=accepted,
            **diagnostics,
        )
        raise HTTPException(
            status_code=500,
            detail=(f"Ingestion failed. Check server logs for details (correlation: {diagnostics['correlation_id']})."),
        )
    finally:
        if db_session:
            db_session.close()

    # Per-label FSMA 204 billing (v121). Only reached once db_session.commit()
    # above has actually succeeded, so every id here is durably persisted --
    # charging earlier (inside the loop, before that commit) would bill a
    # label whose row could still be rolled back by an unrelated failure
    # later in the same request; a retry would then mint a fresh event_id
    # and bypass the UNIQUE(tenant_id, cte_event_id) idempotency guarantee
    # entirely. A Stripe/DB hiccup per label must never fail the response
    # for labels that already ingested successfully.
    if billable_event_ids:
        price_cents = get_settings().price_per_label_cents
        for billed_event_id in billable_event_ids:
            try:
                # Stripe's SDK and the billing DB session are both
                # synchronous; run_in_threadpool keeps this request's async
                # event loop free for other tenants while a Stripe call is
                # in flight. anyio copies the current contextvars into the
                # thread, so the RLS tenant-context GUC hook
                # (shared/tenant_context.py) still applies correctly there.
                await run_in_threadpool(
                    charge_for_label,
                    tenant_id=tenant_id,
                    cte_event_id=billed_event_id,
                    amount_cents=price_cents,
                )
            except Exception as bill_err:  # noqa: BLE001 -- billing is best-effort, must never fail ingest
                _pkg.logger.warning("label_charge_skipped: %s", str(bill_err))

    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        total=len(payload.events),
        events=results,
    )


# ---------------------------------------------------------------------------
# Chain Verification Endpoint
# ---------------------------------------------------------------------------


async def get_recent_events(
    tenant_id: str,
    limit: int = 10,
):
    """
    Get most recent CTE events for a tenant — powers the scan history
    dashboard widget.
    """
    _pkg.validate_tenant_id(tenant_id)
    db_session = None
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text as _text

        db_session = SessionLocal()
        rows = db_session.execute(
            _text("""
                SELECT id, event_type, traceability_lot_code, product_description,
                       quantity, unit_of_measure, location_name, source, ingested_at
                FROM fsma.cte_events
                WHERE tenant_id = :tid
                ORDER BY ingested_at DESC
                LIMIT :lim
            """),
            {"tid": tenant_id, "lim": min(limit, 50)},
        ).fetchall()
        events = [
            {
                "event_id": str(r[0]),
                "event_type": r[1],
                "traceability_lot_code": r[2],
                "product_description": r[3],
                "quantity": float(r[4]) if r[4] else 0,
                "unit_of_measure": r[5],
                "location_name": r[6],
                "source": r[7],
                "ingested_at": r[8].isoformat() if r[8] else None,
            }
            for r in rows
        ]
        return {"tenant_id": tenant_id, "events": events, "total": len(events)}
    except (ImportError, ValueError, RuntimeError) as e:
        _pkg.logger.warning("recent_events_query_failed: %s", str(e))
        return {"tenant_id": tenant_id, "events": [], "total": 0}
    finally:
        if db_session:
            db_session.close()


def _enforce_webhooks_read_principal(
    url_tenant_id: str,
    principal: IngestionPrincipal,
    scope: str,
) -> None:
    """Bind a webhook READ route's URL ``tenant_id`` to the authenticated principal.

    Closes F-1 (re-audit): the previous gate (``_verify_api_key``) only
    checked header presence, leaving these reads as cross-tenant IDORs.
    Mirrors the #2249 stripe-portal fix:

    1. Require the ``webhooks.read`` permission on the principal.
    2. Compare URL ``tenant_id`` to the principal's tenant.
    3. On mismatch, return **404 Not Found** (not 403) — avoids the
       tenant-existence oracle a 403 would create.

    Wildcard (``*``) and ``admin.*`` scopes grant permission BREADTH
    (which actions a key may perform), NOT tenant BREADTH (which tenants
    it may act on). A tenant-bound key carrying ``*`` MUST NOT pivot to
    another tenant by passing ``?tenant_id=<other>``. The only callers
    that legitimately need cross-tenant reads (legacy master / dev_open)
    carry ``tenant_id=None`` and bypass the pin via the unbound branch
    below — they never relied on the wildcard short-circuit. Closes the
    third instance of the same antipattern fixed in PR #2328 (authz.py,
    inflow_workbench.py).
    """
    # Permission check first — a key without webhooks.read should never
    # learn whether a tenant exists.
    if not _pkg._has_permission(principal.scopes, "webhooks.read"):
        _pkg.logger.warning(
            "webhooks_read_permission_denied key_id=%s scope=%s",
            getattr(principal, "key_id", None),
            scope,
        )
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions: requires 'webhooks.read'",
        )

    principal_tenant = principal.tenant_id
    # Unbound principals (master/dev_open, tenant_id=None) keep
    # cross-tenant access. Bound principals — including those holding
    # ``*`` or ``admin.*`` — must match the URL tenant.
    if principal_tenant is None:
        return

    if principal_tenant != url_tenant_id:
        _pkg.logger.warning(
            "webhooks_read_tenant_mismatch url_tenant=%s principal_tenant=%s key_id=%s scope=%s",
            url_tenant_id,
            principal_tenant,
            getattr(principal, "key_id", None),
            scope,
        )
        # 404 not 403 — same shape as #2249 to avoid existence oracle.
        raise HTTPException(status_code=404, detail="Not found")


@router.get(
    "/recent",
    response_model=RecentEventsResponse,
    summary="Get recent CTE events",
    description="Returns the most recently ingested traceability events for the scan history widget.",
)
async def recent_events_endpoint(
    request: Request,
    tenant_id: str,
    limit: int = 10,
    principal: IngestionPrincipal = Depends(get_ingestion_principal),
    _auth: None = Depends(_verify_api_key_present),
):
    """Return the tenant's recent CTE events.

    F-1 (re-audit): bound to the authenticated principal's tenant; URL
    ``tenant_id`` mismatches return 404 to avoid a tenant-existence oracle.
    F-4 (re-audit): tighter rate limit applied (``webhooks.read.recent``).
    """
    _pkg.validate_tenant_id(tenant_id)
    _pkg._enforce_webhooks_read_principal(tenant_id, principal, scope="recent")
    _pkg._check_read_rate_limit(tenant_id, scope="recent", request=request)
    return await _pkg.get_recent_events(tenant_id, limit)


@router.get(
    "/chain/verify",
    response_model=ChainVerifyResponse,
    summary="Verify hash chain integrity",
    description=(
        "Walk the tenant's entire hash chain from genesis to head, recomputing each link and checking for tampering."
    ),
)
async def verify_chain(
    request: Request,
    tenant_id: str,
    principal: IngestionPrincipal = Depends(get_ingestion_principal),
    _auth: None = Depends(_verify_api_key_present),
):
    """Verify the integrity of the tenant's hash chain.

    F-1 (re-audit): bound to the authenticated principal's tenant; URL
    ``tenant_id`` mismatches return 404. F-4 (re-audit): tighter rate
    limit applied (``webhooks.read.chain_verify``).
    """
    _pkg.validate_tenant_id(tenant_id)
    _pkg._enforce_webhooks_read_principal(tenant_id, principal, scope="chain_verify")
    _pkg._check_read_rate_limit(tenant_id, scope="chain_verify", request=request)
    db_session = None
    try:
        from shared.cte_persistence import CTEPersistence
        from shared.database import SessionLocal

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)
        result = persistence.verify_chain(tenant_id)

        return {
            "tenant_id": tenant_id,
            "chain_valid": result.valid,
            "chain_length": result.chain_length,
            "errors": result.errors,
            "checked_at": result.checked_at,
        }
    except (ImportError, ValueError, RuntimeError) as e:
        diagnostics = _failure_diagnostics(request, e)
        _pkg.logger.exception(
            "chain_verification_failed",
            tenant_id=tenant_id,
            **diagnostics,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "Chain verification failed. Check server logs for details "
                f"(correlation: {diagnostics['correlation_id']})."
            ),
        )
    finally:
        if db_session:
            db_session.close()
