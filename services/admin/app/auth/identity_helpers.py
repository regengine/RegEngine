"""Passwordless identity provisioning shared by user-creation flows.

``_load_valid_identity`` (challenges_router.py) only matches users that have
a **verified** ``user_emails`` row with an ``email_fingerprint`` plus an
``organization_memberships`` row. The v094 migration backfilled those rows
for users that existed at migration time, but any user created afterwards
without them can never receive a sign-in code email
(``auth_challenge_email_suppressed_ineligible_identity``).

Every runtime code path that inserts ``users``/``memberships`` rows must call
``ensure_passwordless_identity``. The mapping mirrors the v094 backfill:
``organizations.id == tenants.id`` and the organization role is the
lowercased legacy role name.

Requires the OTP HMAC secret (AUTH_OTP_HMAC_SECRET) in production —
constructing ``AuthCryptoService`` without it raises there, which is
intentional: writing a row without a fingerprint would silently recreate
the suppressed-email bug.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth_crypto import AuthCryptoService
from ..sqlalchemy_models import (
    OrganizationMembershipModel,
    OrganizationModel,
    TenantModel,
    UserEmailModel,
    UserModel,
)

DEFAULT_ORGANIZATION_ROLE = "member"


class EmailOwnershipConflictError(ValueError):
    """A verified email row belongs to a different user.

    Raised instead of reassigning the row, so accepting an invite whose
    address differs only by case from another user's address can never move
    that user's verified email to the invitee.
    """


def ensure_passwordless_identity(
    db: Session,
    *,
    user: UserModel,
    email: str,
    organization_id: uuid.UUID,
    role_name: str | None = None,
    crypto_service: AuthCryptoService | None = None,
) -> None:
    """Idempotently provision the passwordless identity rows for ``user``.

    Ensures, without committing (the caller owns the transaction):
      * a verified ``user_emails`` row for ``email`` with the keyed fingerprint
      * an ``organizations`` row with ``id == organization_id`` (the tenant id)
      * an ``organization_memberships`` row for (user, organization)

    ``email`` must be proven to belong to ``user`` by the calling flow (e.g.
    possession of an invite token sent to that mailbox) — the row is marked
    ``is_verified=True``.
    """
    crypto = crypto_service if crypto_service is not None else AuthCryptoService()
    normalized_email = email.strip().lower()
    fingerprint = crypto.fingerprint_email(normalized_email)

    user_email = db.execute(
        select(UserEmailModel).where(func.lower(UserEmailModel.email) == normalized_email).limit(1)
    ).scalar_one_or_none()
    if user_email is None:
        db.add(
            UserEmailModel(
                user_id=user.id,
                email=normalized_email,
                email_fingerprint=fingerprint,
                is_verified=True,
            )
        )
    else:
        if user_email.user_id != user.id:
            raise EmailOwnershipConflictError("email address is already verified for a different user")
        user_email.email = normalized_email
        user_email.email_fingerprint = fingerprint
        user_email.is_verified = True

    organization = db.get(OrganizationModel, organization_id)
    if organization is None:
        tenant = db.get(TenantModel, organization_id)
        db.add(
            OrganizationModel(
                id=organization_id,
                name=tenant.name if tenant is not None and tenant.name else "Organization",
                enforced_auth_policy="standard",
            )
        )

    membership = db.execute(
        select(OrganizationMembershipModel)
        .where(
            OrganizationMembershipModel.user_id == user.id,
            OrganizationMembershipModel.organization_id == organization_id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if membership is None:
        db.add(
            OrganizationMembershipModel(
                user_id=user.id,
                organization_id=organization_id,
                role=(role_name or DEFAULT_ORGANIZATION_ROLE).strip().lower() or DEFAULT_ORGANIZATION_ROLE,
            )
        )
