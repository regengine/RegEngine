"""v110 — grant curator permissions to canonical system roles.

This is intentionally a data-only migration.  It updates only tenantless
system roles named exactly ``Owner`` or ``Admin``; tenant-defined/custom roles
are not changed.  Duplicate canonical system roles are rejected because an
ambiguous privilege template must be resolved before deployment.

Revision ID: 6f4c2a9d8b17
Revises: e4a7c2d91b06
Create Date: 2026-08-03

Re-parented 2026-09-03: this branch was cut from v109 (51701aedee57) while
main advanced to v116 (e4a7c2d91b06), leaving two heads. It now runs after
v116 so the v111 runtime role grants cover every object main created since.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "6f4c2a9d8b17"  # pragma: allowlist secret
down_revision = "e4a7c2d91b06"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            duplicate_role text;
        BEGIN
            -- The schema-owner migration credential is NOBYPASSRLS while the
            -- roles table is already FORCE-RLS.  This transactional data
            -- migration must inspect/update the canonical templates as owner.
            ALTER TABLE public.roles NO FORCE ROW LEVEL SECURITY;

            SELECT name
              INTO duplicate_role
              FROM roles
             WHERE tenant_id IS NULL
               AND name IN ('Owner', 'Admin')
             GROUP BY name
            HAVING count(*) > 1
             LIMIT 1;

            IF duplicate_role IS NOT NULL THEN
                RAISE EXCEPTION
                    'duplicate canonical system role: %', duplicate_role;
            END IF;

            UPDATE roles
               SET permissions =
                   COALESCE(permissions, '[]'::jsonb)
                   || CASE
                          WHEN NOT (COALESCE(permissions, '[]'::jsonb) ? 'review.read')
                          THEN '["review.read"]'::jsonb
                          ELSE '[]'::jsonb
                      END
                   || CASE
                          WHEN NOT (COALESCE(permissions, '[]'::jsonb) ? 'review.decide')
                          THEN '["review.decide"]'::jsonb
                          ELSE '[]'::jsonb
                      END
             WHERE tenant_id IS NULL
               AND name IN ('Owner', 'Admin');

            ALTER TABLE public.roles FORCE ROW LEVEL SECURITY;
        END $$;
        """
    )


def downgrade() -> None:
    # Deliberately irreversible: without a provenance column we cannot know
    # whether either permission predated this migration. Removing a legitimate
    # grant during rollback would be a privilege-data corruption bug.
    pass
