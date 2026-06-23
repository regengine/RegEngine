"""Passwordless auth challenge creation endpoint."""

from __future__ import annotations

import hmac
import html
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from shared.pii import mask_email
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_crypto import AuthCryptoService
from ..database import get_session
from ..dependencies import get_session_store
from ..e2e_safety import assert_e2e_mode_allowed, e2e_mode_enabled
from ..rate_limit_service import RateLimitExceededException, RateLimitService
from ..session_store import RedisSessionStore
from ..sqlalchemy_models import (
    AuthChallengeModel,
    OrganizationMembershipModel,
    OrganizationModel,
    SessionModel,
    UserEmailModel,
    UserModel,
)
from .schemas import ChallengeCreateRequest, ChallengeCreateResponse, ChallengeVerifyRequest, ChallengeVerifyResponse
from .session_auth import AUTH_SESSION_COOKIE, get_auth_crypto_service

router = APIRouter()
logger = structlog.get_logger("auth.challenges")
assert_e2e_mode_allowed()

AUTH_CHALLENGE_DETAIL = "If this address is eligible, a sign-in code is on its way."
AUTH_CHALLENGE_PURPOSE = "sign_in"
AUTH_CHALLENGE_TTL_SECONDS = 10 * 60
AUTH_BROWSER_NONCE_COOKIE = "regengine_auth_browser_nonce"
AUTH_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
AUTH_CHALLENGE_INVALID_DETAIL = "Invalid or expired sign-in challenge."
AUTH_SSO_REQUIRED_MESSAGE = "Organization requires Single Sign-On."


class _RateLimitServiceProtocol(Protocol):
    async def check_otp_generation(
        self,
        *,
        email_fingerprint: str,
        browser_binding_hash: str,
        ip_address: str,
    ) -> object:
        ...


async def get_rate_limit_service(
    session_store: RedisSessionStore = Depends(get_session_store),
) -> RateLimitService:
    return RateLimitService(await session_store._get_client())


def _client_ip(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "0.0.0.0"


def _browser_nonce_for_request(request: Request, crypto_service: AuthCryptoService) -> str:
    existing_nonce = request.cookies.get(AUTH_BROWSER_NONCE_COOKIE)
    if existing_nonce and len(existing_nonce) <= 256:
        return existing_nonce
    return crypto_service.generate_opaque_session_token()


def _accepted_response(challenge_id: uuid.UUID) -> ChallengeCreateResponse:
    return ChallengeCreateResponse(detail=AUTH_CHALLENGE_DETAIL, challenge_id=str(challenge_id))


def _sso_required_response(organization: OrganizationModel) -> ChallengeCreateResponse:
    return ChallengeCreateResponse(
        message=AUTH_SSO_REQUIRED_MESSAGE,
        sso_redirect=True,
        organization_id=str(organization.id),
    )


def _unauthorized_challenge() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=AUTH_CHALLENGE_INVALID_DETAIL,
    )


def _dispatch_sign_in_code_email(email: str, code: str, challenge_id: uuid.UUID) -> None:
    """Worker handoff for sign-in code email delivery.

    The plaintext code intentionally only crosses this worker boundary and is
    never persisted in the auth_challenges table.
    """
    recorded_e2e_outbox = _record_e2e_sign_in_code(email=email, code=code, challenge_id=challenge_id)
    resend_api_key = os.getenv("RESEND_API_KEY")
    if not resend_api_key:
        if recorded_e2e_outbox:
            logger.info(
                "auth_challenge_email_recorded_e2e_outbox",
                challenge_id=str(challenge_id),
                email=mask_email(email),
            )
        else:
            logger.error(
                "auth_challenge_email_skipped_missing_resend_api_key",
                challenge_id=str(challenge_id),
                email=mask_email(email),
            )
        return

    try:
        import resend
    except ImportError:
        logger.error(
            "auth_challenge_email_skipped_resend_not_installed",
            challenge_id=str(challenge_id),
            email=mask_email(email),
        )
        return

    resend.api_key = resend_api_key
    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@regengine.co")
    safe_code = html.escape(code, quote=True)

    try:
        response = resend.Emails.send(
            {
                "from": from_email,
                "to": email,
                "subject": "Your RegEngine sign-in code",
                "html": (
                    "<div style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;'>"
                    "<h2 style='color: #111827;'>Your RegEngine sign-in code</h2>"
                    "<p style='color: #374151; line-height: 1.6;'>"
                    "Enter this confirmation code to finish signing in:"
                    "</p>"
                    "<p style='font-size: 32px; letter-spacing: 6px; font-weight: 700; color: #111827;'>"
                    f"{safe_code}"
                    "</p>"
                    "<p style='color: #6b7280; font-size: 13px;'>"
                    "This code expires in 10 minutes. If you did not request it, you can ignore this email."
                    "</p>"
                    "</div>"
                ),
            }
        )
        response_id = getattr(response, "id", None) or (response.get("id") if isinstance(response, dict) else None)
        logger.info(
            "auth_challenge_email_sent",
            challenge_id=str(challenge_id),
            email=mask_email(email),
            resend_id=response_id,
        )
    except Exception as exc:  # pragma: no cover - external SDK/network behavior
        logger.warning(
            "auth_challenge_email_send_failed",
            challenge_id=str(challenge_id),
            email=mask_email(email),
            error=str(exc),
        )


