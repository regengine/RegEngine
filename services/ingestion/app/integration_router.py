"""Integration management API router.

Provides REST endpoints for:
  - Listing available integrations
  - Configuring connector credentials per tenant
  - Testing connections
  - Triggering manual syncs
  - CSV upload for the generic CSV/SFTP connector
  - Receiving inbound webhooks from external systems
"""

from __future__ import annotations

import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text

from .webhook_compat import _verify_api_key
from shared.database import get_db_safe

logger = logging.getLogger("integration-router")

router = APIRouter(prefix="/api/v1/integrations", tags=["Integrations"])


# ── Models ────────────────────────────────────────────────────

class ConnectorConfigRequest(BaseModel):
    """Request to configure a connector."""
    connector_id: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    base_url: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class SyncRequest(BaseModel):
    """Request to trigger a manual sync."""
    connector_id: str
    since: Optional[str] = None  # ISO 8601
    limit: int = 100


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
    display_name: str = Field(..., min_length=2, max_length=120)
    source_type: ProfileSourceType = "csv"
    field_mapping: Dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_PROFILE_MAPPING))
    default_cte_type: str = "shipping"
    status: ProfileStatus = "active"
    confidence: float = Field(default=0.75, ge=0, le=1)
    supplier_id: Optional[str] = Field(default=None, max_length=120)
    supplier_name: Optional[str] = Field(default=None, max_length=160)
    notes: Optional[str] = Field(default=None, max_length=1000)


class UpdateIntegrationProfileRequest(BaseModel):
    """Patch mutable fields on a saved integration profile."""
    display_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    source_type: Optional[ProfileSourceType] = None
    field_mapping: Optional[Dict[str, str]] = None
    default_cte_type: Optional[str] = None
    status: Optional[ProfileStatus] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    supplier_id: Optional[str] = Field(default=None, max_length=120)
    supplier_name: Optional[str] = Field(default=None, max_length=160)
    notes: Optional[str] = Field(default=None, max_length=1000)


class MappingPreviewRequest(BaseModel):
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
    db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})


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
        rows = db.execute(
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
        ).mappings().all()
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
        row = db.execute(
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
        ).mappings().first()
        return _profile_from_row(row) if row else None
    except Exception as exc:
        logger.warning("integration_profiles_db_get_failed tenant=%s profile=%s error=%s", tenant_id, profile_id, str(exc))
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
        logger.warning("integration_profiles_db_upsert_failed tenant=%s profile=%s error=%s", profile.tenant_id, profile.profile_id, str(exc))
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


# ── Endpoints ─────────────────────────────────────────────────

@router.get(
    "/profiles/{tenant_id}",
    summary="List saved integration profiles",
)
async def list_integration_profiles(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
):
    """List saved supplier/source mapping profiles for a tenant."""
    profiles = _db_list_profiles(tenant_id)
    if profiles is None:
        profiles = _memory_list_profiles(tenant_id)
    return {"profiles": [profile.model_dump() for profile in profiles], "total": len(profiles)}


@router.post(
    "/profiles/{tenant_id}",
    response_model=IntegrationProfile,
    summary="Create a saved integration profile",
)
async def create_integration_profile(
    tenant_id: str,
    request: CreateIntegrationProfileRequest,
    _: None = Depends(_verify_api_key),
) -> IntegrationProfile:
    """Create a reusable field mapping profile for supplier onboarding."""
    now = _now_iso()
    profile = IntegrationProfile(
        profile_id=f"prof_{uuid.uuid4().hex[:12]}",
        tenant_id=tenant_id,
        created_at=now,
        updated_at=now,
        **request.model_dump(),
    )
    return _save_profile(profile)


@router.get(
    "/profiles/{tenant_id}/{profile_id}",
    response_model=IntegrationProfile,
    summary="Get a saved integration profile",
)
async def get_integration_profile(
    tenant_id: str,
    profile_id: str,
    _: None = Depends(_verify_api_key),
) -> IntegrationProfile:
    """Fetch one saved profile."""
    return _get_profile_or_404(tenant_id, profile_id)


@router.patch(
    "/profiles/{tenant_id}/{profile_id}",
    response_model=IntegrationProfile,
    summary="Update a saved integration profile",
)
async def update_integration_profile(
    tenant_id: str,
    profile_id: str,
    request: UpdateIntegrationProfileRequest,
    _: None = Depends(_verify_api_key),
) -> IntegrationProfile:
    """Patch a saved supplier/source mapping profile."""
    profile = _get_profile_or_404(tenant_id, profile_id)
    updates = request.model_dump(exclude_unset=True)
    profile = profile.model_copy(update={**updates, "updated_at": _now_iso()})
    return _save_profile(profile)


