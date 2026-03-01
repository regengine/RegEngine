-- Migration V31: FSMA 204 compliance infrastructure schema
-- Creates a dedicated schema for FSMA-native product, CTE, KDE, and recall tables.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS fsma;

-- ============================================
-- TENANT AND AUTH
-- ============================================

CREATE TABLE IF NOT EXISTS fsma.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'starter', 'professional', 'enterprise')),
    gln TEXT,
    fda_fei TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fsma.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES fsma.organizations(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member', 'supplier')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================
-- PRODUCT CATALOG (FTL-aligned)
-- ============================================

CREATE TABLE IF NOT EXISTS fsma.products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES fsma.organizations(id) ON DELETE CASCADE,
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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, gtin)
);

CREATE INDEX IF NOT EXISTS idx_fsma_products_org ON fsma.products(org_id);
CREATE INDEX IF NOT EXISTS idx_fsma_products_ftl ON fsma.products(ftl_covered) WHERE ftl_covered = true;

-- ============================================
-- SUPPLY CHAIN LOCATIONS
-- ============================================

CREATE TABLE IF NOT EXISTS fsma.locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES fsma.organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    gln TEXT,
    address JSONB,
    location_type TEXT NOT NULL CHECK (
        location_type IN (
            'farm',
            'ranch',
            'processor',
            'manufacturer',
            'distributor',
            'warehouse',
            'retailer',
            'restaurant',
            'transporter',
            'other'
        )
    ),
    fda_fei TEXT,
    contact JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, gln)
);

CREATE INDEX IF NOT EXISTS idx_fsma_locations_org ON fsma.locations(org_id);

-- ============================================
-- SUPPLIERS
-- ============================================

CREATE TABLE IF NOT EXISTS fsma.suppliers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES fsma.organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    gln TEXT,
    contact_email TEXT,
    compliance_score NUMERIC(5, 2) CHECK (compliance_score IS NULL OR (compliance_score >= 0 AND compliance_score <= 100)),
    last_assessed TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('active', 'pending', 'suspended', 'non_compliant')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fsma_suppliers_org ON fsma.suppliers(org_id);

-- ============================================
-- CRITICAL TRACKING EVENTS (CTEs)
-- ============================================

CREATE TABLE IF NOT EXISTS fsma.critical_tracking_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES fsma.organizations(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES fsma.products(id),
    lot_code TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'growing',
            'receiving',
            'transforming',
            'creating',
            'shipping',
            'initial_packing',
            'first_receiver'
        )
    ),
    epcis_event_type TEXT CHECK (epcis_event_type IN ('ObjectEvent', 'AggregationEvent', 'TransactionEvent', 'TransformationEvent')),
    epcis_action TEXT CHECK (epcis_action IN ('ADD', 'OBSERVE', 'DELETE')),
    epcis_biz_step TEXT,
    location_id UUID REFERENCES fsma.locations(id),
    event_time TIMESTAMPTZ NOT NULL,
    event_timezone TEXT NOT NULL DEFAULT 'UTC',
    record_date DATE NOT NULL,
    source_location_id UUID REFERENCES fsma.locations(id),
    dest_location_id UUID REFERENCES fsma.locations(id),
    quantity NUMERIC(12, 4),
    unit_of_measure TEXT,
    tlc TEXT NOT NULL,
    po_number TEXT,
    bol_number TEXT,
    data_source TEXT CHECK (data_source IN ('api', 'csv_upload', 'supplier_portal', 'manual', 'edi')),
    validation_status TEXT NOT NULL DEFAULT 'pending' CHECK (validation_status IN ('valid', 'pending', 'invalid', 'incomplete')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fsma_cte_org ON fsma.critical_tracking_events(org_id);
CREATE INDEX IF NOT EXISTS idx_fsma_cte_product ON fsma.critical_tracking_events(product_id);
CREATE INDEX IF NOT EXISTS idx_fsma_cte_lot ON fsma.critical_tracking_events(lot_code);
CREATE INDEX IF NOT EXISTS idx_fsma_cte_tlc ON fsma.critical_tracking_events(tlc);
CREATE INDEX IF NOT EXISTS idx_fsma_cte_event_time ON fsma.critical_tracking_events(event_time);
CREATE INDEX IF NOT EXISTS idx_fsma_cte_event_type ON fsma.critical_tracking_events(event_type);

-- ============================================
-- KEY DATA ELEMENTS (KDEs)
-- ============================================

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

-- ============================================
-- AUDIT LOG (append-only)
-- ============================================

CREATE TABLE IF NOT EXISTS fsma.audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES fsma.organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES fsma.users(id) ON DELETE SET NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('create', 'update', 'delete', 'export', 'verify')),
    changes JSONB,
    data_hash TEXT NOT NULL,
    prev_hash TEXT,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fsma_audit_org ON fsma.audit_log(org_id);
