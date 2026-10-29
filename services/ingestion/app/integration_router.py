"""Integration management API router.

Provides REST endpoints for:
  - Listing available integrations
  - Configuring connector credentials per tenant
  - Testing connections
  - Triggering manual syncs
  - CSV upload for the generic CSV/SFTP connector
  - Receiving inbound webhooks from external systems

Hardening (findings 2-6; finding 1 credential store deferred):

- Rate limits on configure / sync / csv-upload / disconnect / profile
  mutations and the inbound webhook (shared slowapi limiter).
- Webhook path fails closed with a uniform 401 body (no secret-state
  oracle) and rejects replayed signature digests inside a short TTL
  nonce window.
- CSV ingest runs every cell through ``sanitize_cell`` before events
  leave the upload handler (formula-injection neutralization).
- Request models are bounded (``extra="forbid"`` + max_length / ge/le).
- Tenant-bound audit events on configure / disconnect / sync /
  csv-upload / profile mutations attribute the signed-in principal
  (``ctx.principal_id`` / ``principal_kind`` / ``actor_email``) and
  never carry secret material.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from shared.database import get_db_safe
from shared.rate_limit import limiter
from shared.tenant_context import TenantContext
from sqlalchemy import text

from .shared.csv_safety import sanitize_cell
from .shared.upload_limits import (
    MAX_CSV_FILE_SIZE_BYTES,
    read_upload_with_limit,
    sanitize_upload_filename,
)
from .webhook_compat import require_tenant_context

logger = logging.getLogger("integration-router")

router = APIRouter(prefix="/api/v1/integrations", tags=["Integrations"])

# Abuse budgets (finding 2). Credential configure and sync are the highest
# risk; webhook already had a limit and keeps 60/min. Profile edits are
# low-frequency human actions.
_CONFIGURE_RATE_LIMIT = "10/minute"
_SYNC_RATE_LIMIT = "10/minute"
_CSV_UPLOAD_RATE_LIMIT = "20/minute"
_DISCONNECT_RATE_LIMIT = "20/minute"
_PROFILE_MUTATION_RATE_LIMIT = "30/minute"
_WEBHOOK_RATE_LIMIT = "60/minute"

# Replay window for webhook signature digests (finding 3). Same digest
# inside this TTL is treated as a replay and rejected with the same
# uniform 401 body as any other verification failure (no oracle).
_WEBHOOK_NONCE_TTL_SECONDS = 300
_webhook_nonce_lock = threading.Lock()
_webhook_nonce_seen: dict[str, float] = {}

# Uniform webhook rejection body — never distinguish missing secret,
# missing signature, bad digest, stale timestamp, or replay.
_WEBHOOK_REJECTED_DETAIL = {"error": "webhook_rejected", "message": "Webhook verification failed"}



# ── Models ────────────────────────────────────────────────────


class ConnectorConfigRequest(BaseModel):
    """Request to configure a connector.

    Finding 5: bounded + ``extra="forbid"``. Secret fields are accepted
    on write but never echoed by the configure response. Finding 1
    (credential store) is deferred — secrets still live in the
    process-local registry until that lands.
    """

    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(..., min_length=1, max_length=120)
    api_key: Optional[str] = Field(default=None, max_length=4096)
    api_secret: Optional[str] = Field(default=None, max_length=4096)
    oauth_client_id: Optional[str] = Field(default=None, max_length=512)
    oauth_client_secret: Optional[str] = Field(default=None, max_length=4096)
    webhook_secret: Optional[str] = Field(default=None, max_length=4096)
    base_url: Optional[str] = Field(default=None, max_length=2048)
    extra: Dict[str, Any] = Field(default_factory=dict, max_length=50)


class SyncRequest(BaseModel):
    """Request to trigger a manual sync."""

    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(..., min_length=1, max_length=120)
    since: Optional[str] = Field(default=None, max_length=40)  # ISO 8601
    limit: int = Field(default=100, ge=1, le=1000)


ProfileSourceType = Literal["csv", "edi", "epcis", "api", "webhook", "spreadsheet", "supplier_portal"]
ProfileStatus = Literal["draft", "active", "archived"]


DEFAULT_PROFILE_MAPPING: Dict[str, str] = {
    "cte_type": "cte_type",
    "traceability_lot_code": "traceability_lot_code",
    "product_description": "product_description",
    "quantity": "quantity",
    "unit_of_measure": "unit_of_measure",
    "location_name": "location_name",
    "timestamp": "timestamp",
    "ship_from_location": "ship_from_location",
    "ship_to_location": "ship_to_location",
    "reference_document": "reference_document",
}


class IntegrationProfile(BaseModel):
    """Reusable supplier/source mapping profile."""

    profile_id: str
    tenant_id: str
    display_name: str
    source_type: ProfileSourceType = "csv"
    field_mapping: Dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_PROFILE_MAPPING))
    default_cte_type: str = "shipping"
    status: ProfileStatus = "draft"
    confidence: float = Field(default=0.75, ge=0, le=1)
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    updated_at: str
    last_used_at: Optional[str] = None


class CreateIntegrationProfileRequest(BaseModel):
    """Create a saved mapping profile for a supplier or source system."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(..., min_length=2, max_length=120)
    source_type: ProfileSourceType = "csv"
    field_mapping: Dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_PROFILE_MAPPING), max_length=64)
    default_cte_type: str = Field(default="shipping", max_length=64)
    status: ProfileStatus = "active"
    confidence: float = Field(default=0.75, ge=0, le=1)
    supplier_id: Optional[str] = Field(default=None, max_length=120)
    supplier_name: Optional[str] = Field(default=None, max_length=160)
    notes: Optional[str] = Field(default=None, max_length=1000)


