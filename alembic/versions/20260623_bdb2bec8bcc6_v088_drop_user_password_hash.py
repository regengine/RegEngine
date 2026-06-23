"""v088 -- purge legacy password auth storage.

Revision ID: bdb2bec8bcc6
Revises: b0c1d2e3f4a5
Create Date: 2026-06-23

Removes the legacy password verifier and reset-token table now that
interactive authentication is passwordless.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "bdb2bec8bcc6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "b0c1d2e3f4a5"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_column("users", "password_hash")


def downgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(), nullable=True))
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
