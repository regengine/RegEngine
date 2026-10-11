"""
GDPR Right-to-Erasure API.

Provides a user-facing endpoint for data deletion requests per GDPR Article
17. The endpoint atomically disables the global identity, replaces stored
email identifiers, deactivates memberships, revokes database sessions, writes
an append-only audit redaction order, and queues graph cleanup.

FSMA 204 compliance note: Audit logs that contain actor_email are
anonymized (email masked) rather than deleted, because 21 CFR 1.1310
requires maintaining the traceability audit trail. The anonymization
preserves the audit trail's integrity while removing PII.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from shared.tenant_context import set_tenant_guc
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import arm_global_admin_context, get_session
from .dependencies import get_current_user, get_session_store
from .graph_outbox import enqueue_graph_write
from .models import TenantContext
from .session_store import RedisSessionStore
from .sqlalchemy_models import (
    AuditLogModel,
    AuthChallengeModel,
    MembershipModel,
    MFARecoveryCodeModel,
    OrganizationMembershipModel,
    SessionModel,
    TenantModel,
    UserEmailModel,
    UserModel,
    WebAuthnChallengeModel,
    WebAuthnCredentialModel,
)

logger = structlog.get_logger("erasure")


@contextmanager
def get_db():
    """Compatibility seam for older tests that patch this name.

    Production erasure uses the request-scoped ``get_session`` dependency so
    tenant GUC and admin arming stay on the same connection as
    ``get_current_user``.
    """
    from .database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()

# Graph node labels that represent a user identity. Only nodes carrying one
# of these labels are ever deleted by erasure. Every other node (trace
# events, CTEs, facilities, lots, audit entries) is somebody's compliance
# evidence, so erasure anonymizes its actor reference instead of deleting
# the record. SupplierContact is the only identity label the codebase
# currently writes to the graph (see supplier_graph_sync.py); User,
# Account and TeamMember are kept as defensive matches for identity nodes
# written by other paths. tenant_id, user_id and erased_actor_id are
# always passed as parameters, never interpolated.
_ERASURE_IDENTITY_LABELS: tuple[str, ...] = (
    "User",
    "Account",
    "TeamMember",
    "SupplierContact",
)

_IDENTITY_LABEL_LIST = "[" + ", ".join(f"'{label}'" for label in _ERASURE_IDENTITY_LABELS) + "]"

# Delete only the erased user's own identity nodes for this tenant.
_CYPHER_DELETE_IDENTITY_NODES = f"""
MATCH (n {{tenant_id: $tenant_id}})
WHERE any(label IN labels(n) WHERE label IN {_IDENTITY_LABEL_LIST})
  AND (n.user_id = $user_id OR n.id = $user_id)
DETACH DELETE n
"""

# Anonymize the actor reference on shared records for this tenant. The
# record itself (and its relationships) is preserved because it is other
# parties' FSMA 204 compliance evidence. Identity nodes are excluded here
# because the delete query above already removed them.
_CYPHER_ANONYMIZE_SHARED_ACTOR_REFS = f"""
MATCH (m {{tenant_id: $tenant_id}})
WHERE (m.actor_id = $user_id OR m.user_id = $user_id)
  AND NOT any(label IN labels(m) WHERE label IN {_IDENTITY_LABEL_LIST})
SET m.actor_id = CASE WHEN m.actor_id = $user_id THEN $erased_actor_id ELSE m.actor_id END,
    m.user_id = CASE WHEN m.user_id = $user_id THEN $erased_actor_id ELSE m.user_id END
