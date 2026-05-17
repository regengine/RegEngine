"""Pydantic request/response models for the auth router.

Extracted from ``auth_routes.py`` (Phase 1 sub-split 2/N). Pure data
classes with no behavior; kept separate from the route handlers so
subsequent handler extractions can import them without circular risk.

``auth_routes.py`` re-exports every name defined here so existing
``from services.admin.app.auth_routes import LoginRequest`` imports
continue to resolve unchanged.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", "password")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class EmailCodeRequest(BaseModel):
    email: EmailStr = Field(max_length=255)


class EmailCodeConfirmRequest(BaseModel):
    email: EmailStr = Field(max_length=255)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class EmailCodeRequestResponse(BaseModel):
    status: str
    detail: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    tenant_id: Optional[UUID] = None
    user: Dict
    available_tenants: List[Dict]


class RegisterRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)
    tenant_name: str = Field(max_length=100)
    partner_tier: Optional[str] = Field(None, pattern=r"^(founding|standard)$")


class SignupAcceptedResponse(BaseModel):
    detail: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    is_sysadmin: bool
    status: str


_SIGNUP_ACCEPTED_DETAIL = "Check your inbox for confirmation instructions."


def _signup_accepted_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=SignupAcceptedResponse(detail=_SIGNUP_ACCEPTED_DETAIL).model_dump(),
    )
