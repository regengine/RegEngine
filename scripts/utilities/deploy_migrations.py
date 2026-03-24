#!/usr/bin/env python3
"""
Automated deployment script for V29 and V005 migrations.
Uses direct database connection (no Supabase UI needed).
"""

import os
import psycopg
from psycopg import IsolationLevel
import sys

# Database connection strings — MUST be set via environment variables
SUPABASE_DSN = os.getenv("SUPABASE_DSN")
if not SUPABASE_DSN:
    print("ERROR: SUPABASE_DSN environment variable is required.", file=sys.stderr)
    print("Example: export SUPABASE_DSN='postgresql://user:pass@host:5432/db'", file=sys.stderr)
    sys.exit(1)

ENERGY_DSN = os.getenv("ENERGY_DB_URL")
if not ENERGY_DSN:
    print("ERROR: ENERGY_DB_URL environment variable is required.", file=sys.stderr)
    sys.exit(1)


def run_migration(dsn: str, migration_file: str, migration_name: str):
    """Execute a migration file against the specified database."""
    print(f"\n{'='*60}")
    print(f"Deploying: {migration_name}")
    print(f"File: {migration_file}")
    print(f"{'='*60}\n")
    
    # Read migration SQL
    try:
        with open(migration_file, 'r') as f:
            sql = f.read()
    except FileNotFoundError:
        print(f"❌ Migration file not found: {migration_file}")
        return False
    
    # Connect and execute
    try:
        conn = psycopg.connect(dsn)
        conn.autocommit = True
        cursor = conn.cursor()
        
        print("📡 Connected to database")
        print("🚀 Executing migration...\n")
        
        cursor.execute(sql)
        
        # Fetch any notices
        for notice in conn.notices:
            print(f"💬 {notice.strip()}")
        
        print(f"\n✅ {migration_name} deployed successfully!")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg.Error as e:
        print(f"\n❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False


def verify_v29_deployment(dsn: str):
    """Verify V29 helper functions were created."""
    print(f"\n{'='*60}")
    print("Verifying V29 Deployment")
    print(f"{'='*60}\n")
    
    try:
        conn = psycopg.connect(dsn)
        cursor = conn.cursor()
        
        # Check for the 3 new functions
        cursor.execute("""
            SELECT 
                proname as function_name,
                pg_get_function_arguments(oid) as arguments
            FROM pg_proc 
            WHERE proname IN ('get_user_tenant_id', 'get_tenant_context', 'set_tenant_from_jwt')
            ORDER BY proname;
        """)
        
        functions = cursor.fetchall()
        
        if len(functions) == 3:
            print("✅ All 3 helper functions created:")
            for func in functions:
                print(f"  - {func[0]}({func[1]})")
        else:
            print(f"⚠️  Expected 3 functions, found {len(functions)}")
            
        cursor.close()
        conn.close()
        return len(functions) == 3
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False


def verify_v005_deployment(dsn: str):
    """Verify V005 tenant_id columns were added."""
    print(f"\n{'='*60}")
    print("Verifying V005 Deployment")
    print(f"{'='*60}\n")
    
    try:
        conn = psycopg.connect(dsn)
        cursor = conn.cursor()
        
        # Check for tenant_id columns
        cursor.execute("""
            SELECT 
                table_name,
                column_name,
                data_type
            FROM information_schema.columns
            WHERE column_name = 'tenant_id'
              AND table_schema = 'public'
            ORDER BY table_name;
        """)
        
        columns = cursor.fetchall()
        
        expected_tables = ['compliance_snapshots', 'mismatches', 'attestations', 'idempotency_keys']
        found_tables = [row[0] for row in columns]
        
        print(f"✅ Found tenant_id in {len(columns)} tables:")
        for col in columns:
            print(f"  - {col[0]} ({col[2]})")
        
        # Check if all expected tables have the column
        missing = [t for t in expected_tables if t not in found_tables]
        if missing:
            print(f"\n⚠️  Missing tenant_id in: {', '.join(missing)}")
            
        cursor.close()
        conn.close()
        return len(missing) == 0
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False


def main():
    """Main deployment workflow."""
    print("\n" + "="*60)
    print("RegEngine Migration Deployment Script")
    print("="*60)
    
    # Change to RegEngine directory
    regengine_dir = "/Users/christophersellers/Desktop/RegEngine"
    os.chdir(regengine_dir)
    print(f"\n📁 Working directory: {regengine_dir}")
    
    success = True
    
    # Deploy V29 to Supabase
    v29_file = "services/admin/migrations/V29__jwt_rls_integration.sql"
    if run_migration(SUPABASE_DSN, v29_file, "V29 (JWT-RLS Integration)"):
        verify_v29_deployment(SUPABASE_DSN)
    else:
        success = False
    
    # Deploy V005 to Energy DB
    v005_file = "services/energy/migrations/V005__add_tenant_isolation.sql"
    if run_migration(ENERGY_DSN, v005_file, "V005 (Energy Tenant Isolation)"):
        verify_v005_deployment(ENERGY_DSN)
    else:
        success = False
    
    # Summary
    print("\n" + "="*60)
    if success:
        print("🎉 All migrations deployed and verified successfully!")
        print("\n📋 Next Steps:")
        print("  1. Restart admin service: cd services/admin && docker-compose restart")
        print("  2. Test JWT claims include tenant_id")
        print("  3. Verify RLS policies are working")
    else:
        print("⚠️  Some migrations failed - please review errors above")
    print("="*60 + "\n")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
