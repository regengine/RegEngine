"""v089 -- add step-up session metadata.

Revision ID: 38e02636e340
Revises: bdb2bec8bcc6
Create Date: 2026-06-23

Adds an explicit authentication timestamp and constrains opaque session
auth_method values so high-assurance route dependencies can distinguish
email OTP sessions from phishing-resistant WebAuthn or SSO sessions.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "38e02636e340"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "bdb2bec8bcc6"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE public.sessions
        SET authenticated_at = COALESCE(created_at, now())
        WHERE authenticated_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE public.sessions
        SET auth_method = 'email_otp'
        WHERE auth_method IS NULL
           OR auth_method NOT IN ('email_otp', 'webauthn', 'sso')
        """
    )
    op.alter_column(
        "sessions",
        "authenticated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "sessions",
        "auth_method",
        existing_type=sa.String(),
        nullable=False,
        server_default="email_otp",
    )
    op.create_check_constraint(
        "ck_sessions_auth_method_values",
        "sessions",
        "auth_method IN ('email_otp', 'webauthn', 'sso')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_sessions_auth_method_values", "sessions", type_="check")
    op.alter_column(
        "sessions",
        "auth_method",
        existing_type=sa.String(),
        nullable=False,
        server_default="legacy_refresh_token",
    )
    op.drop_column("sessions", "authenticated_at")
