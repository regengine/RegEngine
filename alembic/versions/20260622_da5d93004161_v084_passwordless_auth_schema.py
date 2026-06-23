"""v084 -- high-assurance passwordless auth schema.

Revision ID: da5d93004161
Revises: e3f4a5b6c7d8
Create Date: 2026-06-22

Adds the persistent identity, organization membership, OTP challenge, and
opaque-session columns needed for a NIST-aligned passwordless authentication
flow. This migration intentionally avoids route or endpoint behavior changes.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "da5d93004161"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("global_status", sa.String(), nullable=False, server_default="active"),
    )

    op.create_table(
        "user_emails",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("email_fingerprint", sa.String(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_emails_user_id", "user_emails", ["user_id"])
    op.create_index("ix_user_emails_email_fingerprint", "user_emails", ["email_fingerprint"], unique=True)
    op.create_index("ix_user_emails_user_verified", "user_emails", ["user_id", "is_verified"])
    op.create_index("uq_user_emails_email_lower", "user_emails", [sa.text("lower(email)")], unique=True)

    op.execute(
        """
        INSERT INTO public.user_emails (user_id, email, is_verified)
        SELECT id, email, true
        FROM public.users
        WHERE email IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )

    op.create_table(
        "organizations",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "enforced_auth_policy",
            sa.String(),
            nullable=False,
            server_default="passwordless_email_code",
        ),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"])

    op.create_table(
        "organization_memberships",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_organization_memberships_user_org"),
    )
    op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])
    op.create_index(
        "ix_organization_memberships_organization_id",
        "organization_memberships",
        ["organization_id"],
    )

    op.create_table(
        "auth_challenges",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "purpose",
            sa.Enum(
                "sign_in",
                "accept_invite",
                "step_up",
                name="auth_challenge_purpose",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("email_fingerprint", sa.String(), nullable=False),
        sa.Column("code_digest", sa.String(), nullable=False),
        sa.Column("browser_binding_hash", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "pending",
                "consumed",
                "locked",
                "expired",
                name="auth_challenge_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_challenges_expires_at", "auth_challenges", ["expires_at"])
    op.create_index("ix_auth_challenges_status_expires_at", "auth_challenges", ["status", "expires_at"])
    op.create_index(
        "ix_auth_challenges_email_purpose_status",
        "auth_challenges",
        ["email_fingerprint", "purpose", "status"],
    )
    op.create_index("ix_auth_challenges_browser_binding_hash", "auth_challenges", ["browser_binding_hash"])

    op.add_column("sessions", sa.Column("active_membership_id", UUID, nullable=True))
    op.add_column("sessions", sa.Column("token_hash", sa.String(), nullable=True))
    op.add_column(
        "sessions",
        sa.Column(
            "auth_method",
            sa.String(),
            nullable=False,
            server_default="legacy_refresh_token",
        ),
    )
    op.add_column("sessions", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE public.sessions
        SET token_hash = refresh_token_hash
        WHERE token_hash IS NULL
          AND refresh_token_hash IS NOT NULL
        """
    )
    op.create_foreign_key(
        "fk_sessions_active_membership_id",
        "sessions",
        "organization_memberships",
        ["active_membership_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sessions_active_membership_id", "sessions", ["active_membership_id"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_auth_method", "sessions", ["auth_method"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_auth_method", table_name="sessions")
    op.drop_index("ix_sessions_token_hash", table_name="sessions")
    op.drop_index("ix_sessions_active_membership_id", table_name="sessions")
    op.drop_constraint("fk_sessions_active_membership_id", "sessions", type_="foreignkey")
    op.drop_column("sessions", "revoked_at")
    op.drop_column("sessions", "auth_method")
    op.drop_column("sessions", "token_hash")
    op.drop_column("sessions", "active_membership_id")

    op.drop_index("ix_auth_challenges_browser_binding_hash", table_name="auth_challenges")
    op.drop_index("ix_auth_challenges_email_purpose_status", table_name="auth_challenges")
    op.drop_index("ix_auth_challenges_status_expires_at", table_name="auth_challenges")
    op.drop_index("ix_auth_challenges_expires_at", table_name="auth_challenges")
    op.drop_table("auth_challenges")

    op.drop_index("ix_organization_memberships_organization_id", table_name="organization_memberships")
    op.drop_index("ix_organization_memberships_user_id", table_name="organization_memberships")
    op.drop_table("organization_memberships")

    op.drop_index("ix_organizations_name", table_name="organizations")
    op.drop_table("organizations")

    op.drop_index("uq_user_emails_email_lower", table_name="user_emails")
    op.drop_index("ix_user_emails_user_verified", table_name="user_emails")
    op.drop_index("ix_user_emails_email_fingerprint", table_name="user_emails")
    op.drop_index("ix_user_emails_user_id", table_name="user_emails")
    op.drop_table("user_emails")

    op.drop_column("users", "global_status")