CREATE INDEX IF NOT EXISTS idx_fsma_audit_entity ON fsma.audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_fsma_audit_time ON fsma.audit_log(created_at);

-- ============================================
-- RECALL READINESS
-- ============================================

CREATE TABLE IF NOT EXISTS fsma.recall_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES fsma.organizations(id) ON DELETE CASCADE,
    data_completeness NUMERIC(5, 2) CHECK (data_completeness IS NULL OR (data_completeness >= 0 AND data_completeness <= 100)),
    response_time NUMERIC(5, 2) CHECK (response_time IS NULL OR (response_time >= 0 AND response_time <= 100)),
    supplier_coverage NUMERIC(5, 2) CHECK (supplier_coverage IS NULL OR (supplier_coverage >= 0 AND supplier_coverage <= 100)),
    product_coverage NUMERIC(5, 2) CHECK (product_coverage IS NULL OR (product_coverage >= 0 AND product_coverage <= 100)),
    chain_integrity NUMERIC(5, 2) CHECK (chain_integrity IS NULL OR (chain_integrity >= 0 AND chain_integrity <= 100)),
    export_readiness NUMERIC(5, 2) CHECK (export_readiness IS NULL OR (export_readiness >= 0 AND export_readiness <= 100)),
    overall_score NUMERIC(5, 2) GENERATED ALWAYS AS (
        (data_completeness + response_time + supplier_coverage + product_coverage + chain_integrity + export_readiness) / 6
    ) STORED,
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    assessed_by UUID REFERENCES fsma.users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_fsma_recall_org ON fsma.recall_assessments(org_id);

-- ============================================
-- COMPLIANCE SNAPSHOTS
-- ============================================

CREATE TABLE IF NOT EXISTS fsma.compliance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES fsma.organizations(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    overall_score NUMERIC(5, 2) CHECK (overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)),
    cte_coverage NUMERIC(5, 2) CHECK (cte_coverage IS NULL OR (cte_coverage >= 0 AND cte_coverage <= 100)),
    kde_completeness NUMERIC(5, 2) CHECK (kde_completeness IS NULL OR (kde_completeness >= 0 AND kde_completeness <= 100)),
    supplier_score NUMERIC(5, 2) CHECK (supplier_score IS NULL OR (supplier_score >= 0 AND supplier_score <= 100)),
    product_score NUMERIC(5, 2) CHECK (product_score IS NULL OR (product_score >= 0 AND product_score <= 100)),
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_fsma_snapshots_org_date ON fsma.compliance_snapshots(org_id, snapshot_date DESC);

-- ============================================
-- COMPLIANCE ALERTS
-- ============================================

CREATE TABLE IF NOT EXISTS fsma.compliance_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES fsma.organizations(id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL CHECK (
        alert_type IN (
            'missing_kde',
            'temperature_excursion',
            'deadline_approaching',
            'supplier_non_compliant',
            'chain_break',
            'export_failure'
        )
    ),
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'warning', 'info')),
    title TEXT NOT NULL,
    description TEXT,
    entity_type TEXT,
    entity_id UUID,
    resolved BOOLEAN NOT NULL DEFAULT false,
    resolved_at TIMESTAMPTZ,
    resolved_by UUID REFERENCES fsma.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fsma_alerts_org_unresolved ON fsma.compliance_alerts(org_id) WHERE resolved = false;

-- ============================================
-- RLS Helpers and Policies
-- ============================================

CREATE OR REPLACE FUNCTION fsma.current_org_id()
RETURNS UUID
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    org_setting TEXT;
BEGIN
    org_setting := current_setting('app.current_org_id', true);
    IF org_setting IS NULL OR org_setting = '' THEN
        RETURN NULL;
    END IF;
    RETURN org_setting::UUID;
END;
$$;

ALTER TABLE fsma.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.critical_tracking_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.key_data_elements ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.suppliers ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.recall_assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.compliance_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.compliance_alerts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS fsma_org_isolation_products ON fsma.products;
CREATE POLICY fsma_org_isolation_products ON fsma.products
    USING (org_id = fsma.current_org_id())
    WITH CHECK (org_id = fsma.current_org_id());

