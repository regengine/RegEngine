#!/usr/bin/env python3
"""Inventory cross-tenant MERGE collisions in Neo4j.

Read-only. Returns a count and a sample per collision class.
Reference: docs/qa/neo4j-tenant-isolation-plan.md §3.

Usage:
    NEO4J_URI=... NEO4J_USER=... NEO4J_PASSWORD=... \
        python services/graph/scripts/inventory_tenant_collisions.py

Exit codes:
    0 = ran successfully (regardless of collision count)
    1 = connection or query error
"""

import os
import sys

try:
    from neo4j import GraphDatabase
except ImportError:
    print("Install: pip install neo4j", file=sys.stderr)
    sys.exit(1)

QUERIES = {
    "Document.id": """
        MATCH (d:Document)
        WHERE d.tenant_id IS NOT NULL
        WITH d.id AS k, collect(DISTINCT d.tenant_id) AS tenants, count(*) AS n
        WHERE size(tenants) > 1
        RETURN k AS key, tenants, n
        ORDER BY n DESC LIMIT 10
    """,
    "Document.hash": """
        MATCH (d:Document)
        WHERE d.hash IS NOT NULL AND d.tenant_id IS NOT NULL
        WITH d.hash AS k, collect(DISTINCT d.tenant_id) AS tenants, count(*) AS n
        WHERE size(tenants) > 1
        RETURN k AS key, tenants, n
        ORDER BY n DESC LIMIT 10
    """,
    "Provision.pid": """
        MATCH (p:Provision)
        WHERE p.tenant_id IS NOT NULL
        WITH p.pid AS k, collect(DISTINCT p.tenant_id) AS tenants, count(*) AS n
        WHERE size(tenants) > 1
        RETURN k AS key, tenants, n
        ORDER BY n DESC LIMIT 10
    """,
    "Provision.hash": """
        MATCH (p:Provision)
        WHERE p.hash IS NOT NULL AND p.tenant_id IS NOT NULL
        WITH p.hash AS k, collect(DISTINCT p.tenant_id) AS tenants, count(*) AS n
        WHERE size(tenants) > 1
        RETURN k AS key, tenants, n
        ORDER BY n DESC LIMIT 10
    """,
    "Threshold.pid": """
        MATCH (t:Threshold)
        WHERE t.tenant_id IS NOT NULL
        WITH t.pid AS k, collect(DISTINCT t.tenant_id) AS tenants, count(*) AS n
        WHERE size(tenants) > 1
        RETURN k AS key, tenants, n
        ORDER BY n DESC LIMIT 10
    """,
}

TOTALS = {
    "Document (total)": "MATCH (d:Document) RETURN count(d) AS n",
    "Provision (total)": "MATCH (p:Provision) RETURN count(p) AS n",
    "Threshold (total)": "MATCH (t:Threshold) RETURN count(t) AS n",
    "Document missing tenant_id": "MATCH (d:Document) WHERE d.tenant_id IS NULL RETURN count(d) AS n",
    "Provision missing tenant_id": "MATCH (p:Provision) WHERE p.tenant_id IS NULL RETURN count(p) AS n",
}


def main() -> int:
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")
    if not uri or not password:
        print("NEO4J_URI and NEO4J_PASSWORD required", file=sys.stderr)
        return 1

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            print(f"== Neo4j inventory against {uri.split('@')[-1] if '@' in uri else uri}")
            print()
            print("-- Totals --")
            for label, q in TOTALS.items():
                rec = session.run(q).single()
                print(f"  {label:36s} {rec['n']}")
            print()
            print("-- Cross-tenant collisions --")
            total_collisions = 0
            for label, q in QUERIES.items():
                rows = list(session.run(q))
                print(f"  {label:20s} {len(rows)} colliding keys (top 10 shown)")
                total_collisions += len(rows)
                for row in rows:
                    print(f"    key={row['key']!r}  tenants={row['tenants']}  count={row['n']}")
            print()
            print(f"== Total collision classes with hits: {total_collisions}")
            print("== If 0: Step 3 (data split) can be SKIPPED.")
            print("== If >0: Step 3 sizing depends on row counts above.")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
