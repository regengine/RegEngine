"""Internal organization administration endpoints."""

from __future__ import annotations

import uuid
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import arm_global_admin_context, get_session
from ..privileged_auth import PrivilegedActor, require_sysadmin_high_assurance
from ..sqlalchemy_models import OrganizationModel, UserModel

logger = structlog.get_logger("admin.organizations")
router = APIRouter(prefix="/admin/organizations", tags=["admin-organizations"])

OrganizationAuthPolicy = Literal["standard", "sso_only"]


class OrganizationSsoPolicyUpdate(BaseModel):
    domain_name: str = Field(min_length=1, max_length=255)
    domain_verified: bool
    enforced_auth_policy: OrganizationAuthPolicy

    @field_validator("domain_name")
    @classmethod
    def normalize_domain_name(cls, value: str) -> str:
        normalized = value.strip().lower().rstrip(".")
        if (
            not normalized
            or "@" in normalized
            or ":" in normalized
            or "/" in normalized
            or "\\" in normalized
            or any(char.isspace() for char in normalized)
            or "." not in normalized
        ):
            raise ValueError("domain_name must be a bare DNS domain")
        return normalized


class OrganizationSsoPolicyResponse(BaseModel):
    id: uuid.UUID
    domain_name: str | None
    domain_verified: bool
    enforced_auth_policy: OrganizationAuthPolicy


def require_super_admin(
    actor: PrivilegedActor = Depends(require_sysadmin_high_assurance),
) -> UserModel:
    current_user = actor.user
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required.",
        )
    if not bool(getattr(current_user, "is_sysadmin", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required.",
        )
    return current_user


@router.get("/{org_id}/sso-policy", response_model=OrganizationSsoPolicyResponse)
async def read_organization_sso_policy(
    org_id: uuid.UUID,
    _: UserModel = Depends(require_super_admin),
    db: Session = Depends(get_session),
) -> OrganizationSsoPolicyResponse:
    # Preserve the existing high-assurance/sysadmin capability without writes.
    arm_global_admin_context(db)
    organization = db.get(OrganizationModel, org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return OrganizationSsoPolicyResponse(
        id=organization.id, domain_name=organization.domain_name,
        domain_verified=bool(organization.domain_verified),
        enforced_auth_policy=organization.enforced_auth_policy,
    )


@router.put("/{org_id}/sso-policy", response_model=OrganizationSsoPolicyResponse)
async def update_organization_sso_policy(
    org_id: uuid.UUID,
    payload: OrganizationSsoPolicyUpdate,
    _: UserModel = Depends(require_super_admin),
    db: Session = Depends(get_session),
) -> OrganizationSsoPolicyResponse:
    # ``require_super_admin`` has already completed high-assurance human
    # authentication.  Elevation is local to this database transaction.
    arm_global_admin_context(db)
    organization = db.get(OrganizationModel, org_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    organization.domain_name = payload.domain_name
    organization.domain_verified = payload.domain_verified
    organization.enforced_auth_policy = payload.enforced_auth_policy

    try:
        response = OrganizationSsoPolicyResponse(
            id=organization.id,
            domain_name=organization.domain_name,
            domain_verified=bool(organization.domain_verified),
            enforced_auth_policy=organization.enforced_auth_policy,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization domain is already claimed.",
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.error("organization_sso_policy_update_failed", organization_id=str(org_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Organization policy update temporarily unavailable.",
        ) from exc

    return response
