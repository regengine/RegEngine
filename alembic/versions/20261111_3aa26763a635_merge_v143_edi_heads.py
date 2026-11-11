"""Merge the independent EDI rejection and interchange migration heads.

Revision ID: 3aa26763a635
Revises: 056ffd2f8045, c4a9d2e761b0
"""

from typing import Sequence, Union


revision: str = "3aa26763a635"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "056ffd2f8045",
    "c4a9d2e761b0",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
