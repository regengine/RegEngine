"""Schema additions — transformation_links, growing CTE type, tenant seeding function

Consolidates raw SQL migrations:
  - V049: fsma.transformation_links adjacency table (lot-to-lot traceability)
  - V053: Add 'growing' to traceability_events event_type CHECK
  - V055: seed_obligations_for_tenant() function

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-04-15
"""
from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ================================================================
    # Part 1: V049 — transformation_links adjacency table
    # ================================================================

    op.execute("""
        CREATE TABLE IF NOT EXISTS fsma.transformation_links (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id               TEXT NOT NULL,
            transformation_event_id UUID NOT NULL,
            input_tlc               TEXT NOT NULL,
            input_event_id          UUID,
            output_tlc              TEXT NOT NULL,
            output_event_id         UUID,
            input_quantity          NUMERIC,
            input_unit              TEXT,
            output_quantity         NUMERIC,
            output_unit             TEXT,
            process_type            TEXT,
            confidence_score        NUMERIC DEFAULT 1.0,
            link_source             TEXT DEFAULT 'explicit',
            notes                   TEXT,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, transformation_event_id, input_tlc, output_tlc)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tl_input_tlc
            ON fsma.transformation_links (tenant_id, input_tlc)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tl_output_tlc
            ON fsma.transformation_links (tenant_id, output_tlc)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tl_event
            ON fsma.transformation_links (transformation_event_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tl_tenant
            ON fsma.transformation_links (tenant_id)
    """)

    op.execute("ALTER TABLE fsma.transformation_links ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.transformation_links FORCE ROW LEVEL SECURITY")

    # ================================================================
    # Part 2: V053 — Add 'growing' to event_type CHECK constraint
    # ================================================================

    op.execute("""
        ALTER TABLE fsma.traceability_events
            DROP CONSTRAINT IF EXISTS traceability_events_event_type_check
    """)
    op.execute("""
        ALTER TABLE fsma.traceability_events
            ADD CONSTRAINT traceability_events_event_type_check
            CHECK (event_type IN (
                'growing', 'harvesting', 'cooling', 'initial_packing',
                'first_land_based_receiving',
                'shipping', 'receiving', 'transformation'
            ))
    """)

    # ================================================================
    # Part 3: V055 — seed_obligations_for_tenant() function
    # ================================================================

    op.execute("""
        CREATE OR REPLACE FUNCTION seed_obligations_for_tenant(p_tenant_id UUID)
        RETURNS void AS $fn$
        DECLARE
            demo_tenant UUID := '5946c58f-ddf9-4db0-9baa-acb11c6fce91';
            reg_count INT;
        BEGIN
            SELECT COUNT(*) INTO reg_count FROM regulations WHERE tenant_id = p_tenant_id;
            IF reg_count > 0 THEN
                RAISE NOTICE 'Tenant % already has % regulations - skipping seed',
                    p_tenant_id, reg_count;
                RETURN;
            END IF;

            INSERT INTO regulations (id, tenant_id, source_name, citation, section, text, effective_date)
            SELECT gen_random_uuid(), p_tenant_id, source_name, citation, section, text, effective_date
            FROM regulations WHERE tenant_id = demo_tenant;

            INSERT INTO obligations (id, tenant_id, regulation_id, title, description,
                                     risk_category, status, due_date, created_at)
            SELECT gen_random_uuid(), p_tenant_id,
                   (SELECT nr.id FROM regulations nr
                    JOIN regulations dr ON dr.id = o.regulation_id
                    WHERE nr.tenant_id = p_tenant_id AND nr.citation = dr.citation LIMIT 1),
                   o.title, o.description, o.risk_category, o.status, o.due_date, NOW()
            FROM obligations o WHERE o.tenant_id = demo_tenant;

            INSERT INTO controls (id, tenant_id, obligation_id, title, description,
                                  control_type, frequency, status, created_at)
            SELECT gen_random_uuid(), p_tenant_id,
                   (SELECT no2.id FROM obligations no2
                    JOIN obligations do2 ON do2.id = c.obligation_id
                    WHERE no2.tenant_id = p_tenant_id AND no2.title = do2.title LIMIT 1),
                   c.title, c.description, c.control_type, c.frequency, c.status, NOW()
            FROM controls c WHERE c.tenant_id = demo_tenant;

            RAISE NOTICE 'Seeded FSMA 204 obligations for tenant %', p_tenant_id;
        END;
        $fn$ LANGUAGE plpgsql
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS seed_obligations_for_tenant(UUID)")

    # Restore original CHECK constraint (without 'growing')
    op.execute("""
        ALTER TABLE fsma.traceability_events
            DROP CONSTRAINT IF EXISTS traceability_events_event_type_check
    """)
    op.execute("""
        ALTER TABLE fsma.traceability_events
            ADD CONSTRAINT traceability_events_event_type_check
            CHECK (event_type IN (
                'harvesting', 'cooling', 'initial_packing',
                'first_land_based_receiving',
                'shipping', 'receiving', 'transformation'
            ))
    """)

    op.execute("DROP TABLE IF EXISTS fsma.transformation_links")
