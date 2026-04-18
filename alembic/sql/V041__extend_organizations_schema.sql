-- V041: Extend organizations table with multi-tenant profile fields
-- Adds type, contact, and FEI number columns for proper tenant management

DO $$
BEGIN
    -- Add org type column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'organizations' AND column_name = 'type'
    ) THEN
        ALTER TABLE fsma.organizations
            ADD COLUMN type TEXT DEFAULT 'retailer'
            CHECK (type IN ('retailer', 'supplier', 'manufacturer', 'distributor', 'grower', 'importer'));
    END IF;

    -- Add contact fields
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'organizations' AND column_name = 'primary_contact'
    ) THEN
        ALTER TABLE fsma.organizations ADD COLUMN primary_contact TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'organizations' AND column_name = 'contact_email'
    ) THEN
        ALTER TABLE fsma.organizations ADD COLUMN contact_email TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'organizations' AND column_name = 'phone'
    ) THEN
        ALTER TABLE fsma.organizations ADD COLUMN phone TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'organizations' AND column_name = 'address'
    ) THEN
        ALTER TABLE fsma.organizations ADD COLUMN address TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsma' AND table_name = 'organizations' AND column_name = 'fei_number'
    ) THEN
        ALTER TABLE fsma.organizations ADD COLUMN fei_number TEXT;
    END IF;
END $$;

-- Index for FEI number lookups (FDA facility identifier)
CREATE INDEX IF NOT EXISTS idx_organizations_fei
    ON fsma.organizations (fei_number)
    WHERE fei_number IS NOT NULL;

-- Index for org type filtering
CREATE INDEX IF NOT EXISTS idx_organizations_type
    ON fsma.organizations (type);
