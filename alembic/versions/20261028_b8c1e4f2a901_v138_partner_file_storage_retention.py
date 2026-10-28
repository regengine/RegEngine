"""Partner file storage metadata + 30-day retention (v138).

Mirrors supabase/migrations/20261028100000_partner_files_storage_retention.sql
exactly for partner_files / partner_file_derived / partner_file_deletion_log
(tables, indexes, CASE RLS, grants). Bucket creation lives only in
supabase/migrations/20261028100010_partner_uploads_bucket.sql (storage schema
is Supabase-only).

Also prepares Railway fsma.manifest_blobs for hash/pointer cutover: raw_bytes
becomes nullable with a check that at least one of raw_bytes or storage_url is
present (storage_url already exists from v095). Does not move bytes; does not
apply envelope encryption.

Additive and idempotent. Downgrade drops only what this revision created and
restores raw_bytes NOT NULL when safe.

Revision ID: b8c1e4f2a901
Revises: a3f7ce361b0e
Create Date: 2026-10-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b8c1e4f2a901"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "a3f7ce361b0e"  # pragma: allowlist secret
branch_labels = None
depends_on = None

# Mirrored from the supabase SQL migration (minus the hand-only downgrade notes).
_PARTNER_FILES_SQL = """
-- Partner file storage metadata + 30-day retention clock (SEL-549 / first-file).
--
-- Metadata only. Partner file bytes live in the private Supabase Storage bucket
-- `partner-uploads` (see sibling migration 20261028100010). Never store partner
-- file contents in these tables or in the deletion log.
--
-- Clock: delete_after = report_delivered_at + 30 days (trigger-maintained; UTC).
-- Envelope encryption columns (kek_key_id / wrapped_dek) are nullable; v1 may
-- rely on provider at-rest encryption only (design open Q1 deferred).
--
-- RLS uses CASE + (select public.get_tenant_context()), matching epcis /
-- data_gap (not the JWT sketch). Idempotent. Do not apply to prod without
-- C.Lee yes. Synthetic fixtures only until SEL-590 clears.

CREATE TABLE IF NOT EXISTS public.partner_files (
    id                  uuid primary key default gen_random_uuid(),
    tenant_id           uuid not null references public.tenants(id),
    engagement_id       uuid not null,
    storage_bucket      text not null default 'partner-uploads',
    storage_path        text not null,
    content_sha256      text not null,
    ciphertext_sha256   text,
    byte_size           bigint not null,
    content_type        text not null,
    original_filename   text not null,
    kek_key_id          text,
    wrapped_dek         bytea,
    uploaded_at         timestamptz not null default now(),
    report_delivered_at timestamptz,
    -- Maintained by partner_files_set_delete_after trigger (timestamptz + interval
    -- is not IMMUTABLE, so a generated column is not allowed).
    delete_after        timestamptz,
    deleted_at          timestamptz,
    status              text not null default 'uploaded',
    constraint partner_files_byte_size_check
        check (byte_size > 0),
    constraint partner_files_content_sha256_check
        check (content_sha256 ~ '^[0-9a-f]{64}$'),
    constraint partner_files_ciphertext_sha256_check
        check (ciphertext_sha256 is null or ciphertext_sha256 ~ '^[0-9a-f]{64}$'),
    constraint partner_files_status_check
        check (status in (
            'uploaded',
            'processing',
            'report_ready',
            'delivered',
            'pending_delete',
            'deleted'
        )),
    constraint partner_files_storage_bucket_check
        check (storage_bucket = 'partner-uploads'),
    constraint partner_files_storage_path_unique
        unique (storage_bucket, storage_path)
);

CREATE INDEX IF NOT EXISTS partner_files_due_delete_idx
    ON public.partner_files (delete_after)
    WHERE deleted_at IS NULL AND report_delivered_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS partner_files_tenant_uploaded_idx
    ON public.partner_files (tenant_id, uploaded_at desc);

-- delete_after = report_delivered_at + 30 days (trigger; generated col not allowed)
CREATE OR REPLACE FUNCTION public.partner_files_set_delete_after()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.report_delivered_at IS NULL THEN
        NEW.delete_after := NULL;
    ELSE
        NEW.delete_after := NEW.report_delivered_at + interval '30 days';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS partner_files_set_delete_after ON public.partner_files;
CREATE TRIGGER partner_files_set_delete_after
    BEFORE INSERT OR UPDATE OF report_delivered_at
    ON public.partner_files
    FOR EACH ROW
    EXECUTE FUNCTION public.partner_files_set_delete_after();

CREATE TABLE IF NOT EXISTS public.partner_file_derived (
    id              uuid primary key default gen_random_uuid(),
    partner_file_id uuid not null references public.partner_files(id) on delete cascade,
    tenant_id       uuid not null references public.tenants(id),
    kind            text not null,
    storage_bucket  text,
    storage_path    text,
    row_ref         text,
    created_at      timestamptz not null default now(),
    deleted_at      timestamptz,
    constraint partner_file_derived_kind_check
        check (char_length(kind) between 1 and 64)
);

