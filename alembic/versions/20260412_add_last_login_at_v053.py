"""Add last_login_at column to users table

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-04-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add last_login_at timestamp to users table for login tracking."""
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

        COMMENT ON COLUMN users.last_login_at
        IS 'Timestamp of most recent successful login';
    """)


def downgrade() -> None:
    """Remove last_login_at column."""
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_login_at;")
