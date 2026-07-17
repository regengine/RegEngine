"""v095 — supplier remediation slice (manifest staging, scoped tokens, correction patches).

Revision ID: c7a1e5f2b9d4
Revises: feb267263e0a
Create Date: 2026-07-16

Adds the storage for the supplier CSV manifest remediation loop:

1. ``fsma.manifest_blobs`` — byte-exact preservation of uploaded manifests
   (SHA-256 recorded; one row per ``fsma.ingestion_runs`` row).
2. ``fsma.manifest_records`` — per-row staging with verbatim source cells,
   normalized payload, field-level provenance, and validation snapshot.
   Blocked rows stay here; only passing rows are released into
   ``fsma.traceability_events`` via the canonical writer.
3. ``fsma.remediation_cases`` — supplier remediation lifecycle
   (detected → … → released | buyer_review | escalated).
4. ``fsma.remediation_tokens`` — hash-at-rest correction-link tokens
   (24h) with rotating short-lived session hashes (30m). Raw tokens are
   never stored. Unauthenticated bootstrap lookup goes through
   SECURITY DEFINER functions + a hash-keyed SELECT policy, following the
   v075 portal-link precedent.
5. ``fsma.correction_patches`` — append-only, hash-chained correction
   history (v078 audit append-only trigger pattern, ``fsma.allow_mutation``
   break-glass GUC).
6. ``fsma.notification_outbox`` — local notification previews only; no
   delivery worker.

All tables: ``tenant_id UUID NOT NULL`` + ENABLE/FORCE ROW LEVEL SECURITY
with the ``get_tenant_context()`` policy (v078 ``_tenant_rls`` helper).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c7a1e5f2b9d4"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "feb267263e0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_rls(table: str, column: str, policy: str) -> None:
    schema, table_name = table.split(".", 1)
    op.execute(
        f"""
        DO $$
        DECLARE
            column_type text;
            predicate text;
        BEGIN
            IF to_regclass('{table}') IS NULL THEN
                RETURN;
            END IF;
            SELECT data_type INTO column_type
            FROM information_schema.columns
            WHERE table_schema = '{schema}'
              AND table_name = '{table_name}'
              AND column_name = '{column}';
            IF column_type IS NULL THEN
                RETURN;
            END IF;
            IF column_type IN ('text', 'character varying') THEN
                predicate := '{column} = get_tenant_context()::text';
            ELSE
                predicate := '{column} = get_tenant_context()';
            END IF;
            EXECUTE 'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE {table} FORCE ROW LEVEL SECURITY';
            EXECUTE 'DROP POLICY IF EXISTS {policy} ON {table}';
            EXECUTE format(
                'CREATE POLICY {policy} ON {table}
                    FOR ALL
                    USING (%s)
                    WITH CHECK (%s)',
                predicate,
                predicate
            );
        END $$;
        """
    )


def _create_tables() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.manifest_blobs (
            ingestion_run_id UUID PRIMARY KEY
                REFERENCES fsma.ingestion_runs(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL,
            raw_bytes BYTEA NOT NULL,
            sha256 TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            content_type TEXT,
            uploaded_by TEXT,
            storage_url TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_manifest_blobs_tenant
            ON fsma.manifest_blobs (tenant_id);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.manifest_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            ingestion_run_id UUID NOT NULL
                REFERENCES fsma.ingestion_runs(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            raw_row JSONB NOT NULL,
            normalized_payload JSONB,
            field_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
            row_fingerprint TEXT NOT NULL,
            validation_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (validation_status IN ('pending', 'passed', 'failed')),
            release_status TEXT NOT NULL DEFAULT 'staged'
                CHECK (release_status IN ('staged', 'released', 'rejected')),
            released_event_id UUID,
            remediation_case_id UUID,
            rule_failures JSONB NOT NULL DEFAULT '[]'::jsonb,
            ruleset_hash TEXT,
            last_validated_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, ingestion_run_id, row_number)
        );
        CREATE INDEX IF NOT EXISTS idx_manifest_records_tenant_run
            ON fsma.manifest_records (tenant_id, ingestion_run_id);
        CREATE INDEX IF NOT EXISTS idx_manifest_records_fingerprint
            ON fsma.manifest_records (tenant_id, row_fingerprint);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.remediation_cases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            manifest_record_id UUID NOT NULL
                REFERENCES fsma.manifest_records(id) ON DELETE CASCADE,
            exception_case_id UUID,
            supplier_org TEXT NOT NULL,
            manifest_ref TEXT,
            line_ref TEXT,
            validation_issue_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            allowed_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
            due_at TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'detected'
                CHECK (status IN (
                    'detected', 'auto_resolution_attempted',
                    'supplier_action_required', 'notification_ready',
                    'awaiting_supplier', 'correction_submitted',
                    'revalidating', 'released', 'buyer_review', 'escalated'
                )),
            last_revalidation JSONB,
            released_event_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_remediation_cases_tenant_status
            ON fsma.remediation_cases (tenant_id, status);
        CREATE INDEX IF NOT EXISTS idx_remediation_cases_record
            ON fsma.remediation_cases (tenant_id, manifest_record_id);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.remediation_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            case_id UUID NOT NULL
                REFERENCES fsma.remediation_cases(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            superseded_by UUID REFERENCES fsma.remediation_tokens(id),
            session_token_hash TEXT UNIQUE,
            session_expires_at TIMESTAMPTZ,
            exchange_count INTEGER NOT NULL DEFAULT 0,
            supplier_email TEXT,
            created_by TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_remediation_tokens_active
            ON fsma.remediation_tokens (token_hash)
            WHERE revoked_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_remediation_tokens_tenant_case
            ON fsma.remediation_tokens (tenant_id, case_id);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.correction_patches (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            case_id UUID NOT NULL REFERENCES fsma.remediation_cases(id),
            manifest_record_id UUID NOT NULL
                REFERENCES fsma.manifest_records(id),
            patch_seq INTEGER NOT NULL,
            validation_issue_id TEXT,
            field_path TEXT NOT NULL,
            previous_value JSONB,
            proposed_value JSONB NOT NULL,
            correcting_org TEXT NOT NULL,
            actor_name TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            auth_method TEXT NOT NULL DEFAULT 'remediation_token',
            correction_reason TEXT NOT NULL,
            attestation_text TEXT NOT NULL,
            attested_at TIMESTAMPTZ NOT NULL,
            evidence_ref TEXT,
            prev_patch_hash TEXT,
            patch_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, case_id, patch_seq)
        );
        CREATE INDEX IF NOT EXISTS idx_correction_patches_record
            ON fsma.correction_patches (tenant_id, manifest_record_id);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.notification_outbox (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            case_id UUID REFERENCES fsma.remediation_cases(id),
            channel TEXT NOT NULL DEFAULT 'email_preview',
            recipient TEXT,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'previewed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_notification_outbox_tenant_status
            ON fsma.notification_outbox (tenant_id, status);
        """
    )