CREATE INDEX IF NOT EXISTS partner_file_derived_file_idx
    ON public.partner_file_derived (partner_file_id)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS public.partner_file_deletion_log (
    id                  uuid primary key default gen_random_uuid(),
    partner_file_id     uuid not null,
    tenant_id           uuid not null,
    engagement_id       uuid,
    storage_bucket      text not null,
    storage_path        text not null,
    content_sha256      text not null,
    ciphertext_sha256   text,
    byte_size           bigint,
    report_delivered_at timestamptz,
    deleted_at          timestamptz not null default now(),
    actor               text not null,
    reason              text not null,
    entry_hash          text not null,
    prev_entry_hash     text,
    constraint partner_file_deletion_log_content_sha256_check
        check (content_sha256 ~ '^[0-9a-f]{64}$'),
    constraint partner_file_deletion_log_ciphertext_sha256_check
        check (ciphertext_sha256 is null or ciphertext_sha256 ~ '^[0-9a-f]{64}$'),
    constraint partner_file_deletion_log_entry_hash_check
        check (entry_hash ~ '^[0-9a-f]{64}$'),
    constraint partner_file_deletion_log_prev_entry_hash_check
        check (prev_entry_hash is null or prev_entry_hash ~ '^[0-9a-f]{64}$'),
    constraint partner_file_deletion_log_actor_check
        check (
            actor = 'retention_job'
            or actor = 'partner_request'
            or actor like 'ops:%'
        ),
    constraint partner_file_deletion_log_reason_check
        check (reason in ('retention_30d', 'partner_request_15d', 'terms_end'))
);

CREATE INDEX IF NOT EXISTS partner_file_deletion_log_tenant_deleted_idx
    ON public.partner_file_deletion_log (tenant_id, deleted_at desc);

ALTER TABLE public.partner_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_files FORCE ROW LEVEL SECURITY;
ALTER TABLE public.partner_file_derived ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_file_derived FORCE ROW LEVEL SECURITY;
ALTER TABLE public.partner_file_deletion_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_file_deletion_log FORCE ROW LEVEL SECURITY;

-- CASE form, not OR: public.get_tenant_context() raises when app.tenant_id is
-- unset and Postgres does not order OR operands, so the sysadmin arm is tested
-- first (same predicate shape as alembic v096 / v134 / v135 / v137).
DROP POLICY IF EXISTS tenant_isolation_partner_files ON public.partner_files;
CREATE POLICY tenant_isolation_partner_files ON public.partner_files
    FOR ALL
    USING (
        CASE
            WHEN (select current_setting('regengine.is_sysadmin', true)) = 'true'
                 AND current_user = 'regengine_sysadmin' THEN true
            ELSE tenant_id = (select public.get_tenant_context())
        END
    )
    WITH CHECK (
        CASE
            WHEN (select current_setting('regengine.is_sysadmin', true)) = 'true'
                 AND current_user = 'regengine_sysadmin' THEN true
            ELSE tenant_id = (select public.get_tenant_context())
        END
    );

DROP POLICY IF EXISTS tenant_isolation_partner_file_derived ON public.partner_file_derived;
CREATE POLICY tenant_isolation_partner_file_derived ON public.partner_file_derived
    FOR ALL
    USING (
        CASE
            WHEN (select current_setting('regengine.is_sysadmin', true)) = 'true'
                 AND current_user = 'regengine_sysadmin' THEN true
            ELSE tenant_id = (select public.get_tenant_context())
        END
    )
    WITH CHECK (
        CASE
            WHEN (select current_setting('regengine.is_sysadmin', true)) = 'true'
                 AND current_user = 'regengine_sysadmin' THEN true
            ELSE tenant_id = (select public.get_tenant_context())
        END
    );

DROP POLICY IF EXISTS tenant_isolation_partner_file_deletion_log ON public.partner_file_deletion_log;
CREATE POLICY tenant_isolation_partner_file_deletion_log ON public.partner_file_deletion_log
    FOR SELECT
    USING (
        CASE
            WHEN (select current_setting('regengine.is_sysadmin', true)) = 'true'
                 AND current_user = 'regengine_sysadmin' THEN true
            ELSE tenant_id = (select public.get_tenant_context())
        END
    );