class UpdateIntegrationProfileRequest(BaseModel):
    """Patch mutable fields on a saved integration profile."""

    model_config = ConfigDict(extra="forbid")

    display_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    source_type: Optional[ProfileSourceType] = None
    field_mapping: Optional[Dict[str, str]] = Field(default=None, max_length=64)
    default_cte_type: Optional[str] = Field(default=None, max_length=64)
    status: Optional[ProfileStatus] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    supplier_id: Optional[str] = Field(default=None, max_length=120)
    supplier_name: Optional[str] = Field(default=None, max_length=160)
    notes: Optional[str] = Field(default=None, max_length=1000)


class MappingPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: List[Dict[str, Any]] = Field(default_factory=list, max_length=50)


class MappingPreviewResponse(BaseModel):
    profile_id: str
    mapped: int
    missing_fields: Dict[str, List[str]]
    events: List[Dict[str, Any]]


_profile_store: dict[str, dict[str, IntegrationProfile]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tenant_uuid(tenant_id: str) -> Optional[str]:
    try:
        return str(uuid.UUID(str(tenant_id)))
    except (TypeError, ValueError):
        return None


def _set_tenant_context(db: Any, tenant_id: str) -> None:
    # Phase B (#1934): delegate to the canonical tenant-GUC primitive.
    # _if_uuid skips the GUC for non-UUID tenant ids (matching _tenant_uuid's
    # tolerance above); fail-hard get_tenant_context() RLS still rejects any
    # DB access without tenant context.
    from shared.tenant_context import set_tenant_guc_if_uuid

    set_tenant_guc_if_uuid(db, tenant_id)


def _profile_from_row(row: Any) -> IntegrationProfile:
    mapping = row._mapping if hasattr(row, "_mapping") else row
    return IntegrationProfile(
        profile_id=str(mapping["profile_id"]),
        tenant_id=str(mapping["tenant_id"]),
        display_name=mapping["display_name"],
        source_type=mapping["source_type"],
        field_mapping=dict(mapping["field_mapping"] or {}),
        default_cte_type=mapping["default_cte_type"],
        status=mapping["status"],
        confidence=float(mapping["confidence"] or 0),
        supplier_id=mapping.get("supplier_id"),
        supplier_name=mapping.get("supplier_name"),
        notes=mapping.get("notes"),
        created_at=mapping["created_at"].isoformat() if mapping.get("created_at") else _now_iso(),
        updated_at=mapping["updated_at"].isoformat() if mapping.get("updated_at") else _now_iso(),
        last_used_at=mapping["last_used_at"].isoformat() if mapping.get("last_used_at") else None,
    )


def _db_list_profiles(tenant_id: str) -> Optional[list[IntegrationProfile]]:
    if not _tenant_uuid(tenant_id):
        return None
    db = get_db_safe()
    if not db:
        return None
    try:
        _set_tenant_context(db, tenant_id)
        rows = (
            db.execute(
                text(
                    """
                SELECT profile_id, tenant_id::text AS tenant_id, display_name, source_type,
                       field_mapping, default_cte_type, status, confidence, supplier_id,
                       supplier_name, notes, created_at, updated_at, last_used_at
                FROM fsma.supplier_integration_profiles
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                ORDER BY updated_at DESC
                """
                ),
                {"tenant_id": tenant_id},
            )
            .mappings()
            .all()
        )
        return [_profile_from_row(row) for row in rows]
    except Exception as exc:
        logger.warning("integration_profiles_db_list_failed tenant=%s error=%s", tenant_id, str(exc))
        return None
    finally:
        db.close()


def _db_get_profile(tenant_id: str, profile_id: str) -> Optional[IntegrationProfile]:
    if not _tenant_uuid(tenant_id):
        return None
    db = get_db_safe()
    if not db:
        return None
    try:
        _set_tenant_context(db, tenant_id)
        row = (
            db.execute(
                text(
                    """
                SELECT profile_id, tenant_id::text AS tenant_id, display_name, source_type,
                       field_mapping, default_cte_type, status, confidence, supplier_id,
                       supplier_name, notes, created_at, updated_at, last_used_at
                FROM fsma.supplier_integration_profiles
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                  AND profile_id = :profile_id
                """
                ),
                {"tenant_id": tenant_id, "profile_id": profile_id},
            )
            .mappings()
            .first()
        )
        return _profile_from_row(row) if row else None
    except Exception as exc:
        logger.warning(
            "integration_profiles_db_get_failed tenant=%s profile=%s error=%s", tenant_id, profile_id, str(exc)
        )
        return None
    finally:
        db.close()


def _db_upsert_profile(profile: IntegrationProfile) -> bool:
    if not _tenant_uuid(profile.tenant_id):
        return False
    db = get_db_safe()
    if not db:
        return False
    try:
        _set_tenant_context(db, profile.tenant_id)
        db.execute(
            text(
                """
                INSERT INTO fsma.supplier_integration_profiles (
                    profile_id, tenant_id, display_name, source_type, field_mapping,
                    default_cte_type, status, confidence, supplier_id, supplier_name,
                    notes, created_at, updated_at, last_used_at
                )
                VALUES (
                    :profile_id, CAST(:tenant_id AS uuid), :display_name, :source_type,
                    CAST(:field_mapping AS jsonb), :default_cte_type, :status, :confidence,
                    :supplier_id, :supplier_name, :notes, CAST(:created_at AS timestamptz),
                    CAST(:updated_at AS timestamptz), CAST(:last_used_at AS timestamptz)
                )
                ON CONFLICT (tenant_id, profile_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    source_type = EXCLUDED.source_type,
                    field_mapping = EXCLUDED.field_mapping,
                    default_cte_type = EXCLUDED.default_cte_type,
                    status = EXCLUDED.status,
                    confidence = EXCLUDED.confidence,
                    supplier_id = EXCLUDED.supplier_id,
                    supplier_name = EXCLUDED.supplier_name,
                    notes = EXCLUDED.notes,
                    updated_at = EXCLUDED.updated_at,
                    last_used_at = EXCLUDED.last_used_at
                """
            ),
            {
                **profile.model_dump(mode="json"),
                "field_mapping": json.dumps(profile.field_mapping, sort_keys=True),
            },
        )
        db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "integration_profiles_db_upsert_failed tenant=%s profile=%s error=%s",
            profile.tenant_id,
            profile.profile_id,
            str(exc),
        )
        db.rollback()
        return False
    finally:
        db.close()


