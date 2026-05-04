"""v077 -- repair Railway schema drift warnings.

Revision ID: f2c3d4e5a6b7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-04

Railway startup was warning about ORM tables that exist in the admin models
but were only present in legacy Flyway SQL, not the active Alembic chain. This
migration forward-ports the missing active tables and normalizes the legacy
``audit_logs.id`` UUID primary key to the current bigint sequence shape while
preserving the prior UUID in ``legacy_uuid``.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "f2c3d4e5a6b7"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    _create_missing_admin_tables()
    _create_missing_supplier_tables()
    _normalize_audit_log_id()


def downgrade() -> None:
    """Non-destructive repair migration; keep production data in place."""
    pass


def _create_missing_admin_tables() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL DEFAULT 'Default Tenant',
            slug TEXT UNIQUE,
            status TEXT NOT NULL DEFAULT 'active',
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ
        );
        ALTER TABLE public.tenants ADD COLUMN IF NOT EXISTS settings JSONB NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE public.tenants ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
        CREATE UNIQUE INDEX IF NOT EXISTS ix_tenants_slug ON public.tenants(slug);

        CREATE TABLE IF NOT EXISTS public.users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            mfa_secret TEXT,
            mfa_secret_ciphertext TEXT,
            token_version INTEGER NOT NULL DEFAULT 0,
            is_sysadmin BOOLEAN NOT NULL DEFAULT false,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            last_login_at TIMESTAMPTZ
        );
        ALTER TABLE public.users ADD COLUMN IF NOT EXISTS mfa_secret_ciphertext TEXT;
        ALTER TABLE public.users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_sysadmin BOOLEAN NOT NULL DEFAULT false;
        ALTER TABLE public.users ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
        ALTER TABLE public.users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
        ALTER TABLE public.users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
        CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON public.users(email);

        CREATE TABLE IF NOT EXISTS public.roles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID,
            name TEXT NOT NULL,
            permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_roles_tenant ON public.roles(tenant_id);

        CREATE TABLE IF NOT EXISTS public.memberships (
            user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            role_id UUID NOT NULL REFERENCES public.roles(id),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by UUID,
            PRIMARY KEY (user_id, tenant_id)
        );
        ALTER TABLE public.memberships ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
        ALTER TABLE public.memberships ADD COLUMN IF NOT EXISTS created_by UUID;
        CREATE INDEX IF NOT EXISTS ix_memberships_user ON public.memberships(user_id);
        CREATE INDEX IF NOT EXISTS ix_memberships_tenant ON public.memberships(tenant_id);

        CREATE TABLE IF NOT EXISTS public.sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            refresh_token_hash TEXT NOT NULL UNIQUE,
            family_id UUID NOT NULL,
            is_revoked BOOLEAN NOT NULL DEFAULT false,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            user_agent TEXT,
            ip_address TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON public.sessions(user_id);
        CREATE INDEX IF NOT EXISTS ix_sessions_refresh_token_hash
            ON public.sessions(refresh_token_hash);
        CREATE INDEX IF NOT EXISTS ix_sessions_family_id ON public.sessions(family_id);

        CREATE TABLE IF NOT EXISTS public.invites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            role_id UUID NOT NULL REFERENCES public.roles(id),
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            accepted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by UUID NOT NULL REFERENCES public.users(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ix_invites_tenant_email
            ON public.invites(tenant_id, email)
            WHERE revoked_at IS NULL AND accepted_at IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS ix_invites_token_hash ON public.invites(token_hash);
        CREATE INDEX IF NOT EXISTS ix_invites_tenant_created
            ON public.invites(tenant_id, created_at);

        CREATE TABLE IF NOT EXISTS public.review_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID,
            doc_hash TEXT NOT NULL,
            text_raw TEXT NOT NULL,
            extraction JSONB NOT NULL,
            provenance JSONB,
            embedding JSONB,
            confidence_score DOUBLE PRECISION NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            reviewer_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ
        );
        UPDATE public.review_items
        SET tenant_id = '00000000-0000-0000-0000-000000000001'::uuid
        WHERE tenant_id IS NULL;
        ALTER TABLE public.review_items ALTER COLUMN tenant_id SET NOT NULL;
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'review_items_unique_content'
                  AND conrelid = 'public.review_items'::regclass
            ) THEN
                ALTER TABLE public.review_items
                    ADD CONSTRAINT review_items_unique_content
                    UNIQUE (tenant_id, doc_hash, text_raw);
            END IF;
        END $$;
        CREATE INDEX IF NOT EXISTS ix_review_items_status_created
            ON public.review_items(status, created_at);
        CREATE INDEX IF NOT EXISTS ix_review_items_tenant_status
            ON public.review_items(tenant_id, status);

        CREATE TABLE IF NOT EXISTS public.admin_mfa_recovery_codes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_mfa_recovery_codes_user
            ON public.admin_mfa_recovery_codes(user_id);

        CREATE TABLE IF NOT EXISTS public.password_reset_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) UNIQUE NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id
            ON public.password_reset_tokens(user_id);
        """
    )


