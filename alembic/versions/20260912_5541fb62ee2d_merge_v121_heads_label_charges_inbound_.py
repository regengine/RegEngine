"""merge v121 heads (label_charges + inbound_email_addresses + billing_usage_counters)

Revision ID: 5541fb62ee2d
Revises: 7551be5c64ac, 8301f3cad96a, ceb552c6d36d
Create Date: 2026-09-12 21:00:02.395024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5541fb62ee2d'
down_revision: Union[str, Sequence[str], None] = ('7551be5c64ac', '8301f3cad96a', 'ceb552c6d36d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
