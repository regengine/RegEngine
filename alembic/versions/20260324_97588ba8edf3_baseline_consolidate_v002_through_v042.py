# ============================================================================
# BASELINE MIGRATION — Consolidates Flyway-style V002 through V042
# ============================================================================
# For EXISTING databases that already have these tables applied, do NOT run
# `alembic upgrade head`.  Instead, stamp the database to mark this revision
# as already applied:
#
#     alembic stamp head
#
# For NEW databases, run normally:
#
#     alembic upgrade head
# ============================================================================

"""baseline — consolidate V002 through V042

Revision ID: 97588ba8edf3
Revises:
Create Date: 2026-03-24 18:06:50.080590

"""
from typing import Sequence, Union
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '97588ba8edf3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Path to the legacy Flyway-style migration files
_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

# Ordered list of legacy SQL files to apply
_SQL_FILES = [
    "V002__fsma_cte_persistence.sql",
    "V036__fsma_204_regulatory_seed_data.sql",
    "V037__obligation_cte_rules.sql",
    "V038__unify_compliance_alerts.sql",
    "V039__hash_chain_immutability.sql",
    "V040__obligation_cte_rules_rls_doc.sql",
    "V041__extend_organizations_schema.sql",
    "V042__tenant_feature_data_tables.sql",
]


def upgrade() -> None:
    """Apply all legacy migrations (V002 through V042) as a single baseline."""
    for filename in _SQL_FILES:
        sql_path = _MIGRATIONS_DIR / filename
        sql = sql_path.read_text(encoding="utf-8")
        # Strip Flyway-style BEGIN/COMMIT — Alembic manages the transaction
        sql = sql.replace("BEGIN;", "").replace("COMMIT;", "")
        op.execute(sql)


def downgrade() -> None:
    """Drop all tables and objects created by V002–V042.

    WARNING: This destroys all data. Only use in development.
    Order matters — drop dependent tables first.
    """
    # --- V042: Tenant feature data tables ---
    op.execute("DROP TABLE IF EXISTS fsma.tenant_portal_links CASCADE")
    op.execute("DROP TABLE IF EXISTS fsma.tenant_exchanges CASCADE")
    op.execute("DROP TABLE IF EXISTS fsma.tenant_onboarding CASCADE")
    op.execute("DROP TABLE IF EXISTS fsma.tenant_settings CASCADE")
    op.execute("DROP TABLE IF EXISTS fsma.tenant_notification_prefs CASCADE")
    op.execute("DROP TABLE IF EXISTS fsma.tenant_team_members CASCADE")
    op.execute("DROP TABLE IF EXISTS fsma.tenant_products CASCADE")
    op.execute("DROP TABLE IF EXISTS fsma.tenant_suppliers CASCADE")

    # --- V041: No tables created (only ALTER TABLE on fsma.organizations) ---
    # Columns added by V041 are left in place; removing them could break
    # other migrations or application code.

    # --- V040: No tables created (only COMMENT) ---

    # --- V039: Drop immutability trigger ---
    op.execute("DROP TRIGGER IF EXISTS chain_immutability ON fsma.hash_chain")
    op.execute("DROP FUNCTION IF EXISTS fsma.prevent_chain_mutation()")

    # --- V038: No tables created (only ALTER TABLE on fsma.compliance_alerts) ---

    # --- V037: obligation_cte_rules ---
    op.execute("DROP TABLE IF EXISTS obligation_cte_rules CASCADE")

    # --- V036: food_traceability_list (seed data tables) ---
    op.execute("DROP TABLE IF EXISTS food_traceability_list CASCADE")

    # --- V002: Core FSMA CTE tables ---
    op.execute("DROP TABLE IF EXISTS fsma.fda_export_log CASCADE")
    op.execute("DROP TABLE IF EXISTS fsma.compliance_alerts CASCADE")
    op.execute("DROP TABLE IF EXISTS fsma.hash_chain CASCADE")
    op.execute("DROP TABLE IF EXISTS fsma.cte_kdes CASCADE")
    op.execute("DROP TABLE IF EXISTS fsma.cte_events CASCADE")

    # Drop the fsma schema only if it's now empty
    op.execute("DROP SCHEMA IF EXISTS fsma CASCADE")