def _create_missing_supplier_tables() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.supplier_facilities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            supplier_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            street TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            postal_code TEXT NOT NULL,
            fda_registration_number TEXT,
            roles JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS ix_supplier_facilities_tenant
            ON public.supplier_facilities(tenant_id);
        CREATE INDEX IF NOT EXISTS ix_supplier_facilities_user
            ON public.supplier_facilities(supplier_user_id);

        CREATE TABLE IF NOT EXISTS public.supplier_facility_ftl_categories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            facility_id UUID NOT NULL REFERENCES public.supplier_facilities(id) ON DELETE CASCADE,
            category_id TEXT NOT NULL,
            category_name TEXT NOT NULL,
            required_ctes JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_supplier_facility_ftl_category UNIQUE (facility_id, category_id)
        );
        CREATE INDEX IF NOT EXISTS ix_supplier_ftl_categories_tenant
            ON public.supplier_facility_ftl_categories(tenant_id);
        CREATE INDEX IF NOT EXISTS ix_supplier_ftl_categories_facility
            ON public.supplier_facility_ftl_categories(facility_id);

        CREATE TABLE IF NOT EXISTS public.supplier_traceability_lots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            supplier_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            facility_id UUID NOT NULL REFERENCES public.supplier_facilities(id) ON DELETE CASCADE,
            tlc_code TEXT NOT NULL,
            product_description TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            CONSTRAINT uq_supplier_tlc_per_tenant UNIQUE (tenant_id, tlc_code)
        );
        CREATE INDEX IF NOT EXISTS ix_supplier_tlcs_tenant
            ON public.supplier_traceability_lots(tenant_id);
        CREATE INDEX IF NOT EXISTS ix_supplier_tlcs_supplier
            ON public.supplier_traceability_lots(supplier_user_id);
        CREATE INDEX IF NOT EXISTS ix_supplier_tlcs_facility
            ON public.supplier_traceability_lots(facility_id);

        CREATE TABLE IF NOT EXISTS public.supplier_cte_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            supplier_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            facility_id UUID NOT NULL REFERENCES public.supplier_facilities(id) ON DELETE CASCADE,
            lot_id UUID NOT NULL REFERENCES public.supplier_traceability_lots(id) ON DELETE CASCADE,
            cte_type TEXT NOT NULL,
            event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            kde_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload_sha256 TEXT NOT NULL,
            merkle_prev_hash TEXT,
            merkle_hash TEXT NOT NULL,
            sequence_number BIGINT NOT NULL,
            obligation_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_supplier_cte_events_tenant_sequence
                UNIQUE (tenant_id, sequence_number)
        );
        CREATE INDEX IF NOT EXISTS ix_supplier_cte_events_tenant
            ON public.supplier_cte_events(tenant_id);
        CREATE INDEX IF NOT EXISTS ix_supplier_cte_events_facility
            ON public.supplier_cte_events(facility_id);
        CREATE INDEX IF NOT EXISTS ix_supplier_cte_events_lot
            ON public.supplier_cte_events(lot_id);

        CREATE TABLE IF NOT EXISTS public.supplier_funnel_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            supplier_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            facility_id UUID REFERENCES public.supplier_facilities(id) ON DELETE SET NULL,
            event_name TEXT NOT NULL,
            step TEXT,
            status TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_supplier_funnel_events_tenant
            ON public.supplier_funnel_events(tenant_id);
        CREATE INDEX IF NOT EXISTS ix_supplier_funnel_events_user
            ON public.supplier_funnel_events(supplier_user_id);
        CREATE INDEX IF NOT EXISTS ix_supplier_funnel_events_event
            ON public.supplier_funnel_events(event_name);
        CREATE INDEX IF NOT EXISTS ix_supplier_funnel_events_created
            ON public.supplier_funnel_events(created_at);

        ALTER TABLE public.supplier_facilities ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.supplier_facilities FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation_supplier_facilities
            ON public.supplier_facilities;
        CREATE POLICY tenant_isolation_supplier_facilities
            ON public.supplier_facilities
            FOR ALL
            USING (tenant_id = get_tenant_context())
            WITH CHECK (tenant_id = get_tenant_context());

        ALTER TABLE public.supplier_facility_ftl_categories ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.supplier_facility_ftl_categories FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation_supplier_ftl_categories
            ON public.supplier_facility_ftl_categories;
        CREATE POLICY tenant_isolation_supplier_ftl_categories
            ON public.supplier_facility_ftl_categories
            FOR ALL
            USING (tenant_id = get_tenant_context())
            WITH CHECK (tenant_id = get_tenant_context());

        ALTER TABLE public.supplier_traceability_lots ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.supplier_traceability_lots FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation_supplier_lots
            ON public.supplier_traceability_lots;
        CREATE POLICY tenant_isolation_supplier_lots
            ON public.supplier_traceability_lots
            FOR ALL
            USING (tenant_id = get_tenant_context())
            WITH CHECK (tenant_id = get_tenant_context());

        ALTER TABLE public.supplier_cte_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.supplier_cte_events FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation_supplier_cte_events
            ON public.supplier_cte_events;
        CREATE POLICY tenant_isolation_supplier_cte_events
            ON public.supplier_cte_events
            FOR ALL
            USING (tenant_id = get_tenant_context())
            WITH CHECK (tenant_id = get_tenant_context());

        ALTER TABLE public.supplier_funnel_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.supplier_funnel_events FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation_supplier_funnel_events
            ON public.supplier_funnel_events;
        CREATE POLICY tenant_isolation_supplier_funnel_events
            ON public.supplier_funnel_events
            FOR ALL
            USING (tenant_id = get_tenant_context())
            WITH CHECK (tenant_id = get_tenant_context());
        """
    )


def _normalize_audit_log_id() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.audit_logs (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            actor_id UUID,
            actor_email TEXT,
            actor_ip TEXT,
            actor_ua TEXT,
            event_type TEXT NOT NULL,
            event_category TEXT NOT NULL,
            action TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            resource_type TEXT,
            resource_id TEXT,
            endpoint TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            request_id UUID,
            prev_hash TEXT,
            integrity_hash TEXT NOT NULL
        );

        DO $$
        DECLARE
            id_udt TEXT;
        BEGIN
            SELECT udt_name INTO id_udt
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'audit_logs'
              AND column_name = 'id';

            IF id_udt = 'uuid' THEN
                PERFORM set_config('audit.allow_break_glass', 'true', true);

                ALTER TABLE public.audit_logs ADD COLUMN id_bigint BIGINT;
                WITH numbered AS (
                    SELECT ctid,
                           row_number() OVER (ORDER BY "timestamp", id::text) AS new_id
                    FROM public.audit_logs
                    WHERE id_bigint IS NULL
                )
                UPDATE public.audit_logs AS a
                SET id_bigint = numbered.new_id
                FROM numbered
                WHERE a.ctid = numbered.ctid;

                CREATE SEQUENCE IF NOT EXISTS public.audit_logs_id_seq AS BIGINT;
                PERFORM setval(
                    'public.audit_logs_id_seq',
                    COALESCE((SELECT max(id_bigint) FROM public.audit_logs), 0) + 1,
                    false
                );

                DROP INDEX IF EXISTS public.idx_audit_integrity;
                ALTER TABLE public.audit_logs DROP CONSTRAINT IF EXISTS audit_logs_pkey;
                ALTER TABLE public.audit_logs RENAME COLUMN id TO legacy_uuid;
                ALTER TABLE public.audit_logs RENAME COLUMN id_bigint TO id;
                ALTER TABLE public.audit_logs ALTER COLUMN id SET NOT NULL;
                ALTER TABLE public.audit_logs
                    ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq');
                ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;
                ALTER TABLE public.audit_logs ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);
                CREATE UNIQUE INDEX IF NOT EXISTS ix_audit_logs_legacy_uuid
                    ON public.audit_logs(legacy_uuid);
            END IF;
        END $$;

        ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS actor_ua TEXT;
        ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS severity TEXT DEFAULT 'info';
        ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS endpoint TEXT;
        ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS request_id UUID;
        ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS prev_hash TEXT;
        ALTER TABLE public.audit_logs ALTER COLUMN severity SET DEFAULT 'info';

        CREATE INDEX IF NOT EXISTS idx_audit_tenant_time
            ON public.audit_logs(tenant_id, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_event_type
            ON public.audit_logs(tenant_id, event_type);
        CREATE INDEX IF NOT EXISTS idx_audit_actor
            ON public.audit_logs(tenant_id, actor_id);
        CREATE INDEX IF NOT EXISTS idx_audit_resource
            ON public.audit_logs(tenant_id, resource_type, resource_id);
        CREATE INDEX IF NOT EXISTS idx_audit_integrity
            ON public.audit_logs(tenant_id, id, integrity_hash);
        """
    )
