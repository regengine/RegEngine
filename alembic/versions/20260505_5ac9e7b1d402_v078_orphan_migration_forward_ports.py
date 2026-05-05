"""v078 -- forward-port active orphan migration DDL.

Revision ID: 5ac9e7b1d402
Revises: f2c3d4e5a6b7
Create Date: 2026-05-05

Burns down the orphan migration allowlist (#2004). Dead Flyway/quarantined
files were deleted; active DDL from those files is folded into this Alembic
head with idempotent guards.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "5ac9e7b1d402"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "f2c3d4e5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    _core_admin_tables()
    _public_compliance_tables()
    _public_supplier_and_utility_tables()
    _authority_lineage_tables()
    _fsma_infrastructure_tables()
    _ingestion_schema_tables()
    _outbox_tables()
    _forward_port_quarantined_alembic()
    _rls_and_function_hardening()


def downgrade() -> None:
    """Non-destructive forward-port; leave data and tables in place."""
    pass


def _core_admin_tables() -> None:
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
        CREATE INDEX IF NOT EXISTS ix_sessions_refresh_token_hash ON public.sessions(refresh_token_hash);
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
        CREATE INDEX IF NOT EXISTS ix_invites_tenant_created ON public.invites(tenant_id, created_at);

        CREATE TABLE IF NOT EXISTS public.admin_mfa_recovery_codes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_mfa_recovery_codes_user
            ON public.admin_mfa_recovery_codes(user_id);
        DELETE FROM public.admin_mfa_recovery_codes
        WHERE code_hash NOT LIKE '$argon2%';

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

        CREATE TABLE IF NOT EXISTS public.api_keys (
            id SERIAL PRIMARY KEY,
            key_id VARCHAR(64) UNIQUE NOT NULL,
            key_hash VARCHAR(64) NOT NULL,
            key_prefix VARCHAR(12) NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            tenant_id UUID,
            partner_id VARCHAR(64),
            billing_tier VARCHAR(50),
            allowed_jurisdictions TEXT[] DEFAULT ARRAY[]::TEXT[],
            scopes TEXT[] DEFAULT ARRAY[]::TEXT[],
            rate_limit_per_minute INTEGER DEFAULT 60,
            rate_limit_per_hour INTEGER DEFAULT 1000,
            rate_limit_per_day INTEGER DEFAULT 10000,
            enabled BOOLEAN DEFAULT true NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            last_used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            created_by VARCHAR(36),
            revoked_by VARCHAR(36),
            revoke_reason TEXT,
            extra_data JSONB DEFAULT '{}'::jsonb,
            total_requests INTEGER DEFAULT 0
        );
        ALTER TABLE public.api_keys ADD COLUMN IF NOT EXISTS partner_id VARCHAR(64);
        ALTER TABLE public.api_keys ADD COLUMN IF NOT EXISTS extra_data JSONB DEFAULT '{}'::jsonb;
        ALTER TABLE public.api_keys ADD COLUMN IF NOT EXISTS total_requests INTEGER DEFAULT 0;
        CREATE UNIQUE INDEX IF NOT EXISTS ix_api_keys_key_id ON public.api_keys(key_id);
        CREATE INDEX IF NOT EXISTS ix_api_keys_key_hash ON public.api_keys(key_hash);
        CREATE INDEX IF NOT EXISTS ix_api_keys_tenant_enabled ON public.api_keys(tenant_id, enabled);
        CREATE INDEX IF NOT EXISTS ix_api_keys_partner_id
            ON public.api_keys(partner_id)
            WHERE partner_id IS NOT NULL;

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
        DELETE FROM public.review_items a
        USING public.review_items b
        WHERE a.id > b.id
          AND COALESCE(a.tenant_id, '00000000-0000-0000-0000-000000000001'::uuid)
              = COALESCE(b.tenant_id, '00000000-0000-0000-0000-000000000001'::uuid)
          AND a.doc_hash = b.doc_hash
          AND a.text_raw = b.text_raw;
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


def _public_compliance_tables() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'compliance_status_type') THEN
                CREATE TYPE compliance_status_type AS ENUM ('COMPLIANT', 'AT_RISK', 'NON_COMPLIANT');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_severity_type') THEN
                CREATE TYPE alert_severity_type AS ENUM ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_source_type') THEN
                CREATE TYPE alert_source_type AS ENUM (
                    'FDA_RECALL', 'FDA_WARNING_LETTER', 'FDA_IMPORT_ALERT',
                    'RETAILER_REQUEST', 'INTERNAL_AUDIT', 'MANUAL'
                );
            END IF;
        END $$;

        CREATE TABLE IF NOT EXISTS public.tenant_compliance_status (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL UNIQUE,
            status compliance_status_type NOT NULL DEFAULT 'COMPLIANT',
            last_status_change TIMESTAMPTZ NOT NULL DEFAULT now(),
            active_alert_count INTEGER NOT NULL DEFAULT 0,
            critical_alert_count INTEGER NOT NULL DEFAULT 0,
            completeness_score DOUBLE PRECISION DEFAULT 1.0,
            next_deadline TIMESTAMPTZ,
            next_deadline_description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS public.compliance_alerts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            source_type alert_source_type NOT NULL,
            source_id VARCHAR(255) NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            severity alert_severity_type NOT NULL DEFAULT 'MEDIUM',
            countdown_start TIMESTAMPTZ NOT NULL DEFAULT now(),
            countdown_end TIMESTAMPTZ NOT NULL,
            countdown_hours INTEGER NOT NULL DEFAULT 24,
            required_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
            acknowledged_at TIMESTAMPTZ,
            acknowledged_by VARCHAR(255),
            resolved_at TIMESTAMPTZ,
            resolved_by VARCHAR(255),
            resolution_notes TEXT,
            match_reason JSONB,
            raw_data JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, source_type, source_id)
        );

        CREATE TABLE IF NOT EXISTS public.compliance_status_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            previous_status compliance_status_type,
            new_status compliance_status_type NOT NULL,
            trigger_type VARCHAR(100) NOT NULL,
            trigger_alert_id UUID,
            trigger_description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS public.compliance_notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            alert_id UUID REFERENCES public.compliance_alerts(id),
            notification_type VARCHAR(50) NOT NULL,
            recipient VARCHAR(255) NOT NULL,
            subject TEXT,
            status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
            sent_at TIMESTAMPTZ,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS public.tenant_product_profile (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL UNIQUE,
            product_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
            supply_regions JSONB NOT NULL DEFAULT '[]'::jsonb,
            supplier_identifiers JSONB NOT NULL DEFAULT '[]'::jsonb,
            fda_product_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
            retailer_relationships JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_compliance_alerts_tenant_status
            ON public.compliance_alerts(tenant_id, status);
        CREATE INDEX IF NOT EXISTS idx_compliance_alerts_countdown
            ON public.compliance_alerts(countdown_end)
            WHERE status = 'ACTIVE';
        CREATE INDEX IF NOT EXISTS idx_compliance_alerts_severity
            ON public.compliance_alerts(severity, status);
        CREATE INDEX IF NOT EXISTS idx_compliance_status_log_tenant
            ON public.compliance_status_log(tenant_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_compliance_notifications_alert
            ON public.compliance_notifications(alert_id);

        CREATE OR REPLACE FUNCTION public.update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS update_tenant_compliance_status_updated_at
            ON public.tenant_compliance_status;
        CREATE TRIGGER update_tenant_compliance_status_updated_at
            BEFORE UPDATE ON public.tenant_compliance_status
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_compliance_alerts_updated_at
            ON public.compliance_alerts;
        CREATE TRIGGER update_compliance_alerts_updated_at
            BEFORE UPDATE ON public.compliance_alerts
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_tenant_product_profile_updated_at
            ON public.tenant_product_profile;
        CREATE TRIGGER update_tenant_product_profile_updated_at
            BEFORE UPDATE ON public.tenant_product_profile
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        CREATE OR REPLACE FUNCTION public.calculate_compliance_status(p_tenant_id UUID)
        RETURNS compliance_status_type AS $$
        DECLARE
            v_critical_count INTEGER;
            v_high_count INTEGER;
            v_total_active INTEGER;
        BEGIN
            SELECT
                COUNT(*) FILTER (WHERE severity = 'CRITICAL' AND status = 'ACTIVE'),
                COUNT(*) FILTER (WHERE severity = 'HIGH' AND status = 'ACTIVE'),
                COUNT(*) FILTER (WHERE status = 'ACTIVE')
            INTO v_critical_count, v_high_count, v_total_active
            FROM public.compliance_alerts
            WHERE tenant_id = p_tenant_id;

            IF v_critical_count > 0 THEN
                RETURN 'NON_COMPLIANT';
            ELSIF v_high_count > 0 OR v_total_active > 0 THEN
                RETURN 'AT_RISK';
            ELSE
                RETURN 'COMPLIANT';
            END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def _public_supplier_and_utility_tables() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.tool_leads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT NOT NULL UNIQUE,
            domain TEXT NOT NULL,
            company_name TEXT,
            first_tool_used TEXT,
            verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_tool_access TIMESTAMPTZ NOT NULL DEFAULT now(),
            access_count INTEGER NOT NULL DEFAULT 1,
            source_url TEXT,
            ip_country TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_tool_leads_domain ON public.tool_leads(domain);
        CREATE INDEX IF NOT EXISTS idx_tool_leads_verified_at ON public.tool_leads(verified_at);

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
        CREATE INDEX IF NOT EXISTS ix_supplier_facilities_tenant ON public.supplier_facilities(tenant_id);
        CREATE INDEX IF NOT EXISTS ix_supplier_facilities_user ON public.supplier_facilities(supplier_user_id);

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
        CREATE INDEX IF NOT EXISTS ix_supplier_tlcs_tenant ON public.supplier_traceability_lots(tenant_id);
        CREATE INDEX IF NOT EXISTS ix_supplier_tlcs_supplier ON public.supplier_traceability_lots(supplier_user_id);
        CREATE INDEX IF NOT EXISTS ix_supplier_tlcs_facility ON public.supplier_traceability_lots(facility_id);

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
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_supplier_cte_events_tenant_sequence'
                  AND conrelid = 'public.supplier_cte_events'::regclass
            ) THEN
                ALTER TABLE public.supplier_cte_events
                    ADD CONSTRAINT uq_supplier_cte_events_tenant_sequence
                    UNIQUE (tenant_id, sequence_number);
            END IF;
        END $$;
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

        CREATE TABLE IF NOT EXISTS public.sandbox_shares (
            id TEXT PRIMARY KEY,
            csv_text TEXT NOT NULL,
            result_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '30 days',
            ip_hash TEXT,
            view_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_sandbox_shares_expires
            ON public.sandbox_shares(expires_at);

        CREATE OR REPLACE FUNCTION public.cleanup_expired_sandbox_shares()
        RETURNS INTEGER AS $$
        DECLARE
            deleted_count INTEGER;
        BEGIN
            DELETE FROM public.sandbox_shares WHERE expires_at < now();
            GET DIAGNOSTICS deleted_count = ROW_COUNT;
            RETURN deleted_count;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def _authority_lineage_tables() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.pcos_authority_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            document_code VARCHAR(100) NOT NULL,
            document_name VARCHAR(255) NOT NULL,
            document_type VARCHAR(50) NOT NULL,
            issuer_name VARCHAR(255) NOT NULL,
            issuer_type VARCHAR(50),
            effective_date DATE NOT NULL,
            expiration_date DATE,
            supersedes_document_id UUID REFERENCES public.pcos_authority_documents(id),
            document_hash VARCHAR(64),
            hash_algorithm VARCHAR(20) DEFAULT 'SHA-256',
            original_file_path TEXT,
            content_type VARCHAR(100),
            file_size_bytes BIGINT,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            ingested_by UUID,
            extraction_method VARCHAR(50),
            extraction_notes TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            verified_at TIMESTAMPTZ,
            verified_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_authority_doc_code_tenant UNIQUE (tenant_id, document_code)
        );
        CREATE INDEX IF NOT EXISTS idx_authority_docs_tenant
            ON public.pcos_authority_documents(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_authority_docs_type
            ON public.pcos_authority_documents(document_type);
        CREATE INDEX IF NOT EXISTS idx_authority_docs_issuer
            ON public.pcos_authority_documents(issuer_name);
        CREATE INDEX IF NOT EXISTS idx_authority_docs_status
            ON public.pcos_authority_documents(status);
        CREATE INDEX IF NOT EXISTS idx_authority_docs_effective
            ON public.pcos_authority_documents(effective_date);

        CREATE TABLE IF NOT EXISTS public.pcos_extracted_facts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            authority_document_id UUID NOT NULL REFERENCES public.pcos_authority_documents(id) ON DELETE CASCADE,
            fact_key VARCHAR(100) NOT NULL,
            fact_category VARCHAR(50) NOT NULL,
            fact_name VARCHAR(255) NOT NULL,
            fact_description TEXT,
            fact_value_type VARCHAR(20) NOT NULL,
            fact_value_decimal NUMERIC(15, 4),
            fact_value_integer INTEGER,
            fact_value_string TEXT,
            fact_value_boolean BOOLEAN,
            fact_value_date DATE,
            fact_value_json JSONB,
            fact_unit VARCHAR(50),
            validity_conditions JSONB NOT NULL DEFAULT '{}'::jsonb,
            version INTEGER NOT NULL DEFAULT 1,
            previous_fact_id UUID REFERENCES public.pcos_extracted_facts(id),
            is_current BOOLEAN NOT NULL DEFAULT true,
            source_page INTEGER,
            source_section VARCHAR(255),
            source_quote TEXT,
            extraction_confidence NUMERIC(3, 2),
            extraction_method VARCHAR(50),
            extraction_notes TEXT,
            extracted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            extracted_by UUID,
            verified_at TIMESTAMPTZ,
            verified_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_fact_key_version UNIQUE (tenant_id, fact_key, version)
        );
        CREATE INDEX IF NOT EXISTS idx_extracted_facts_tenant
            ON public.pcos_extracted_facts(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_extracted_facts_authority
            ON public.pcos_extracted_facts(authority_document_id);
        CREATE INDEX IF NOT EXISTS idx_extracted_facts_key
            ON public.pcos_extracted_facts(fact_key);
        CREATE INDEX IF NOT EXISTS idx_extracted_facts_category
            ON public.pcos_extracted_facts(fact_category);
        CREATE INDEX IF NOT EXISTS idx_extracted_facts_current
            ON public.pcos_extracted_facts(tenant_id, fact_key, is_current)
            WHERE is_current = true;

        CREATE TABLE IF NOT EXISTS public.pcos_fact_citations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            citing_entity_type VARCHAR(50) NOT NULL,
            citing_entity_id UUID NOT NULL,
            extracted_fact_id UUID NOT NULL REFERENCES public.pcos_extracted_facts(id) ON DELETE CASCADE,
            fact_value_used TEXT NOT NULL,
            context_applied JSONB,
            citation_type VARCHAR(50) NOT NULL,
            citation_notes TEXT,
            evaluation_result VARCHAR(20),
            comparison_operator VARCHAR(20),
            input_value TEXT,
            cited_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_fact_citations_tenant
            ON public.pcos_fact_citations(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_fact_citations_entity
            ON public.pcos_fact_citations(citing_entity_type, citing_entity_id);
        CREATE INDEX IF NOT EXISTS idx_fact_citations_fact
            ON public.pcos_fact_citations(extracted_fact_id);
        """
    )


