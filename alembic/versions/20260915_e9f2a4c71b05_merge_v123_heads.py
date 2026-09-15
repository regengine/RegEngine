"""merge v123 heads (v121 merge + agent_org_pods + email_ingestion_hardening + v081 pair)

Revision ID: e9f2a4c71b05
Revises: 5541fb62ee2d, bd0c6549153a, d14f8a2b9c31, 3e7a1c5b9f24, a7b8c9d0e1f2
Create Date: 2026-09-15 03:20:00.000000

Five parallel heads blocked every `alembic upgrade head` in CI (dependabot PRs
#3105-#3109 all red on "Multiple head revisions are present"). Three are the
active line; 3e7a1c5b9f24 and a7b8c9d0e1f2 are an orphaned v081 pair (June,
off d2e3f4a5b6c7, referenced by nothing) that shipped with the repo.
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
    '3e7a1c5b9f24',
    'a7b8c9d0e1f2',
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
