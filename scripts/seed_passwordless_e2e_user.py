#!/usr/bin/env python3
"""Seed the local Playwright passwordless auth user.

This script is intentionally limited to REGENGINE_E2E_MODE=true so it cannot
silently create identities in non-test environments.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = ROOT_DIR / "services"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))

from services.admin.app.e2e_safety import e2e_mode_enabled  # noqa: E402


def _require_e2e_mode() -> None:
    if not e2e_mode_enabled():
        raise SystemExit("Refusing to seed passwordless users outside REGENGINE_E2E_MODE=true")


def _email_domain(email: str) -> str:
    if "@" not in email:
        raise SystemExit("TEST_USER_EMAIL must be a valid email address")
    return email.rsplit("@", 1)[1].lower()


def _is_sysadmin() -> bool:
    return os.getenv("REGENGINE_E2E_IS_SYSADMIN", "").strip().lower() in {"1", "true", "yes", "on"}


def _session_auth_method() -> str | None:
    value = os.getenv("REGENGINE_E2E_SESSION_AUTH_METHOD", "").strip().lower()
    if not value:
        return None
    if value not in {"email_otp", "webauthn", "sso"}:
        raise SystemExit("REGENGINE_E2E_SESSION_AUTH_METHOD must be email_otp, webauthn, or sso")
    return value


def main() -> int:
    _require_e2e_mode()

    from services.admin.app.auth_crypto import AuthCryptoService
    from services.admin.app.database import SessionLocal, init_db
    from services.admin.app.sqlalchemy_models import (
        MembershipModel,
        OrganizationMembershipModel,
        OrganizationModel,
        RoleModel,
        SessionModel,
        TenantModel,
        UserEmailModel,
        UserModel,
    )

    init_db()

    email = os.getenv("TEST_USER_EMAIL", "playwright-e2e@example.com").strip().lower()
    org_name = os.getenv("REGENGINE_E2E_ORG_NAME", "E2E Passwordless Org").strip()
    domain = _email_domain(email)
    crypto = AuthCryptoService()
    fingerprint = crypto.fingerprint_email(email)
    is_sysadmin = _is_sysadmin()
    session_auth_method = _session_auth_method()

    with SessionLocal() as db:
        organization = db.execute(
            select(OrganizationModel).where(OrganizationModel.domain_name == domain).limit(1)
        ).scalar_one_or_none()
        if organization is None:
            organization = OrganizationModel(
                id=uuid.uuid4(),
                name=org_name,
                domain_name=domain,
                domain_verified=True,
                enforced_auth_policy="standard",
            )
            db.add(organization)
            db.flush()
        else:
            organization.name = organization.name or org_name
            organization.domain_verified = True
            organization.enforced_auth_policy = "standard"

        user = db.execute(select(UserModel).where(func.lower(UserModel.email) == email).limit(1)).scalar_one_or_none()
        if user is None:
            user = UserModel(
                id=uuid.uuid4(),
                email=email,
                global_status="active",
                status="active",
                is_sysadmin=is_sysadmin,
            )
            db.add(user)
            db.flush()
        else:
            user.global_status = "active"
            user.status = "active"
            user.is_sysadmin = is_sysadmin

        user_email = db.execute(
            select(UserEmailModel).where(func.lower(UserEmailModel.email) == email).limit(1)
        ).scalar_one_or_none()
        if user_email is None:
            user_email = UserEmailModel(
                id=uuid.uuid4(),
                user_id=user.id,
                email=email,
                email_fingerprint=fingerprint,
                is_verified=True,
            )
            db.add(user_email)
        else:
            user_email.user_id = user.id
            user_email.email_fingerprint = fingerprint
            user_email.is_verified = True

        membership = db.execute(
            select(OrganizationMembershipModel)
            .where(
                OrganizationMembershipModel.user_id == user.id,
                OrganizationMembershipModel.organization_id == organization.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if membership is None:
            membership = OrganizationMembershipModel(
                id=uuid.uuid4(),
                user_id=user.id,
                organization_id=organization.id,
                role="owner",
            )
            db.add(membership)
        else:
            membership.role = membership.role or "owner"

        # Legacy tenant context, mirroring the v094 mapping
        # (organizations.id == tenants.id): /auth/me and PermissionChecker
        # resolve the session's tenant and role from tenants/roles/memberships,
        # so without these rows a passwordless login has no tenant_id and no
        # permissions on tenant-scoped admin endpoints.
        tenant = db.get(TenantModel, organization.id)
        if tenant is None:
            tenant = TenantModel(
                id=organization.id,
                name=org_name,
                slug=f"e2e-{uuid.uuid4().hex[:12]}",
                status="active",
                settings={},
            )
            db.add(tenant)
            db.flush()

        owner_role = db.execute(
            select(RoleModel).where(RoleModel.tenant_id == tenant.id, RoleModel.name == "Owner").limit(1)
        ).scalar_one_or_none()
        if owner_role is None:
            owner_role = RoleModel(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                name="Owner",
                permissions=["*"],
            )
            db.add(owner_role)
            db.flush()

        legacy_membership = db.execute(
            select(MembershipModel)
            .where(
                MembershipModel.user_id == user.id,
                MembershipModel.tenant_id == tenant.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if legacy_membership is None:
            db.add(
                MembershipModel(
                    user_id=user.id,
                    tenant_id=tenant.id,
                    role_id=owner_role.id,
                    is_active=True,
                )
            )
        else:
            legacy_membership.is_active = True

        db.commit()

        if session_auth_method is not None:
            now = datetime.now(timezone.utc)
            active_session = db.execute(
                select(SessionModel)
                .where(
                    SessionModel.user_id == user.id,
                    SessionModel.is_revoked.is_(False),
                    SessionModel.revoked_at.is_(None),
                    SessionModel.expires_at > now,
                )
                .order_by(SessionModel.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if active_session is None:
                print(
                    "passwordless seed committed without an active session; "
                    "session_auth_method was not applied",
                    file=sys.stderr,
                )
            else:
                active_session.auth_method = session_auth_method
                db.commit()

        print(
            json.dumps(
                {
                    "email": email,
                    "user_id": str(user.id),
                    "organization_id": str(organization.id),
                    "membership_id": str(membership.id),
                    "tenant_id": str(tenant.id),
                    "is_sysadmin": bool(user.is_sysadmin),
                    "session_auth_method": session_auth_method,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
