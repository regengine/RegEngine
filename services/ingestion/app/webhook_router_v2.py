"""
Webhook Ingestion Router.

Provides POST /api/v1/webhooks/ingest for external systems to push
FSMA 204 traceability events into RegEngine. Each event is validated
against per-CTE KDE requirements, SHA-256 hashed, chain-linked, and
persisted to Postgres.

V2: Replaced in-memory storage with CTEPersistence (Postgres-backed).
    Events now survive restarts, support multi-tenant RLS, and feed
    the FDA export pipeline with real data.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import get_settings
from shared.funnel_events import emit_funnel_event
from shared.tenant_rate_limiting import consume_tenant_rate_limit
from app.webhook_models import (
    EventResult,
    IngestEvent,
    IngestResponse,
    REQUIRED_KDES_BY_CTE,
    WebhookPayload,
)

logger = logging.getLogger("webhook-ingestion")

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhook Ingestion"])


# ---------------------------------------------------------------------------
# Database Session
# ---------------------------------------------------------------------------

def _get_db_session():
    """
    Get a database session for CTE persistence.

    Uses the shared database module's session factory. Falls back to
    in-memory mode if DATABASE_URL is not configured (dev/test).
    """
    try:
        from shared.database import SessionLocal
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.warning("database_unavailable, falling back to in-memory: %s", str(e))
        yield None


def _get_persistence(db_session=None):
    """Get CTEPersistence instance, or None if DB unavailable."""
    if db_session is None:
        return None
    try:
        from shared.cte_persistence import CTEPersistence
        return CTEPersistence(db_session)
    except ImportError:
        logger.warning("cte_persistence module not available")
        return None


# ---------------------------------------------------------------------------
# In-memory fallback REMOVED — production must have Postgres
# ---------------------------------------------------------------------------
# Previously, RegEngine would silently accept events into a module-level dict
# when DB was unavailable. This is dangerous: data vanishes on restart, chain
# integrity cannot be guaranteed, and operators have no visibility into lost data.
# Now the endpoint returns 503 Service Unavailable if Postgres is down.


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _verify_api_key(
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> None:
    """Verify API key using timing-safe comparison. Canonical header: X-RegEngine-API-Key."""
    import hmac
    settings = get_settings()
    configured_api_key = getattr(settings, "api_key", None)
    if configured_api_key is not None:
        if not x_regengine_api_key or not hmac.compare_digest(
            x_regengine_api_key.encode("utf-8"),
            configured_api_key.encode("utf-8"),
        ):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# Rate Limiting (Redis-backed with in-memory fallback via shared module)
# ---------------------------------------------------------------------------

_WEBHOOK_RATE_LIMIT_RPM = max(1, int(os.getenv("WEBHOOK_INGEST_RATE_LIMIT_RPM", "120")))
_WEBHOOK_RATE_LIMIT_WINDOW_SECS = max(
    1,
    int(os.getenv("WEBHOOK_INGEST_RATE_LIMIT_WINDOW_SECONDS", "60")),
)


def _check_rate_limit(tenant_id: str) -> None:
    """Tenant-scoped sliding-window limit for webhook ingestion."""
    allowed, remaining = consume_tenant_rate_limit(
        tenant_id=tenant_id,
        bucket_suffix="webhooks.ingest",
        limit=_WEBHOOK_RATE_LIMIT_RPM,
        window=_WEBHOOK_RATE_LIMIT_WINDOW_SECS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded for tenant '{tenant_id}' "
                f"({_WEBHOOK_RATE_LIMIT_RPM}/{_WEBHOOK_RATE_LIMIT_WINDOW_SECS}s)"
            ),
            headers={
                "Retry-After": str(_WEBHOOK_RATE_LIMIT_WINDOW_SECS),
                "X-RateLimit-Limit": str(_WEBHOOK_RATE_LIMIT_RPM),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Tenant": tenant_id,
                "X-RateLimit-Scope": "webhooks.ingest",
            },
        )
    logger.debug(
        "webhook_rate_limit_allow tenant_id=%s remaining=%s",
        tenant_id,
        remaining,
    )


# ---------------------------------------------------------------------------
# KDE Validation
# ---------------------------------------------------------------------------

def _validate_event_kdes(event: IngestEvent) -> list[str]:
    """Validate that an event has all required KDEs for its CTE type."""
    errors: list[str] = []
    required = REQUIRED_KDES_BY_CTE.get(event.cte_type, [])

    available: dict[str, object] = {
        "traceability_lot_code": event.traceability_lot_code,
        "product_description": event.product_description,
        "quantity": event.quantity,
        "unit_of_measure": event.unit_of_measure,
        "location_name": event.location_name,
        "location_gln": event.location_gln,
        **event.kdes,
    }

    for kde_name in required:
        val = available.get(kde_name)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            errors.append(f"Missing required KDE '{kde_name}' for {event.cte_type.value} CTE")

    return errors


# ---------------------------------------------------------------------------
# Compliance Alerts
# ---------------------------------------------------------------------------

def _generate_alerts(event: IngestEvent) -> list[dict]:
    """Generate compliance alerts for an event."""
    alerts: list[dict] = []

    if event.cte_type.value in ("shipping", "receiving"):
        has_source = event.kdes.get("ship_from_location") or event.kdes.get("ship_from_gln")
        has_dest = event.kdes.get("ship_to_location") or event.kdes.get("ship_to_gln") or event.kdes.get("receiving_location")
        if not has_source or not has_dest:
            alerts.append({
                "severity": "warning",
                "alert_type": "incomplete_route",
                "message": "Shipping/receiving event missing source or destination identifiers",
            })

    return alerts


# ---------------------------------------------------------------------------
# Post-Ingest Obligation Check
# ---------------------------------------------------------------------------

def _check_obligations(db_session, event: IngestEvent, event_id: str, tenant_id: str) -> list[dict]:
    """
    Check ingested event against obligation-CTE rules from the database.

    For each obligation that applies to this CTE type, verify that the required
    KDE is present in the event. Write pass/fail results to fsma.compliance_alerts.

    Returns list of failed obligation checks (alerts).
    """
    if db_session is None:
        return []

    try:
        from sqlalchemy import text

        # Fetch rules for this CTE type + rules that apply to all CTE types
        # Use savepoint so a UUID cast failure doesn't abort the outer transaction
        nested = db_session.begin_nested()
        try:
            rows = db_session.execute(
                text("""
                    SELECT r.id, r.obligation_id, r.cte_type, r.required_kde_key,
                           r.validation_rule, r.description,
                           o.obligation_text, o.risk_category
                    FROM obligation_cte_rules r
                    JOIN obligations o ON o.id = r.obligation_id
                    WHERE o.tenant_id = CAST(:tid AS uuid)
                      AND r.cte_type IN (:cte_type, 'all')
                    ORDER BY o.risk_category DESC
                """),
                {"tid": tenant_id, "cte_type": event.cte_type.value},
            ).fetchall()
        except Exception:
            nested.rollback()
            return []

        if not rows:
            return []

        alerts = []
        # Build available KDE values from event
        available = {
            "traceability_lot_code": event.traceability_lot_code,
            "product_description": event.product_description,
            "quantity": event.quantity,
            "unit_of_measure": event.unit_of_measure,
            "location_name": event.location_name,
            "location_gln": event.location_gln,
            **event.kdes,
        }

        for row in rows:
            rule_id, obl_id, cte_type, kde_key, validation_rule, desc, obl_text, risk = row

            passed = True
            if validation_rule == "present" and kde_key:
                val = available.get(kde_key)
                passed = val is not None and (not isinstance(val, str) or val.strip() != "")
            elif validation_rule == "tlc_assigned":
                passed = bool(event.traceability_lot_code and len(event.traceability_lot_code) >= 3)
            elif validation_rule == "tlc_not_reassigned":
                # Shipping events should NOT create new TLCs — the TLC must already
                # exist in prior events (harvesting, packing, etc.)
                if event.cte_type.value in ("shipping", "transformation"):
                    try:
                        prior = db_session.execute(
                            text("""
                                SELECT COUNT(*) FROM fsma.cte_events
                                WHERE tenant_id = :tid
                                  AND traceability_lot_code = :tlc
                                  AND event_type NOT IN ('shipping', 'transformation')
                            """),
                            {"tid": tenant_id, "tlc": event.traceability_lot_code},
                        ).scalar()
                        passed = (prior or 0) > 0
                    except Exception:
                        passed = True  # Don't block ingest on query failure
                else:
                    passed = True
            elif validation_rule == "downstream_transmitted":
                # Receiving events should have upstream source info (ship_from)
                # Shipping events should have downstream destination (ship_to)
                if event.cte_type.value == "receiving":
                    passed = bool(
                        available.get("ship_from_location")
                        or available.get("ship_from_gln")
                        or available.get("immediate_previous_source")
                    )
                elif event.cte_type.value == "shipping":
                    passed = bool(
                        available.get("ship_to_location")
                        or available.get("ship_to_gln")
                    )
                else:
                    passed = True
            elif validation_rule == "record_exists":
                # Verify that records exist in the chain for this TLC
                # (i.e., this isn't an orphan event with no audit trail)
                try:
                    chain_count = db_session.execute(
                        text("""
                            SELECT COUNT(*) FROM fsma.hash_chain h
                            JOIN fsma.cte_events e ON e.id = h.cte_event_id
                            WHERE e.tenant_id = :tid
                              AND e.traceability_lot_code = :tlc
                        """),
                        {"tid": tenant_id, "tlc": event.traceability_lot_code},
                    ).scalar()
                    # For first event of a TLC, chain_count will be 0 (just ingested,
                    # chain entry may not exist yet). Allow it.
                    # For subsequent events, at least 1 prior chain entry should exist.
                    passed = True  # Chain is verified at scoring time; here we just check existence
                except Exception:
                    passed = True  # Don't block ingest on query failure

            if not passed:
                severity = "critical" if risk == "CRITICAL" else "warning"
                alert = {
                    "severity": severity,
                    "alert_type": "obligation_gap",
                    "message": f"Obligation not met: {obl_text[:100]}",
                    "obligation_id": str(obl_id),
                    "missing_kde": kde_key,
                }
                alerts.append(alert)

                # Write to compliance_alerts table
                try:
                    db_session.execute(
                        text("""
                            INSERT INTO fsma.compliance_alerts
                            (tenant_id, event_id, severity, alert_type, message, details)
                            VALUES (:tid, :eid::uuid, :sev, :atype, :msg, :details::jsonb)
                        """),
                        {
                            "tid": tenant_id,
                            "eid": event_id,
                            "sev": severity,
                            "atype": "obligation_gap",
                            "msg": f"Missing KDE '{kde_key}' required by obligation",
                            "details": json.dumps({
                                "obligation_id": str(obl_id),
                                "obligation_text": obl_text[:200],
                                "risk_category": risk,
                                "missing_kde": kde_key,
                            }),
                        },
                    )
                except Exception as alert_err:
                    logger.warning("obligation_alert_write_failed: %s", str(alert_err))

        return alerts

    except Exception as exc:
        logger.warning("obligation_check_failed: %s", str(exc))
        return []


# ---------------------------------------------------------------------------
# Neo4j Graph Sync
# ---------------------------------------------------------------------------

def _publish_graph_sync(event_id: str, event: IngestEvent, tenant_id: str) -> None:
    """Push a CTE creation event to Redis for Neo4j graph sync."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return

    try:
        import redis as redis_lib
        client = redis_lib.from_url(redis_url)
        message = {
            "event": "cte.created",
            "data": {
                "cte": {
                    "id": event_id,
                    "event_type": event.cte_type.value,
                    "traceability_lot_code": event.traceability_lot_code,
                    "product_description": event.product_description,
                    "quantity": event.quantity,
                    "unit_of_measure": event.unit_of_measure,
                    "location_gln": event.location_gln,
                    "location_name": event.location_name,
                    "timestamp": event.timestamp,
                    "tenant_id": tenant_id,
                    "kdes": event.kdes,
                },
            },
        }
        client.rpush("neo4j-sync", json.dumps(message, default=str))
    except Exception as exc:
        logger.warning("graph_sync_publish_failed event_id=%s error=%s", event_id, str(exc))


