#!/usr/bin/env python3
"""
RegEngine Database Initialization - Apply Neo4j Constraints
This script applies the required database constraints for production deployment.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path to import neo4j_utils
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.neo4j_utils import Neo4jClient


def apply_constraints(neo4j_client: Neo4jClient):
    """Apply all required database constraints."""

    constraints = [
        # Task 3.1: Unique constraint for Lot TLC + Tenant
        {
            "name": "lot_tlc_tenant_unique",
            "query": """
                CREATE CONSTRAINT lot_tlc_tenant_unique IF NOT EXISTS
                FOR (l:Lot) REQUIRE (l.tlc, l.tenant_id) IS UNIQUE
            """,
        },
        # Additional production-ready constraints
        {
            "name": "tenant_id_unique",
            "query": """
                CREATE CONSTRAINT tenant_id_unique IF NOT EXISTS
                FOR (t:Tenant) REQUIRE t.id IS UNIQUE
            """,
        },
        {
            "name": "facility_gln_tenant_unique",
            "query": """
                CREATE CONSTRAINT facility_gln_tenant_unique IF NOT EXISTS
                FOR (f:Facility) REQUIRE (f.gln, f.tenant_id) IS UNIQUE
            """,
        },
    ]

    indexes = [
        {
            "name": "lot_gtin_index",
            "query": """
                CREATE INDEX lot_gtin_index IF NOT EXISTS
                FOR (l:Lot) ON (l.gtin)
            """,
        },
        {
            "name": "lot_created_at_index",
            "query": """
                CREATE INDEX lot_created_at_index IF NOT EXISTS
                FOR (l:Lot) ON (l.created_at)
            """,
        },
    ]

    print("🔧 Applying Neo4j Database Constraints...")
    print("=" * 60)

    try:
        with neo4j_client.driver.session() as session:
            # Apply constraints
            for constraint in constraints:
                print(f"  ➤ Creating constraint: {constraint['name']}")
                try:
                    session.run(constraint["query"])
                    print(f"    ✅ Success")
                except Exception as e:
                    print(f"    ⚠️  Warning: {str(e)}")

            # Apply indexes
            print("\n🔍 Creating Performance Indexes...")
            for index in indexes:
                print(f"  ➤ Creating index: {index['name']}")
                try:
                    session.run(index["query"])
                    print(f"    ✅ Success")
                except Exception as e:
                    print(f"    ⚠️  Warning: {str(e)}")

            # Verify constraints
            print("\n✅ Verification - Active Constraints:")
            result = session.run("SHOW CONSTRAINTS")
            for record in result:
                print(
                    f"  • {record.get('name', 'unnamed')}: {record.get('type', 'unknown')}"
                )

            # Verify indexes
            print("\n✅ Verification - Active Indexes:")
            result = session.run("SHOW INDEXES")
            for record in result:
                print(
                    f"  • {record.get('name', 'unnamed')}: {record.get('type', 'unknown')}"
                )

    except Exception as e:
        print(f"\n❌ Error applying constraints: {str(e)}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ Database initialization complete!")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("RegEngine - Database Constraint Initialization")
    print("=" * 60 + "\n")

    # Initialize Neo4j client
    try:
        neo4j = Neo4jClient()
        apply_constraints(neo4j)
    except Exception as e:
        print(f"❌ Failed to connect to Neo4j: {str(e)}")
        print("\nPlease ensure:")
        print("  1. Neo4j is running")
        print(
            "  2. Environment variables are set (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)"
        )
        sys.exit(1)
