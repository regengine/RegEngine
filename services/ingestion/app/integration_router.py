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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.webhook_compat import _verify_api_key

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


# ── Endpoints ─────────────────────────────────────────────────

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
    )

    cls = get_connector_class(config_req.connector_id)
    if cls is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown connector: {config_req.connector_id}",
        )

    # Derive the category from the connector class metadata if available,
    # falling back to the connector's class name rather than hardcoding "unknown".
    _category = "unknown"
    try:
        _info = cls(ConnectorConfig(
            connector_id=config_req.connector_id,
            display_name=config_req.connector_id,
            category="unknown",
        )).get_connector_info()
        _category = _info.get("category", cls.__name__.lower())
    except Exception:
        logger.debug("Connector info lookup failed", exc_info=True)
        _category = cls.__name__.lower()

    config = ConnectorConfig(
        connector_id=config_req.connector_id,
        display_name=config_req.connector_id,
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

    connector = get_or_create_connector(tenant_id, config_req.connector_id, config)
    return {
        "configured": True,
        "connector_id": config_req.connector_id,
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
    from shared.external_connectors.registry import get_tenant_connectors

    connectors = get_tenant_connectors(tenant_id)
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
    from shared.external_connectors.registry import get_tenant_connectors

    connectors = get_tenant_connectors(tenant_id)
    connector = connectors.get(sync_req.connector_id)
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
    from shared.external_connectors.registry import get_tenant_connectors

    connectors = get_tenant_connectors(tenant_id)
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
    from shared.external_connectors.registry import remove_connector
    remove_connector(tenant_id, connector_id)
    return {"disconnected": True, "connector_id": connector_id}
