-- V39: Create supplier portal tables
--
-- These tables back the SupplierFacilityModel, SupplierFacilityFTLCategoryModel,
-- and SupplierTraceabilityLotModel ORM models in sqlalchemy_models.py.
-- Previously they were defined in the ORM but had no corresponding migration.

-- 1. Supplier-operated facilities
CREATE TABLE IF NOT EXISTS supplier_facilities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    supplier_user_id UUID NOT NULL REFERENCES users(id),
    name            TEXT NOT NULL,
    street          TEXT NOT NULL,
    city            TEXT NOT NULL,
    state           TEXT NOT NULL,
    postal_code     TEXT NOT NULL,
    fda_registration_number TEXT,
    roles           JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_supplier_facilities_tenant ON supplier_facilities(tenant_id);
CREATE INDEX IF NOT EXISTS ix_supplier_facilities_user   ON supplier_facilities(supplier_user_id);

-- RLS
ALTER TABLE supplier_facilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_facilities FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_supplier_facilities ON supplier_facilities;
CREATE POLICY tenant_isolation_supplier_facilities ON supplier_facilities
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid)
    WITH CHECK (tenant_id = get_tenant_context()::uuid);


-- 2. FTL category assignments scoped to supplier facilities
CREATE TABLE IF NOT EXISTS supplier_facility_ftl_categories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    facility_id     UUID NOT NULL REFERENCES supplier_facilities(id) ON DELETE CASCADE,
    category_id     TEXT NOT NULL,
    category_name   TEXT NOT NULL,
    required_ctes   JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_supplier_facility_ftl_category UNIQUE (facility_id, category_id)
);

CREATE INDEX IF NOT EXISTS ix_supplier_ftl_categories_tenant   ON supplier_facility_ftl_categories(tenant_id);
CREATE INDEX IF NOT EXISTS ix_supplier_ftl_categories_facility ON supplier_facility_ftl_categories(facility_id);

-- RLS
ALTER TABLE supplier_facility_ftl_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_facility_ftl_categories FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_supplier_ftl_categories ON supplier_facility_ftl_categories;
CREATE POLICY tenant_isolation_supplier_ftl_categories ON supplier_facility_ftl_categories
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid)
    WITH CHECK (tenant_id = get_tenant_context()::uuid);


-- 3. Supplier-managed traceability lots (TLCs)
CREATE TABLE IF NOT EXISTS supplier_traceability_lots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    supplier_user_id UUID NOT NULL REFERENCES users(id),
    facility_id     UUID NOT NULL REFERENCES supplier_facilities(id) ON DELETE CASCADE,
    tlc_code        TEXT NOT NULL,
    product_description TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ,

    CONSTRAINT uq_supplier_tlc_per_tenant UNIQUE (tenant_id, tlc_code)
);

CREATE INDEX IF NOT EXISTS ix_supplier_tlcs_tenant   ON supplier_traceability_lots(tenant_id);
CREATE INDEX IF NOT EXISTS ix_supplier_tlcs_supplier ON supplier_traceability_lots(supplier_user_id);
CREATE INDEX IF NOT EXISTS ix_supplier_tlcs_facility ON supplier_traceability_lots(facility_id);

-- RLS
ALTER TABLE supplier_traceability_lots ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_traceability_lots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_supplier_lots ON supplier_traceability_lots;
CREATE POLICY tenant_isolation_supplier_lots ON supplier_traceability_lots
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid)
    WITH CHECK (tenant_id = get_tenant_context()::uuid);
