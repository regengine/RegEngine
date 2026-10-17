"""Compatibility helpers for webhook auth and ingestion.

This module is the stable import surface for non-router ingestion modules.
All auth logic delegates to ``shared.auth.require_api_key`` — the single
canonical auth path for every RegEngine service.

Legacy ``webhook_router.py`` has been retired; ``webhook_router_v2.py``
remains the mounted HTTP router.

Note: ``ingest_events()`` here does NOT call the v2 router endpoint
directly because that function depends on FastAPI DI params
(``principal``, ``_auth``, ``db_session``) that are unavailable
outside HTTP context.  Instead it performs the core ingestion logic
using the same internal helpers and persistence layer.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from fastapi import Depends, Header, HTTPException, Request
from shared.api_key_store import APIKeyResponse
from shared.auth import APIKey, require_api_key
from shared.database import get_db_session as _get_db_session
from shared.tenant_context import TenantContext, resolve_tenant_context

from .webhook_models import EventResult, IngestEvent, IngestResponse, WebhookPayload
from .webhook_router_v2 import (
    _check_rate_limit,
    _generate_alerts,
    _publish_graph_sync,
    _validate_event_kdes,
    _verify_api_key as _verify_api_key_sync,
)

logger = logging.getLogger("webhook-compat")


def _batch_dedup_key(event: IngestEvent) -> str:
    key = (
        f"{event.cte_type.value}|{event.traceability_lot_code}"
        f"|{event.timestamp}|{event.location_gln or event.location_name or ''}"
    )
    # Repeated warehouse lines can share a TLC, time, and location. Their
    # interchange position distinguishes W07/W12 lines without changing
    # the batch key for any other event type.
    line_index = event.kdes.get("edi_line_index")
    if event.kdes.get("edi_transaction_set") in ("944", "945") and isinstance(line_index, int) and line_index > 0:
        return (
            f"{key}|{event.kdes.get('edi_isa13') or ''}"
            f"|{event.kdes.get('edi_control_number') or ''}|{line_index}"
        )
    return key


async def _verify_api_key(
    request: Request,
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> Union[APIKey, APIKeyResponse]:
    """Auth gate — delegates to shared.auth.require_api_key.

    This is the stable import surface for ingestion sub-routers.
    All auth logic (preshared key, scoped keys, test bypass) lives
    in ``shared/auth.py``. The accepted key is stored on ``request.state``
    and resolved through the shared tenant context so legacy routers cannot
    use path/query/header tenant claims to pivot across tenants.
    """
    api_key = await require_api_key(
        request=request,
        x_regengine_api_key=x_regengine_api_key,
    )
    request.state.tenant_context = await resolve_tenant_context(request)
    return api_key


async def require_tenant_context(
    request: Request,
    _api_key: Union[APIKey, APIKeyResponse] = Depends(_verify_api_key),
) -> TenantContext:
    """Return the authenticated tenant context for legacy route handlers."""
    ctx = getattr(request.state, "tenant_context", None)
    if ctx is None:
        ctx = await resolve_tenant_context(request)
        request.state.tenant_context = ctx
    return ctx


@dataclass
class SourceFileReceipt:
    """The uploaded file an ingestion run retains verbatim (fsma.manifest_blobs).

    ``record_count`` counts the file's data rows including ones the parser
    rejected; ``parse_errors`` are those rejections, recorded on the run so
    the receipt accounts for every row, not only the ones that became events.
    """

    filename: str
    raw_bytes: bytes
    content_type: Optional[str] = None
    initiated_by: Optional[str] = None
    record_count: int = 0
    parse_errors: List[str] = field(default_factory=list)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()


def _run_source_system(source: str):
    from shared.canonical_event import IngestionSource

    try:
        return IngestionSource(source)
    except ValueError:
        return IngestionSource.CSV_UPLOAD


def _open_ingestion_run(db_session, tenant_id: str, source: str, receipt: SourceFileReceipt) -> str:
    """Record the upload before any row is processed.

    Writes the fsma.ingestion_runs row (file name, SHA-256, size, row count)
    and the verbatim bytes to fsma.manifest_blobs, the same retention the
    supplier-remediation path uses. Runs in the caller's transaction: if the
    receipt cannot be written the upload fails, because events without a
    retained source are exactly what the receipt exists to prevent.
    """
    from shared.canonical_event import IngestionRun
    from shared.canonical_persistence import CanonicalEventStore
    from sqlalchemy import text

    store = CanonicalEventStore(db_session, dual_write=False)
    run = IngestionRun(
        tenant_id=tenant_id,
        source_system=_run_source_system(source),
        source_file_name=receipt.filename,
        source_file_hash=receipt.sha256,
        source_file_size=len(receipt.raw_bytes),
        record_count=receipt.record_count,
        initiated_by=receipt.initiated_by,
    )
    run_id = store.create_ingestion_run(run)
    db_session.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO fsma.manifest_blobs
                (ingestion_run_id, tenant_id, raw_bytes, sha256,
                 original_filename, content_type, uploaded_by)
            VALUES
                (CAST(:run_id AS uuid), CAST(:tenant_id AS uuid), :raw_bytes,
                 :sha256, :filename, :content_type, :uploaded_by)
            """
        ),
        {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "raw_bytes": receipt.raw_bytes,
            "sha256": receipt.sha256,
            "filename": receipt.filename,
            "content_type": receipt.content_type,
            "uploaded_by": receipt.initiated_by,
        },
    )
    return run_id


