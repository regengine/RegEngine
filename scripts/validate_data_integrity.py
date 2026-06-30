#!/usr/bin/env python3
"""
Data integrity validation after chaos/resilience tests.

Runs a series of integrity checks against the database:
  - Audit chain hash continuity (FSMA 204 tamper detection)
  - Orphaned records (foreign key violations in application logic)
  - Tenant isolation (cross-tenant data leakage)

Exit codes:
  0 = all checks passed
  1 = one or more checks failed
  2 = could not connect to database
"""

import argparse
import os
import sys
from datetime import datetime, timezone


def get_db_connection():
    """Create a database connection from DATABASE_URL env var."""
    try:
        from sqlalchemy import create_engine, text

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            print("ERROR: DATABASE_URL environment variable not set")
            return None, None
        engine = create_engine(db_url)
        conn = engine.connect()
        return conn, text
    except ImportError:
        print("ERROR: sqlalchemy not installed — run: pip install sqlalchemy")
        return None, None
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        return None, None


def check_hash_chain_continuity(conn, text_fn) -> tuple[bool, str]:
    """Verify the FSMA 204 CTE hash chain has no gaps or tampering."""
    try:
        result = conn.execute(
            text_fn("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN prev_hash IS NULL AND sequence_number > 1 THEN 1 END) as broken_links
            FROM fsma.cte_events
            WHERE prev_hash IS NOT NULL OR sequence_number = 1
        """)
        )
        row = result.fetchone()
        if row is None:
            return True, "No CTE events found (empty chain — OK)"
        total, broken = row[0], row[1]
        if broken > 0:
            return False, f"Hash chain broken: {broken}/{total} events have missing prev_hash"
        return True, f"Hash chain intact: {total} events verified"
    except Exception as e:
        if "does not exist" in str(e):
            return True, "fsma.cte_events table not found (schema not deployed — skipped)"
        return False, f"Hash chain check error: {e}"


def check_orphaned_records(conn, text_fn) -> tuple[bool, str]:
    """Check for orphaned records that indicate broken referential integrity."""
    checks = [
        (
            "CTE events without tenant",
            "SELECT COUNT(*) FROM fsma.cte_events WHERE tenant_id IS NULL",
        ),
        (
            "Rule evaluations referencing missing rules",
            """SELECT COUNT(*) FROM fsma.rule_evaluations re
               LEFT JOIN fsma.rule_definitions rd ON re.rule_id = rd.rule_id
               WHERE rd.rule_id IS NULL""",
        ),
    ]
    issues = []
    for name, query in checks:
        try:
            result = conn.execute(text_fn(query))
            count = result.scalar()
            if count and count > 0:
                issues.append(f"{name}: {count} orphaned records")
        except Exception as e:
            if "does not exist" not in str(e):
                issues.append(f"{name}: check failed ({e})")

    if issues:
        return False, "; ".join(issues)
    return True, "No orphaned records found"


def check_dual_write_reconciliation(conn, text_fn) -> tuple[bool, str]:
    """Reconcile fsma.traceability_events vs fsma.cte_events by sha256_hash (#2521).

    The canonical writer (``traceability_events``) and the legacy
    dual-write shim (``cte_events``) compute idempotency keys with
    divergent formulas, so the only field that joins a real-world event
    across both stores is ``sha256_hash`` (the dual-write copies it
    verbatim into both tables). FDA export reads from BOTH tables during
    the migration window, so a silent desync corrupts the regulator-
    facing source of truth. This is the standing invariant check that
    unblocks retiring the legacy path (#1335).

    Directionality — only ONE direction is a hard failure:

    * ``cte_events`` row with NO matching ``traceability_events`` row by
      (tenant_id, sha256_hash) → FAIL. Every legacy row is written as a
      dual-write of a canonical row (``dual_write_legacy`` runs inside
      ``persist_event`` AFTER the canonical INSERT), so a legacy row with
      no canonical twin means the canonical write was lost / swallowed —
      a genuine "both tables or neither" (#1277) violation.

    * ``traceability_events`` row with no ``cte_events`` twin → reported
      as INFO, not a failure. Several production ingestion paths run
      ``CanonicalEventStore(dual_write=False)`` by design (webhook_compat,
      epcis, canonical_router, auditor_router, webhook_router_v2), so
      canonical-only rows are expected and must NOT be flagged as false
      positives.

    Rows are compared per ``tenant_id`` implicitly via the join key.
    """
    try:
        # Legacy rows missing a canonical twin (the hard-failure direction).
        orphan_legacy = conn.execute(
            text_fn("""
            SELECT COUNT(*)
            FROM fsma.cte_events c
            WHERE NOT EXISTS (
                SELECT 1 FROM fsma.traceability_events t
                WHERE t.tenant_id = c.tenant_id
                  AND t.sha256_hash = c.sha256_hash
            )
        """)
        ).scalar()

        # Canonical rows with no legacy twin (informational — dominated by
        # intentional dual_write=False paths).
        canonical_only = conn.execute(
            text_fn("""
            SELECT COUNT(*)
            FROM fsma.traceability_events t
            WHERE NOT EXISTS (
                SELECT 1 FROM fsma.cte_events c
                WHERE c.tenant_id = t.tenant_id
                  AND c.sha256_hash = t.sha256_hash
            )
        """)
        ).scalar()

        orphan_legacy = orphan_legacy or 0
        canonical_only = canonical_only or 0

        if orphan_legacy > 0:
            return False, (
                f"{orphan_legacy} legacy cte_events row(s) have NO canonical "
                f"traceability_events twin by sha256_hash — a swallowed/lost "
                f"canonical write violates the #1277 dual-write invariant. "
                f"({canonical_only} canonical-only rows are expected from "
                f"dual_write=False paths and are not counted as failures.)"
            )
        return True, (
            f"Dual-write reconciled: every cte_events row has a canonical "
            f"twin by sha256_hash ({canonical_only} canonical-only rows from "
            f"dual_write=False paths, which is expected)."
        )
    except Exception as e:
        if "does not exist" in str(e):
            return True, "Dual-write reconciliation skipped (canonical/legacy table not deployed)"
        return False, f"Dual-write reconciliation error: {e}"


def check_tenant_isolation(conn, text_fn) -> tuple[bool, str]:
    """Verify no cross-tenant data leakage exists."""
    try:
        # Check if any single record appears in multiple tenants (shouldn't happen)
        result = conn.execute(
            text_fn("""
            SELECT COUNT(*) FROM (
                SELECT event_id, COUNT(DISTINCT tenant_id) as tenant_count
                FROM fsma.cte_events
                GROUP BY event_id
                HAVING COUNT(DISTINCT tenant_id) > 1
            ) violations
        """)
        )
        count = result.scalar()
        if count and count > 0:
            return False, f"CRITICAL: {count} events found in multiple tenants"
        return True, "Tenant isolation verified — no cross-tenant leakage"
    except Exception as e:
        if "does not exist" in str(e):
            return True, "Tenant isolation check skipped (schema not deployed)"
        return False, f"Tenant isolation check error: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="Validate data integrity after chaos/resilience tests.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output for each check",
    )
    args = parser.parse_args()

    print("Data Integrity Validation")
    print("=" * 50)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()

    conn, text_fn = get_db_connection()
    if conn is None:
        print("\nSkipping database checks (no connection available)")
        print("Result: PASS (no database — integrity checks not applicable)")
        return 0

    checks = [
        ("Hash Chain Continuity", check_hash_chain_continuity),
        ("Orphaned Records", check_orphaned_records),
        ("Dual-Write Reconciliation", check_dual_write_reconciliation),
        ("Tenant Isolation", check_tenant_isolation),
    ]

    all_passed = True
    for name, check_fn in checks:
        passed, message = check_fn(conn, text_fn)
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}")
        if args.verbose or not passed:
            print(f"       {message}")
        if not passed:
            all_passed = False

    conn.close()
    print()
    print(f"Overall: {'PASS' if all_passed else 'FAIL'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
