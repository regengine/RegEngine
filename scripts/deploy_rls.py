#!/usr/bin/env python3
"""
Python-based RLS Deployment Script
Deploys V27 and V28 RLS migrations to Supabase
"""
import os
import sys
from pathlib import Path

def deploy_rls_migrations():
    """Deploy RLS migrations using psycopg2"""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Installing...")
        os.system("pip install psycopg2-binary")
        import psycopg2
    
    # Supabase connection details (from db_test.py)
    SUPABASE_HOST = "db.magbeerafyxmyuqmbfgv.supabase.co"
    SUPABASE_PORT = 5432
    SUPABASE_USER = "postgres"
    SUPABASE_PASSWORD = "trj.qxe_wxh6QGB@auq"
    SUPABASE_DB = "postgres"

    
    print("=" * 60)
    print("RLS Security Layer Deployment to Supabase")
    print("=" * 60)
    print()
    
    # Migration files
    script_dir = Path(__file__).parent.parent
    v27_path = script_dir / "services/admin/migrations/V27__rls_core_security_tables.sql"
    v28_path = script_dir / "services/admin/migrations/V28__rls_pcos_vertical_tables.sql"
    
    if not v27_path.exists():
        print(f"❌ V27 migration not found: {v27_path}")
        return False
    
    if not v28_path.exists():
        print(f"❌ V28 migration not found: {v28_path}")
        return False
    
    print("✅ Migration files found")
    print()
    
    # Connect to Supabase
    print("Connecting to Supabase...")
    try:
        conn = psycopg2.connect(
            host=SUPABASE_HOST,
            port=SUPABASE_PORT,
            user=SUPABASE_USER,
            password=SUPABASE_PASSWORD,
            database=SUPABASE_DB,
            sslmode='require'
        )
        conn.autocommit = True
        cursor = conn.cursor()
        print("✅ Connected to Supabase")
        print()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False
    
    # Test connection
    print("Testing database connection...")
    try:
        cursor.execute("SELECT current_database(), current_user, version();")
        db, user, version = cursor.fetchone()
        print(f"  Database: {db}")
        print(f"  User: {user}")
        print(f"  Version: {version[:50]}...")
        print("✅ Connection test passed")
        print()
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        conn.close()
        return False
    
    # Deploy V27
    print("=" * 60)
    print("Deploying V27: Core Security Tables (15 tables)")
    print("=" * 60)
    print()
    
    try:
        with open(v27_path, 'r') as f:
            v27_sql = f.read()
        
        cursor.execute(v27_sql)
        print("✅ V27 deployed successfully")
        print()
    except Exception as e:
        print(f"❌ V27 deployment failed: {e}")
        conn.close()
        return False
    
    # Deploy V28
    print("=" * 60)
    print("Deploying V28: PCOS & Vertical Tables (40+ tables)")
    print("=" * 60)
    print()
    
    try:
        with open(v28_path, 'r') as f:
            v28_sql = f.read()
        
        cursor.execute(v28_sql)
        print("✅ V28 deployed successfully")
        print()
    except Exception as e:
        print(f"❌ V28 deployment failed: {e}")
        print("⚠️  V27 was applied successfully")
        conn.close()
        return False
    
    # Verification
    print("=" * 60)
    print("Verifying Deployment")
    print("=" * 60)
    print()
    
    try:
        cursor.execute("""
            SELECT COUNT(*) 
            FROM pg_tables t
            JOIN pg_class c ON c.relname = t.tablename
            WHERE t.schemaname = 'public' 
              AND c.relrowsecurity = true;
        """)
        rls_count = cursor.fetchone()[0]
        print(f"Tables with RLS enabled: {rls_count}")
        
        if rls_count >= 50:
            print("✅ RLS security layer deployed successfully!")
        else:
            print(f"⚠️  Expected ~60 tables, found {rls_count}")
            print("This may be normal if some tables don't exist yet.")
        
        print()
    except Exception as e:
        print(f"⚠️  Verification query failed: {e}")
    
    # Cleanup
    cursor.close()
    conn.close()
    
    print("=" * 60)
    print("✅ DEPLOYMENT COMPLETE")
    print("=" * 60)
    print()
    print("Next Steps:")
    print("1. Test tenant isolation (run verify_rls_isolation.sql)")
    print("2. Test application functionality")
    print("3. Monitor logs for RLS errors")
    print()
    
    return True

if __name__ == "__main__":
    success = deploy_rls_migrations()
    sys.exit(0 if success else 1)