def _fsma_infrastructure_tables() -> None:
    op.execute(
        """
        CREATE SCHEMA IF NOT EXISTS fsma;

        CREATE TABLE IF NOT EXISTS fsma.organizations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            gln TEXT,
            fda_fei TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS fsma.products (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            tenant_id UUID,
            name TEXT NOT NULL,
            description TEXT,
            gtin TEXT,
            sku TEXT,
            fda_product_code TEXT,
            ftl_category TEXT,
            ftl_covered BOOLEAN NOT NULL DEFAULT false,
            ftl_exclusion TEXT,
            unit_of_measure TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        ALTER TABLE fsma.products ADD COLUMN IF NOT EXISTS tenant_id UUID;
        UPDATE fsma.products SET tenant_id = org_id WHERE tenant_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_fsma_products_tenant ON fsma.products(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_fsma_products_org ON fsma.products(org_id);
        CREATE INDEX IF NOT EXISTS idx_fsma_products_ftl
            ON fsma.products(ftl_covered)
            WHERE ftl_covered = true;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_fsma_products_tenant_gtin
            ON fsma.products(tenant_id, gtin)
            WHERE gtin IS NOT NULL AND gtin != '';

        CREATE TABLE IF NOT EXISTS fsma.locations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            tenant_id UUID,
            name TEXT NOT NULL,
            gln TEXT,
            address JSONB,
            location_type TEXT NOT NULL,
            fda_fei TEXT,
            contact JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        ALTER TABLE fsma.locations ADD COLUMN IF NOT EXISTS tenant_id UUID;
        UPDATE fsma.locations SET tenant_id = org_id WHERE tenant_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_fsma_locations_tenant ON fsma.locations(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_fsma_locations_org ON fsma.locations(org_id);

        CREATE TABLE IF NOT EXISTS fsma.suppliers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            tenant_id UUID,
            name TEXT NOT NULL,
            gln TEXT,
            contact_email TEXT,
            compliance_score NUMERIC(5, 2),
            last_assessed TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        ALTER TABLE fsma.suppliers ADD COLUMN IF NOT EXISTS tenant_id UUID;
        UPDATE fsma.suppliers SET tenant_id = org_id WHERE tenant_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_fsma_suppliers_tenant ON fsma.suppliers(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_fsma_suppliers_org ON fsma.suppliers(org_id);

        CREATE TABLE IF NOT EXISTS fsma.critical_tracking_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            tenant_id UUID,
            product_id UUID,
            lot_code TEXT NOT NULL,
            event_type TEXT NOT NULL,
            epcis_event_type TEXT,
            epcis_action TEXT,
            epcis_biz_step TEXT,
            location_id UUID,
            event_time TIMESTAMPTZ NOT NULL,
            event_timezone TEXT NOT NULL DEFAULT 'UTC',
            record_date DATE NOT NULL,
            source_location_id UUID,
            dest_location_id UUID,
            quantity NUMERIC(12, 4),
            unit_of_measure TEXT,
            tlc TEXT NOT NULL,
            po_number TEXT,
            bol_number TEXT,
            data_source TEXT,
            validation_status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        ALTER TABLE fsma.critical_tracking_events ADD COLUMN IF NOT EXISTS tenant_id UUID;
        UPDATE fsma.critical_tracking_events SET tenant_id = org_id WHERE tenant_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_fsma_cte_tenant ON fsma.critical_tracking_events(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_fsma_cte_org ON fsma.critical_tracking_events(org_id);
        CREATE INDEX IF NOT EXISTS idx_fsma_cte_product ON fsma.critical_tracking_events(product_id);
        CREATE INDEX IF NOT EXISTS idx_fsma_cte_lot ON fsma.critical_tracking_events(lot_code);
        CREATE INDEX IF NOT EXISTS idx_fsma_cte_tlc ON fsma.critical_tracking_events(tlc);
        CREATE INDEX IF NOT EXISTS idx_fsma_cte_event_time ON fsma.critical_tracking_events(event_time);
        CREATE INDEX IF NOT EXISTS idx_fsma_cte_event_type ON fsma.critical_tracking_events(event_type);

        CREATE TABLE IF NOT EXISTS fsma.key_data_elements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cte_id UUID NOT NULL REFERENCES fsma.critical_tracking_events(id) ON DELETE CASCADE,
            kde_type TEXT NOT NULL,
            kde_value TEXT NOT NULL,
            kde_unit TEXT,
            required BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_fsma_kde_cte ON fsma.key_data_elements(cte_id);

        CREATE TABLE IF NOT EXISTS fsma.audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            tenant_id UUID,
            user_id UUID,
            entity_type TEXT NOT NULL,
            entity_id UUID NOT NULL,
            action TEXT NOT NULL,
            changes JSONB,
            data_hash TEXT NOT NULL,
            prev_hash TEXT,
            ip_address INET,
            user_agent TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        ALTER TABLE fsma.audit_log ADD COLUMN IF NOT EXISTS tenant_id UUID;
        UPDATE fsma.audit_log SET tenant_id = org_id WHERE tenant_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_fsma_audit_log_tenant ON fsma.audit_log(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_fsma_audit_org ON fsma.audit_log(org_id);
        CREATE INDEX IF NOT EXISTS idx_fsma_audit_entity ON fsma.audit_log(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_fsma_audit_time ON fsma.audit_log(created_at);

        CREATE TABLE IF NOT EXISTS fsma.recall_assessments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            tenant_id UUID,
            data_completeness NUMERIC(5, 2),
            response_time NUMERIC(5, 2),
            supplier_coverage NUMERIC(5, 2),
            product_coverage NUMERIC(5, 2),
            chain_integrity NUMERIC(5, 2),
            export_readiness NUMERIC(5, 2),
            assessed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            assessed_by UUID
        );
        ALTER TABLE fsma.recall_assessments ADD COLUMN IF NOT EXISTS tenant_id UUID;
        UPDATE fsma.recall_assessments SET tenant_id = org_id WHERE tenant_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_fsma_recall_tenant ON fsma.recall_assessments(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_fsma_recall_org ON fsma.recall_assessments(org_id);

        CREATE TABLE IF NOT EXISTS fsma.compliance_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            tenant_id UUID,
            snapshot_date DATE NOT NULL,
            overall_score NUMERIC(5, 2),
            cte_coverage NUMERIC(5, 2),
            kde_completeness NUMERIC(5, 2),
            supplier_score NUMERIC(5, 2),
            product_score NUMERIC(5, 2),
            details JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        ALTER TABLE fsma.compliance_snapshots ADD COLUMN IF NOT EXISTS tenant_id UUID;
        UPDATE fsma.compliance_snapshots SET tenant_id = org_id WHERE tenant_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_fsma_snapshots_tenant_date
            ON fsma.compliance_snapshots(tenant_id, snapshot_date DESC);

        CREATE TABLE IF NOT EXISTS fsma.compliance_alerts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            tenant_id UUID,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            entity_type TEXT,
            entity_id UUID,
            resolved BOOLEAN NOT NULL DEFAULT false,
            resolved_at TIMESTAMPTZ,
            resolved_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        ALTER TABLE fsma.compliance_alerts ADD COLUMN IF NOT EXISTS tenant_id UUID;
        UPDATE fsma.compliance_alerts SET tenant_id = org_id WHERE tenant_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_fsma_alerts_tenant_unresolved
            ON fsma.compliance_alerts(tenant_id)
            WHERE resolved = false;
        """
    )