-- Inserts into the deletion log go through the retention worker (regengine /
-- SECURITY DEFINER RPC). No authenticated UPDATE/DELETE on the log.
DROP POLICY IF EXISTS partner_file_deletion_log_insert_worker ON public.partner_file_deletion_log;
CREATE POLICY partner_file_deletion_log_insert_worker ON public.partner_file_deletion_log
    FOR INSERT
    WITH CHECK (
        CASE
            WHEN (select current_setting('regengine.is_sysadmin', true)) = 'true'
                 AND current_user = 'regengine_sysadmin' THEN true
            ELSE tenant_id = (select public.get_tenant_context())
        END
    );

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.partner_files FROM anon;
        REVOKE ALL ON public.partner_file_derived FROM anon;
        REVOKE ALL ON public.partner_file_deletion_log FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        -- Metadata reads/writes for tenant users go through the app role /
        -- signed upload path, not broad authenticated table DML.
        REVOKE ALL ON public.partner_files FROM authenticated;
        REVOKE ALL ON public.partner_file_derived FROM authenticated;
        REVOKE ALL ON public.partner_file_deletion_log FROM authenticated;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
        GRANT SELECT, INSERT, UPDATE ON public.partner_files TO regengine;
        GRANT SELECT, INSERT, UPDATE ON public.partner_file_derived TO regengine;
        -- Append-only audit: INSERT + SELECT only. Never UPDATE/DELETE.
        GRANT SELECT, INSERT ON public.partner_file_deletion_log TO regengine;
        REVOKE UPDATE, DELETE ON public.partner_file_deletion_log FROM regengine;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
        GRANT SELECT ON public.partner_files TO regengine_sysadmin;
        GRANT SELECT ON public.partner_file_derived TO regengine_sysadmin;
        GRANT SELECT ON public.partner_file_deletion_log TO regengine_sysadmin;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        -- Prefer SECURITY DEFINER RPCs; keep service_role from mutating the log.
        REVOKE UPDATE, DELETE ON public.partner_file_deletion_log FROM service_role;
    END IF;
END $$;

"""

_MANIFEST_BLOBS_SQL = """
-- Railway cutover helper: allow hash/pointer-only manifest_blobs rows.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma'
          AND table_name = 'manifest_blobs'
          AND column_name = 'raw_bytes'
    ) THEN
        ALTER TABLE fsma.manifest_blobs ALTER COLUMN raw_bytes DROP NOT NULL;
    END IF;
END $$;

ALTER TABLE fsma.manifest_blobs DROP CONSTRAINT IF EXISTS manifest_blobs_payload_present_check;
ALTER TABLE fsma.manifest_blobs
    ADD CONSTRAINT manifest_blobs_payload_present_check
    CHECK (
        raw_bytes IS NOT NULL
        OR (storage_url IS NOT NULL AND length(btrim(storage_url)) > 0)
    );
"""


def upgrade() -> None:
    # Split on semicolons outside dollar-quoted blocks so DO $$ ... $$; stays intact.
    def _statements(sql: str) -> list[str]:
        out: list[str] = []
        buf: list[str] = []
        in_dollar = False
        i = 0
        while i < len(sql):
            if sql.startswith("$$", i):
                in_dollar = not in_dollar
                buf.append("$$")
                i += 2
                continue
            ch = sql[i]
            if ch == ";" and not in_dollar:
                stmt = "".join(buf).strip()
                if stmt and not all(
                    line.strip().startswith("--") or not line.strip()
                    for line in stmt.splitlines()
                ):
                    out.append(stmt)
                buf = []
                i += 1
                continue
            buf.append(ch)
            i += 1
        tail = "".join(buf).strip()
        if tail:
            out.append(tail)
        return out

    for statement in _statements(_PARTNER_FILES_SQL) + _statements(_MANIFEST_BLOBS_SQL):
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(
        sa.text(
            """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'fsma' AND table_name = 'manifest_blobs'
    ) THEN
        ALTER TABLE fsma.manifest_blobs DROP CONSTRAINT IF EXISTS manifest_blobs_payload_present_check;
        IF NOT EXISTS (
            SELECT 1 FROM fsma.manifest_blobs WHERE raw_bytes IS NULL
        ) THEN
            ALTER TABLE fsma.manifest_blobs ALTER COLUMN raw_bytes SET NOT NULL;
        END IF;
    END IF;
END $$;
"""
        )
    )
    op.execute(sa.text("DROP POLICY IF EXISTS partner_file_deletion_log_insert_worker ON public.partner_file_deletion_log"))
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation_partner_file_deletion_log ON public.partner_file_deletion_log"))
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation_partner_file_derived ON public.partner_file_derived"))
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation_partner_files ON public.partner_files"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS partner_files_set_delete_after ON public.partner_files"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.partner_files_set_delete_after()"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.partner_file_deletion_log_tenant_deleted_idx"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.partner_file_derived_file_idx"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.partner_files_tenant_uploaded_idx"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.partner_files_due_delete_idx"))
    op.execute(sa.text("DROP TABLE IF EXISTS public.partner_file_deletion_log"))
    op.execute(sa.text("DROP TABLE IF EXISTS public.partner_file_derived"))
    op.execute(sa.text("DROP TABLE IF EXISTS public.partner_files"))