"""


def _erased_actor_token(user_id: str) -> str:
    """Return a stable pseudonymous actor id for an erased user.

    Deterministic sha256 of the user id, so every shared record that
    referenced the user converges on the same token and repeated erasure
    replays stay idempotent. The raw user id cannot be recovered from it.
    """
    digest = hashlib.sha256(f"gdpr-erasure:{user_id}".encode("utf-8")).hexdigest()
    return f"erased-user-{digest[:16]}"


async def _delete_neo4j_user_graph_data(
    tenant_id: str,
    user_id: str,
    erased_actor_id: Optional[str] = None,
) -> None:
    """Remove a user's graph identity and anonymize their shared references.

    Identity nodes (User, Account, TeamMember, SupplierContact) for
    *user_id* are deleted; shared records that reference the user via
    ``actor_id``/``user_id`` are kept with the reference replaced by a
    stable ``erased-user-<hash>`` token, preserving other parties'
    traceability evidence.

    This is best-effort: if Neo4j is not configured (``NEO4J_URI`` /
    ``NEO4J_URL`` absent) the call is skipped silently.  If the driver is
    configured but a query fails, a warning is logged and the function
    returns without raising so that the already-committed Postgres erasure
    is not affected.

    ``tenant_id``, ``user_id`` and ``erased_actor_id`` are passed as Cypher
    parameters to prevent injection. Both queries stay tenant-scoped:
    account erasure is not tenant offboarding and must not touch another
    tenant's graph.
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

    token = erased_actor_id or _erased_actor_token(str(user_id))
    try:
        from neo4j import AsyncGraphDatabase

        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "")
        if not neo4j_password:
            # Never open the driver with an empty password: skip the graph
            # delete (the HTTP response still reports the Postgres erasure)
            # and leave a warning so the half-wired Neo4j gets fixed.
            logger.warning(
                "erasure_neo4j_skip",
                reason="NEO4J_PASSWORD not configured",
                tenant_id=tenant_id,
                user_id=user_id,
            )
            return
        async with AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password)) as neo4j_driver:
            async with neo4j_driver.session() as session:
                await session.run(
                    _CYPHER_DELETE_IDENTITY_NODES,
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
                await session.run(
                    _CYPHER_ANONYMIZE_SHARED_ACTOR_REFS,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    erased_actor_id=token,
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


def _erased_email(user_id: uuid.UUID, row_id: uuid.UUID | None = None) -> str:
    """Return a unique, non-routable replacement for an erased email."""

    suffix = f"+{row_id.hex}" if row_id is not None else ""
    return f"erased+{user_id.hex}{suffix}@invalid.regengine.local"


def _apply_account_erasure(
    db,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> int:
    """Apply the durable account-erasure transaction without committing.

    The global user row has no ``deleted_at`` column and there is no durable
    hard-delete queue in the current schema.  Treating it as a generic
    ``user_account`` retention table previously generated invalid SQL and the
    retention helper swallowed the error.  This explicit operation matches the
    actual schema and leaves a tamper-evident redaction order that audit exports
    and tenant audit views honor.
    """

    user = db.get(UserModel, user_id)
    if user is None:
        raise LookupError("authenticated user no longer exists")

    membership_tenants = set(
        db.execute(select(MembershipModel.tenant_id).where(MembershipModel.user_id == user_id)).scalars().all()
    )
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        # ``audit_logs`` intentionally has tenant-only SELECT/INSERT policies,
        # even for the armed admin role. Enumerate tenant IDs under the reviewed
        # global arm, then bind each tenant locally and look only for this
        # authenticated identity's history. This finds audit-history-only
        # tenants without adding a broader audit_logs policy.
        audit_tenants = set()
        tenant_ids = db.execute(select(TenantModel.id)).scalars().all()
        for audit_tenant_id in tenant_ids:
            set_tenant_guc(db, str(audit_tenant_id))
            if db.execute(
                select(AuditLogModel.tenant_id)
                .where(
                    AuditLogModel.tenant_id == audit_tenant_id,
                    AuditLogModel.actor_id == user_id,
                )
                .limit(1)
            ).scalar_one_or_none() is not None:
                audit_tenants.add(audit_tenant_id)
    else:
        audit_tenants = set(
            db.execute(
                select(AuditLogModel.tenant_id)
                .where(AuditLogModel.actor_id == user_id)
                .distinct()
            )
            .scalars()
            .all()
        )
    marker_tenants = membership_tenants | audit_tenants | {tenant_id}
    if tenant_id not in membership_tenants:
        raise PermissionError("authenticated user is not a member of the selected tenant")

    now = datetime.now(timezone.utc)
    db.execute(
        update(SessionModel)
        .where(SessionModel.user_id == user_id)
        .values(
            is_revoked=True,
            revoked_at=func.coalesce(SessionModel.revoked_at, now),
            user_agent=None,
            ip_address=None,
            token_hash=None,
            active_membership_id=None,
        )
    )
    db.execute(
        update(MembershipModel)
        .where(MembershipModel.user_id == user_id)
        .values(is_active=False)
    )

    email_rows = db.execute(select(UserEmailModel).where(UserEmailModel.user_id == user_id)).scalars().all()
    email_fingerprints = [row.email_fingerprint for row in email_rows if row.email_fingerprint]
    for email_row in email_rows:
        email_row.email = _erased_email(user_id, email_row.id)
        email_row.email_fingerprint = None
        email_row.is_verified = False

    # Authentication factors/challenges are not compliance evidence. Remove
    # them instead of retaining durable links to the erased identity.
    db.execute(delete(OrganizationMembershipModel).where(OrganizationMembershipModel.user_id == user_id))
    db.execute(delete(WebAuthnCredentialModel).where(WebAuthnCredentialModel.user_id == user_id))
    db.execute(delete(WebAuthnChallengeModel).where(WebAuthnChallengeModel.user_id == user_id))
    db.execute(delete(MFARecoveryCodeModel).where(MFARecoveryCodeModel.user_id == user_id))
    if email_fingerprints:
        db.execute(delete(AuthChallengeModel).where(AuthChallengeModel.email_fingerprint.in_(email_fingerprints)))

    user.email = _erased_email(user_id)
    user.global_status = "erased"
    user.status = "erased"
    user.is_sysadmin = False
    user.mfa_secret = None
    user.mfa_secret_ciphertext = None
    user.token_version = int(user.token_version or 0) + 1
    user.last_login_at = None

    from .audit import AuditLogger

    historical_audit_rows = 0
    for marker_tenant_id in sorted(marker_tenants, key=str):
        # ``audit_logs`` deliberately has no global-sysadmin INSERT policy.
        # Bind each marker write to the tenant derived from this authenticated
        # user's membership/audit history. The setting is transaction-local
        # and cannot be selected by request data.
        if db.bind is not None and db.bind.dialect.name != "sqlite":
            set_tenant_guc(db, str(marker_tenant_id))
        tenant_audit_rows = int(
            db.execute(
                select(func.count(AuditLogModel.id)).where(
                    AuditLogModel.tenant_id == marker_tenant_id,
                    AuditLogModel.actor_id == user_id,
                )
            ).scalar_one()
        )
        historical_audit_rows += tenant_audit_rows
        audit_entry_id = AuditLogger.log_event(
            db,
            tenant_id=marker_tenant_id,
            event_type="data.delete",
            event_category="data_modification",
            severity="info",
            actor_id=user_id,
            actor_email=None,
            action="gdpr_anonymize_user",
            resource_type="user_account",
            resource_id=str(user_id),
            endpoint="/v1/account/erasure",
            metadata={
                "gdpr_article": 17,
                "marker_kind": "per_user_anonymization_order",
                "redacted_user_id": str(user_id),
                "redacted_tenant_id": str(marker_tenant_id),
                "redacted_fields": [
                    "email",
                    "mfa_secret",
                    "session_ip",
                    "session_user_agent",
                    "webauthn_credentials",
                ],
                "records_affected": tenant_audit_rows,
            },
        )
        if audit_entry_id is None:
            raise SQLAlchemyError("account erasure audit marker could not be persisted")

        # Graph cleanup is two durable steps: delete the user's identity
        # nodes, then anonymize their actor reference on shared records.
        # Shared trace/CTE nodes are never deleted; they are other
        # parties' compliance evidence.
        erased_actor_id = _erased_actor_token(str(user_id))
        enqueue_graph_write(
            db,
            tenant_id=str(marker_tenant_id),
            operation="user_erasure",
            cypher=_CYPHER_DELETE_IDENTITY_NODES,
            params={"user_id": str(user_id)},
            dedupe_key=f"user_erasure:{marker_tenant_id}:{user_id}",
        )
        enqueue_graph_write(
            db,
            tenant_id=str(marker_tenant_id),
            operation="user_erasure",
            cypher=_CYPHER_ANONYMIZE_SHARED_ACTOR_REFS,
            params={"user_id": str(user_id), "erased_actor_id": erased_actor_id},
            dedupe_key=f"user_erasure_anonymize:{marker_tenant_id}:{user_id}",
        )
    return historical_audit_rows


async def _revoke_erased_user_runtime_sessions(
    session_store: RedisSessionStore,
    user_id: uuid.UUID,
) -> None:
    """Revoke Redis sessions/elevation state; fail closed after two tries."""

    from .auth.elevation_helpers import _revoke_all_elevation_tokens_for_user

    async def _retry(operation):
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                return await operation()
            except Exception as exc:  # noqa: BLE001 - backend failures all map to 503
                last_error = exc
        assert last_error is not None
        raise last_error

    await _retry(lambda: session_store.revoke_all_user_sessions(user_id))
    await _retry(lambda: _revoke_all_elevation_tokens_for_user(session_store, user_id))


@router.post(
    "/erasure",
    response_model=ErasureResponse,
    summary="Request account data erasure (GDPR Article 17)",
    description=(
        "Disables the account, replaces stored email identifiers, revokes all "
        "sessions, and records a mandatory PII-masking order while preserving "
        "the regulated audit trail."
    ),
)
async def request_erasure(
    body: ErasureRequest,
    current_user: UserModel = Depends(get_current_user),
    session_store: RedisSessionStore = Depends(get_session_store),
    db: Session = Depends(get_session),
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
    if not user_id:
        raise HTTPException(status_code=401, detail="Could not identify user")

    try:
        # Same request-scoped admin session as ``get_current_user``. Tenant is
        # the authenticated principal's bound context, not a new connection.
        tenant_id = TenantContext.get_tenant_context(db)
        if tenant_id is None:
            raise HTTPException(status_code=403, detail="Tenant context required")
        try:
            user_uuid = uuid.UUID(str(user_id))
            tenant_uuid = uuid.UUID(str(tenant_id))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=403, detail="Valid tenant-bound identity required") from exc

        logger.info(
            "erasure_requested",
            user_id=str(user_id),
            tenant_id=str(tenant_id) if tenant_id else None,
            reason_supplied=bool(body.reason),
        )

        try:
            arm_global_admin_context(db)
            _historical_audit_rows = _apply_account_erasure(
                db,
                user_id=user_uuid,
                tenant_id=tenant_uuid,
            )
            db.commit()
        except Exception:
            # The global flag is transaction-local. Rollback clears it on any
            # pre-commit failure; a successful commit clears it without
            # opening a second transaction. No database operation may occur
            # between that durable commit and runtime credential cleanup.
            db.rollback()
            raise

        try:
            await _revoke_erased_user_runtime_sessions(session_store, user_uuid)
        except Exception as exc:  # noqa: BLE001 - Redis errors must not produce a false 2xx
            logger.error("erasure_session_revocation_failed", user_id=str(user_id), error_type=type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Account data was disabled, but authentication cleanup is still pending",
            ) from exc

        # The post-commit Neo4j call below is retained as a low-latency
        # best-effort attempt — the outbox row above is the durability
        # guarantee. The Cypher MATCH/DETACH DELETE is idempotent, so a
        # successful immediate delete followed by a redundant drainer
        # replay is harmless. If Neo4j is reachable: deletion is fast.
        # If unreachable: this no-ops (warning logged) and the drainer
        # eventually applies the same Cypher.
        await _delete_neo4j_user_graph_data(str(tenant_id), str(user_id))

        return ErasureResponse(
            status="accepted",
            message=(
                "Your identity has been disabled, stored email identifiers replaced, "
                "and sessions revoked. Compliance audit history is retained under a "
                "mandatory PII-masking order."
            ),
            soft_deleted=True,
            audit_logs_anonymized=True,
            hard_delete_scheduled=False,
            hard_delete_date=None,
        )

    except HTTPException:
        raise
    except LookupError as e:
        logger.warning("erasure_user_missing", user_id=str(user_id), error=str(e))
        raise HTTPException(status_code=404, detail="Authenticated user no longer exists") from e
    except PermissionError as e:
        logger.warning("erasure_tenant_membership_missing", user_id=str(user_id), error=str(e))
        raise HTTPException(status_code=403, detail="Authenticated user is not a member of the selected tenant") from e
    except ImportError as e:
        logger.error("erasure_import_error", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="Account erasure dependency unavailable. Contact support.",
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
