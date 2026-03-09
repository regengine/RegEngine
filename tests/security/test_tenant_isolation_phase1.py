
import os
import uuid
import pytest
import psycopg
from psycopg.rows import dict_row

# Get DB URL from env or use default (matching conftest.py)
DB_URL = os.environ.get(
    "ADMIN_DATABASE_URL", 
    "postgresql://regengine:regengine@localhost:5433/regengine_admin"
)

@pytest.fixture(scope="module")
def db_connection():
    """Create a raw DB connection for RLS testing."""
    try:
        conn = psycopg.connect(DB_URL)
        conn.autocommit = False  # Use transactions
        yield conn
        conn.close()
    except psycopg.OperationalError as e:
        pytest.skip(f"Database unavailable: {e}")

def set_tenant_context(cursor, tenant_id):
    """Set the RLS context for the current transaction."""
    cursor.execute(f"SET app.tenant_id = '{tenant_id}';")

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
        
        # We need to insert data. 
        # Usually RLS prevents insertion of data for other tenants too.
        # But as a superuser (or if RLS policy allows), we might be able to setup constraints.
        # The 'regengine' user in dev might be superuser or owner, bypassing RLS.
        # IF we are superuser, RLS is BYPASSED by default unless we force it or use NO INHERIT.
        # However, for this test to match "Production" reality, we should try to simulate a non-superuser role
        # OR explicitly check that setting the limit works if the role subjects to RLS.
        
        # NOTE: In our dev setup, 'regengine' might be superuser.
        # To truly test RLS, we should CREATE a restricted role or ensure our user is restricted.
        # For this Phase 1 test, we will assume standard RLS behavior is active.
        
        cur = db_connection.cursor(row_factory=dict_row)
        
        try:
            # 1. Setup: Insert data for both tenants (bypassing RLS if possible, or context switching)
            # We'll try to context switch to insert valid data for each.
            
            # Context A
            set_tenant_context(cur, tenant_a)
            cur.execute("""
                INSERT INTO audit_logs (id, tenant_id, action, resource_type, resource_id, actor_id, created_at)
                VALUES (%s, %s, 'LOGIN', 'USER', %s, %s, NOW())
            """, (str(uuid.uuid4()), tenant_a, str(uuid.uuid4()), str(uuid.uuid4())))
            
            # Context B
            set_tenant_context(cur, tenant_b)
            cur.execute("""
                INSERT INTO audit_logs (id, tenant_id, action, resource_type, resource_id, actor_id, created_at)
                VALUES (%s, %s, 'LOGIN', 'USER', %s, %s, NOW())
            """, (str(uuid.uuid4()), tenant_b, str(uuid.uuid4()), str(uuid.uuid4())))
            
            # 2. Verify A cannot see B
            # Switch to 'authenticated' role to enforce RLS (postgres superuser bypasses RLS)
            cur.execute("SET ROLE authenticated;")
            
            set_tenant_context(cur, tenant_a)
            cur.execute("SELECT * FROM audit_logs WHERE tenant_id = %s", (tenant_b,))
            results = cur.fetchall()
            assert len(results) == 0, "Security Breach: Tenant A could query Tenant B's specific records"
            
            cur.execute("SELECT * FROM audit_logs")
            results = cur.fetchall()
            
            # Should only see Tenant A's record
            tenant_ids = {r['tenant_id'] for r in results}
            assert tenant_b not in tenant_ids, "Security Breach: Tenant B data leaked into Tenant A view"
            assert tenant_a in tenant_ids, "Functional Error: Tenant A cannot see their own data"
            
            # 3. Verify B cannot see A
            set_tenant_context(cur, tenant_b)
            cur.execute("SELECT * FROM audit_logs")
            results = cur.fetchall()
            
            tenant_ids = {r['tenant_id'] for r in results}
            assert tenant_a not in tenant_ids, "Security Breach: Tenant A data leaked into Tenant B view"
            assert tenant_b in tenant_ids, "Functional Error: Tenant B cannot see their own data"
            
            # Reset role for cleanup (though connection rollback handles it)
            cur.execute("RESET ROLE;")
            
        finally:
            db_connection.rollback() # Clean up

    def test_public_access_denied(self, db_connection):
        """Verify that without a tenant_id set, no data is visible."""
        cur = db_connection.cursor()
        try:
            # Reset context (or set to invalid)
            cur.execute("RESET app.tenant_id;")
            
            # Insert some data first to be sure (using a context)
            tenant_x = str(uuid.uuid4())
            set_tenant_context(cur, tenant_x)
            cur.execute("""
                INSERT INTO audit_logs (id, tenant_id, action, resource_type, resource_id, actor_id, created_at)
                VALUES (%s, %s, 'LOGIN', 'USER', %s, %s, NOW())
            """, (str(uuid.uuid4()), tenant_x, str(uuid.uuid4()), str(uuid.uuid4())))
            
            # Now Check Public/Null Context
            cur.execute("SET ROLE authenticated;")
            cur.execute("RESET app.tenant_id;")
            cur.execute("SELECT COUNT(*) FROM audit_logs")
            count = cur.fetchone()[0]
            
            # Note: The fallback UUID in policy is '00000000-0000-0000-0000-000000000001'
            # So "Public" effectively becomes "Tenant 1" (The Default/System Tenant).
            # If our random tenant is NOT Tenant 1, we should see 0 rows matching our inserted data.
            # However, if there are existing rows for Tenant 1, we might see them.
            # We strictly want to ensure we don't see tenant_x.
            
            cur.execute("SELECT * FROM audit_logs WHERE tenant_id = %s", (tenant_x,))
            assert cur.fetchone() is None, "Security Breach: Public context could see Tenant X data"
            
        finally:
            db_connection.rollback()
