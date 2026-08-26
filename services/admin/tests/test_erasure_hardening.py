"""Account-erasure schema and fail-closed regression tests."""

from __future__ import annotations

import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from services.admin.app import erasure_routes as erasure
from services.admin.app.sqlalchemy_models import (
    AuditLogModel,
    AuthChallengeModel,
    Base,
    MembershipModel,
    MFARecoveryCodeModel,
    OrganizationMembershipModel,
    OrganizationModel,
    RoleModel,
    SessionModel,
    TenantModel,
    UserEmailModel,
    UserModel,
    WebAuthnChallengeModel,
    WebAuthnCredentialModel,
)


def _sqlite_erasure_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE graph_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT,
                    operation TEXT NOT NULL,
                    cypher TEXT NOT NULL,
                    params TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    enqueued_at TEXT NOT NULL,
                    next_attempt_at TEXT NOT NULL,
                    dedupe_key TEXT
                )
                """
            )
        )
    return Session(engine)


def test_apply_account_erasure_matches_real_schema_atomically():
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    role_id = uuid.uuid4()
    other_role_id = uuid.uuid4()
    session_id = uuid.uuid4()
    organization_membership_id = uuid.uuid4()
    email_fingerprint = "fingerprint"
    db = _sqlite_erasure_session()
    try:
        db.add_all(
            [
                TenantModel(id=tenant_id, name="Tenant A", slug=f"tenant-{tenant_id.hex}"),
                TenantModel(id=other_tenant_id, name="Tenant B", slug=f"tenant-{other_tenant_id.hex}"),
                RoleModel(id=role_id, tenant_id=tenant_id, name="Owner", permissions=[]),
                RoleModel(id=other_role_id, tenant_id=other_tenant_id, name="Owner", permissions=[]),
                OrganizationModel(id=tenant_id, name="Tenant A"),
                OrganizationModel(id=other_tenant_id, name="Tenant B"),
                UserModel(
                    id=user_id,
                    email="person@example.com",
                    global_status="active",
                    status="active",
                    is_sysadmin=True,
                    token_version=4,
                    mfa_secret="legacy-secret",  # pragma: allowlist secret
                    mfa_secret_ciphertext="encrypted-secret",  # pragma: allowlist secret
                ),
                UserModel(
                    id=other_user_id,
                    email="other-person@example.com",
                    global_status="active",
                    status="active",
                    is_sysadmin=False,
                    token_version=9,
                ),
                UserEmailModel(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    email="person@example.com",
                    email_fingerprint=email_fingerprint,
                    is_verified=True,
                ),
                UserEmailModel(
                    id=uuid.uuid4(),
                    user_id=other_user_id,
                    email="other-person@example.com",
                    email_fingerprint="other-fingerprint",
                    is_verified=True,
                ),
                MembershipModel(user_id=user_id, tenant_id=tenant_id, role_id=role_id, is_active=True),
                MembershipModel(
                    user_id=user_id,
                    tenant_id=other_tenant_id,
                    role_id=other_role_id,
                    is_active=True,
                ),
                MembershipModel(
                    user_id=other_user_id,
                    tenant_id=tenant_id,
                    role_id=role_id,
                    is_active=True,
                ),
                MembershipModel(
                    user_id=other_user_id,
                    tenant_id=other_tenant_id,
                    role_id=other_role_id,
                    is_active=True,
                ),
                OrganizationMembershipModel(
                    id=organization_membership_id,
                    user_id=user_id,
                    organization_id=tenant_id,
                    role="owner",
                ),
                OrganizationMembershipModel(user_id=user_id, organization_id=other_tenant_id, role="owner"),
                SessionModel(
                    id=session_id,
                    user_id=user_id,
                    active_membership_id=organization_membership_id,
                    refresh_token_hash=f"refresh-{session_id}",
                    family_id=uuid.uuid4(),
                    auth_method="webauthn",
                    expires_at=erasure.datetime.now(erasure.timezone.utc),
                    is_revoked=False,
                    user_agent="Sensitive Browser",
                    ip_address="203.0.113.42",
                ),
                WebAuthnCredentialModel(
                    user_id=user_id,
                    credential_id=f"credential-{user_id}",
                    public_key=b"public-key",
                ),
                WebAuthnChallengeModel(
                    user_id=user_id,
                    challenge=f"challenge-{user_id}",
                    purpose="authentication",
                    expires_at=erasure.datetime.now(erasure.timezone.utc),
                ),
                MFARecoveryCodeModel(user_id=user_id, code_hash="recovery-hash"),
                AuthChallengeModel(
                    purpose="sign_in",
                    email_fingerprint=email_fingerprint,
                    code_digest="code-digest",
                    browser_binding_hash="browser-binding",
                    status="pending",
                    expires_at=erasure.datetime.now(erasure.timezone.utc),
                ),
                AuditLogModel(
                    tenant_id=other_tenant_id,
                    actor_id=user_id,
                    actor_email="person@example.com",
                    actor_ip="203.0.113.42",
                    event_type="data.read",
                    event_category="data_access",
                    action="view",
                    severity="info",
                    resource_type="profile",
                    resource_id=str(user_id),
                    metadata_={"email": "person@example.com"},
                    sequence_num=1,
                    integrity_hash="seed-hash",
                ),
                AuditLogModel(
                    tenant_id=other_tenant_id,
                    actor_id=other_user_id,
                    actor_email="other-person@example.com",
                    event_type="data.read",
                    event_category="data_access",
                    action="view",
                    severity="info",
                    resource_type="profile",
                    resource_id=str(other_user_id),
                    metadata_={"email": "other-person@example.com"},
                    sequence_num=2,
                    integrity_hash="other-seed-hash",
                ),
            ]
        )
        db.commit()

        other_user_before = (
            db.get(UserModel, other_user_id).email,
            db.get(UserModel, other_user_id).status,
            db.get(UserModel, other_user_id).global_status,
            db.get(UserModel, other_user_id).token_version,
        )
        other_memberships_before = db.execute(
            select(MembershipModel.tenant_id, MembershipModel.is_active)
            .where(MembershipModel.user_id == other_user_id)
            .order_by(MembershipModel.tenant_id)
        ).all()
        other_audits_before = db.execute(
            select(AuditLogModel.id, AuditLogModel.integrity_hash, AuditLogModel.metadata_)
            .where(AuditLogModel.actor_id == other_user_id)
            .order_by(AuditLogModel.id)
        ).all()

        affected = erasure._apply_account_erasure(db, user_id=user_id, tenant_id=tenant_id)
        db.commit()

        assert affected == 1
        erased_user = db.get(UserModel, user_id)
        assert erased_user is not None
        assert erased_user.email.endswith("@invalid.regengine.local")
        assert erased_user.email != "person@example.com"
        assert erased_user.status == "erased"
        assert erased_user.global_status == "erased"
        assert erased_user.is_sysadmin is False
        assert erased_user.token_version == 5
        assert erased_user.mfa_secret is None
        assert erased_user.mfa_secret_ciphertext is None

        erased_email = db.execute(select(UserEmailModel).where(UserEmailModel.user_id == user_id)).scalar_one()
        assert erased_email.email.endswith("@invalid.regengine.local")
        assert erased_email.email_fingerprint is None
        assert erased_email.is_verified is False
        assert db.get(MembershipModel, (user_id, tenant_id)).is_active is False
        assert db.get(MembershipModel, (user_id, other_tenant_id)).is_active is False
        erased_session = db.get(SessionModel, session_id)
        assert erased_session.is_revoked is True
        assert erased_session.user_agent is None
        assert erased_session.ip_address is None
        assert erased_session.token_hash is None
        assert erased_session.active_membership_id is None
        assert db.execute(
            select(OrganizationMembershipModel).where(OrganizationMembershipModel.user_id == user_id)
        ).scalars().all() == []
        assert db.execute(
            select(WebAuthnCredentialModel).where(WebAuthnCredentialModel.user_id == user_id)
        ).scalars().all() == []
        assert db.execute(
            select(WebAuthnChallengeModel).where(WebAuthnChallengeModel.user_id == user_id)
        ).scalars().all() == []
        assert db.execute(
            select(MFARecoveryCodeModel).where(MFARecoveryCodeModel.user_id == user_id)
        ).scalars().all() == []
        assert db.execute(
            select(AuthChallengeModel).where(AuthChallengeModel.email_fingerprint == email_fingerprint)
        ).scalars().all() == []

        markers = db.execute(
            select(AuditLogModel).where(
                AuditLogModel.action == "gdpr_anonymize_user",
            )
        ).scalars().all()
        assert {marker.tenant_id for marker in markers} == {tenant_id, other_tenant_id}
        assert all(marker.actor_email is None for marker in markers)
        assert all(marker.metadata_["redacted_user_id"] == str(user_id) for marker in markers)
        assert all(marker.metadata_["marker_kind"] == "per_user_anonymization_order" for marker in markers)

        outbox_rows = db.execute(text("SELECT tenant_id, operation, params FROM graph_outbox")).all()
        assert {row.tenant_id for row in outbox_rows} == {str(tenant_id), str(other_tenant_id)}
        assert all(row.operation == "user_erasure" for row in outbox_rows)
        assert all(str(user_id) in row.params for row in outbox_rows)
        assert (
            db.get(UserModel, other_user_id).email,
            db.get(UserModel, other_user_id).status,
            db.get(UserModel, other_user_id).global_status,
            db.get(UserModel, other_user_id).token_version,
        ) == other_user_before
        assert db.execute(
            select(MembershipModel.tenant_id, MembershipModel.is_active)
            .where(MembershipModel.user_id == other_user_id)
            .order_by(MembershipModel.tenant_id)
        ).all() == other_memberships_before
        assert db.execute(
            select(AuditLogModel.id, AuditLogModel.integrity_hash, AuditLogModel.metadata_)
            .where(AuditLogModel.actor_id == other_user_id)
            .order_by(AuditLogModel.id)
        ).all() == other_audits_before
        assert all(str(other_user_id) not in row.params for row in outbox_rows)
    finally:
        db.close()


def test_erasure_route_does_not_call_generic_nonexistent_user_account_table():
    source = inspect.getsource(erasure.request_erasure)
    assert "process_deletion_request" not in source
    assert "anonymize_audit_logs_for_user" not in source
    assert "_apply_account_erasure" in source


@pytest.mark.asyncio
async def test_redis_cleanup_failure_never_returns_success():
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user = MagicMock(id=user_id, email="person@example.com")
    db = MagicMock()

    with (
        patch.object(erasure.TenantContext, "get_tenant_context", return_value=tenant_id),
        patch.object(erasure, "_apply_account_erasure", return_value=0),
        patch.object(erasure, "arm_global_admin_context"),
        patch.object(
            erasure,
            "_revoke_erased_user_runtime_sessions",
            new=AsyncMock(side_effect=ConnectionError("redis unavailable")),
        ),
        patch.object(erasure, "_delete_neo4j_user_graph_data", new_callable=AsyncMock) as graph_delete,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await erasure.request_erasure(
                body=erasure.ErasureRequest(confirm=True),
                current_user=user,
                session_store=MagicMock(),
                db=db,
            )

    assert exc_info.value.status_code == 503
    db.commit.assert_called_once()
    graph_delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_erasure_maps_missing_user_and_membership_errors():
    user = MagicMock(id=uuid.uuid4(), email="person@example.com")
    db = MagicMock()
    tenant_id = uuid.uuid4()

    with (
        patch.object(erasure.TenantContext, "get_tenant_context", return_value=tenant_id),
        patch.object(erasure, "arm_global_admin_context"),
        patch.object(erasure, "_apply_account_erasure", side_effect=LookupError("gone")),
    ):
        with pytest.raises(HTTPException) as missing:
            await erasure.request_erasure(
                body=erasure.ErasureRequest(confirm=True),
                current_user=user,
                session_store=MagicMock(),
                db=db,
            )
    assert missing.value.status_code == 404

    with (
        patch.object(erasure.TenantContext, "get_tenant_context", return_value=tenant_id),
        patch.object(erasure, "arm_global_admin_context"),
        patch.object(erasure, "_apply_account_erasure", side_effect=PermissionError("no membership")),
    ):
        with pytest.raises(HTTPException) as forbidden:
            await erasure.request_erasure(
                body=erasure.ErasureRequest(confirm=True),
                current_user=user,
                session_store=MagicMock(),
                db=db,
            )
    assert forbidden.value.status_code == 403


@pytest.mark.asyncio
async def test_runtime_session_cleanup_retries_then_fails_closed():
    store = MagicMock()
    store.revoke_all_user_sessions = AsyncMock(side_effect=ConnectionError("redis unavailable"))
    with pytest.raises(ConnectionError):
        await erasure._revoke_erased_user_runtime_sessions(store, uuid.uuid4())
    assert store.revoke_all_user_sessions.await_count == 2
