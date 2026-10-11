"""v085 -- enterprise SSO domain policy.

Revision ID: f8a9b0c1d2e3
Revises: da5d93004161
Create Date: 2026-06-23

Adds organization domain routing metadata and constrains auth policy values
for Phase 6 enterprise SSO enforcement.

Downgrade guard: reverting this revision rewrites auth policy rows it did
not create. The upgrade only normalises NULL and out-of-vocabulary values to
'standard', but the downgrade sets every 'standard' and 'sso_only' row back
to 'passwordless_email_code', including organisations that already carried
'standard' or enforced 'sso_only' before this revision ever ran. Rolling
back silently lifts SSO enforcement, so the downgrade requires the same
explicit two-variable acknowledgement the baseline and v108 downgrades use.
"""

import os
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f8a9b0c1d2e3"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "da5d93004161"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("domain_name", sa.String(), nullable=True))
    op.create_index("ix_organizations_domain_name", "organizations", ["domain_name"], unique=True)

    op.execute(
        """
        UPDATE public.organizations
        SET enforced_auth_policy = 'standard'
        WHERE enforced_auth_policy IS NULL
           OR enforced_auth_policy NOT IN ('standard', 'sso_only')
        """
    )
    op.alter_column(
        "organizations",
        "enforced_auth_policy",
        existing_type=sa.String(),
        nullable=False,
        server_default="standard",
    )
    op.create_check_constraint(
        "organization_auth_policy",
        "organizations",
        "enforced_auth_policy IN ('standard', 'sso_only')",
    )


def _require_destructive_downgrade_ack() -> None:
    """Refuse to run the destructive downgrade without an explicit opt-in.

    Same shape and same two variables as the v108 downgrade guard
    (``20260801_a43b0fb1edd0``) and the baseline downgrade guard (#1264):
    ``REGENGINE_ENV`` must name a non-production environment AND
    ``REGENGINE_ALLOW_BASELINE_DOWNGRADE`` must be ``1``. In production or
    staging the recovery path is a snapshot restore, not a downgrade that
    rewrites live auth policy rows.

    To override (dev only)::

        REGENGINE_ENV=development \\
        REGENGINE_ALLOW_BASELINE_DOWNGRADE=1 \\
        alembic downgrade f8a9b0c1d2e3
    """
    env = os.environ.get("REGENGINE_ENV", "unset").lower()
    ack = os.environ.get("REGENGINE_ALLOW_BASELINE_DOWNGRADE", "0")
    if env in {"development", "dev", "test", "ci"} and ack == "1":
        return
    raise RuntimeError(
        "v085 downgrade blocked. Reverting this revision rewrites every "
        "public.organizations row with enforced_auth_policy 'standard' or "
        "'sso_only' back to 'passwordless_email_code', including rows that "
        "already carried those values before this revision ran, so a rollback "
        "silently lifts SSO enforcement. None of that is recoverable by "
        "re-upgrading: upgrade() normalises unrecognised values to 'standard' "
        "and cannot tell which rows used to enforce SSO.\n\n"
        "To proceed in a development environment, set BOTH:\n"
        "  REGENGINE_ENV=development\n"
        "  REGENGINE_ALLOW_BASELINE_DOWNGRADE=1\n\n"
        "For production rollback, restore from a database snapshot rather than "
        "running this downgrade.\n\n"
        f"Current: REGENGINE_ENV={env!r}, "
        f"REGENGINE_ALLOW_BASELINE_DOWNGRADE={ack!r}"
    )


def downgrade() -> None:
    _require_destructive_downgrade_ack()
    op.drop_constraint("organization_auth_policy", "organizations", type_="check")
    op.execute(
        """
        UPDATE public.organizations
        SET enforced_auth_policy = 'passwordless_email_code'
        WHERE enforced_auth_policy IN ('standard', 'sso_only')
        """
    )
    op.alter_column(
        "organizations",
        "enforced_auth_policy",
        existing_type=sa.String(),
        nullable=False,
        server_default="passwordless_email_code",
    )

    op.drop_index("ix_organizations_domain_name", table_name="organizations")
    op.drop_column("organizations", "domain_name")
