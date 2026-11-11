"""Durable EDI rejections: fsma.edi_rejections (v144).

The EDI routes return a ``rejection_id`` when they refuse a document, but the
evidence lived only in one worker's memory, so a restart or a different worker
lost it. Each row holds the errors and extracted fields for one rejection.

Append-only: the runtime role can insert and select, and a row is never updated
or deleted by the app. RLS is forced, with the v137 policy shape. v111's
inventory lists the table so the per-deploy cutover keeps these grants.

Mirrors ``supabase/migrations/20261111120000_v144_edi_rejections.sql``. Additive
and idempotent. Downgrade drops only what this revision created.

Revision ID: 056ffd2f8045
Revises: c4a9d2e761b0
Create Date: 2026-11-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "056ffd2f8045"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c4a9d2e761b0"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_UPGRADE_STATEMENTS: tuple[str, ...] = (
    """
CREATE TABLE IF NOT EXISTS fsma.edi_rejections (
    rejection_id          text primary key,
    tenant_id             uuid not null,
    transaction_set       text not null,
    traceability_lot_code text,
    partner_id            text,
    source                text,
    reason                text not null,
    needs_review          boolean not null default false,
    errors                jsonb not null default '[]'::jsonb,
    extracted             jsonb not null default '{}'::jsonb,
    recorded_at           timestamptz not null default now()
);
""",
    """
create index if not exists idx_edi_rejections_tenant_recorded
    on fsma.edi_rejections (tenant_id, recorded_at desc);
""",
    """
ALTER TABLE fsma.edi_rejections ENABLE ROW LEVEL SECURITY;
""",
    """
ALTER TABLE fsma.edi_rejections FORCE ROW LEVEL SECURITY;
""",
    """
drop policy if exists tenant_isolation_edi_rejections on fsma.edi_rejections;
""",
    """
create policy tenant_isolation_edi_rejections on fsma.edi_rejections
    for all
    using (
        case
            when (select current_setting('regengine.is_sysadmin', true)) = 'true'
                 and current_user = 'regengine_sysadmin' then true
            else tenant_id = (select public.get_tenant_context())
        end
    )
    with check (
        case
            when (select current_setting('regengine.is_sysadmin', true)) = 'true'
                 and current_user = 'regengine_sysadmin' then true
            else tenant_id = (select public.get_tenant_context())
        end
    );
""",
    """
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on fsma.edi_rejections from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on fsma.edi_rejections from authenticated;
    end if;
    if exists (select 1 from pg_roles where rolname = 'regengine') then
        grant select, insert on fsma.edi_rejections to regengine;
    end if;
    if exists (select 1 from pg_roles where rolname = 'regengine_sysadmin') then
        grant select on fsma.edi_rejections to regengine_sysadmin;
    end if;
end $$;
""",
)


def upgrade() -> None:
    for statement in _UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_edi_rejections ON fsma.edi_rejections")
    op.execute("DROP INDEX IF EXISTS fsma.idx_edi_rejections_tenant_recorded")
    op.execute("DROP TABLE IF EXISTS fsma.edi_rejections")
