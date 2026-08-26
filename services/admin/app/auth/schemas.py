"""Pydantic request/response models for the auth router.

Extracted from ``auth_routes.py`` (Phase 1 sub-split 2/N). Pure data
classes with no behavior; kept separate from the route handlers so
subsequent handler extractions can import them without circular risk.

``auth_routes.py`` re-exports the active passwordless schemas defined here.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class EmailCodeRequest(BaseModel):
    email: EmailStr = Field(max_length=255)


class EmailCodeConfirmRequest(BaseModel):
    email: EmailStr = Field(max_length=255)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class EmailCodeRequestResponse(BaseModel):
    status: str
    detail: str


class ChallengeCreateRequest(BaseModel):
    email: EmailStr = Field(max_length=255)


class ChallengeCreateResponse(BaseModel):
    detail: str
    challenge_id: str


class ChallengeVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ChallengeVerifyResponse(BaseModel):
    status: str


class AuthMeResponse(BaseModel):
    user_id: UUID
    email: str
    organization_id: Optional[UUID] = None
    # The tenant this browser session acts as. Distinct from
    # ``organization_id`` (a user may belong to an org with no tenant row, and
    # tenant ids live in the ``memberships`` table). The frontend needs this to
    # send ``X-Tenant-ID`` on ingestion calls and to gate the readiness proxy;
    # without it, passwordless dashboards fall back to demo data.
    tenant_id: Optional[UUID] = None
    role: Optional[str] = None
    auth_method: str
    is_sysadmin: bool
    permissions: List[str]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    tenant_id: Optional[UUID] = None
    user: Dict
    available_tenants: List[Dict]


class UserResponse(BaseModel):
    id: UUID
    email: str
    is_sysadmin: bool
    status: str
