"""
GDPR Right-to-Erasure API.

Provides a user-facing endpoint for data deletion requests per
GDPR Article 17. Soft-deletes user account data immediately and
schedules hard-delete after the configured retention period.

FSMA 204 compliance note: Audit logs that contain actor_email are
anonymized (email masked) rather than deleted, because 21 CFR 1.1310
requires maintaining the traceability audit trail. The anonymization
preserves the audit trail's integrity while removing PII.
"""

from __future__ import annotations

import os
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from shared.database import get_db
from sqlalchemy.exc import SQLAlchemyError

from .dependencies import get_current_user
from .graph_outbox import enqueue_graph_write
from .models import TenantContext
from .sqlalchemy_models import UserModel

logger = structlog.get_logger("erasure")

# Cypher to detach-delete only graph nodes that represent the erased user.
# tenant_id and user_id are always passed as parameters, never interpolated.
_CYPHER_DELETE_USER_GRAPH_DATA = """
MATCH (n {tenant_id: $tenant_id})
WHERE n.user_id = $user_id
   OR n.actor_id = $user_id
   OR (
        n.id = $user_id
        AND any(label IN labels(n) WHERE label IN [
            'User',
            'Account',
            'TeamMember',
            'SupplierContact'
        ])
   )
DETACH DELETE n
"""


