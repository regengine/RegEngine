"""Ensure tenant feature tables exist (safety-net for V042)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-11 00:00:00.000000

"""
from typing import Sequence, Union
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def upgrade() -> None:
    """Ensure all tenant tables exist — all CREATE TABLE IF NOT EXISTS, fully idempotent."""
    sql_path = _MIGRATIONS_DIR / "V052__ensure_tenant_tables.sql"
    sql = sql_path.read_text(encoding="utf-8")
    op.execute(sql)


def downgrade() -> None:
    """Drop tenant_data table only (other tables existed before this migration)."""
    op.execute("DROP TABLE IF EXISTS fsma.tenant_data CASCADE")