def _ingestion_schema_tables() -> None:
    op.execute(
        """
        CREATE SCHEMA IF NOT EXISTS ingestion;

        CREATE TABLE IF NOT EXISTS ingestion.documents (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL,
            title TEXT NOT NULL,
            source_type VARCHAR(50) NOT NULL,
            document_type VARCHAR(50) NOT NULL,
            vertical VARCHAR(50) NOT NULL,
            content_sha256 VARCHAR(64) NOT NULL UNIQUE,
            content_sha512 VARCHAR(128) NOT NULL,
            text_sha256 VARCHAR(64),
            text_sha512 VARCHAR(128),
            source_url TEXT NOT NULL,
            fetch_timestamp TIMESTAMPTZ NOT NULL,
            http_status INTEGER,
            etag TEXT,
            last_modified TIMESTAMPTZ,
            effective_date DATE,
            publication_date TIMESTAMPTZ,
            agencies TEXT[],
            cfr_references TEXT[],
            keywords TEXT[],
            text_length INTEGER DEFAULT 0,
            content_length INTEGER DEFAULT 0,
            content_type VARCHAR(100),
            storage_key TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS ingestion.jobs (
            job_id UUID PRIMARY KEY,
            tenant_id UUID,
            vertical VARCHAR(50) NOT NULL,
            source_type VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            documents_processed INTEGER DEFAULT 0,
            documents_succeeded INTEGER DEFAULT 0,
            documents_failed INTEGER DEFAULT 0,
            documents_skipped INTEGER DEFAULT 0,
            config JSONB,
            error_message TEXT,
            error_details JSONB
        );

        CREATE TABLE IF NOT EXISTS ingestion.audit_log (
            id BIGSERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            job_id UUID NOT NULL,
            action VARCHAR(50) NOT NULL,
            resource_type VARCHAR(50) NOT NULL,
            resource_id TEXT,
            status VARCHAR(20) NOT NULL,
            details JSONB,
            error TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_documents_tenant ON ingestion.documents(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_documents_vertical ON ingestion.documents(vertical);
        CREATE INDEX IF NOT EXISTS idx_documents_source_type ON ingestion.documents(source_type);
        CREATE INDEX IF NOT EXISTS idx_documents_created_at ON ingestion.documents(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_documents_content_sha256 ON ingestion.documents(content_sha256);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON ingestion.jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON ingestion.jobs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_vertical ON ingestion.jobs(vertical);
        CREATE INDEX IF NOT EXISTS idx_audit_log_job_id ON ingestion.audit_log(job_id);
        CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON ingestion.audit_log(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_log_action ON ingestion.audit_log(action);
        CREATE INDEX IF NOT EXISTS idx_documents_title_search
            ON ingestion.documents USING gin(to_tsvector('english', title));
        """
    )


