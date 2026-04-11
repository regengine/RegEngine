"""
Settings Router.

Tenant-level account settings — company profile, API key management,
data retention, and integrations configuration.
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app.webhook_compat import _verify_api_key

logger = logging.getLogger("settings")


def _get_db():
    """Get database session. Returns None if unavailable."""
    try:
        from shared.database import SessionLocal
        return SessionLocal()
    except Exception as exc:
        logger.warning("db_unavailable error=%s", str(exc))
        return None

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


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
    now = datetime.now(timezone.utc)
    return SettingsResponse(
        tenant_id=tenant_id,
        profile=CompanyProfile(),
        data_retention=DataRetention(),
        integrations=[
            IntegrationStatus(id="sensitech", name="Sensitech TempTale", category="iot", status="connected", last_sync=now.isoformat()),
            IntegrationStatus(id="tive", name="Tive Trackers", category="iot", status="disconnected"),
            IntegrationStatus(id="sap", name="SAP S/4HANA", category="erp", status="disconnected"),
            IntegrationStatus(id="netsuite", name="Oracle NetSuite", category="erp", status="disconnected"),
            IntegrationStatus(id="walmart", name="Walmart GDSN", category="retailer", status="pending"),
            IntegrationStatus(id="kroger", name="Kroger 84.51°", category="retailer", status="disconnected"),
        ],
        api_keys=[
            {"id": "key-001", "name": "Production API Key", "prefix": "rge_prod_", "created": now.isoformat(), "last_used": now.isoformat(), "status": "active"},
            {"id": "key-002", "name": "Development Key", "prefix": "rge_dev_", "created": now.isoformat(), "last_used": None, "status": "active"},
        ],
        plan={
            "id": "professional",
            "name": "Professional",
            "price_monthly": 499,
            "facilities_limit": 5,
            "events_limit": 50000,
            "facilities_used": 2,
            "events_used": 12847,
        },
    )


# In-memory fallback for when DB is unavailable
_settings_store: dict[str, SettingsResponse] = {}


def _db_get_settings(tenant_id: str) -> Optional[SettingsResponse]:
    """Query settings from database."""
    db = _get_db()
    if not db:
        return None
    try:
        row = db.execute(
            text("SELECT settings FROM fsma.tenant_settings WHERE tenant_id = :tid"),
            {"tid": tenant_id}
        ).fetchone()
        if not row:
            return None
        settings_data = json.loads(row[0]) if row[0] else {}
        settings_data["tenant_id"] = tenant_id
        return SettingsResponse(**settings_data)
    except Exception as exc:
        logger.warning("db_read_failed error=%s", str(exc))
        return None
    finally:
        db.close()


def _db_save_settings(tenant_id: str, settings: SettingsResponse) -> bool:
    """Insert or update settings in database."""
    db = _get_db()
    if not db:
        return False
    try:
        settings_json = json.dumps(settings.model_dump(exclude={"tenant_id"}))
        db.execute(
            text("""
                INSERT INTO fsma.tenant_settings (tenant_id, settings, created_at, updated_at)
                VALUES (:tid, :json, now(), now())
                ON CONFLICT (tenant_id) DO UPDATE SET settings = :json, updated_at = now()
            """),
            {"tid": tenant_id, "json": settings_json}
        )
        db.commit()
        return True
    except Exception as exc:
        logger.warning("db_write_failed error=%s", str(exc))
        if db:
            db.rollback()
        return False
    finally:
        db.close()


@router.get(
    "/{tenant_id}",
    response_model=SettingsResponse,
    summary="Get tenant settings",
)
async def get_settings_endpoint(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
) -> SettingsResponse:
    """Get all settings for a tenant."""
    # Try DB first
    settings = _db_get_settings(tenant_id)
    if settings:
        return settings
    
    # Fall back to memory or return defaults
    if tenant_id not in _settings_store:
        _settings_store[tenant_id] = _default_settings(tenant_id)
    return _settings_store[tenant_id]


@router.put(
    "/{tenant_id}/profile",
    summary="Update company profile",
)
async def update_profile(
    tenant_id: str,
    profile: CompanyProfile,
    _: None = Depends(_verify_api_key),
):
    """Update company profile."""
    # Get current settings
    settings = _db_get_settings(tenant_id)
    if settings is None:
        if tenant_id not in _settings_store:
            _settings_store[tenant_id] = _default_settings(tenant_id)
        settings = _settings_store[tenant_id]
    
    settings.profile = profile
    
    # Try DB first, fall back to memory
    db_success = _db_save_settings(tenant_id, settings)
    if not db_success:
        _settings_store[tenant_id] = settings
    
    return {"updated": True}


@router.put(
    "/{tenant_id}/retention",
    summary="Update data retention",
)
async def update_retention(
    tenant_id: str,
    retention: DataRetention,
    _: None = Depends(_verify_api_key),
):
    """Update data retention settings."""
    # Get current settings
    settings = _db_get_settings(tenant_id)
    if settings is None:
        if tenant_id not in _settings_store:
            _settings_store[tenant_id] = _default_settings(tenant_id)
        settings = _settings_store[tenant_id]
    
    settings.data_retention = retention
    
    # Try DB first, fall back to memory
    db_success = _db_save_settings(tenant_id, settings)
    if not db_success:
        _settings_store[tenant_id] = settings
    
    return {"updated": True}
