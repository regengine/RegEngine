"""Merge the independent EDI line-identity and rejection migration heads.

Revision ID: a1b3974d0c96
Revises: 62355c37e367, 056ffd2f8045
"""

from typing import Sequence, Union


revision: str = "a1b3974d0c96"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "62355c37e367",
    "056ffd2f8045",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
