"""merge v090 heads (hash_chain_fk_drop + audit_logs_sequence_num)

Revision ID: d1bdfe74d1fd
Revises: 44225a26ed58, 4c5d6e7f8a9b
Create Date: 2026-06-30 14:49:58.768956

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1bdfe74d1fd'  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = ('44225a26ed58', '4c5d6e7f8a9b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