def _outbox_tables() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.graph_outbox (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID,
            operation TEXT NOT NULL,
            cypher TEXT NOT NULL,
            params JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 10,
            last_error TEXT,
            enqueued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            drained_at TIMESTAMPTZ,
            next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            dedupe_key TEXT
        );
        DELETE FROM public.graph_outbox a
        USING public.graph_outbox b
        WHERE a.id > b.id
          AND a.operation = b.operation
          AND a.dedupe_key IS NOT NULL
          AND a.dedupe_key = b.dedupe_key;
        DROP INDEX IF EXISTS public.uq_graph_outbox_dedupe;
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_graph_outbox_dedupe'
                  AND conrelid = 'public.graph_outbox'::regclass
            ) THEN
                ALTER TABLE public.graph_outbox
                    ADD CONSTRAINT uq_graph_outbox_dedupe
                    UNIQUE (operation, dedupe_key);
            END IF;
        END $$;
        CREATE INDEX IF NOT EXISTS idx_graph_outbox_pending
            ON public.graph_outbox(next_attempt_at ASC, id ASC)
            WHERE status = 'pending';
        CREATE INDEX IF NOT EXISTS idx_graph_outbox_tenant_status
            ON public.graph_outbox(tenant_id, status);

        CREATE TABLE IF NOT EXISTS public.webhook_outbox (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL,
            event_type TEXT NOT NULL,
            target_url TEXT NOT NULL,
            payload JSONB NOT NULL,
            dedupe_key TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 10,
            last_error TEXT,
            last_status_code INTEGER,
            enqueued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            delivered_at TIMESTAMPTZ,
            next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        DELETE FROM public.webhook_outbox a
        USING public.webhook_outbox b
        WHERE a.id > b.id
          AND a.event_type = b.event_type
          AND a.dedupe_key IS NOT NULL
          AND a.dedupe_key = b.dedupe_key;
        DROP INDEX IF EXISTS public.uq_webhook_outbox_dedupe;
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_webhook_outbox_dedupe'
                  AND conrelid = 'public.webhook_outbox'::regclass
            ) THEN
                ALTER TABLE public.webhook_outbox
                    ADD CONSTRAINT uq_webhook_outbox_dedupe
                    UNIQUE (event_type, dedupe_key);
            END IF;
        END $$;
        CREATE INDEX IF NOT EXISTS idx_webhook_outbox_pending
            ON public.webhook_outbox(next_attempt_at ASC, id ASC)
            WHERE status = 'pending';
        CREATE INDEX IF NOT EXISTS idx_webhook_outbox_tenant_status
            ON public.webhook_outbox(tenant_id, status);
        """
    )


def _forward_port_quarantined_alembic() -> None:
    _cte_kdes_jsonb()
    _identity_resolution_forward_ports()
    _fda_export_fingerprint()
    _cte_append_only_triggers()


def _cte_kdes_jsonb() -> None:
    op.execute(
        """
        DO $mig$
        DECLARE
            col_type text;
        BEGIN
            SELECT data_type INTO col_type
            FROM information_schema.columns
            WHERE table_schema = 'fsma'
              AND table_name   = 'cte_kdes'
              AND column_name  = 'kde_value';

            IF col_type IS NULL OR col_type = 'jsonb' THEN
                RETURN;
            END IF;

            CREATE TABLE IF NOT EXISTS fsma.cte_kdes_backfill_log_v059 (
                cte_event_id UUID,
                kde_key TEXT,
                original TEXT,
                converted JSONB,
                reason TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            ALTER TABLE fsma.cte_kdes ADD COLUMN IF NOT EXISTS kde_value_jsonb jsonb;

            DECLARE
                rec RECORD;
                converted jsonb;
                reason text;
            BEGIN
                FOR rec IN SELECT cte_event_id, kde_key, kde_value FROM fsma.cte_kdes LOOP
                    converted := NULL;
                    reason := NULL;

                    IF rec.kde_value IS NULL OR rec.kde_value = '' THEN
                        converted := 'null'::jsonb;
                    ELSE
                        BEGIN
                            converted := rec.kde_value::jsonb;
                        EXCEPTION WHEN others THEN
                            converted := NULL;
                        END;

                        IF converted IS NULL THEN
                            DECLARE
                                candidate text;
                            BEGIN
                                candidate := rec.kde_value;
                                candidate := replace(candidate, 'None', 'null');
                                candidate := replace(candidate, 'True', 'true');
                                candidate := replace(candidate, 'False', 'false');
                                candidate := replace(candidate, '''', '"');
                                BEGIN
                                    converted := candidate::jsonb;
                                    reason := 'python-repr-heuristic';
                                EXCEPTION WHEN others THEN
                                    converted := to_jsonb(rec.kde_value);
                                    reason := 'unparseable-wrapped-as-string';
                                END;
                            END;
                        END IF;
                    END IF;

                    UPDATE fsma.cte_kdes
                    SET kde_value_jsonb = converted
                    WHERE cte_event_id = rec.cte_event_id
                      AND kde_key = rec.kde_key;

                    IF reason IS NOT NULL THEN
                        INSERT INTO fsma.cte_kdes_backfill_log_v059 (
                            cte_event_id, kde_key, original, converted, reason
                        ) VALUES (
                            rec.cte_event_id, rec.kde_key, rec.kde_value, converted, reason
                        );
                    END IF;
                END LOOP;
            END;

            ALTER TABLE fsma.cte_kdes DROP COLUMN kde_value;
            ALTER TABLE fsma.cte_kdes RENAME COLUMN kde_value_jsonb TO kde_value;
        END
        $mig$;
        """
    )


def _identity_resolution_forward_ports() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            dup_record RECORD;
            survivor_alias_id UUID;
        BEGIN
            IF to_regclass('fsma.entity_aliases') IS NULL THEN
                RETURN;
            END IF;

            FOR dup_record IN
                SELECT tenant_id, alias_type, alias_value, COUNT(*) AS dup_count
                FROM fsma.entity_aliases
                GROUP BY tenant_id, alias_type, alias_value
                HAVING COUNT(*) > 1
            LOOP
                SELECT alias_id
                INTO survivor_alias_id
                FROM fsma.entity_aliases
                WHERE tenant_id = dup_record.tenant_id
                  AND alias_type = dup_record.alias_type
                  AND alias_value = dup_record.alias_value
                ORDER BY created_at ASC NULLS LAST, alias_id ASC
                LIMIT 1;

                DELETE FROM fsma.entity_aliases
                WHERE tenant_id = dup_record.tenant_id
                  AND alias_type = dup_record.alias_type
                  AND alias_value = dup_record.alias_value
                  AND alias_id <> survivor_alias_id;
            END LOOP;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uniq_entity_aliases_tenant_type_value'
                  AND conrelid = 'fsma.entity_aliases'::regclass
            ) THEN
                ALTER TABLE fsma.entity_aliases
                    ADD CONSTRAINT uniq_entity_aliases_tenant_type_value
                    UNIQUE (tenant_id, alias_type, alias_value);
            END IF;

            CREATE INDEX IF NOT EXISTS idx_entity_aliases_tlc_prefix
                ON fsma.entity_aliases(tenant_id, alias_value)
                WHERE alias_type = 'tlc_prefix';
        END $$;

        DO $$
        DECLARE
            _constraint_name text;
        BEGIN
            IF to_regclass('fsma.identity_review_queue') IS NULL THEN
                RETURN;
            END IF;

            ALTER TABLE fsma.identity_review_queue
                ADD COLUMN IF NOT EXISTS previous_review_id UUID
                REFERENCES fsma.identity_review_queue(review_id)
                ON DELETE SET NULL;

            SELECT c.conname INTO _constraint_name
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'fsma'
              AND t.relname = 'identity_review_queue'
              AND c.contype = 'u'
              AND c.conkey @> (
                  SELECT ARRAY(
                      SELECT a.attnum FROM pg_attribute a
                      WHERE a.attrelid = t.oid
                        AND a.attname IN ('entity_a_id', 'entity_b_id')
                  )
              )
            LIMIT 1;

            IF _constraint_name IS NOT NULL THEN
                EXECUTE format(
                    'ALTER TABLE fsma.identity_review_queue DROP CONSTRAINT %I',
                    _constraint_name
                );
            END IF;

            DROP INDEX IF EXISTS fsma.uq_identity_review_open_pair;
            CREATE UNIQUE INDEX uq_identity_review_open_pair
                ON fsma.identity_review_queue(entity_a_id, entity_b_id)
                WHERE status IN ('pending', 'deferred');
        END $$;

        DO $$
        BEGIN
            IF to_regclass('fsma.entity_merge_history') IS NULL THEN
                RETURN;
            END IF;
            ALTER TABLE fsma.entity_merge_history
                ADD COLUMN IF NOT EXISTS alias_snapshot JSONB;
        END $$;
        """
    )


def _fda_export_fingerprint() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.fda_export_log') IS NULL THEN
                RETURN;
            END IF;

            ALTER TABLE fsma.fda_export_log
                ADD COLUMN IF NOT EXISTS export_fingerprint TEXT;

            CREATE UNIQUE INDEX IF NOT EXISTS idx_export_log_tenant_fingerprint
                ON fsma.fda_export_log(tenant_id, export_fingerprint)
                WHERE export_fingerprint IS NOT NULL;
        END $$;
        """
    )


def _cte_append_only_triggers() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.prevent_cte_mutation()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('fsma.allow_mutation', true) = 'true' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION
                'CTE records are append-only (FDA 21 CFR 1.1455). Set fsma.allow_mutation=true for authorized corrections. Table: %, Operation: %',
                TG_TABLE_NAME, TG_OP;
        END;
        $$;

        DO $$
        BEGIN
            IF to_regclass('fsma.cte_events') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS cte_events_append_only ON fsma.cte_events;
                CREATE TRIGGER cte_events_append_only
                    BEFORE UPDATE OR DELETE ON fsma.cte_events
                    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_cte_mutation();
            END IF;

            IF to_regclass('fsma.hash_chain') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS chain_immutability ON fsma.hash_chain;
                DROP TRIGGER IF EXISTS hash_chain_append_only ON fsma.hash_chain;
                CREATE TRIGGER hash_chain_append_only
                    BEFORE UPDATE OR DELETE ON fsma.hash_chain
                    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_cte_mutation();
            END IF;
        END $$;
        """
    )


def _rls_and_function_hardening() -> None:
    op.execute(
        """
        CREATE SCHEMA IF NOT EXISTS audit;
        CREATE TABLE IF NOT EXISTS audit.rls_policy_restoration_log (
            id BIGSERIAL PRIMARY KEY,
            schema_name TEXT NOT NULL,
            table_name TEXT NOT NULL,
            policy_name TEXT NOT NULL,
            restored_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE OR REPLACE FUNCTION audit.log_sysadmin_access()
        RETURNS TRIGGER AS $fn$
        BEGIN
            IF current_setting('regengine.is_sysadmin', true) = 'true'
               AND current_user = 'regengine_sysadmin' THEN
                INSERT INTO audit.sysadmin_access_log (table_name, operation, connection_info)
                VALUES (
                    TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
                    TG_OP,
                    jsonb_build_object(
                        'current_user', current_user,
                        'session_user', session_user,
                        'client_addr', inet_client_addr()::TEXT,
                        'application_name', current_setting('application_name', true),
                        'backend_pid', pg_backend_pid()
                    )
                );
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $fn$ LANGUAGE plpgsql SECURITY DEFINER
           SET search_path = pg_catalog, audit;
        """
    )
    _tenant_rls("public.roles", "tenant_id", "tenant_isolation_roles")
    _tenant_rls("public.memberships", "tenant_id", "tenant_isolation_memberships")
    _tenant_rls("public.invites", "tenant_id", "tenant_isolation_invites")
    _tenant_rls("public.review_items", "tenant_id", "tenant_isolation_review_items")
    _tenant_rls("public.tenant_compliance_status", "tenant_id", "tenant_isolation_compliance_status")
    _tenant_rls("public.compliance_alerts", "tenant_id", "tenant_isolation_compliance_alerts")
    _tenant_rls("public.compliance_status_log", "tenant_id", "tenant_isolation_compliance_status_log")
    _tenant_rls("public.compliance_notifications", "tenant_id", "tenant_isolation_compliance_notifications")
    _tenant_rls("public.tenant_product_profile", "tenant_id", "tenant_isolation_product_profile")
    _tenant_rls("public.audit_logs", "tenant_id", "tenant_isolation_audit_logs")
    _tenant_rls("public.supplier_facilities", "tenant_id", "tenant_isolation_supplier_facilities")
    _tenant_rls("public.supplier_facility_ftl_categories", "tenant_id", "tenant_isolation_supplier_ftl_categories")
    _tenant_rls("public.supplier_traceability_lots", "tenant_id", "tenant_isolation_supplier_lots")
    _tenant_rls("public.supplier_cte_events", "tenant_id", "tenant_isolation_supplier_cte_events")
    _tenant_rls("public.supplier_funnel_events", "tenant_id", "tenant_isolation_supplier_funnel_events")
    _tenant_rls("public.pcos_authority_documents", "tenant_id", "tenant_isolation_authority_documents")
    _tenant_rls("public.pcos_extracted_facts", "tenant_id", "tenant_isolation_extracted_facts")
    _tenant_rls("public.pcos_fact_citations", "tenant_id", "tenant_isolation_fact_citations")
    _tenant_rls("fsma.products", "tenant_id", "tenant_isolation_products")
    _tenant_rls("fsma.locations", "tenant_id", "tenant_isolation_locations")
    _tenant_rls("fsma.suppliers", "tenant_id", "tenant_isolation_suppliers")
    _tenant_rls("fsma.critical_tracking_events", "tenant_id", "tenant_isolation_cte")
    _tenant_rls("fsma.audit_log", "tenant_id", "tenant_isolation_audit_log")
    _tenant_rls("fsma.recall_assessments", "tenant_id", "tenant_isolation_recall")
    _tenant_rls("fsma.compliance_snapshots", "tenant_id", "tenant_isolation_snapshots")
    _tenant_rls("fsma.compliance_alerts", "tenant_id", "tenant_isolation_alerts")
    _outbox_rls()
    _api_keys_rls()
    _tenant_root_rls()
    _user_and_session_rls()
    _audit_append_only()


def _tenant_rls(table: str, column: str, policy: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('{table}') IS NULL THEN
                RETURN;
            END IF;
            EXECUTE 'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE {table} FORCE ROW LEVEL SECURITY';
            EXECUTE 'DROP POLICY IF EXISTS {policy} ON {table}';
            EXECUTE 'CREATE POLICY {policy} ON {table}
                FOR ALL
                USING ({column} = get_tenant_context())
                WITH CHECK ({column} = get_tenant_context())';
        END $$;
        """
    )


def _api_keys_rls() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.api_keys') IS NULL THEN
                RETURN;
            END IF;
            ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;
            ALTER TABLE public.api_keys FORCE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS tenant_isolation_api_keys ON public.api_keys;
            CREATE POLICY tenant_isolation_api_keys ON public.api_keys
                FOR ALL
                USING (
                    tenant_id IS NULL
                    OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
                    OR (
                        current_user = 'regengine_sysadmin'
                        AND current_setting('regengine.is_sysadmin', true) = 'true'
                    )
                )
                WITH CHECK (
                    tenant_id IS NULL
                    OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
                    OR (
                        current_user = 'regengine_sysadmin'
                        AND current_setting('regengine.is_sysadmin', true) = 'true'
                    )
                );
        END $$;
        """
    )


def _tenant_root_rls() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.tenants') IS NULL THEN
                RETURN;
            END IF;
            ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
            ALTER TABLE public.tenants FORCE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS tenants_read_all ON public.tenants;
            CREATE POLICY tenants_read_all ON public.tenants FOR SELECT USING (true);
            DROP POLICY IF EXISTS tenants_write_own ON public.tenants;
            CREATE POLICY tenants_write_own ON public.tenants
                FOR UPDATE USING (id = get_tenant_context())
                WITH CHECK (id = get_tenant_context());
        END $$;
        """
    )


def _user_and_session_rls() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.users') IS NOT NULL THEN
                ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.users FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS user_self_isolation ON public.users;
                CREATE POLICY user_self_isolation ON public.users
                    FOR ALL
                    USING (
                        id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
                        OR (
                            current_user = 'regengine_sysadmin'
                            AND current_setting('regengine.is_sysadmin', true) = 'true'
                        )
                    )
                    WITH CHECK (
                        id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
                        OR (
                            current_user = 'regengine_sysadmin'
                            AND current_setting('regengine.is_sysadmin', true) = 'true'
                        )
                    );
            END IF;

            IF to_regclass('public.sessions') IS NOT NULL THEN
                ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.sessions FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS sessions_user_isolation ON public.sessions;
                CREATE POLICY sessions_user_isolation ON public.sessions
                    FOR ALL
                    USING (
                        user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
                        OR (
                            current_user = 'regengine_sysadmin'
                            AND current_setting('regengine.is_sysadmin', true) = 'true'
                        )
                    )
                    WITH CHECK (
                        user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
                        OR (
                            current_user = 'regengine_sysadmin'
                            AND current_setting('regengine.is_sysadmin', true) = 'true'
                        )
                    );
            END IF;
        END $$;
        """
    )


def _audit_append_only() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.prevent_audit_modification()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('audit.allow_break_glass', true) = 'true' THEN
                RAISE WARNING
                    'audit_logs modification via break-glass. op=% user=% row_id=%',
                    TG_OP, current_user, COALESCE(NEW.id::text, OLD.id::text);
                RETURN COALESCE(NEW, OLD);
            END IF;
            RAISE EXCEPTION
                'audit_logs is append-only (ISO 27001 12.4.2). Operation % rejected.',
                TG_OP
                USING ERRCODE = 'check_violation';
        END;
        $$;

        DO $$
        BEGIN
            IF to_regclass('public.audit_logs') IS NULL THEN
                RETURN;
            END IF;
            DROP TRIGGER IF EXISTS audit_no_update ON public.audit_logs;
            DROP TRIGGER IF EXISTS audit_no_delete ON public.audit_logs;
            DROP TRIGGER IF EXISTS audit_append_only ON public.audit_logs;
            CREATE TRIGGER audit_append_only
                BEFORE UPDATE OR DELETE ON public.audit_logs
                FOR EACH ROW EXECUTE FUNCTION public.prevent_audit_modification();
            REVOKE UPDATE, DELETE, TRUNCATE ON public.audit_logs FROM PUBLIC;
        END $$;
        """
    )


def _outbox_rls() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.graph_outbox') IS NOT NULL THEN
                ALTER TABLE public.graph_outbox ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_graph_outbox ON public.graph_outbox;
                CREATE POLICY tenant_isolation_graph_outbox ON public.graph_outbox
                    USING (
                        tenant_id IS NULL
                        OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
                        OR (
                            current_user = 'regengine_sysadmin'
                            AND current_setting('regengine.is_sysadmin', true) = 'true'
                        )
                    );
            END IF;

            IF to_regclass('public.webhook_outbox') IS NOT NULL THEN
                ALTER TABLE public.webhook_outbox ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_webhook_outbox ON public.webhook_outbox;
                CREATE POLICY tenant_isolation_webhook_outbox ON public.webhook_outbox
                    USING (
                        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
                        OR (
                            current_user = 'regengine_sysadmin'
                            AND current_setting('regengine.is_sysadmin', true) = 'true'
                        )
                    );
            END IF;
        END $$;
        """
    )
