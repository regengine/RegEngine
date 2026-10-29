"""
Settings Router.

Tenant-level account settings — company profile, API key management,
data retention, and integrations configuration.

Hardening (settings router):

- Data-retention floors are enforced on *writes* only. The PUT body model
  (:class:`DataRetentionUpdate`) rejects values below the FSMA-204 /
  21 CFR 1.1455(c) floor with HTTP 422. Reads deliberately use the
  floor-free :class:`DataRetention` so legacy JSONB written before the
  floor existed still loads without a 500.
- ``api_keys`` are redacted at every response boundary: callers only ever
  see safe metadata, never the stored key/secret/token material. Redaction
  operates on a copy — the persisted blob and the in-memory cache keep the
  full records so profile/retention re-saves do not destroy key state.
- Both PUT endpoints are rate limited with the shared slowapi limiter and
  emit a best-effort ``SETTINGS_UPDATE`` audit event (changed field names
  only — never profile values, which are PII).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from shared.rate_limit import limiter
from shared.tenant_context import TenantContext
from shared.tenant_settings import get_jsonb, set_jsonb

from .webhook_compat import require_tenant_context

logger = logging.getLogger("settings")


router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])

# ---------------------------------------------------------------------------
# Data-retention floors (21 CFR 1.1455(c): FSMA 204 records kept 2 years).
#
# Enforced on writes only — see ``DataRetentionUpdate``. ``DataRetention``
# itself stays floor-free so legacy under-floor blobs still deserialize on
# GET instead of raising a validation error (500).
# ---------------------------------------------------------------------------
MIN_CTE_RETENTION_DAYS = 730
MIN_AUDIT_LOG_RETENTION_DAYS = 730
MIN_EXPORT_RETENTION_DAYS = 1

# Allowlist / denylist for api_keys redaction. Only the safe metadata keys
# are ever echoed back; anything key-ish is dropped (and, when it is the only
# identifier, reduced to a last-4 fingerprint).
_API_KEY_SAFE_FIELDS = frozenset(
    {"id", "name", "label", "prefix", "last4", "created_at", "last_used_at", "status", "scopes"}
)
_API_KEY_SECRET_FIELDS = ("key", "secret", "token", "hash", "api_key", "value")


class CompanyProfile(BaseModel):
    """Company profile settings."""

    company_name: str = ""
    company_type: str = "distributor"
    primary_contact: str = ""
    contact_email: str = ""
    phone: str = ""
    address: str = ""
    website: str = ""
    fei_number: str = ""  # FDA Establishment Identifier


class DataRetention(BaseModel):
    """Data retention settings."""

    cte_retention_days: int = 1095  # 3 years (FSMA requirement)
    audit_log_retention_days: int = 2555  # 7 years
    export_retention_days: int = 365
    auto_archive: bool = True


class DataRetentionUpdate(DataRetention):
    """Write-time data retention model with FSMA-204 floors.

    Used *only* by ``PUT /{tenant_id}/retention``. Values below the floor are
    rejected with HTTP 422. The read model (:class:`DataRetention`) stays
    floor-free so legacy JSONB persisted before these floors existed still
    loads on GET.
    """

    cte_retention_days: int = Field(default=1095, ge=MIN_CTE_RETENTION_DAYS)
    audit_log_retention_days: int = Field(default=2555, ge=MIN_AUDIT_LOG_RETENTION_DAYS)
    export_retention_days: int = Field(default=365, ge=MIN_EXPORT_RETENTION_DAYS)


class IntegrationStatus(BaseModel):
    """Third-party integration status."""

    id: str
    name: str
    category: str  # iot, erp, retailer, monitoring
    status: str  # connected, disconnected, pending
    last_sync: Optional[str] = None


class SettingsResponse(BaseModel):
    """Complete settings response."""

    tenant_id: str
    profile: CompanyProfile
    data_retention: DataRetention
    integrations: list[IntegrationStatus]
    api_keys: list[dict]
    plan: dict


def _default_settings(tenant_id: str) -> SettingsResponse:
    """Settings for a tenant that has never saved any.

    Every value here is an honest zero: no integration is connected, nothing
    has ever synced, no API key exists, and no usage has accrued. Earlier
    versions returned a demo payload (a "connected" Sensitech feed synced
    "now", two active API keys, 12,847 events used) that read as real tenant
    state on the settings page.
    """
    return SettingsResponse(
        tenant_id=tenant_id,
        profile=CompanyProfile(),
        data_retention=DataRetention(),
        integrations=[
            IntegrationStatus(id="sensitech", name="Sensitech TempTale", category="iot", status="disconnected"),
            IntegrationStatus(id="tive", name="Tive Trackers", category="iot", status="disconnected"),
            IntegrationStatus(id="sap", name="SAP S/4HANA", category="erp", status="disconnected"),
            IntegrationStatus(id="netsuite", name="Oracle NetSuite", category="erp", status="disconnected"),
            IntegrationStatus(id="walmart", name="Walmart GDSN", category="retailer", status="disconnected"),
            IntegrationStatus(id="kroger", name="Kroger 84.51\u00b0", category="retailer", status="disconnected"),
        ],
        api_keys=[],
        plan={
            "id": "professional",
            "name": "Professional",
            "price_monthly": 499,
            "facilities_limit": 5,
            "events_limit": 50000,
            "facilities_used": 0,
            "events_used": 0,
        },
    )


# In-memory fallback for when DB is unavailable
_settings_store: dict[str, SettingsResponse] = {}


def _redact_api_key_entry(entry: object) -> dict:
    """Reduce one api_keys record to safe metadata.

    Keeps only allowlisted keys (id, name, label, prefix, last4, timestamps,
    status, scopes). Drops anything key-ish (key, secret, token, hash,
    api_key, value). If the entry carries no safe identifier at all but does
    carry a raw key-ish string, it is masked to a last-4 fingerprint so the
    caller can still distinguish keys without ever seeing the material.
    """
    if not isinstance(entry, dict):
        return {}
    safe = {k: v for k, v in entry.items() if k in _API_KEY_SAFE_FIELDS}
    if not safe:
        for field_name in _API_KEY_SECRET_FIELDS:
            value = entry.get(field_name)
            if isinstance(value, str) and value:
                safe = {"last4": value[-4:], "status": "redacted"}
                break
    return safe


def _redact_api_keys(api_keys: object) -> list[dict]:
    """Redact a whole api_keys list for response."""
    if not isinstance(api_keys, list):
        return []
    return [_redact_api_key_entry(entry) for entry in api_keys]


def _redacted_response(settings: SettingsResponse) -> SettingsResponse:
    """Return a response copy with api_keys reduced to safe metadata.

    Operates on a copy: the stored blob and the in-memory cache retain the
    full key records so profile/retention re-saves do not destroy them.
    """
    return settings.model_copy(update={"api_keys": _redact_api_keys(settings.api_keys)})


def _audit_settings_update(
    tenant_id: str,
    endpoint: str,
    changed_fields: list[str],
    *,
    db_fallback: bool,
) -> None:
    """Fire-and-forget audit log for a settings mutation.

    Best-effort by design: a successful PUT never fails because the audit
    write failed. Scheduled on the running loop like the EPCIS validation and
    chain-verification audit paths; a failed write is logged via a done
    callback and never raised into the request path.

    Details carry tenant_id, endpoint, the changed field *names*, and whether
    the DB write fell back to memory -- never profile values (PII) or any key
    material.
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

        audit = AuditLogger.get_instance()
        actor = AuditActor(
            actor_id="settings-router",
            actor_type="service",
            tenant_id=tenant_id,
        )
        resource = AuditResource(
            resource_type="tenant_settings",
            resource_id=tenant_id,
            tenant_id=tenant_id,
        )
        coro = audit.log(
            event_type=AuditEventType.SETTINGS_UPDATE,
            category=AuditEventCategory.CONFIGURATION,
            severity=AuditSeverity.WARNING if db_fallback else AuditSeverity.INFO,
            actor=actor,
            action="settings_update",
            outcome="success",
            resource=resource,
            message=f"Tenant settings updated via {endpoint}",
            details={
                "tenant_id": tenant_id,
                "endpoint": endpoint,
                "changed_fields": changed_fields,
                "db_fallback_to_memory": db_fallback,
            },
            tags=["settings", "configuration"],
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro).add_done_callback(_audit_task_done)
        except RuntimeError:
            pass  # No running loop -- skip async audit
    except Exception:
        logger.debug("settings_audit: could not emit audit event", exc_info=True)


