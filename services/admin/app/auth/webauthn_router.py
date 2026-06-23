"""WebAuthn passkey registration and login routes."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth_crypto import AuthCryptoService
from ..database import get_session
from ..sqlalchemy_models import (
    OrganizationMembershipModel,
    SessionModel,
    UserEmailModel,
    UserModel,
    WebAuthnChallengeModel,
    WebAuthnCredentialModel,
)
from .session_auth import AUTH_SESSION_COOKIE, get_auth_crypto_service, get_current_active_user

router = APIRouter()
logger = structlog.get_logger("auth.webauthn")

WEBAUTHN_CHALLENGE_TTL_SECONDS = 10 * 60
WEBAUTHN_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
WEBAUTHN_RP_ID_ENV = "WEBAUTHN_RP_ID"
WEBAUTHN_RP_NAME_ENV = "WEBAUTHN_RP_NAME"
WEBAUTHN_EXPECTED_ORIGIN_ENV = "WEBAUTHN_EXPECTED_ORIGIN"
WEBAUTHN_LOGIN_OPTIONS_MIN_SECONDS_ENV = "WEBAUTHN_LOGIN_OPTIONS_MIN_SECONDS"
WEBAUTHN_DEFAULT_RP_ID = "localhost"
WEBAUTHN_DEFAULT_RP_NAME = "RegEngine"
WEBAUTHN_REGISTRATION_PURPOSE = "registration"
WEBAUTHN_AUTHENTICATION_PURPOSE = "authentication"


class WebAuthnLoginOptionsRequest(BaseModel):
    email: EmailStr = Field(max_length=255)


class WebAuthnCredentialPayload(BaseModel):
    credential: dict[str, Any]


def _invalid_webauthn() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired passkey ceremony.",
    )


def _temporarily_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication service temporarily unavailable.",
    )


def _rp_id() -> str:
    return os.getenv(WEBAUTHN_RP_ID_ENV, WEBAUTHN_DEFAULT_RP_ID).strip() or WEBAUTHN_DEFAULT_RP_ID


def _rp_name() -> str:
    return os.getenv(WEBAUTHN_RP_NAME_ENV, WEBAUTHN_DEFAULT_RP_NAME).strip() or WEBAUTHN_DEFAULT_RP_NAME


def _expected_origin(request: Request) -> str:
    configured = os.getenv(WEBAUTHN_EXPECTED_ORIGIN_ENV, "").strip()
    if configured:
        return configured.rstrip("/")
    return f"{request.url.scheme}://{request.url.netloc}".rstrip("/")


def _login_options_min_seconds() -> float:
    raw_value = os.getenv(WEBAUTHN_LOGIN_OPTIONS_MIN_SECONDS_ENV, "0.05").strip()
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return 0.05


async def _apply_login_options_timing_floor(started_at: float) -> None:
    remaining = _login_options_min_seconds() - (time.perf_counter() - started_at)
    if remaining > 0:
        await asyncio.sleep(remaining)


def _bytes_to_b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_to_bytes(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _credential_id_to_text(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return _bytes_to_b64url(value)
    return value


def _public_key_to_bytes(value: bytes | bytearray | memoryview) -> bytes:
    return bytes(value)


def _challenge_to_text(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return _bytes_to_b64url(value)
    return value


def _challenge_from_text(value: str) -> bytes:
    return _b64url_to_bytes(value)


def _extract_client_data_challenge(credential: dict[str, Any]) -> str:
    try:
        response = credential["response"]
        client_data_json = response["clientDataJSON"]
        client_data = json.loads(_b64url_to_bytes(client_data_json).decode("utf-8"))
        challenge = client_data["challenge"]
    except Exception as exc:
        raise ValueError("credential response is missing clientDataJSON challenge") from exc
    if not isinstance(challenge, str) or not challenge:
        raise ValueError("credential response challenge is invalid")
    return challenge


def _extract_credential_id(credential: dict[str, Any]) -> str:
    credential_id = credential.get("id") or credential.get("rawId")
    if not isinstance(credential_id, str) or not credential_id:
        raise ValueError("credential id is required")
    return credential_id


def _webauthn_generate_registration_options(
    *,
    user: UserModel,
    existing_credentials: list[WebAuthnCredentialModel],
) -> tuple[dict[str, Any], str]:
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        UserVerificationRequirement,
    )

    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=_b64url_to_bytes(credential.credential_id))
        for credential in existing_credentials
    ]
    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=_rp_name(),
        user_id=str(user.id).encode("utf-8"),
        user_name=str(user.email),
        user_display_name=str(user.email),
        exclude_credentials=exclude_credentials,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    return json.loads(options_to_json(options)), _challenge_to_text(options.challenge)


def _webauthn_verify_registration_response(
    *,
    credential: dict[str, Any],
    expected_challenge: str,
    request: Request,
):
    from webauthn import verify_registration_response

    return verify_registration_response(
        credential=credential,
        expected_challenge=_challenge_from_text(expected_challenge),
        expected_origin=_expected_origin(request),
        expected_rp_id=_rp_id(),
        require_user_verification=True,
    )


def _webauthn_generate_authentication_options(
    *,
    credentials: list[WebAuthnCredentialModel],
) -> tuple[dict[str, Any], str]:
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

    allow_credentials = [
        PublicKeyCredentialDescriptor(id=_b64url_to_bytes(credential.credential_id))
        for credential in credentials
    ]
    options = generate_authentication_options(
        rp_id=_rp_id(),
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return json.loads(options_to_json(options)), _challenge_to_text(options.challenge)


def _webauthn_verify_authentication_response(
    *,
    credential: dict[str, Any],
    expected_challenge: str,
    stored_credential: WebAuthnCredentialModel,
    request: Request,
):
    from webauthn import verify_authentication_response

    return verify_authentication_response(
        credential=credential,
        expected_challenge=_challenge_from_text(expected_challenge),
        expected_rp_id=_rp_id(),
        expected_origin=_expected_origin(request),
        credential_public_key=stored_credential.public_key,
        credential_current_sign_count=int(stored_credential.sign_count or 0),
        require_user_verification=True,
    )


def _fake_authentication_options() -> dict[str, Any]:
    return {
        "challenge": secrets.token_urlsafe(32),
        "timeout": 60000,
        "rpId": _rp_id(),
        "allowCredentials": [],
        "userVerification": "required",
    }


def _store_challenge(
    *,
    db: Session,
    user_id: uuid.UUID | None,
    purpose: str,
    challenge: str,
    now: datetime,
) -> WebAuthnChallengeModel:
    state = WebAuthnChallengeModel(
        id=uuid.uuid4(),
        user_id=user_id,
        purpose=purpose,
        challenge=challenge,
        expires_at=now + timedelta(seconds=WEBAUTHN_CHALLENGE_TTL_SECONDS),
        consumed_at=None,
    )
    db.add(state)
    return state


def _load_challenge_for_update(
    *,
    db: Session,
    purpose: str,
    challenge: str,
    now: datetime,
) -> WebAuthnChallengeModel | None:
    stmt = (
        select(WebAuthnChallengeModel)
        .where(
            WebAuthnChallengeModel.challenge == challenge,
            WebAuthnChallengeModel.purpose == purpose,
            WebAuthnChallengeModel.consumed_at.is_(None),
            WebAuthnChallengeModel.expires_at > now,
        )
        .with_for_update()
    )
    return db.execute(stmt).scalar_one_or_none()


def _load_existing_credentials(db: Session, user_id: uuid.UUID) -> list[WebAuthnCredentialModel]:
    stmt = (
        select(WebAuthnCredentialModel)
        .where(WebAuthnCredentialModel.user_id == user_id)
        .order_by(WebAuthnCredentialModel.created_at)
    )
    return list(db.execute(stmt).scalars().all())


def _load_user_by_email(db: Session, normalized_email: str) -> UserModel | None:
    stmt = (
        select(UserModel)
        .join(UserEmailModel, UserEmailModel.user_id == UserModel.id)
        .where(
            func.lower(UserEmailModel.email) == normalized_email,
            UserEmailModel.is_verified.is_(True),
            UserModel.global_status == "active",
            UserModel.status == "active",
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _load_credential_for_update(db: Session, credential_id: str) -> WebAuthnCredentialModel | None:
    stmt = (
        select(WebAuthnCredentialModel)
        .where(WebAuthnCredentialModel.credential_id == credential_id)
        .with_for_update()
    )
    return db.execute(stmt).scalar_one_or_none()


def _load_active_user_for_update(db: Session, user_id: uuid.UUID) -> UserModel | None:
    stmt = (
        select(UserModel)
        .where(
            UserModel.id == user_id,
            UserModel.global_status == "active",
            UserModel.status == "active",
        )
        .with_for_update()
    )
    return db.execute(stmt).scalar_one_or_none()


def _load_first_membership_id(db: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    stmt = (
        select(OrganizationMembershipModel.id)
        .where(OrganizationMembershipModel.user_id == user_id)
        .order_by(OrganizationMembershipModel.id)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _resolve_new_sign_count(current: int, verified) -> int:
    new_sign_count = int(getattr(verified, "new_sign_count", current) or 0)
    if current > 0 and new_sign_count > 0 and new_sign_count <= current:
        raise _invalid_webauthn()
    return new_sign_count if new_sign_count > 0 else current


@router.post("/webauthn/register/generate-options")
async def generate_webauthn_registration_options(
    db: Session = Depends(get_session),
    current_user: UserModel = Depends(get_current_active_user),
) -> dict[str, Any]:
    try:
        existing_credentials = _load_existing_credentials(db, current_user.id)
        options, challenge = _webauthn_generate_registration_options(
            user=current_user,
            existing_credentials=existing_credentials,
        )
        _store_challenge(
            db=db,
            user_id=current_user.id,
            purpose=WEBAUTHN_REGISTRATION_PURPOSE,
            challenge=challenge,
            now=datetime.now(timezone.utc),
        )
        db.commit()
        return options
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error("webauthn_registration_options_failed", user_id=str(current_user.id), error=str(exc))
        raise _temporarily_unavailable() from exc


@router.post("/webauthn/register/verify", status_code=status.HTTP_200_OK)
async def verify_webauthn_registration(
    payload: WebAuthnCredentialPayload,
    request: Request,
    db: Session = Depends(get_session),
    current_user: UserModel = Depends(get_current_active_user),
) -> dict[str, str]:
    current_user_id = current_user.id
    try:
        challenge_text = _extract_client_data_challenge(payload.credential)
    except ValueError as exc:
        raise _invalid_webauthn() from exc

    try:
        if db.in_transaction():
            db.rollback()
        with db.begin():
            now = datetime.now(timezone.utc)
            challenge = _load_challenge_for_update(
                db=db,
                purpose=WEBAUTHN_REGISTRATION_PURPOSE,
                challenge=challenge_text,
                now=now,
            )
            if challenge is None or challenge.user_id != current_user_id:
                raise _invalid_webauthn()
            try:
                verified = _webauthn_verify_registration_response(
                    credential=payload.credential,
                    expected_challenge=challenge.challenge,
                    request=request,
                )
            except Exception as exc:
                raise _invalid_webauthn() from exc

            credential = WebAuthnCredentialModel(
                id=uuid.uuid4(),
                user_id=current_user_id,
                credential_id=_credential_id_to_text(verified.credential_id),
                public_key=_public_key_to_bytes(verified.credential_public_key),
                sign_count=int(getattr(verified, "sign_count", 0) or 0),
                created_at=now,
                last_used_at=None,
            )
            db.add(credential)
            challenge.consumed_at = now
    except HTTPException:
        raise
    except IntegrityError as exc:
        logger.warning("webauthn_credential_duplicate", user_id=str(current_user_id), error=str(exc))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Passkey is already registered.") from exc
    except Exception as exc:
        logger.error("webauthn_registration_verify_failed", user_id=str(current_user_id), error=str(exc))
        raise _temporarily_unavailable() from exc

    return {"status": "verified"}


@router.post("/webauthn/login/generate-options")
async def generate_webauthn_login_options(
    payload: WebAuthnLoginOptionsRequest,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    started_at = time.perf_counter()
    normalized_email = str(payload.email).strip().lower()
    try:
        user = _load_user_by_email(db, normalized_email)
        if user is None:
            options = _fake_authentication_options()
            await _apply_login_options_timing_floor(started_at)
            return options

        credentials = _load_existing_credentials(db, user.id)
        if not credentials:
            options = _fake_authentication_options()
            await _apply_login_options_timing_floor(started_at)
            return options

        options, challenge = _webauthn_generate_authentication_options(credentials=credentials)
        _store_challenge(
            db=db,
            user_id=user.id,
            purpose=WEBAUTHN_AUTHENTICATION_PURPOSE,
            challenge=challenge,
            now=datetime.now(timezone.utc),
        )
        db.commit()
        await _apply_login_options_timing_floor(started_at)
        return options
    except Exception as exc:
        db.rollback()
        logger.error("webauthn_login_options_failed", error=str(exc))
        raise _temporarily_unavailable() from exc


@router.post("/webauthn/login/verify", status_code=status.HTTP_200_OK)
async def verify_webauthn_login(
    payload: WebAuthnCredentialPayload,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
    crypto_service: AuthCryptoService = Depends(get_auth_crypto_service),
) -> dict[str, str]:
    try:
        challenge_text = _extract_client_data_challenge(payload.credential)
        credential_id = _extract_credential_id(payload.credential)
    except ValueError as exc:
        raise _invalid_webauthn() from exc

    session_token: str | None = None

    try:
        with db.begin():
            now = datetime.now(timezone.utc)
            challenge = _load_challenge_for_update(
                db=db,
                purpose=WEBAUTHN_AUTHENTICATION_PURPOSE,
                challenge=challenge_text,
                now=now,
            )
            credential = _load_credential_for_update(db, credential_id)
            if challenge is None or credential is None or credential.user_id != challenge.user_id:
                raise _invalid_webauthn()

            user = _load_active_user_for_update(db, credential.user_id)
            if user is None:
                raise _invalid_webauthn()

            try:
                verified = _webauthn_verify_authentication_response(
                    credential=payload.credential,
                    expected_challenge=challenge.challenge,
                    stored_credential=credential,
                    request=request,
                )
            except Exception as exc:
                raise _invalid_webauthn() from exc

            current_sign_count = int(credential.sign_count or 0)
            credential.sign_count = _resolve_new_sign_count(current_sign_count, verified)
            credential.last_used_at = now
            challenge.consumed_at = now

            session_token = crypto_service.generate_opaque_session_token()
            token_hash = crypto_service.hash_session_token(session_token)
            db.add(
                SessionModel(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    active_membership_id=_load_first_membership_id(db, user.id),
                    token_hash=token_hash,
                    auth_method="webauthn",
                    authenticated_at=now,
                    refresh_token_hash=token_hash,
                    family_id=uuid.uuid4(),
                    is_revoked=False,
                    expires_at=now + timedelta(seconds=WEBAUTHN_SESSION_TTL_SECONDS),
                    revoked_at=None,
                    last_used_at=now,
                )
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("webauthn_login_verify_failed", error=str(exc))
        raise _temporarily_unavailable() from exc

    if session_token is None:
        raise _invalid_webauthn()

    response.set_cookie(
        AUTH_SESSION_COOKIE,
        session_token,
        max_age=WEBAUTHN_SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return {"status": "verified"}
