"""merge v127 heads (v127 inbound-address lookup + v126 run FKs + v126 inbound_email drop)

Revision ID: ed902d03df45
Revises: d2e7a7319b33, 2db4f1d7b4ca, 486eb6809921
Create Date: 2026-09-28 19:20:27.583381

#3150 (v127 d2e7a7319b33, on v126 c51d4898e0a2), #3152 (2db4f1d7b4ca, on
v125) and #3153 (486eb6809921, on v125) merged minutes apart, each written
against a main that lacked the other two. Main then had three heads, and
every deploy of it died in scripts/run-migrations.sh on "Multiple head
revisions are present" before gunicorn started (production deployment
9d50ac07 of ef02a8a3; the previous deployment kept serving). Nothing was
applied from any branch by that failure.

A merge alone would only move the failure: on a database c51d4898e0a2 already
reached, 2db4f1d7b4ca's DROP CONSTRAINT manifest_blobs_ingestion_run_id_fkey
fails because c51d4898e0a2 dropped that key. 2db4f1d7b4ca now leaves
fsma.manifest_blobs to c51d4898e0a2 (see its docstring).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ed902d03df45"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "d2e7a7319b33",  # pragma: allowlist secret
    "2db4f1d7b4ca",  # pragma: allowlist secret
    "486eb6809921",  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