def _audit_task_done(task) -> None:
    """Fail loud, not silent: a detached audit write that raised must log."""
    import asyncio

    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.error("settings_audit_write_failed error=%s", exc)


def _db_get_settings(tenant_id: str) -> Optional[SettingsResponse]:
    """Query settings from database via shared helper.

    The stored JSONB blob never persists tenant_id (excluded by
    ``_db_save_settings``); attach the authoritative tenant_id from the
    function argument when constructing the response model.
    """
    stored = get_jsonb(tenant_id, "tenant_settings", "settings")
    if stored:
        return SettingsResponse(**{**stored, "tenant_id": tenant_id})
    return None


def _db_save_settings(tenant_id: str, settings: SettingsResponse) -> bool:
    """Insert or update settings in database via shared helper."""
    return set_jsonb(tenant_id, "tenant_settings", "settings", settings.model_dump(exclude={"tenant_id"}))


@router.get(
    "/{tenant_id}",
    response_model=SettingsResponse,
    summary="Get tenant settings",
)
async def get_settings_endpoint(
    tenant_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
) -> SettingsResponse:
    """Get all settings for a tenant."""
    tenant_id = ctx.tenant_id
    # Try DB first
    settings = _db_get_settings(tenant_id)
    if settings:
        _settings_store[tenant_id] = settings  # cache for fallback
        return _redacted_response(settings)

    # Fall back to memory or return defaults
    if tenant_id not in _settings_store:
        _settings_store[tenant_id] = _default_settings(tenant_id)
    return _redacted_response(_settings_store[tenant_id])