def _record_e2e_sign_in_code(*, email: str, code: str, challenge_id: uuid.UUID) -> bool:
    """Write the plaintext OTP to the Playwright-only outbox fixture."""
    outbox_path = os.getenv("REGENGINE_E2E_EMAIL_OUTBOX")
    if not outbox_path or not e2e_mode_enabled():
        return False

    record = {
        "kind": "auth_challenge",
        "email": email,
        "code": code,
        "challenge_id": str(challenge_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = Path(outbox_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as outbox:
        outbox.write(json.dumps(record, sort_keys=True) + "\n")
    return True


@router.post(
    "/challenges",
    response_model=ChallengeCreateResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_auth_challenge(
    payload: ChallengeCreateRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    rate_limit_service: _RateLimitServiceProtocol = Depends(get_rate_limit_service),
    crypto_service: AuthCryptoService = Depends(get_auth_crypto_service),
) -> ChallengeCreateResponse:
    normalized_email = str(payload.email).strip().lower()
    email_domain = _email_domain(normalized_email)
    try:
        organization = _load_organization_by_domain(db, email_domain)
    except Exception as exc:
        logger.error(
            "auth_challenge_policy_lookup_failed",
            email_domain=email_domain,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable.",
        ) from exc
    if (
        organization is not None
        and organization.enforced_auth_policy == "sso_only"
        and bool(getattr(organization, "domain_verified", False))
    ):
        return _sso_required_response(organization)

    email_fingerprint = crypto_service.fingerprint_email(normalized_email)
    browser_nonce = _browser_nonce_for_request(request, crypto_service)
    browser_binding_hash = crypto_service.hash_session_token(browser_nonce)

    try:
        await rate_limit_service.check_otp_generation(
            email_fingerprint=email_fingerprint,
            browser_binding_hash=browser_binding_hash,
            ip_address=_client_ip(request),
        )
    except RateLimitExceededException as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait before requesting another sign-in code.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    challenge_id = uuid.uuid4()
    code = crypto_service.generate_secure_otp()
    code_digest = crypto_service.hash_otp(
        challenge_id=challenge_id,
        purpose=AUTH_CHALLENGE_PURPOSE,
        email_fingerprint=email_fingerprint,
        code=code,
    )

    challenge = AuthChallengeModel(
        id=challenge_id,
        purpose=AUTH_CHALLENGE_PURPOSE,
        email_fingerprint=email_fingerprint,
        code_digest=code_digest,
        browser_binding_hash=browser_binding_hash,
        status="pending",
        failed_attempts=0,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=AUTH_CHALLENGE_TTL_SECONDS),
    )
    db.add(challenge)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("auth_challenge_create_failed", email=mask_email(normalized_email), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable.",
        ) from exc

    background_tasks.add_task(_dispatch_sign_in_code_email, normalized_email, code, challenge_id)
    response.set_cookie(
        AUTH_BROWSER_NONCE_COOKIE,
        browser_nonce,
        max_age=AUTH_CHALLENGE_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/auth",
    )
    return _accepted_response(challenge_id)


def _email_domain(email: str) -> str:
    return email.rsplit("@", 1)[1].lower()


def _load_organization_by_domain(db: Session, domain_name: str) -> OrganizationModel | None:
    stmt = select(OrganizationModel).where(OrganizationModel.domain_name == domain_name).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def _load_challenge_for_update(db: Session, challenge_id: uuid.UUID) -> AuthChallengeModel | None:
    stmt = select(AuthChallengeModel).where(AuthChallengeModel.id == challenge_id).with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def _challenge_is_pending(challenge: AuthChallengeModel, now: datetime) -> bool:
    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return (
        challenge.status == "pending"
        and expires_at > now
        and int(challenge.failed_attempts or 0) < 5
    )


def _browser_binding_matches(
    *,
    request: Request,
    challenge: AuthChallengeModel,
    crypto_service: AuthCryptoService,
) -> bool:
    browser_nonce = request.cookies.get(AUTH_BROWSER_NONCE_COOKIE)
    if not browser_nonce:
        return False
    browser_binding_hash = crypto_service.hash_session_token(browser_nonce)
    return hmac.compare_digest(browser_binding_hash, str(challenge.browser_binding_hash))


def _load_valid_identity(
    *,
    db: Session,
    email_fingerprint: str,
) -> tuple[UserModel, OrganizationMembershipModel] | None:
    stmt = (
        select(UserModel, OrganizationMembershipModel)
        .join(UserEmailModel, UserEmailModel.user_id == UserModel.id)
        .join(OrganizationMembershipModel, OrganizationMembershipModel.user_id == UserModel.id)
        .where(
            UserEmailModel.email_fingerprint == email_fingerprint,
            UserEmailModel.is_verified.is_(True),
            UserModel.global_status == "active",
            UserModel.status == "active",
        )
        .order_by(OrganizationMembershipModel.id)
        .limit(1)
    )
    row = db.execute(stmt).first()
    if not row:
        return None
    user, membership = row
    return user, membership


@router.post(
    "/challenges/{challenge_id}/verify",
    response_model=ChallengeVerifyResponse,
    status_code=status.HTTP_200_OK,
)
async def verify_auth_challenge(
    challenge_id: uuid.UUID,
    payload: ChallengeVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
    crypto_service: AuthCryptoService = Depends(get_auth_crypto_service),
) -> ChallengeVerifyResponse:
    session_token: str | None = None
    auth_failed = False

    try:
        with db.begin():
            now = datetime.now(timezone.utc)
            challenge = _load_challenge_for_update(db, challenge_id)
            if challenge is None or not _challenge_is_pending(challenge, now):
                auth_failed = True
            elif not _browser_binding_matches(
                request=request,
                challenge=challenge,
                crypto_service=crypto_service,
            ):
                auth_failed = True
            elif not crypto_service.verify_otp_hash(
                expected_hash=challenge.code_digest,
                challenge_id=challenge.id,
                purpose=challenge.purpose,
                email_fingerprint=challenge.email_fingerprint,
                code=payload.code,
            ):
                challenge.failed_attempts = int(challenge.failed_attempts or 0) + 1
                if challenge.failed_attempts >= 5:
                    challenge.status = "locked"
                auth_failed = True
            else:
                challenge.status = "consumed"
                identity = _load_valid_identity(
                    db=db,
                    email_fingerprint=challenge.email_fingerprint,
                )
                if identity is None:
                    auth_failed = True
                else:
                    user, membership = identity
                    session_token = crypto_service.generate_opaque_session_token()
                    token_hash = crypto_service.hash_session_token(session_token)
                    db.add(
                        SessionModel(
                            id=uuid.uuid4(),
                            user_id=user.id,
                            active_membership_id=membership.id,
                            token_hash=token_hash,
                            auth_method="email_otp",
                            authenticated_at=now,
                            refresh_token_hash=token_hash,
                            family_id=uuid.uuid4(),
                            is_revoked=False,
                            expires_at=now + timedelta(seconds=AUTH_SESSION_TTL_SECONDS),
                            revoked_at=None,
                            last_used_at=now,
                        )
                    )
    except Exception as exc:
        logger.error("auth_challenge_verify_failed", challenge_id=str(challenge_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable.",
        ) from exc

    if auth_failed or session_token is None:
        raise _unauthorized_challenge()

    response.set_cookie(
        AUTH_SESSION_COOKIE,
        session_token,
        max_age=AUTH_SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return ChallengeVerifyResponse(status="verified")
