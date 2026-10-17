"""Consolidate four exact-scope duplicate permissive RLS policy pairs.

Revision ID: 93eb33f262a1
Revises: ed902d03df45
Create Date: 2026-10-16

The catalog pairs are all FOR ALL TO PUBLIC with the same USING predicate.
An omitted WITH CHECK on an ALL policy inherits USING, so both effective
write checks in each pair are the same as well. Other policy overlaps have
different role scopes and are intentionally left alone.
"""

from alembic import op

revision = "93eb33f262a1"  # pragma: allowlist secret
down_revision = "ed902d03df45"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_PREDICATE = "(tenant_id = get_tenant_context())"
_OR_PREDICATE = f"({_PREDICATE}) OR ({_PREDICATE})"

# table, retained policy, retained explicit check, removed policy,
# removed explicit check. A missing check inherits USING for FOR ALL.
_PAIRS = (
    ("audit_logs", "tenant_isolation_audit_logs", True, "tenant_isolation_audit", False),
    (
        "pcos_authority_documents",
        "tenant_isolation_authority_documents",
        True,
        "pcos_authority_documents_tenant_isolation",
        False,
    ),
    (
        "pcos_extracted_facts",
        "tenant_isolation_extracted_facts",
        True,
        "pcos_extracted_facts_tenant_isolation",
        False,
    ),
    (
        "pcos_fact_citations",
        "tenant_isolation_fact_citations",
        True,
        "pcos_fact_citations_tenant_isolation",
        False,
    ),
)


def _assert_catalog_policy(table: str, name: str, explicit_check: bool) -> None:
    """Fail closed if the exported policy snapshot has changed before apply."""
    check_clause = f"with_check = '{_PREDICATE}'" if explicit_check else "with_check IS NULL"
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = '{table}'
                  AND policyname = '{name}'
                  AND permissive = 'PERMISSIVE'
                  AND roles = ARRAY['public']::name[]
                  AND cmd = 'ALL'
                  AND qual = '{_PREDICATE}'
                  AND {check_clause}
            ) THEN
                RAISE EXCEPTION 'RLS policy snapshot mismatch: public.{table}.{name}';
            END IF;
        END
        $$;
        """
    )


def _create_original(table: str, name: str, explicit_check: bool) -> None:
    check_clause = f" WITH CHECK ({_PREDICATE})" if explicit_check else ""
    op.execute(
        f"CREATE POLICY {name} ON public.{table} AS PERMISSIVE FOR ALL TO PUBLIC USING ({_PREDICATE}){check_clause}"
    )


def upgrade() -> None:
    for table, retained, retained_check, removed, removed_check in _PAIRS:
        _assert_catalog_policy(table, retained, retained_check)
        _assert_catalog_policy(table, removed, removed_check)
        op.execute(f"DROP POLICY {retained} ON public.{table}")
        op.execute(f"DROP POLICY {removed} ON public.{table}")
        op.execute(
            f"CREATE POLICY {retained} ON public.{table} AS PERMISSIVE FOR ALL "
            f"TO PUBLIC USING ({_OR_PREDICATE}) WITH CHECK ({_OR_PREDICATE})"
        )


def downgrade() -> None:
    for table, retained, retained_check, removed, removed_check in reversed(_PAIRS):
        op.execute(f"DROP POLICY {retained} ON public.{table}")
        _create_original(table, retained, retained_check)
        _create_original(table, removed, removed_check)