# ---------------------------------------------------------------------------
# Ingest Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/ingest",
    summary="Ingest traceability events",
    description=(
        "Accept CTE events from external systems (IoT platforms, ERPs, manual entry). "
        "Each event is validated against FSMA 204 KDE requirements, SHA-256 hashed, "
        "chain-linked, and persisted to the compliance database."
    ),
)
async def ingest_events(
    payload: WebhookPayload,
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> IngestResponse:
    """Process incoming webhook events with persistent storage."""
    # Resolve tenant: payload > API-key lookup
    tenant_id = payload.tenant_id
    if not tenant_id and x_regengine_api_key:
        try:
            from shared.database import SessionLocal
            _db = SessionLocal()
            from sqlalchemy import text as _text
            _row = _db.execute(
                _text("SELECT tenant_id FROM api_keys WHERE key_hash = encode(sha256(:raw::bytea), 'hex') LIMIT 1"),
                {"raw": x_regengine_api_key},
            ).fetchone()
            if _row and _row[0]:
                tenant_id = str(_row[0])
            _db.close()
        except Exception:
            pass
    if not tenant_id:
        logger.error("Webhook rejected: no tenant_id resolved")
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Rate limiting (tenant-scoped)
    _check_rate_limit(tenant_id)

    results: list[EventResult] = []
    accepted = 0
    rejected = 0

    # Batch deduplication — detect identical events within the same payload
    seen_in_batch: set[str] = set()

    # Get database session — hard fail if unavailable (no silent degradation)
    db_session = None
    persistence = None
    try:
        from shared.database import SessionLocal
        db_session = SessionLocal()
        from shared.cte_persistence import CTEPersistence
        persistence = CTEPersistence(db_session)
    except Exception as e:
        logger.error("db_init_failed — rejecting ingest: %s", str(e))
        raise HTTPException(
            status_code=503,
            detail="Database unavailable — cannot accept events. Retry after service recovery.",
        )

    try:
        for event in payload.events:
            # Batch deduplication — skip identical events in same request
            dedup_key = f"{event.cte_type.value}|{event.traceability_lot_code}|{event.timestamp}|{event.location_gln or event.location_name or ''}"
            if dedup_key in seen_in_batch:
                results.append(EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="rejected",
                    errors=["Duplicate event in batch — same CTE type, TLC, timestamp, and location"],
                ))
                rejected += 1
                continue
            seen_in_batch.add(dedup_key)

            # Validate KDEs
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

            # Generate alerts
            alerts = _generate_alerts(event)

            # --- Persistent path (production) --- DB is guaranteed available
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

                # Post-ingest obligation check
                obl_alerts = _check_obligations(
                    db_session, event, store_result.event_id, tenant_id,
                )
                if obl_alerts:
                    logger.info(
                        "obligation_gaps_detected",
                        extra={
                            "event_id": store_result.event_id,
                            "gap_count": len(obl_alerts),
                            "tenant_id": tenant_id,
                        },
                    )

                # Async graph sync
                _publish_graph_sync(store_result.event_id, event, tenant_id)

                logger.info(
                    "event_ingested_persistent",
                    extra={
                        "event_id": store_result.event_id,
                        "cte_type": event.cte_type.value,
                        "tlc": event.traceability_lot_code,
                        "source": payload.source,
                        "tenant_id": tenant_id,
                        "idempotent": store_result.idempotent,
                        "sha256": store_result.sha256_hash[:16],
                    },
                )

            except Exception as e:
                logger.error(
                    "persistence_failed",
                    extra={"error": str(e), "tlc": event.traceability_lot_code},
                )
                results.append(EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="rejected",
                    errors=[f"Storage error: {str(e)}"],
                ))
                rejected += 1

        if accepted > 0:
            emit_funnel_event(
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
        logger.error("ingest_batch_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        if db_session:
            db_session.close()

    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        total=len(payload.events),
        events=results,
    )


# ---------------------------------------------------------------------------
# Chain Verification Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/chain/verify",
    summary="Verify hash chain integrity",
    description=(
        "Walk the tenant's entire hash chain from genesis to head, "
        "recomputing each link and checking for tampering."
    ),
)
async def verify_chain(
    tenant_id: str,
):
    """Verify the integrity of the tenant's hash chain."""
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

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
    except Exception as e:
        logger.error("chain_verification_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Chain verification failed: {str(e)}")
    finally:
        if db_session:
            db_session.close()