async def _delete_neo4j_user_graph_data(tenant_id: str, user_id: str) -> None:
    """Delete Neo4j nodes for *user_id* as part of GDPR erasure.

    This is best-effort: if Neo4j is not configured (``NEO4J_URI`` /
    ``NEO4J_URL`` absent) the call is skipped silently.  If the driver is
    configured but the query fails, a warning is logged and the function
    returns without raising so that the already-committed Postgres erasure
    is not affected.

    ``tenant_id`` and ``user_id`` are passed as Cypher parameters to prevent
    injection.  The query must stay user-scoped: account erasure is not tenant
    offboarding and must not delete the tenant's traceability graph.
    """
    if not tenant_id or not user_id:
        logger.debug(
            "erasure_neo4j_skip",
            reason="tenant_id/user_id missing",
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return

    neo4j_uri = (os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL") or "").strip()
    if not neo4j_uri:
        logger.debug(
            "erasure_neo4j_skip",
            reason="NEO4J_URI not configured",
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return

    try:
        from neo4j import AsyncGraphDatabase

        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "")
        async with AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password)) as neo4j_driver:
            async with neo4j_driver.session() as session:
                await session.run(
                    _CYPHER_DELETE_USER_GRAPH_DATA,
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
        logger.info(
            "erasure_neo4j_user_graph_data_deleted",
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "erasure_neo4j_user_graph_data_failed",
            tenant_id=tenant_id,
            user_id=user_id,
            error=str(exc),
        )


router = APIRouter(prefix="/v1/account", tags=["Account"])


class ErasureRequest(BaseModel):
    """Request body for GDPR right-to-erasure."""

    reason: Optional[str] = Field(
        default=None,
        description="Optional reason for the deletion request",
    )
    confirm: bool = Field(
        ...,
        description="Must be true to confirm deletion. This action is irreversible.",
    )


class ErasureResponse(BaseModel):
    """Response from erasure request."""

    status: str
    message: str
    soft_deleted: bool = False
    audit_logs_anonymized: bool = False
    hard_delete_scheduled: bool = False
    hard_delete_date: Optional[str] = None


@router.post(
    "/erasure",
    response_model=ErasureResponse,
    summary="Request account data erasure (GDPR Article 17)",
    description=(
        "Soft-deletes your account data and schedules permanent deletion. "
        "Audit logs are anonymized (email masked) to preserve FSMA 204 "
        "traceability requirements while removing PII."
    ),
)
async def request_erasure(
    body: ErasureRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """Process a GDPR right-to-erasure request for the authenticated user."""
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="You must set confirm=true to proceed with account erasure.",
        )

    # RE-SEC-001: ``current_user`` is a SQLAlchemy ``UserModel`` instance, not
    # a dict. Previously this code called ``.get("user_id")`` etc. which
    # raised AttributeError on every invocation; the broad ``except Exception``
    # below swallowed it and returned a misleading "logged and processed
    # manually" 500. GDPR Article 17 erasure was silently non-functional.
    # Tenant comes from the RLS context bound by ``get_current_user`` --
    # ``UserModel`` does not carry a tenant_id column.
    user_id = current_user.id
    email = current_user.email or "unknown"
    if not user_id:
        raise HTTPException(status_code=401, detail="Could not identify user")

    try:
        from shared.audit_logging import AuditActor
        from shared.data_retention import (
            DataRetentionManager,
            DeletionRequest,
            RetentionPolicy,
        )
        from shared.pii import mask_email

        with get_db() as db:
            # Tenant is read from the RLS context bound by ``get_current_user``
            # on the same connection, not from the user object (UserModel has
            # no tenant_id) and not from the request body (untrusted).
            tenant_id = TenantContext.get_tenant_context(db)

            logger.info(
                "erasure_requested",
                user_id=str(user_id),
                tenant_id=str(tenant_id) if tenant_id else None,
                reason=body.reason,
            )

            manager = DataRetentionManager()

            # ``AuditActor`` exposes ``email`` (not ``actor_email``).
            # The previous attribute name raised TypeError on every
            # erasure call and silently kept GDPR Article 17 broken
            # even after #1441 realigned the downstream method
            # signatures.  This is fix #1092.
            actor = AuditActor(
                actor_type="user",
                actor_id=user_id,
                email=mask_email(email),
                tenant_id=str(tenant_id) if tenant_id else None,
            )

            # The DeletionRequest enum uses USER_INITIATED in this codebase
            # (not USER_REQUEST, which was the wrong identifier previously).
            deletion_request = DeletionRequest.USER_INITIATED

            # Parse tenant/user as UUID when possible (both the shared
            # retention layer and the audit-log INSERT require UUIDs).
            # If parsing fails the erasure still proceeds for the
            # soft-delete side; the per-user anonymization then
            # degrades to a logged no-op.
            try:
                user_uuid = uuid.UUID(str(user_id))
            except (TypeError, ValueError):
                user_uuid = None
            try:
                tenant_uuid = uuid.UUID(str(tenant_id)) if tenant_id else None
            except (TypeError, ValueError):
                tenant_uuid = None

            # 1. Soft-delete the user account record (global resource,
            # no tenant_id required — see _GLOBAL_RESOURCES).
            result = await manager.process_deletion_request(
                db=db,
                resource_type="user_account",
                record_id=user_id,
                policy=RetentionPolicy.USER_ACCOUNT,
                deletion_request=deletion_request,
                actor=actor,
                reason=body.reason or "GDPR Article 17 right-to-erasure request",
            )

            # 2. Emit a per-user GDPR anonymization order for the
            # tenant's audit trail.  Uses the new
            # ``anonymize_audit_logs_for_user`` method introduced for
            # #1092 — the previous batch ``anonymize_audit_logs``
            # targeted the retention threshold (24-month-old rows) and
            # had the wrong semantics for a right-to-erasure request.
            anonymized_count = 0
            if user_uuid is not None and tenant_uuid is not None:
                try:
                    anonymized_count, _anonymize_errors = await manager.anonymize_audit_logs_for_user(
                        db=db,
                        user_id=user_uuid,
                        tenant_id=tenant_uuid,
                        actor=actor,
                    )
                except Exception as anon_err:  # noqa: BLE001
                    # Do not fail the whole erasure if anonymization
                    # errors; the soft-delete is the primary action.
                    logger.warning(
                        "erasure_anonymize_audit_logs_failed",
                        user_id=user_id,
                        error=str(anon_err),
                    )
                    anonymized_count = 0
            else:
                logger.warning(
                    "erasure_anonymize_audit_logs_skipped_non_uuid",
                    user_id=user_id,
                    tenant_id=tenant_id,
                )

            # 3. Durable Neo4j user-graph deletion via the graph outbox.
            #    Pre-fix: a post-commit best-effort call to
            #    _delete_neo4j_user_graph_data opened its own AsyncGraphDatabase
            #    driver. If Neo4j was unreachable at request time, the deletion
            #    silently no-op'd while the Postgres commit had already
            #    persisted the soft-delete — a real GDPR liability.
            #
            #    Now: enqueue an outbox row inside the same Postgres
            #    transaction as the soft-delete + audit anonymization. The
            #    drainer (admin/app/graph_outbox.py:GraphOutboxDrainer)
            #    replays the Cypher with retry + backoff. Both halves land
            #    atomically (or neither does); Neo4j unavailability shifts
            #    from "silent no-op" to "eventually consistent".
            #
            #    Parameters are passed as Cypher params, not interpolated.
            #    User-scoped; tenant-graph offboarding is a different flow.
            if tenant_id is not None:
                enqueue_graph_write(
                    db,
                    tenant_id=str(tenant_id),
                    operation="user_erasure",
                    cypher=_CYPHER_DELETE_USER_GRAPH_DATA,
                    params={"user_id": str(user_id)},
                    dedupe_key=f"user_erasure:{user_id}",
                )

            db.commit()

        # The post-commit Neo4j call below is retained as a low-latency
        # best-effort attempt — the outbox row above is the durability
        # guarantee. The Cypher MATCH/DETACH DELETE is idempotent, so a
        # successful immediate delete followed by a redundant drainer
        # replay is harmless. If Neo4j is reachable: deletion is fast.
        # If unreachable: this no-ops (warning logged) and the drainer
        # eventually applies the same Cypher.
        if tenant_id is not None:
            await _delete_neo4j_user_graph_data(str(tenant_id), str(user_id))

        return ErasureResponse(
            status="accepted",
            message=(
                "Your account data has been marked for deletion. "
                "Audit logs have been anonymized to comply with both GDPR and FSMA 204. "
                "Permanent deletion will occur after the retention period."
            ),
            soft_deleted=result.get("soft_deleted", False),
            audit_logs_anonymized=bool(anonymized_count),
            hard_delete_scheduled=result.get("hard_delete_scheduled", False),
            hard_delete_date=result.get("hard_delete_date"),
        )

    except ImportError as e:
        logger.error("erasure_import_error", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="Data retention module not available. Contact support.",
        )
    except SQLAlchemyError as e:
        # RE-SEC-001: previously this branch was a broad ``except Exception``
        # that swallowed AttributeError from the dict-style ``current_user``
        # access above and returned a misleading "logged and will be processed
        # manually" 500. The user was assured GDPR Article 17 had been
        # honored; in reality every request silently failed. We now narrow to
        # known infrastructure failure modes (DB / cache). Programmer errors
        # (AttributeError, TypeError, KeyError, etc.) propagate to FastAPI's
        # default 500 handler so they surface in tests, in Sentry, and in the
        # /v1/account/erasure response itself rather than being whitewashed.
        logger.error("erasure_failed_db", user_id=str(user_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Erasure request failed due to a backend error. Please retry.",
        )