@router.put(
    "/{tenant_id}/profile",
    summary="Update company profile",
)
@limiter.limit("30/minute")
async def update_profile(
    request: Request,
    tenant_id: str,
    profile: CompanyProfile,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Update company profile."""
    tenant_id = ctx.tenant_id
    # Get current settings
    settings = _db_get_settings(tenant_id)
    if settings is None:
        if tenant_id not in _settings_store:
            _settings_store[tenant_id] = _default_settings(tenant_id)
        settings = _settings_store[tenant_id]

    settings.profile = profile

    # Try DB first, fall back to memory
    db_success = _db_save_settings(tenant_id, settings)
    if db_success:
        _settings_store[tenant_id] = settings  # keep cache in sync
    else:
        logger.error("db_write_failed_fallback_to_memory tenant_id=%s endpoint=update_profile", tenant_id)
        _settings_store[tenant_id] = settings

    _audit_settings_update(
        tenant_id,
        endpoint="update_profile",
        changed_fields=sorted(profile.model_dump().keys()),
        db_fallback=not db_success,
    )

    return {"updated": True}


@router.put(
    "/{tenant_id}/retention",
    summary="Update data retention",
)
@limiter.limit("30/minute")
async def update_retention(
    request: Request,
    tenant_id: str,
    retention: DataRetentionUpdate,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Update data retention settings."""
    tenant_id = ctx.tenant_id
    # Get current settings
    settings = _db_get_settings(tenant_id)
    if settings is None:
        if tenant_id not in _settings_store:
            _settings_store[tenant_id] = _default_settings(tenant_id)
        settings = _settings_store[tenant_id]

    # Persist via the floor-free read model so the stored blob round-trips
    # through GET without re-validation.
    settings.data_retention = DataRetention(**retention.model_dump())

    # Try DB first, fall back to memory
    db_success = _db_save_settings(tenant_id, settings)
    if db_success:
        _settings_store[tenant_id] = settings  # keep cache in sync
    else:
        logger.error("db_write_failed_fallback_to_memory tenant_id=%s endpoint=update_retention", tenant_id)
        _settings_store[tenant_id] = settings

    _audit_settings_update(
        tenant_id,
        endpoint="update_retention",
        changed_fields=sorted(retention.model_dump().keys()),
        db_fallback=not db_success,
    )

    return {"updated": True}
