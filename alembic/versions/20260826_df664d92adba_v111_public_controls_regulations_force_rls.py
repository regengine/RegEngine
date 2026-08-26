"""v111 — FORCE ROW LEVEL SECURITY on public.controls and public.regulations.

Revision ID: df664d92adba
Revises: 6f8c2d1a4b90
Create Date: 2026-08-26

v056 Part 4 arms the regulatory control-plane trio identically — a
``tenant_isolation_*`` policy ``TO regengine, regengine_sysadmin`` plus
``ENABLE ROW LEVEL SECURITY`` — for ``obligations``, ``controls`` and
``regulations``. Only ``obligations`` was ever also FORCED
(``v051`` line 461, re-asserted by ``v056`` line 296). ``controls`` and
``regulations`` have carried ENABLE-without-FORCE ever since::

    grep -rn "FORCE ROW LEVEL SECURITY" alembic/ | grep -Ei "controls|regulations"
    (no matches before this revision)

``ENABLE`` alone does not apply the policy to the table OWNER, so any
connection made as the owning role reads and writes every tenant's rows
with RLS silently inert. That is not hypothetical: the backend CI job
reproduces the production role layout by making the app role ``regengine``
the owner of the database it migrates
(``.github/workflows/backend-ci.yml`` lines 525-526), so under CI the
application role is the table owner and bypasses the tenant predicate on
exactly these two tables. ``public.regulations`` and ``public.controls``
are tenant-scoped FSMA data (``tenant_id UUID NOT NULL``, seeded per
tenant by ``seed_obligations_for_tenant``), so this is a cross-tenant read
and write hole, not a lookup-table exemption.

Fix: FORCE both tables, matching the sibling ``public.obligations``.

Deliberately NOT guarded on ``to_regclass``. Both relations are created by
the consolidated baseline (``alembic/sql/V036__fsma_204_regulatory_seed_data.sql``
lines 12 and 36, applied by revision 97588ba8edf3), so they exist on every
database that can reach this revision; a guard here could only ever hide a
broken chain. See the v104 docstring — "A conditional CREATE POLICY is what
caused this incident" — for why a silently-skipping RLS migration is a
banned shape in this tree.

Blast-radius note: FORCE subjects the owner to the ``tenant_isolation_*``
policies, which are granted ``TO regengine, regengine_sysadmin``. Any
migration/owner role outside that set (and without BYPASSRLS) would lose
access to these two tables. ``public.obligations`` has been FORCE since
v051 and is written by the same code paths, so any deployment that can
already read and write ``public.obligations`` is unaffected by this change.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "df664d92adba"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "6f8c2d1a4b90"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tenant-scoped public-schema tables that v056 Part 4 enabled RLS on but
# never forced. public.obligations is intentionally absent — already FORCE.
_TABLES: tuple[str, ...] = ("public.controls", "public.regulations")


def upgrade() -> None:
    for table in _TABLES:
        # ENABLE is re-asserted so the FORCE below can never sit on a table
        # whose row security got turned off out of band; both are idempotent.
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Reverse of upgrade: return the owner to bypassing RLS. ENABLE is left
    # in place — it predates this revision (v056 Part 4) and is not ours to
    # remove.
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
