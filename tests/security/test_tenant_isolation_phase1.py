import os
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

from tests.integration_requirements import psycopg_connect_or_skip

# Get DB URL from env or use default (matching conftest.py)
DB_URL = os.environ.get("ADMIN_DATABASE_URL", "postgresql://regengine:regengine@localhost:5433/regengine_admin")


@pytest.fixture(scope="module")
def db_connection():
    """Create a raw DB connection for RLS testing."""
    conn = psycopg_connect_or_skip(
        DB_URL,
        reason="PostgreSQL database is unavailable for RLS verification",
    )
    conn.autocommit = False  # Use transactions
    try:
        yield conn
    finally:
        conn.close()


def set_tenant_context(cursor, tenant_id):
    """Set the RLS context for the current transaction."""
    cursor.execute(f"SET app.tenant_id = '{tenant_id}';")


def _make_probe_role(cur):
    """Create a throwaway non-superuser role subject to RLS.

    ``audit_logs`` has FORCE RLS with a PUBLIC tenant-isolation policy, but
    superusers always bypass RLS — probing as the (superuser) test connection
    would vacuously pass. CREATE ROLE / GRANT are transactional, so the module
    fixture's rollback removes the role again; the random suffix keeps reruns
    collision-free even after a crashed run against a shared database.
    """
    with cur.connection.cursor() as check_cur:
        check_cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        if not check_cur.fetchone()[0]:
            pytest.skip("RLS probe requires a superuser connection to create the probe role")
    role = f"rls_probe_{uuid.uuid4().hex[:8]}"
    cur.execute(f'CREATE ROLE "{role}" NOLOGIN')
    cur.execute(f'GRANT SELECT ON audit_logs TO "{role}"')
    return role


def _insert_audit_row(cur, tenant_id):
    """Insert an audit_logs row matching the real migrated schema."""
    cur.execute(
        """
        INSERT INTO audit_logs
            (tenant_id, actor_id, event_type, event_category, action,
             severity, resource_type, resource_id, integrity_hash)
        VALUES (%s, %s, 'auth.login', 'auth', 'LOGIN',
                'info', 'USER', %s, %s)
        """,
        (tenant_id, str(uuid.uuid4()), str(uuid.uuid4()), f"test-integrity-{uuid.uuid4().hex}"),
    )


class TestPhase1TenantIsolation:
    """
    Phase 1: Strict Verification of "Double-Lock" RLS.

    These tests connect directly to the database to bypass the API layer
    and verify that the Row Level Security (RLS) policies themselves
    are enforcing isolation.
    """

    def test_rls_enforcement_on_audit_logs(self, db_connection):
        """
        Verify that a user context switched to Tenant A cannot see Tenant B's audit logs.
        """
        tenant_a = str(uuid.uuid4())
        tenant_b = str(uuid.uuid4())

        cur = db_connection.cursor(row_factory=dict_row)

        try:
            probe_role = _make_probe_role(cur)

            # 1. Setup: insert one row per tenant as the superuser connection
            # (bypasses RLS), setting the context to match each row anyway.
            set_tenant_context(cur, tenant_a)
            _insert_audit_row(cur, tenant_a)

            set_tenant_context(cur, tenant_b)
            _insert_audit_row(cur, tenant_b)

            # 2. Verify A cannot see B — probe as the restricted role so the
            # PUBLIC tenant-isolation policy actually applies.
            cur.execute(f'SET ROLE "{probe_role}"')

            set_tenant_context(cur, tenant_a)
            cur.execute("SELECT * FROM audit_logs WHERE tenant_id = %s", (tenant_b,))
            results = cur.fetchall()
            assert len(results) == 0, "Security Breach: Tenant A could query Tenant B's specific records"

            cur.execute("SELECT * FROM audit_logs")
            results = cur.fetchall()

            # Should only see Tenant A's record
            tenant_ids = {str(r["tenant_id"]) for r in results}
            assert tenant_b not in tenant_ids, "Security Breach: Tenant B data leaked into Tenant A view"
            assert tenant_a in tenant_ids, "Functional Error: Tenant A cannot see their own data"

            # 3. Verify B cannot see A
            set_tenant_context(cur, tenant_b)
            cur.execute("SELECT * FROM audit_logs")
            results = cur.fetchall()

            tenant_ids = {str(r["tenant_id"]) for r in results}
            assert tenant_a not in tenant_ids, "Security Breach: Tenant A data leaked into Tenant B view"
            assert tenant_b in tenant_ids, "Functional Error: Tenant B cannot see their own data"

            # Reset role for cleanup (though connection rollback handles it)
            cur.execute("RESET ROLE;")

        finally:
            db_connection.rollback()  # Clean up

    def test_public_access_denied(self, db_connection):
        """Without a tenant context, queries must fail closed — not return rows.

        Since alembic v097 (e4d7b2a9c561), ``get_tenant_context()`` RAISES on an
        unset ``app.tenant_id`` instead of returning a fallback tenant. A
        context-less query through the RLS policy therefore errors out; the
        pre-v097 expectation (silent empty result for the fallback tenant) would
        now mask a regression of the #2461 fail-closed guarantee.
        """
        cur = db_connection.cursor()
        try:
            probe_role = _make_probe_role(cur)

            # Insert a row under a real tenant context first.
            tenant_x = str(uuid.uuid4())
            set_tenant_context(cur, tenant_x)
            _insert_audit_row(cur, tenant_x)

            # Now query as the restricted role with NO tenant context.
            cur.execute(f'SET ROLE "{probe_role}"')
            cur.execute("RESET app.tenant_id;")
            with pytest.raises(psycopg.Error) as excinfo:
                cur.execute("SELECT * FROM audit_logs WHERE tenant_id = %s", (tenant_x,))
            assert "tenant context required" in str(excinfo.value), (
                f"Expected the fail-hard get_tenant_context() error, got: {excinfo.value}"
            )

        finally:
            db_connection.rollback()
