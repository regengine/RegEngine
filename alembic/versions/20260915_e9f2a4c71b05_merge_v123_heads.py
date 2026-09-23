"""merge v123 heads (v121 merge + agent_org_pods + email_ingestion_hardening)

Revision ID: e9f2a4c71b05
Revises: 5541fb62ee2d, bd0c6549153a, d14f8a2b9c31
Create Date: 2026-09-15 03:20:00.000000

Three active heads blocked every `alembic upgrade head` in CI (dependabot PRs
#3105-#3109 all red on "Multiple head revisions are present"). The v081 pair
(3e7a1c5b9f24, a7b8c9d0e1f2) is already consumed by the v082 merge
70d5e59e3257 — listing them again here makes Alembic try to delete their
version rows twice and die with KeyError on scratch replays.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9f2a4c71b05'  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    '5541fb62ee2d',
    'bd0c6549153a',
    'd14f8a2b9c31',
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