DROP POLICY IF EXISTS fsma_org_isolation_cte ON fsma.critical_tracking_events;
CREATE POLICY fsma_org_isolation_cte ON fsma.critical_tracking_events
    USING (org_id = fsma.current_org_id())
    WITH CHECK (org_id = fsma.current_org_id());

DROP POLICY IF EXISTS fsma_org_isolation_suppliers ON fsma.suppliers;
CREATE POLICY fsma_org_isolation_suppliers ON fsma.suppliers
    USING (org_id = fsma.current_org_id())
    WITH CHECK (org_id = fsma.current_org_id());

DROP POLICY IF EXISTS fsma_org_isolation_locations ON fsma.locations;
CREATE POLICY fsma_org_isolation_locations ON fsma.locations
    USING (org_id = fsma.current_org_id())
    WITH CHECK (org_id = fsma.current_org_id());

DROP POLICY IF EXISTS fsma_org_isolation_audit ON fsma.audit_log;
CREATE POLICY fsma_org_isolation_audit ON fsma.audit_log
    USING (org_id = fsma.current_org_id())
    WITH CHECK (org_id = fsma.current_org_id());

DROP POLICY IF EXISTS fsma_org_isolation_recall ON fsma.recall_assessments;
CREATE POLICY fsma_org_isolation_recall ON fsma.recall_assessments
    USING (org_id = fsma.current_org_id())
    WITH CHECK (org_id = fsma.current_org_id());

DROP POLICY IF EXISTS fsma_org_isolation_snapshots ON fsma.compliance_snapshots;
CREATE POLICY fsma_org_isolation_snapshots ON fsma.compliance_snapshots
    USING (org_id = fsma.current_org_id())
    WITH CHECK (org_id = fsma.current_org_id());

DROP POLICY IF EXISTS fsma_org_isolation_alerts ON fsma.compliance_alerts;
CREATE POLICY fsma_org_isolation_alerts ON fsma.compliance_alerts
    USING (org_id = fsma.current_org_id())
    WITH CHECK (org_id = fsma.current_org_id());

DROP POLICY IF EXISTS fsma_org_isolation_kdes ON fsma.key_data_elements;
CREATE POLICY fsma_org_isolation_kdes ON fsma.key_data_elements
    USING (
        EXISTS (
            SELECT 1
            FROM fsma.critical_tracking_events cte
            WHERE cte.id = cte_id
              AND cte.org_id = fsma.current_org_id()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM fsma.critical_tracking_events cte
            WHERE cte.id = cte_id
              AND cte.org_id = fsma.current_org_id()
        )
    );

-- ============================================
-- Hash Chain and Audit Trigger
-- ============================================

CREATE OR REPLACE FUNCTION fsma.compute_record_hash(
    entity_type TEXT,
    entity_id UUID,
    record_data JSONB,
    prev_hash TEXT DEFAULT NULL
) RETURNS TEXT
LANGUAGE sql
VOLATILE
AS $$
    SELECT encode(
        digest(
            convert_to(
                COALESCE(prev_hash, '0') || '|' ||
                entity_type || '|' ||
                entity_id::text || '|' ||
                record_data::text || '|' ||
                extract(epoch from now())::text,
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    );
$$;

CREATE OR REPLACE FUNCTION fsma.audit_cte_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    prev TEXT;
    data_hash TEXT;
BEGIN
    SELECT al.data_hash INTO prev
    FROM fsma.audit_log al
    WHERE al.entity_type = 'cte' AND al.entity_id = NEW.id
    ORDER BY al.created_at DESC
    LIMIT 1;

    data_hash := fsma.compute_record_hash('cte', NEW.id, to_jsonb(NEW), prev);

    INSERT INTO fsma.audit_log (org_id, entity_type, entity_id, action, changes, data_hash, prev_hash)
    VALUES (
        NEW.org_id,
        'cte',
        NEW.id,
        CASE WHEN TG_OP = 'INSERT' THEN 'create' ELSE 'update' END,
        CASE
            WHEN TG_OP = 'UPDATE' THEN jsonb_build_object('old', to_jsonb(OLD), 'new', to_jsonb(NEW))
            ELSE NULL
        END,
        data_hash,
        prev
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_cte ON fsma.critical_tracking_events;
CREATE TRIGGER trg_audit_cte
    AFTER INSERT OR UPDATE ON fsma.critical_tracking_events
    FOR EACH ROW
    EXECUTE FUNCTION fsma.audit_cte_changes();
