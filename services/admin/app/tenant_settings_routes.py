"""Tenant settings and onboarding status endpoints."""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from .database import get_session
from .dependencies import get_current_user
from .sqlalchemy_models import TenantModel, MembershipModel, UserModel

router = APIRouter(prefix="/tenants", tags=["Tenant Settings"])
logger = structlog.get_logger("tenant_settings")


def _get_tenant_for_user(
    tenant_id: UUID, user: UserModel, db: Session
) -> TenantModel:
    """Load tenant after verifying user has membership."""
    membership = db.execute(
        select(MembershipModel).where(
            MembershipModel.user_id == user.id,
            MembershipModel.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this tenant")

    tenant = db.get(TenantModel, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


VALID_PARTNER_TIERS = {"founding", "standard"}


class SettingsUpdate(BaseModel):
    """Partial settings update — merged into existing settings."""

    workspace_profile: dict | None = None
    onboarding: dict | None = None


class PartnerStatusUpdate(BaseModel):
    """Set or clear a tenant's design partner tier."""

    tier: str | None = None  # "founding", "standard", or null to clear


class OnboardingResponse(BaseModel):
    workspace_profile: dict
    onboarding: dict
    is_complete: bool
    partner_tier: str | None = None


@router.patch("/{tenant_id}/settings")
async def update_tenant_settings(
    tenant_id: UUID,
    payload: SettingsUpdate,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Merge-update tenant settings (workspace profile, onboarding state)."""
    tenant = _get_tenant_for_user(tenant_id, user, db)

    current = tenant.settings or {}
    update = payload.model_dump(exclude_none=True)

    # Deep merge each top-level key
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            current[key] = {**current[key], **value}
        else:
            current[key] = value

    tenant.settings = current
    flag_modified(tenant, "settings")
    db.commit()

    logger.info(
        "tenant_settings_updated",
        tenant_id=str(tenant_id),
        keys=list(update.keys()),
    )
    return {"status": "ok", "settings": current}


@router.get("/{tenant_id}/onboarding", response_model=OnboardingResponse)
async def get_onboarding_status(
    tenant_id: UUID,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Return onboarding progress and workspace profile for a tenant."""
    tenant = _get_tenant_for_user(tenant_id, user, db)

    settings = tenant.settings or {}
    onboarding = settings.get("onboarding", {})
    workspace_profile = settings.get("workspace_profile", {})

    # Consider setup complete when the 3 workspace setup steps are done
    is_complete = all(
        onboarding.get(k, False)
        for k in ("workspace_setup_completed", "facility_created", "ftl_check_completed")
    )

    return OnboardingResponse(
        workspace_profile=workspace_profile,
        onboarding=onboarding,
        is_complete=is_complete,
        partner_tier=settings.get("partner_tier"),
    )


@router.patch("/{tenant_id}/partner-status")
async def update_partner_status(
    tenant_id: UUID,
    payload: PartnerStatusUpdate,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Set or clear a tenant's design partner tier. Requires sysadmin."""
    if not user.is_sysadmin:
        raise HTTPException(status_code=403, detail="Sysadmin access required")

    if payload.tier and payload.tier not in VALID_PARTNER_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier. Must be one of: {', '.join(sorted(VALID_PARTNER_TIERS))}",
        )

    tenant = db.get(TenantModel, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    current = tenant.settings or {}
    if payload.tier:
        current["partner_tier"] = payload.tier
    else:
        current.pop("partner_tier", None)

    tenant.settings = current
    flag_modified(tenant, "settings")
    db.commit()

    logger.info(
        "partner_status_updated",
        tenant_id=str(tenant_id),
        tier=payload.tier,
        admin_user=str(user.id),
    )
    return {"status": "ok", "partner_tier": payload.tier}
