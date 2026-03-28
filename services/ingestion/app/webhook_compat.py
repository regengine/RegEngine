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

import logging
from typing import Optional

from fastapi import Header, Request

from app.webhook_models import EventResult, IngestResponse, WebhookPayload
from app.webhook_router_v2 import (
    _check_rate_limit,
    _generate_alerts,
    _get_db_session,
    _publish_graph_sync,
    _validate_event_kdes,
    _verify_api_key as _verify_api_key_sync,
)
from shared.auth import require_api_key

logger = logging.getLogger("webhook-compat")


async def _verify_api_key(
    request: Request,
    x_regengine_api_key: Optional[str] = Header(
        default=None, alias="X-RegEngine-API-Key"
    ),
) -> None:
    """Auth gate — delegates to shared.auth.require_api_key.

    This is the stable import surface for ingestion sub-routers.
    All auth logic (preshared key, scoped keys, test bypass) lives
    in ``shared/auth.py``.  Callers use ``Depends(_verify_api_key)``
    exactly as before; the return value is discarded.
    """
    await require_api_key(request=request, x_regengine_api_key=x_regengine_api_key)


async def ingest_events(
    payload: WebhookPayload,
    x_regengine_api_key: Optional[str] = None,
) -> IngestResponse:
    """Perform ingestion outside of HTTP/FastAPI context.

    Unlike the v2 router endpoint, this function manages its own DB
    session and does not rely on FastAPI dependency injection.
    """
    # Verify the API key using the sync helper (no Request object needed)
    _verify_api_key_sync(x_regengine_api_key=x_regengine_api_key)

    tenant_id = payload.tenant_id
    if not tenant_id:
        raise ValueError("Tenant context required — payload must include tenant_id")

    from app.tenant_validation import validate_tenant_id
    validate_tenant_id(tenant_id)

    _check_rate_limit(tenant_id)

    # Obtain a DB session from the generator dependency manually
    db_gen = _get_db_session()
    db_session = next(db_gen)

    if db_session is None:
        raise RuntimeError("Database unavailable — cannot accept events.")

    try:
        from shared.cte_persistence import CTEPersistence
        persistence = CTEPersistence(db_session)
    except (ImportError, RuntimeError, ConnectionError) as exc:
        # Exhaust the generator so cleanup runs
        try:
            next(db_gen, None)
        except StopIteration:
            pass
        raise RuntimeError(f"Database unavailable: {exc}") from exc

    results: list[EventResult] = []
    accepted = 0
    rejected = 0
    seen_in_batch: set[str] = set()

    try:
        for event in payload.events:
            dedup_key = (
                f"{event.cte_type.value}|{event.traceability_lot_code}"
                f"|{event.timestamp}|{event.location_gln or event.location_name or ''}"
            )
            if dedup_key in seen_in_batch:
                results.append(EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="rejected",
                    errors=["Duplicate event in batch"],
                ))
                rejected += 1
                continue
            seen_in_batch.add(dedup_key)

            errors = _validate_event_kdes(event)
            if errors:
                results.append(EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="rejected",
                    errors=errors,
                ))
                rejected += 1
                continue

            alerts = _generate_alerts(event)

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
                results.append(EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="accepted",
                    event_id=store_result.event_id,
                    sha256_hash=store_result.sha256_hash,
                    chain_hash=store_result.chain_hash,
                ))
                accepted += 1
                _publish_graph_sync(store_result.event_id, event, tenant_id)

                # Canonical normalization + rule evaluation
                try:
                    from shared.canonical_event import normalize_webhook_event
                    from shared.canonical_persistence import CanonicalEventStore
                    canonical = normalize_webhook_event(event, tenant_id)
                    canonical_store = CanonicalEventStore(db_session, dual_write=False)
                    canonical_store.persist_event(canonical)
                    # Auto-evaluate rules
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
                    # Auto-create exceptions from failures
                    if not summary.compliant:
                        from shared.exception_queue import ExceptionQueueService
                        exc_svc = ExceptionQueueService(db_session)
                        exc_svc.create_exceptions_from_evaluation(tenant_id, summary)
                except (ImportError, ValueError, TypeError, RuntimeError) as canon_err:
                    logger.warning("compat_canonical_write_skipped: %s", str(canon_err))
            except (ValueError, TypeError, RuntimeError) as exc:
                logger.error("compat_persistence_failed: %s", str(exc))
                results.append(EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="rejected",
                    errors=[f"Storage error: {exc}"],
                ))
                rejected += 1

        if db_session:
            db_session.commit()
    except Exception:
        if db_session:
            db_session.rollback()
        raise
    finally:
        # Exhaust the generator to trigger its finally block (close session)
        try:
            next(db_gen, None)
        except StopIteration:
            pass

    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        total=len(payload.events),
        events=results,
    )
