"""RLS probe helper shared by the live tenant-isolation e2e and its offline tests.

It lives outside ``tests/test_e2e_tenant_isolation.py`` because that module
resolves a live database at import time: under ``REGENGINE_REQUIRE_DB=1``
importing it without one fails collection, which would also take down the
DB-free regression tests in ``tests/test_rls_probe_helper.py``.
"""

import pytest

# Tables (and readable columns) the RLS probes below may touch. Fixed
# allowlist, so table/column names never come from test input.
_RLS_PROBE_COLUMNS = {
    "fsma.traceability_events": ("tenant_id", "product_reference"),
    "fsma.request_cases": ("tenant_id", "request_case_id"),
    "fsma.rule_evaluations": ("tenant_id", "event_id"),
    "fsma.hash_chain": ("tenant_id",),
    "fsma.exception_cases": ("tenant_id", "case_id"),
}


def _rls_unfiltered_rows(db_session, table, guc_tenant):
    """Read a whole table with NO tenant predicate, as the app role.

    ``SET ROLE regengine`` drops the test connection's RLS bypass (the
    suite connects as a superuser/owner, for whom RLS is inert), and
    ``app.tenant_id`` supplies the tenant context the RLS policies match
    on. Whatever comes back passed real row-level security. Role and GUC
    are reset before returning so later steps run exactly as before.

    Fails loudly when the connection cannot assume the app role: a
    skipped probe would leave the RLS proof unexecuted while the job
    stays green, which is exactly how an isolation regression hides.
    The caller's transaction is left alone (no rollback), so earlier
    uncommitted scenario rows survive for the failure output.
    """
    from sqlalchemy import text

    if table not in _RLS_PROBE_COLUMNS:
        raise ValueError(f"RLS probe allowlist has no table {table!r}")
    select_cols = ", ".join(f"{col}::text" for col in _RLS_PROBE_COLUMNS[table])
    try:
        db_session.execute(text("SET ROLE regengine"))
    except Exception as exc:
        try:
            db_session.execute(text("RESET ROLE"))
        except Exception:
            pass
        pytest.fail(
            f"cannot SET ROLE regengine for RLS probe: {exc}. "
            "The RLS proof cannot run without the app role; fix the grant, do not skip."
        )
    try:
        db_session.execute(
            text("SELECT set_config('app.tenant_id', :tid, false)"),
            {"tid": guc_tenant},
        )
        return db_session.execute(text(f"SELECT {select_cols} FROM {table}")).fetchall()
    finally:
        # Both settings are session-level: a rollback alone would NOT
        # clear them, so reset explicitly. If the transaction aborted,
        # roll back first, then reset.
        try:
            db_session.execute(text("RESET app.tenant_id"))
            db_session.execute(text("RESET ROLE"))
        except Exception:
            db_session.rollback()
            db_session.execute(text("RESET app.tenant_id"))
            db_session.execute(text("RESET ROLE"))
