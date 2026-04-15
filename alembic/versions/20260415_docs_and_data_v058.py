"""Documentation comments and data updates — developer portal docs, cottage cheese exemption

Consolidates raw SQL migrations:
  - V051: COMMENT ON developer portal tables (documentation only)
  - V057: FTL cottage cheese exemption (data update)

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-04-15
"""
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ================================================================
    # Part 1: V051 — Developer portal schema documentation
    # ================================================================

    _comments = {
        "developer_invite_codes": (
            "Developer portal registration gate. Invite codes control portal access. "
            "RLS: anon SELECT for registration validation. No tenant_id - global codes."
        ),
        "developer_profiles": (
            "Developer portal user profiles. 1:1 with auth.users via auth_user_id. "
            "RLS: users can SELECT/UPDATE their own profile only. "
            "No tenant_id - developer portal is per-user, not per-tenant."
        ),
        "developer_api_keys": (
            "Developer API keys. key_hash stores SHA-256 hash (never plaintext). "
            "key_prefix stores first 12 chars for display. "
            "RLS: developers can manage their own keys only (via developer_id FK)."
        ),
        "developer_api_usage": (
            "Developer API usage log. One row per API request for analytics. "
            "RLS: developers can read their own usage only (via developer_id FK)."
        ),
        "assessment_submissions": (
            "Lead capture from free compliance tools (no login required). "
            "RLS: anon INSERT + SELECT (duplicate check) + UPDATE (enrichment). "
            "Triggers notify-new-lead edge function on INSERT. "
            "No tenant_id - these are anonymous pre-signup submissions."
        ),
    }
    for table, comment in _comments.items():
        # Guard: table may not exist on all databases
        op.execute(f"""
            DO $$ BEGIN
                EXECUTE 'COMMENT ON TABLE {table} IS ''{comment}''';
            EXCEPTION WHEN undefined_table THEN NULL;
            END $$
        """)

    # ================================================================
    # Part 2: V057 — Cottage cheese exemption (data update)
    # ================================================================

    # Guard: schema may differ — only run if expected columns exist
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'food_traceability_list'
                  AND column_name = 'food_name'
            ) THEN
                EXECUTE $exec$
                    UPDATE food_traceability_list
                    SET examples   = array_remove(examples, 'cottage cheese'),
                        exclusions = CASE
                            WHEN exclusions IS NULL THEN
                                ARRAY['hard cheeses',
                                      'cottage cheese (exempt per \u00a71.1305(d), IMS List, finalized April 2026)']
                            ELSE
                                array_append(exclusions,
                                    'cottage cheese (exempt per \u00a71.1305(d), IMS List, finalized April 2026)')
                        END
                    WHERE food_name = 'Fresh Soft Cheese (pasteurized milk)'
                $exec$;
            ELSE
                RAISE NOTICE 'food_traceability_list.food_name column not found - skipping cottage cheese update';
            END IF;
        END $$
    """)


def downgrade() -> None:
    # Reverse cottage cheese exemption (guarded)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'food_traceability_list' AND column_name = 'food_name'
            ) THEN
                EXECUTE $exec$
                    UPDATE food_traceability_list
                    SET examples   = array_append(examples, 'cottage cheese'),
                        exclusions = array_remove(exclusions,
                            'cottage cheese (exempt per \u00a71.1305(d), IMS List, finalized April 2026)')
                    WHERE food_name = 'Fresh Soft Cheese (pasteurized milk)'
                $exec$;
            END IF;
        END $$
    """)

    # Remove table comments (no-op — comments don't need reversal)