def _close_ingestion_run(
    db_session,
    run_id: str,
    tenant_id: str,
    *,
    accepted: int,
    rejected: int,
    results: List[EventResult],
    receipt: SourceFileReceipt,
) -> None:
    """Close the run with counts that cover every row of the file."""
    from shared.canonical_persistence import CanonicalEventStore

    errors: List[Dict[str, Any]] = [{"stage": "parse", "error": err} for err in receipt.parse_errors]
    for result in results:
        if result.status == "rejected":
            errors.append(
                {
                    "stage": "persist",
                    "traceability_lot_code": result.traceability_lot_code,
                    "errors": list(result.errors or []),
                }
            )
    CanonicalEventStore(db_session, dual_write=False).complete_ingestion_run(
        run_id,
        tenant_id,
        accepted=accepted,
        rejected=rejected + len(receipt.parse_errors),
        errors=errors,
    )


async def ingest_events(
    payload: WebhookPayload,
    *,
    principal_tenant_id: str,
    x_regengine_api_key: Optional[str] = None,
    source_file: Optional[SourceFileReceipt] = None,
) -> IngestResponse:
    """Internal ingestion helper — not an HTTP route.

    Callers must derive ``principal_tenant_id`` from an authenticated
    principal (typically ``resolve_principal_tenant_id`` in a router
    that has already resolved a verified ``APIKey`` / ``APIKeyResponse``).
    Without a principal-derived tenant this helper has no request
    context to fall back on and would otherwise trust whatever
    ``tenant_id`` the payload carries — see the "internal helper
    requires tenant-bearing payload" limitation in the project README.

    The helper rejects calls where the payload-supplied tenant is
    absent or disagrees with the authenticated principal, so a caller
    cannot forge cross-tenant writes even by accident.

    ``source_file`` (file uploads) opens an ingestion run before the first
    row is processed, retains the file verbatim, stamps ``ingestion_run_id``
    on every canonical event, and closes the run with counts covering every
    row of the file. The run id is returned on the response.
    """
    if not principal_tenant_id:
        raise PermissionError("ingest_events requires principal_tenant_id from authenticated context")

    _verify_api_key_sync(x_regengine_api_key=x_regengine_api_key)

    payload_tenant_id = payload.tenant_id
    if not payload_tenant_id:
        raise ValueError("payload.tenant_id is required for symmetric verification with principal_tenant_id")
    if payload_tenant_id != principal_tenant_id:
        raise PermissionError("payload.tenant_id does not match authenticated principal")

    tenant_id = principal_tenant_id

    from app.tenant_validation import validate_tenant_id

    validate_tenant_id(tenant_id)

    _check_rate_limit(tenant_id)

    # Obtain a DB session from the generator dependency manually
    db_gen = _get_db_session()
    db_session = next(db_gen)

    if db_session is None:
        raise RuntimeError("Database unavailable — cannot accept events.")

    run_id: Optional[str] = None
    try:
        from shared.cte_persistence import CTEPersistence

        persistence = CTEPersistence(db_session)
    except (ImportError, RuntimeError, ConnectionError) as exc:
        # Exhaust the generator so cleanup runs
        next(db_gen, None)
        raise RuntimeError(f"Database unavailable: {exc}") from exc

    results: list[EventResult] = []
    accepted = 0
    rejected = 0
    seen_in_batch: set[str] = set()

    try:
        if source_file is not None:
            # The receipt is written first so a run exists even if every row
            # is rejected; the same transaction carries run, blob and events.
            run_id = _open_ingestion_run(db_session, tenant_id, payload.source, source_file)
        for event in payload.events:
            dedup_key = _batch_dedup_key(event)
            if dedup_key in seen_in_batch:
                results.append(
                    EventResult(
                        traceability_lot_code=event.traceability_lot_code,
                        cte_type=event.cte_type.value,
                        status="rejected",
                        errors=["Duplicate event in batch"],
                    )
                )
                rejected += 1
                continue
            seen_in_batch.add(dedup_key)

            errors = _validate_event_kdes(event)
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

            alerts = _generate_alerts(event)

            # Each event gets its own savepoint so a failure on one
            # event (storage, canonical write, or rule evaluation)
            # never poisons the DB transaction for subsequent events.
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
                )

                # Canonical normalization + rule evaluation (best-effort).
                # Runs BEFORE the primary savepoint commits so a rule
                # rejection (under RULES_ENGINE_ENFORCE=cte_only|all) can
                # roll back the primary CTE write along with it.
                # Canonical/rules internal errors are swallowed: the
                # primary write still commits, preserving the prior
                # best-effort behavior for tenants without seeded rules.
                summary = None
                canon_sp = db_session.begin_nested()
                try:
                    from shared.canonical_event import normalize_webhook_event
                    from shared.canonical_persistence import CanonicalEventStore

                    canonical = normalize_webhook_event(event, tenant_id, ingestion_run_id=run_id)
                    canonical_store = CanonicalEventStore(db_session, dual_write=False)
                    canonical_store.persist_event(canonical)
                    from shared.rules_engine import RulesEngine

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
                    summary = engine.evaluate_event(event_data, persist=True, tenant_id=tenant_id)
                    canon_sp.commit()
                except (ImportError, ValueError, TypeError, RuntimeError) as canon_err:
                    canon_sp.rollback()
                    summary = None
                    # Finding A — under enforcement modes (cte_only/all)
                    # a canonical/rules crash must not silently accept.
                    # ``handle_preeval_exception`` raises HTTPException(500)
                    # in those modes; under OFF it warns and returns
                    # so the legacy best-effort accept path remains.
                    from shared.rules.enforcement import handle_preeval_exception  # noqa: PLC0415

                    handle_preeval_exception(canon_err, where="webhook_compat")
                    logger.warning("compat_canonical_write_skipped: %s", str(canon_err))

                # Enforcement: if RULES_ENGINE_ENFORCE is set and the
                # summary meets the reject policy, roll back the outer
                # savepoint (undoes primary CTE + committed canonical +
                # persisted eval rows) and emit a rejected result.
                # Summary=None (canonical/rules skipped) never rejects —
                # preserves prior behavior for every tenant when the
                # flag is off or the rules path fails best-effort.
                reject_reason: Optional[str] = None
                if summary is not None:
                    from shared.rules.enforcement import current_mode, should_reject

                    should, reject_reason = should_reject(summary)
                    if should:
                        # Finding B — durable rejection audit row,
                        # written via its own session BEFORE the
                        # outer savepoint rollback wipes the in-flight
                        # rule_evaluations rows. Without this the
                        # rejection trace lived in stdout only.
                        try:
                            from shared.rules.rejection_audit import (
                                reasons_from_summary,
                                record_rejection,
                            )

                            _first_crit = (summary.critical_failures or [None])[0]
                            # ``summary is not None`` implies the try block
                            # above committed, so ``canonical`` is bound.
                            _canon_event_id = None
                            try:
                                _canon_event_id = str(canonical.event_id)
                            except (NameError, AttributeError):
                                _canon_event_id = None
                            record_rejection(
                                tenant_id=tenant_id,
                                rule_id=getattr(_first_crit, "rule_id", None),
                                rule_version=getattr(_first_crit, "rule_version", None),
                                event_id=_canon_event_id,
                                reasons=reasons_from_summary(summary),
                                source="webhook_compat",
                                enforcement_mode=current_mode(),
                            )
                        except Exception:  # noqa: BLE001
                            logger.error("compat_rejection_audit_inline_error")
                            raise HTTPException(
                                status_code=503, detail="Rejection audit storage is unavailable"
                            ) from None

                        savepoint.rollback()
                        results.append(
                            EventResult(
                                traceability_lot_code=event.traceability_lot_code,
                                cte_type=event.cte_type.value,
                                status="rejected",
                                errors=[f"rule_violation: {reject_reason}"],
                            )
                        )
                        rejected += 1
                        continue

                # Accepted path. Savepoint commits the primary CTE write.
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
                _publish_graph_sync(store_result.event_id, event, tenant_id)

                # Non-blocking failures → exception queue. Separate
                # savepoint so an exception-queue write failure doesn't
                # unwind the accepted CTE persist.
                if summary is not None and not summary.compliant:
                    exc_sp = db_session.begin_nested()
                    try:
                        from shared.exception_queue import ExceptionQueueService

                        exc_svc = ExceptionQueueService(db_session)
                        exc_svc.create_exceptions_from_evaluation(tenant_id, summary)
                        exc_sp.commit()
                    except (ImportError, ValueError, TypeError, RuntimeError) as exc_err:
                        exc_sp.rollback()
                        logger.warning("compat_exception_queue_skipped: %s", str(exc_err))
            except (ValueError, TypeError, RuntimeError) as exc:
                savepoint.rollback()
                # F-3: SQLAlchemyError-class exceptions stringify with SQL + bound
                # params. Log the detail server-side under a correlation_id and
                # return only that opaque token to the caller.
                correlation_id = str(uuid.uuid4())
                logger.warning(
                    "compat_persistence_failed correlation_id=%s error_type=%s error=%s",
                    correlation_id,
                    type(exc).__name__,
                    str(exc),
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

        if run_id is not None and source_file is not None:
            _close_ingestion_run(
                db_session,
                run_id,
                tenant_id,
                accepted=accepted,
                rejected=rejected,
                results=results,
                receipt=source_file,
            )
        if db_session:
            db_session.commit()
    except Exception:
        if db_session:
            db_session.rollback()
        raise
    finally:
        # Exhaust the generator to trigger its finally block (close session)
        next(db_gen, None)

    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        total=len(payload.events),
        events=results,
        ingestion_run_id=run_id,
    )