def _memory_list_profiles(tenant_id: str) -> list[IntegrationProfile]:
    return list(_profile_store.get(tenant_id, {}).values())


def _memory_get_profile(tenant_id: str, profile_id: str) -> Optional[IntegrationProfile]:
    return _profile_store.get(tenant_id, {}).get(profile_id)


def _save_profile(profile: IntegrationProfile) -> IntegrationProfile:
    if not _db_upsert_profile(profile):
        _profile_store.setdefault(profile.tenant_id, {})[profile.profile_id] = profile
    return profile


def _get_profile_or_404(tenant_id: str, profile_id: str) -> IntegrationProfile:
    profile = _db_get_profile(tenant_id, profile_id) or _memory_get_profile(tenant_id, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Integration profile '{profile_id}' not found")
    return profile


def _extract_path(event: Dict[str, Any], path: str) -> Any:
    current: Any = event
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _apply_profile_mapping(event: Dict[str, Any], profile: IntegrationProfile) -> tuple[Dict[str, Any], list[str]]:
    mapped: Dict[str, Any] = {}
    missing: list[str] = []
    for canonical, source_path in profile.field_mapping.items():
        value = _extract_path(event, source_path)
        if value is None or value == "":
            missing.append(canonical)
            continue
        mapped[canonical] = value
    mapped.setdefault("cte_type", profile.default_cte_type)
    mapped["_integration_profile_id"] = profile.profile_id
    mapped["_source_type"] = profile.source_type
    if profile.supplier_name:
        mapped.setdefault("supplier_name", profile.supplier_name)
    return mapped, missing


# ── Hardening helpers (findings 3, 4, 6) ───────────────────────


def _sanitize_value(value: Any) -> Any:
    """Recursively neutralize CSV formula prefixes in string leaves."""
    if isinstance(value, str):
        return sanitize_cell(value)
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    return value


def _sanitize_ingest_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply ``sanitize_cell`` to every string in parse_csv ingest dicts."""
    return [_sanitize_value(event) for event in events]


def _webhook_nonce_key(tenant_id: str, connector_id: str, payload: bytes, signature_header: str) -> str:
    """Stable digest for replay detection (tenant + connector + body + sig)."""
    material = b"|".join(
        [
            tenant_id.encode("utf-8"),
            connector_id.encode("utf-8"),
            payload,
            signature_header.encode("utf-8"),
        ]
    )
    return hashlib.sha256(material).hexdigest()


def _webhook_nonce_seen_before(nonce_key: str) -> bool:
    """Return True if this nonce was already accepted inside the TTL window.

    Does not record the key — call ``_webhook_nonce_remember`` only after
    successful verification so a failed attempt does not burn the nonce.
    """
    now = time.monotonic()
    with _webhook_nonce_lock:
        stale = [k for k, ts in _webhook_nonce_seen.items() if now - ts > _WEBHOOK_NONCE_TTL_SECONDS]
        for k in stale:
            _webhook_nonce_seen.pop(k, None)
        return nonce_key in _webhook_nonce_seen


def _webhook_nonce_remember(nonce_key: str) -> None:
    """Record a successfully verified webhook digest for the replay TTL."""
    with _webhook_nonce_lock:
        _webhook_nonce_seen[nonce_key] = time.monotonic()


def _reset_webhook_nonces_for_tests() -> None:
    """Test-only: clear the in-process webhook nonce cache."""
    with _webhook_nonce_lock:
        _webhook_nonce_seen.clear()


def _audit_task_done(task) -> None:
    """Fail loud, not silent: a detached audit write that raised must log."""
    import asyncio

    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("integration_audit_write_failed error=%s", exc)


def _audit_integration_event(
    *,
    ctx: TenantContext,
    event_type_name: str,
    action: str,
    tenant_id: str,
    connector_or_profile_id: str,
    resource_type: str,
    changed_fields: list[str],
) -> None:
    """Fire-and-forget tenant-bound audit for an integration mutation.

    Best-effort: a successful mutation never fails because the audit
    write could not be scheduled. Details carry field NAMES and ids
    only — never api_key / api_secret / oauth / webhook_secret / extra
    secret material (finding 1 / finding 6).
    """
    try:
        import asyncio

        from shared.audit_logging import (
            AuditActor,
            AuditEventCategory,
            AuditEventType,
            AuditLogger,
            AuditResource,
            AuditSeverity,
        )

        event_type = getattr(AuditEventType, event_type_name)
        audit = AuditLogger.get_instance()
        actor = AuditActor(
            actor_id=ctx.principal_id,
            actor_type=ctx.principal_kind,
            email=ctx.actor_email,
            tenant_id=tenant_id,
        )
        resource = AuditResource(
            resource_type=resource_type,
            resource_id=connector_or_profile_id,
            tenant_id=tenant_id,
        )
        coro = audit.log(
            event_type=event_type,
            category=AuditEventCategory.CONFIGURATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action=action,
            outcome="success",
            resource=resource,
            message=f"integration {action}",
            details={
                "tenant_id": tenant_id,
                "changed_fields": changed_fields,
                "resource_id": connector_or_profile_id,
            },
            tags=["integration", "connector"],
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro).add_done_callback(_audit_task_done)
        except RuntimeError:
            try:
                coro.close()
            except Exception:
                pass
    except Exception:  # pragma: no cover - defensive
        logger.debug("audit_integration_event: could not emit audit event", exc_info=True)


# ── Endpoints ─────────────────────────────────────────────────


@router.get(
    "/profiles/{tenant_id}",
    summary="List saved integration profiles",
)
async def list_integration_profiles(
    tenant_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """List saved supplier/source mapping profiles for a tenant."""
    tenant_id = ctx.tenant_id
    profiles = _db_list_profiles(tenant_id)
    if profiles is None:
        profiles = _memory_list_profiles(tenant_id)
    return {"profiles": [profile.model_dump() for profile in profiles], "total": len(profiles)}


@router.post(
    "/profiles/{tenant_id}",
    response_model=IntegrationProfile,
    summary="Create a saved integration profile",
)
@limiter.limit(_PROFILE_MUTATION_RATE_LIMIT)
async def create_integration_profile(
    request: Request,
    tenant_id: str,
    body: CreateIntegrationProfileRequest,
    ctx: TenantContext = Depends(require_tenant_context),
) -> IntegrationProfile:
    """Create a reusable field mapping profile for supplier onboarding."""
    tenant_id = ctx.tenant_id
    now = _now_iso()
    profile = IntegrationProfile(
        profile_id=f"prof_{uuid.uuid4().hex[:12]}",
        tenant_id=tenant_id,
        created_at=now,
        updated_at=now,
        **body.model_dump(),
    )
    saved = _save_profile(profile)
    _audit_integration_event(
        ctx=ctx,
        event_type_name="DATA_CREATE",
        action="profile_create",
        tenant_id=tenant_id,
        connector_or_profile_id=saved.profile_id,
        resource_type="integration_profile",
        changed_fields=sorted(body.model_dump(exclude_unset=True).keys()) or ["display_name"],
    )
    return saved


@router.get(
    "/profiles/{tenant_id}/{profile_id}",
    response_model=IntegrationProfile,
    summary="Get a saved integration profile",
)
async def get_integration_profile(
    tenant_id: str,
    profile_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
) -> IntegrationProfile:
    """Fetch one saved profile."""
    tenant_id = ctx.tenant_id
    return _get_profile_or_404(tenant_id, profile_id)


@router.patch(
    "/profiles/{tenant_id}/{profile_id}",
    response_model=IntegrationProfile,
    summary="Update a saved integration profile",
)
@limiter.limit(_PROFILE_MUTATION_RATE_LIMIT)
async def update_integration_profile(
    request: Request,
    tenant_id: str,
    profile_id: str,
    body: UpdateIntegrationProfileRequest,
    ctx: TenantContext = Depends(require_tenant_context),
) -> IntegrationProfile:
    """Patch a saved supplier/source mapping profile."""
    tenant_id = ctx.tenant_id
    profile = _get_profile_or_404(tenant_id, profile_id)
    updates = body.model_dump(exclude_unset=True)
    profile = profile.model_copy(update={**updates, "updated_at": _now_iso()})
    saved = _save_profile(profile)
    _audit_integration_event(
        ctx=ctx,
        event_type_name="DATA_UPDATE",
        action="profile_update",
        tenant_id=tenant_id,
        connector_or_profile_id=profile_id,
        resource_type="integration_profile",
        changed_fields=sorted(updates.keys()) or ["profile_id"],
    )
    return saved


@router.post(
    "/profiles/{tenant_id}/{profile_id}/preview",
    response_model=MappingPreviewResponse,
    summary="Preview profile mapping against sample events",
)
@limiter.limit(_PROFILE_MUTATION_RATE_LIMIT)
async def preview_integration_profile_mapping(
    request: Request,
    tenant_id: str,
    profile_id: str,
    body: MappingPreviewRequest,
    ctx: TenantContext = Depends(require_tenant_context),
) -> MappingPreviewResponse:
    """Apply a saved profile to sample events without committing records."""
    tenant_id = ctx.tenant_id
    profile = _get_profile_or_404(tenant_id, profile_id)
    mapped_events: list[Dict[str, Any]] = []
    missing_fields: Dict[str, List[str]] = {}
    for index, event in enumerate(body.events):
        mapped, missing = _apply_profile_mapping(event, profile)
        mapped_events.append(mapped)
        if missing:
            missing_fields[str(index)] = missing

    profile.last_used_at = _now_iso()
    _save_profile(profile)
    return MappingPreviewResponse(
        profile_id=profile.profile_id,
        mapped=len(mapped_events),
        missing_fields=missing_fields,
        events=mapped_events,
    )


@router.get(
    "/available",
    summary="List all available integrations",
    dependencies=[Depends(require_tenant_context)],
)
async def list_available_integrations():
    """List all registered integration connectors with their metadata."""
    from shared.external_connectors.registry import list_available_connectors

    return {"integrations": list_available_connectors()}


@router.get(
    "/status/{tenant_id}",
    summary="Get integration statuses for a tenant",
)
async def get_integration_statuses(
    tenant_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Get connection status of all integrations for a tenant."""
    tenant_id = ctx.tenant_id
    from shared.external_connectors.registry import get_all_integration_statuses

    return {"integrations": get_all_integration_statuses(tenant_id)}


@router.post(
    "/configure/{tenant_id}",
    summary="Configure an integration connector",
)
@limiter.limit(_CONFIGURE_RATE_LIMIT)
async def configure_connector(
    request: Request,
    tenant_id: str,
    config_req: ConnectorConfigRequest,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Set up credentials for an integration connector.

    This stores the connector config and creates an active instance
    for the tenant.
    """
    from shared.external_connectors.base import AuthType, ConnectorConfig
    from shared.external_connectors.registry import (
        get_connector_class,
        get_or_create_connector,
        remove_connector,
        resolve_connector_id,
    )

    tenant_id = ctx.tenant_id
    connector_id = resolve_connector_id(config_req.connector_id)
    cls = get_connector_class(connector_id)
    if cls is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown connector: {config_req.connector_id}",
        )

    # Fail fast on a provably non-public base URL: every connector GET runs
    # through SSRF validation, so a loopback, link-local, or otherwise
    # non-global literal base could never sync. Rejecting here surfaces the
    # misconfiguration at setup instead of as a late "Connection test
    # failed" during sync. This check is deliberately DNS-free (no live
    # lookup at setup time); hostnames that resolve to private addresses
    # are still refused per hop at fetch time. On-prem bases are not
    # supported; that needs an explicit allowlist decision first.
    if config_req.base_url:
        from ipaddress import ip_address
        from urllib.parse import urlparse

        from shared.url_validation import SSRFError, validate_url

        try:
            validate_url(config_req.base_url, resolve_dns=False)
            host = urlparse(config_req.base_url).hostname or ""
            try:
                literal = ip_address(host)
            except ValueError:
                literal = None
            if literal is not None:
                mapped = getattr(literal, "ipv4_mapped", None)
                if not (mapped or literal).is_global:
                    raise SSRFError(f"base_url IP {literal} is not a public global address")
        except SSRFError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"base_url is not a publicly reachable URL: {exc}",
            ) from exc

    # Derive the category from the connector class metadata if available,
    # falling back to the connector's class name rather than hardcoding "unknown".
    _category = "unknown"
    try:
        _info = cls(
            ConnectorConfig(
                connector_id=connector_id,
                display_name=connector_id,
                category="unknown",
            )
        ).get_connector_info()
        _category = _info.get("category", cls.__name__.lower())
    except Exception:
        logger.debug("Connector info lookup failed", exc_info=True)
        _category = cls.__name__.lower()

    config = ConnectorConfig(
        connector_id=connector_id,
        display_name=connector_id,
        category=_category,
        api_key=config_req.api_key or "",
        api_secret=config_req.api_secret or "",
        oauth_client_id=config_req.oauth_client_id or "",
        oauth_client_secret=config_req.oauth_client_secret or "",
        webhook_secret=config_req.webhook_secret or "",
        base_url=config_req.base_url or "",
        tenant_id=tenant_id,
        extra=config_req.extra,
    )

    # Reconfigure replaces the cached instance instead of keeping the
    # first one, so a rotated secret (for example the webhook secret)
    # takes effect immediately for this tenant.
    remove_connector(tenant_id, connector_id)
    connector = get_or_create_connector(tenant_id, connector_id, config)
    # Finding 6: audit configure with field NAMES only — never secret values.
    changed = [
        name
        for name, present in (
            ("api_key", bool(config_req.api_key)),
            ("api_secret", bool(config_req.api_secret)),
            ("oauth_client_id", bool(config_req.oauth_client_id)),
            ("oauth_client_secret", bool(config_req.oauth_client_secret)),
            ("webhook_secret", bool(config_req.webhook_secret)),
            ("base_url", bool(config_req.base_url)),
            ("extra", bool(config_req.extra)),
        )
        if present
    ]
    _audit_integration_event(
        ctx=ctx,
        event_type_name="CONFIG_CHANGE",
        action="configure",
        tenant_id=tenant_id,
        connector_or_profile_id=connector_id,
        resource_type="integration_connector",
        changed_fields=changed or ["connector_id"],
    )
    return {
        "configured": True,
        "connector_id": connector_id,
        "status": connector.status.value,
    }


@router.post(
    "/test/{tenant_id}/{connector_id}",
    summary="Test an integration connection",
)
async def test_connection(
    tenant_id: str,
    connector_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Test that a configured connector can reach its external system."""
    from shared.external_connectors.registry import (
        get_tenant_connectors,
        resolve_connector_id,
    )

    tenant_id = ctx.tenant_id
    connectors = get_tenant_connectors(tenant_id)
    connector_id = resolve_connector_id(connector_id)
    connector = connectors.get(connector_id)
    if not connector:
        raise HTTPException(
            status_code=404,
            detail=f"Connector '{connector_id}' not configured for tenant '{tenant_id}'",
        )

    connected = await connector.test_connection()
    return {
        "connector_id": connector_id,
        "connected": connected,
        "status": connector.status.value,
    }


@router.post(
    "/sync/{tenant_id}",
    summary="Trigger a manual sync",
)
@limiter.limit(_SYNC_RATE_LIMIT)
async def trigger_sync(
    request: Request,
    tenant_id: str,
    sync_req: SyncRequest,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Manually trigger a sync for a configured connector.

    Fetches events from the external system and ingests them
    into RegEngine's CTE pipeline.
    """
    from shared.external_connectors.registry import (
        get_tenant_connectors,
        resolve_connector_id,
    )

    tenant_id = ctx.tenant_id
    connectors = get_tenant_connectors(tenant_id)
    connector_id = resolve_connector_id(sync_req.connector_id)
    connector = connectors.get(connector_id)
    if not connector:
        raise HTTPException(
            status_code=404,
            detail=f"Connector '{sync_req.connector_id}' not configured",
        )

    since = None
    if sync_req.since:
        since = datetime.fromisoformat(sync_req.since.replace("Z", "+00:00"))

    result = await connector.sync(since=since, limit=sync_req.limit)

    _audit_integration_event(
        ctx=ctx,
        event_type_name="DATA_BULK_OPERATION",
        action="sync",
        tenant_id=tenant_id,
        connector_or_profile_id=connector_id,
        resource_type="integration_connector",
        changed_fields=["sync"],
    )
    return {
        "connector_id": result.connector_id,
        "events_fetched": result.events_fetched,
        "events_accepted": result.events_accepted,
        "events_rejected": result.events_rejected,
        "errors": result.errors,
        "duration_ms": result.duration_ms,
        "success": result.success,
    }


@router.post(
    "/csv-upload/{tenant_id}",
    summary="Upload CSV for CTE import",
)
@limiter.limit(_CSV_UPLOAD_RATE_LIMIT)
async def upload_csv(
    request: Request,
    tenant_id: str,
    file: UploadFile = File(...),
    source_system: str = Query(default="csv_upload", description="Source ERP system name", max_length=120),
    default_cte_type: str = Query(default="receiving", description="Default CTE type for rows", max_length=64),
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Upload a CSV file and import rows as CTE events.

    Uses the CSV/SFTP connector to parse and normalize rows.
    Supports auto-column-mapping for SAP, NetSuite, Fishbowl,
    QuickBooks, and custom CSV formats.
    """
    from shared.external_connectors.base import ConnectorConfig
    from shared.external_connectors.csv_sftp import CSVSFTPConnector

    tenant_id = ctx.tenant_id
    safe_filename = sanitize_upload_filename(file.filename, fallback="upload.csv")
    content = await read_upload_with_limit(
        file,
        max_bytes=MAX_CSV_FILE_SIZE_BYTES,
        label="CSV file",
    )
    if not content:
        raise HTTPException(status_code=400, detail="Empty CSV upload")
    try:
        csv_text = content.decode("utf-8-sig")  # handle BOM
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV upload must be valid UTF-8") from exc

    config = ConnectorConfig(
        connector_id="csv_sftp",
        display_name="CSV Upload",
        category="developer",
        tenant_id=tenant_id,
        extra={
            "source_system": source_system,
            "default_cte_type": default_cte_type,
        },
    )
    connector = CSVSFTPConnector(config)
    events = connector.parse_csv(csv_text, source_file=safe_filename)

    # Convert to ingest format, then neutralize CSV formula prefixes
    # (finding 4). Applied at the HTTP ingest surface so every string
    # that leaves parse_csv is sanitized before it reaches callers.
    ingest_events = _sanitize_ingest_events([e.to_ingest_dict() for e in events])

    _audit_integration_event(
        ctx=ctx,
        event_type_name="DATA_CREATE",
        action="csv_upload",
        tenant_id=tenant_id,
        connector_or_profile_id="csv_sftp",
        resource_type="integration_csv_upload",
        changed_fields=["csv_upload"],
    )
    return {
        "filename": safe_filename,
        "rows_parsed": len(events),
        "events": ingest_events,
        "source_system": source_system,
        "default_cte_type": default_cte_type,
    }


@router.post(
    "/webhook/{tenant_id}/{connector_id}",
    summary="Receive inbound webhook from external system",
)
@limiter.limit(_WEBHOOK_RATE_LIMIT)
async def receive_webhook(
    tenant_id: str,
    connector_id: str,
    request: Request,
):
    """Handle inbound webhook from an external integration.

    Each connector validates signatures and normalizes the payload
    into CTE events.

    Note: This endpoint does NOT require API key auth — it uses
    the connector's webhook secret for verification instead.
    Connectors must fail closed (raise ValueError, mapped to a
    uniform 401) when their webhook secret is not configured or
    the signature is missing or invalid. Finding 3: the 401 body
    never distinguishes missing-secret / bad-digest / replay
    (no secret-state oracle), and a repeated signature digest
    inside the nonce TTL is rejected as a replay. The response
    carries only an accepted count, never the normalized
    inspection data.
    """
    from shared.external_connectors.registry import (
        get_tenant_connectors,
        resolve_connector_id,
    )

    connectors = get_tenant_connectors(tenant_id)
    connector_id = resolve_connector_id(connector_id)
    connector = connectors.get(connector_id)
    if not connector:
        raise HTTPException(
            status_code=404,
            detail=f"Connector '{connector_id}' not configured",
        )

    payload = await request.body()
    headers = dict(request.headers)
    # Prefer the common HMAC header names; empty string if absent so
    # the nonce key is still stable for a given body.
    signature_header = (
        headers.get("x-signature")
        or headers.get("x-hub-signature-256")
        or headers.get("x-safetyculture-signature")
        or ""
    )
    nonce_key = _webhook_nonce_key(tenant_id, connector_id, payload, signature_header)
    if _webhook_nonce_seen_before(nonce_key):
        # Replay inside the TTL — same uniform body as any other
        # verification failure (finding 3).
        raise HTTPException(status_code=401, detail=_WEBHOOK_REJECTED_DETAIL)

    try:
        events = await connector.handle_webhook(payload, headers)
        _webhook_nonce_remember(nonce_key)
        logger.info(
            "webhook_received connector=%s tenant=%s events=%d",
            connector_id,
            tenant_id,
            len(events),
        )
        # Never return normalized inspection data to the webhook
        # caller. The caller is authenticated only by the shared
        # webhook secret, so echoing tenant records here would leak
        # one tenant's data to anyone holding the secret.
        return {
            "accepted": len(events),
            "connector_id": connector_id,
        }
    except NotImplementedError:
        # NotImplemented is not a secret-state signal; keep 501 so
        # clients can disable an unsupported webhook.
        raise HTTPException(
            status_code=501,
            detail=f"Connector '{connector_id}' does not support webhooks",
        )
    except ValueError:
        # Finding 3: uniform body — never echo str(exc) (oracle).
        raise HTTPException(status_code=401, detail=_WEBHOOK_REJECTED_DETAIL)


@router.delete(
    "/disconnect/{tenant_id}/{connector_id}",
    summary="Disconnect an integration",
)
@limiter.limit(_DISCONNECT_RATE_LIMIT)
async def disconnect_connector(
    request: Request,
    tenant_id: str,
    connector_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Remove a configured connector for a tenant."""
    from shared.external_connectors.registry import (
        remove_connector,
        resolve_connector_id,
    )

    tenant_id = ctx.tenant_id
    connector_id = resolve_connector_id(connector_id)
    remove_connector(tenant_id, connector_id)
    _audit_integration_event(
        ctx=ctx,
        event_type_name="CONFIG_CHANGE",
        action="disconnect",
        tenant_id=tenant_id,
        connector_or_profile_id=connector_id,
        resource_type="integration_connector",
        changed_fields=["disconnect"],
    )
    return {"disconnected": True, "connector_id": connector_id}