def _patch_append_only() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.prevent_patch_mutation()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('fsma.allow_mutation', true) = 'true' THEN
                RAISE WARNING
                    'correction_patches modification via break-glass. op=% user=% row_id=%',
                    TG_OP, current_user, COALESCE(NEW.id::text, OLD.id::text);
                RETURN COALESCE(NEW, OLD);
            END IF;
            RAISE EXCEPTION
                'correction_patches is append-only. Operation % rejected. Set fsma.allow_mutation=true for authorized break-glass.',
                TG_OP
                USING ERRCODE = 'check_violation';
        END;
        $$;

        DO $$
        BEGIN
            IF to_regclass('fsma.correction_patches') IS NULL THEN
                RETURN;
            END IF;
            DROP TRIGGER IF EXISTS correction_patches_append_only
                ON fsma.correction_patches;
            CREATE TRIGGER correction_patches_append_only
                BEFORE UPDATE OR DELETE ON fsma.correction_patches
                FOR EACH ROW EXECUTE FUNCTION fsma.prevent_patch_mutation();
            REVOKE UPDATE, DELETE, TRUNCATE ON fsma.correction_patches FROM PUBLIC;
        END $$;
        """
    )


def _token_lookup() -> None:
    """Unauthenticated bootstrap lookup under FORCE RLS (v075 precedent).

    A supplier presents a raw token before any tenant context exists, so the
    hash-keyed SELECT policy plus SECURITY DEFINER functions are the only
    RLS path in. The caller can only ever see the row whose hash it already
    holds; expiry/revocation are enforced (and audited) in the app layer.
    """
    op.execute("DROP POLICY IF EXISTS remediation_token_lookup ON fsma.remediation_tokens")
    op.execute(
        """
        CREATE POLICY remediation_token_lookup
            ON fsma.remediation_tokens
            FOR SELECT
            USING (
                token_hash = NULLIF(current_setting('app.remediation_token_hash', true), '')
                OR session_token_hash = NULLIF(current_setting('app.remediation_token_hash', true), '')
            )
        """
    )
    for fn_name, column in (
        ("get_remediation_token_by_hash", "token_hash"),
        ("get_remediation_token_by_session_hash", "session_token_hash"),
    ):
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION fsma.{fn_name}(p_hash TEXT)
            RETURNS TABLE (
                id UUID,
                tenant_id UUID,
                case_id UUID,
                expires_at TIMESTAMPTZ,
                revoked_at TIMESTAMPTZ,
                superseded_by UUID,
                session_token_hash TEXT,
                session_expires_at TIMESTAMPTZ,
                exchange_count INTEGER
            )
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = fsma, public, pg_temp
            AS $fn$
            BEGIN
                PERFORM set_config('app.remediation_token_hash', p_hash, true);

                RETURN QUERY
                SELECT
                    t.id,
                    t.tenant_id,
                    t.case_id,
                    t.expires_at,
                    t.revoked_at,
                    t.superseded_by,
                    t.session_token_hash,
                    t.session_expires_at,
                    t.exchange_count
                FROM fsma.remediation_tokens AS t
                WHERE t.{column} = p_hash
                LIMIT 1;
            END;
            $fn$
            """
        )
        op.execute(f"REVOKE ALL ON FUNCTION fsma.{fn_name}(TEXT) FROM PUBLIC")
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                    GRANT EXECUTE ON FUNCTION fsma.{fn_name}(TEXT) TO regengine;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                    GRANT EXECUTE ON FUNCTION fsma.{fn_name}(TEXT) TO regengine_sysadmin;
                END IF;
            END
            $$;
            """
        )


def upgrade() -> None:
    _create_tables()
    _tenant_rls("fsma.manifest_blobs", "tenant_id", "tenant_isolation_manifest_blobs")
    _tenant_rls("fsma.manifest_records", "tenant_id", "tenant_isolation_manifest_records")
    _tenant_rls("fsma.remediation_cases", "tenant_id", "tenant_isolation_remediation_cases")
    _tenant_rls("fsma.remediation_tokens", "tenant_id", "tenant_isolation_remediation_tokens")
    _tenant_rls("fsma.correction_patches", "tenant_id", "tenant_isolation_correction_patches")
    _tenant_rls("fsma.notification_outbox", "tenant_id", "tenant_isolation_notification_outbox")
    _patch_append_only()
    _token_lookup()


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS fsma.get_remediation_token_by_hash(TEXT)")
    op.execute("DROP FUNCTION IF EXISTS fsma.get_remediation_token_by_session_hash(TEXT)")
    op.execute("DROP TABLE IF EXISTS fsma.notification_outbox")
    op.execute("DROP TABLE IF EXISTS fsma.correction_patches")
    op.execute("DROP FUNCTION IF EXISTS fsma.prevent_patch_mutation()")
    op.execute("DROP TABLE IF EXISTS fsma.remediation_tokens")
    op.execute("DROP TABLE IF EXISTS fsma.remediation_cases")
    op.execute("DROP TABLE IF EXISTS fsma.manifest_records")
    op.execute("DROP TABLE IF EXISTS fsma.manifest_blobs")
