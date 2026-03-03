-- Migration V32: enforce tenant-scoped uniqueness for supplier CTE sequence numbers.

DO $$
BEGIN
    IF to_regclass('public.supplier_cte_events') IS NULL THEN
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_supplier_cte_events_tenant_sequence'
          AND conrelid = 'supplier_cte_events'::regclass
    ) THEN
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM supplier_cte_events
        GROUP BY tenant_id, sequence_number
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Cannot apply migration V32: duplicate (tenant_id, sequence_number) rows exist in supplier_cte_events';
    END IF;

    ALTER TABLE supplier_cte_events
        ADD CONSTRAINT uq_supplier_cte_events_tenant_sequence
        UNIQUE (tenant_id, sequence_number);
END $$;

DROP INDEX IF EXISTS ix_supplier_cte_events_sequence;