@router.post(
    "/profiles/{tenant_id}/{profile_id}/preview",
    response_model=MappingPreviewResponse,
    summary="Preview profile mapping against sample events",
)
async def preview_integration_profile_mapping(
    tenant_id: str,
    profile_id: str,
    request: MappingPreviewRequest,
    _: None = Depends(_verify_api_key),
) -> MappingPreviewResponse:
    """Apply a saved profile to sample events without committing records."""
    profile = _get_profile_or_404(tenant_id, profile_id)
    mapped_events: list[Dict[str, Any]] = []
    missing_fields: Dict[str, List[str]] = {}
    for index, event in enumerate(request.events):
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
    dependencies=[Depends(_verify_api_key)],
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
    _: None = Depends(_verify_api_key),
):
    """Get connection status of all integrations for a tenant."""
    from shared.external_connectors.registry import get_all_integration_statuses
    return {"integrations": get_all_integration_statuses(tenant_id)}


@router.post(
    "/configure/{tenant_id}",
    summary="Configure an integration connector",
)
async def configure_connector(
    tenant_id: str,
    config_req: ConnectorConfigRequest,
    _: None = Depends(_verify_api_key),
):
    """Set up credentials for an integration connector.

    This stores the connector config and creates an active instance
    for the tenant.
    """
    from shared.external_connectors.base import AuthType, ConnectorConfig
    from shared.external_connectors.registry import (
        get_connector_class,
        get_or_create_connector,
        resolve_connector_id,
    )

    connector_id = resolve_connector_id(config_req.connector_id)
    cls = get_connector_class(connector_id)
    if cls is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown connector: {config_req.connector_id}",
        )

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

    connector = get_or_create_connector(tenant_id, connector_id, config)
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
    _: None = Depends(_verify_api_key),
):
    """Test that a configured connector can reach its external system."""
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
async def trigger_sync(
    tenant_id: str,
    sync_req: SyncRequest,
    _: None = Depends(_verify_api_key),
):
    """Manually trigger a sync for a configured connector.

    Fetches events from the external system and ingests them
    into RegEngine's CTE pipeline.
    """
    from shared.external_connectors.registry import (
        get_tenant_connectors,
        resolve_connector_id,
    )

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
async def upload_csv(
    tenant_id: str,
    file: UploadFile = File(...),
    source_system: str = Query(default="csv_upload", description="Source ERP system name"),
    default_cte_type: str = Query(default="receiving", description="Default CTE type for rows"),
    _: None = Depends(_verify_api_key),
):
    """Upload a CSV file and import rows as CTE events.

    Uses the CSV/SFTP connector to parse and normalize rows.
    Supports auto-column-mapping for SAP, NetSuite, Fishbowl,
    QuickBooks, and custom CSV formats.
    """
    from shared.external_connectors.base import ConnectorConfig
    from shared.external_connectors.csv_sftp import CSVSFTPConnector

    content = await file.read()
    csv_text = content.decode("utf-8-sig")  # handle BOM

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
    events = connector.parse_csv(csv_text, source_file=file.filename or "upload.csv")

    # Convert to ingest format
    ingest_events = [e.to_ingest_dict() for e in events]

    return {
        "filename": file.filename,
        "rows_parsed": len(events),
        "events": ingest_events,
        "source_system": source_system,
        "default_cte_type": default_cte_type,
    }


@router.post(
    "/webhook/{tenant_id}/{connector_id}",
    summary="Receive inbound webhook from external system",
)
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

    try:
        events = await connector.handle_webhook(payload, headers)
        ingest_events = [e.to_ingest_dict() for e in events]
        logger.info(
            "webhook_received connector=%s tenant=%s events=%d",
            connector_id, tenant_id, len(events),
        )
        return {
            "accepted": len(events),
            "events": ingest_events,
        }
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail=f"Connector '{connector_id}' does not support webhooks",
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.delete(
    "/disconnect/{tenant_id}/{connector_id}",
    summary="Disconnect an integration",
)
async def disconnect_connector(
    tenant_id: str,
    connector_id: str,
    _: None = Depends(_verify_api_key),
):
    """Remove a configured connector for a tenant."""
    from shared.external_connectors.registry import (
        remove_connector,
        resolve_connector_id,
    )
    connector_id = resolve_connector_id(connector_id)
    remove_connector(tenant_id, connector_id)
    return {"disconnected": True, "connector_id": connector_id}
