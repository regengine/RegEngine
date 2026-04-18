"""Tenant settings and onboarding status endpoints."""

from __future__ import annotations

from typing import Iterable, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from .database import get_session
from .dependencies import get_current_user
from .sqlalchemy_models import TenantModel, MembershipModel, RoleModel, UserModel

router = APIRouter(prefix="/tenants", tags=["Tenant Settings"])
logger = structlog.get_logger("tenant_settings")


# Privileged role names for settings mutations (#1386).
_ADMIN_ROLE_NAMES = frozenset({"Owner", "Admin", "owner", "admin"})


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


def _get_user_role_name(
    tenant_id: UUID, user: UserModel, db: Session
) -> Optional[str]:
    """Resolve the role name for (user, tenant) from the memberships table.

    Returns the role name string or ``None`` if no active membership
    exists. System sysadmins always return ``"Sysadmin"`` to bypass
    tenant-scoped role checks.
    """
    if getattr(user, "is_sysadmin", False):
        return "Sysadmin"

    membership = db.execute(
        select(MembershipModel).where(
            MembershipModel.user_id == user.id,
            MembershipModel.tenant_id == tenant_id,
            MembershipModel.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if not membership:
        return None

    role = db.get(RoleModel, membership.role_id)
    if not role:
        return None
    return role.name


def _require_tenant_admin(
    tenant_id: UUID, user: UserModel, db: Session
) -> TenantModel:
    """Load tenant after verifying the user has Owner/Admin/Sysadmin role.

    Fixes #1386: the previous ``_get_tenant_for_user`` only verified a
    membership row existed, letting any Member or Viewer overwrite
    ``tenant.settings`` -- including billing/retention/mfa/sso/webhook
    keys. This helper enforces the role gate.
    """
    role_name = _get_user_role_name(tenant_id, user, db)
    if role_name is None:
        raise HTTPException(
            status_code=403, detail="Not a member of this tenant"
        )

    if role_name not in _ADMIN_ROLE_NAMES and role_name != "Sysadmin":
        logger.warning(
            "tenant_settings_non_admin_blocked",
            user_id=str(user.id),
            tenant_id=str(tenant_id),
            role=role_name,
        )
        raise HTTPException(
            status_code=403,
            detail=(
                "Only tenant Owner or Admin roles may modify tenant "
                f"settings. Current role: {role_name}"
            ),
        )

    tenant = db.get(TenantModel, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


# Allowlist of settings keys members/admins may touch through the
# settings merge endpoint. Anything outside this list requires a
# higher-privilege code path (e.g. /partner-status for partner_tier).
# Unknown keys are silently dropped and logged -- the alternative
# (rejecting the whole request) is hostile to forward-compatible UIs
# that include future keys.
_SETTINGS_ALLOWED_TOP_LEVEL = frozenset({"workspace_profile", "onboarding"})
_SETTINGS_BLOCKED_WORKSPACE_KEYS = frozenset(
    {
        # Security/billing knobs that must not be overwritten via a
        # generic merge endpoint. Enumerated explicitly so a future
        # additive workspace_profile schema does not accidentally
        # whitelist them.
        "retention_days",
        "mfa_required",
        "sso_config",
        "webhook_url",
        "webhook_urls",
        "custom_domain",
        "partner_tier",
        "billing_tier",
        "billing_email",
    }
)


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


class SettingsUpdateResponse(BaseModel):
    """Response for updating tenant settings."""
    status: str
    settings: dict


class PartnerStatusResponse(BaseModel):
    """Response for updating partner status."""
    status: str
    partner_tier: str | None = None


def _strip_blocked_keys(value: dict, blocked: Iterable[str]) -> tuple[dict, list[str]]:
    """Return a copy of ``value`` with any blocked keys removed.

    Also returns the list of blocked keys that were present so the
    route can log / surface them.
    """
    removed: list[str] = []
    cleaned = {}
    blocked_set = set(blocked)
    for k, v in (value or {}).items():
        if k in blocked_set:
            removed.append(k)
            continue
        cleaned[k] = v
    return cleaned, removed


@router.patch("/{tenant_id}/settings", response_model=SettingsUpdateResponse)
async def update_tenant_settings(
    tenant_id: UUID,
    payload: SettingsUpdate,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Merge-update tenant settings (workspace profile, onboarding state).

    Security hardening (#1386):
    - The caller MUST hold a privileged role (Owner / Admin) or be a
      Sysadmin. Members and Viewers get 403 even if they belong to the
      tenant.
    - Blocked keys are stripped from the merge input. Security /
      billing / integration settings (retention_days, mfa_required,
      sso_config, webhook_url(s), custom_domain, partner_tier,
      billing_tier, billing_email) cannot be overwritten through this
      endpoint regardless of role -- they have dedicated endpoints
      with additional controls.
    """
    tenant = _require_tenant_admin(tenant_id, user, db)

    current = tenant.settings or {}
    update = payload.model_dump(exclude_none=True)

    # Drop non-allowlisted top-level keys entirely (shouldn't happen
    # because SettingsUpdate only defines two fields, but
    # model_dump can widen if future fields are added).
    filtered_update = {k: v for k, v in update.items() if k in _SETTINGS_ALLOWED_TOP_LEVEL}

    stripped_keys: list[str] = []
    if isinstance(filtered_update.get("workspace_profile"), dict):
        cleaned, removed = _strip_blocked_keys(
            filtered_update["workspace_profile"], _SETTINGS_BLOCKED_WORKSPACE_KEYS
        )
        filtered_update["workspace_profile"] = cleaned
        stripped_keys.extend(f"workspace_profile.{k}" for k in removed)
    if isinstance(filtered_update.get("onboarding"), dict):
        cleaned, removed = _strip_blocked_keys(
            filtered_update["onboarding"], _SETTINGS_BLOCKED_WORKSPACE_KEYS
        )
        filtered_update["onboarding"] = cleaned
        stripped_keys.extend(f"onboarding.{k}" for k in removed)

    if stripped_keys:
        logger.warning(
            "tenant_settings_blocked_keys_dropped",
            user_id=str(user.id),
            tenant_id=str(tenant_id),
            stripped=stripped_keys,
        )

    # Deep merge each top-level key (only allowlisted ones survive here)
    for key, value in filtered_update.items():
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
        keys=list(filtered_update.keys()),
        blocked_dropped=stripped_keys or None,
        actor_user_id=str(user.id),
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


@router.patch("/{tenant_id}/partner-status", response_model=PartnerStatusResponse)
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
