#!/usr/bin/env python3
"""One-time backfill for Decision 3 (Oct 8, 2026) Obligation quarantine.

Background: linker reads in services/graph/app/traceability_linker.py now
share an Obligation row across tenants only when it carries
``catalog = true``. Catalog writers (regulation_loader,
supplier_graph_sync) stamp new rows on creation, but rows written before
this change have no marker. Run this script BEFORE deploying the
quarantine predicate, or regulation lookups go empty for every tenant.

What it marks: null-tenant Obligation rows matching a catalog-writer
shape, which is rows with an ``obligation_id`` (supplier_graph_sync) or
rows with ``text`` linked from a Section by :REQUIRES (regulation_loader).

What it leaves alone: null-tenant rows matching neither shape stay
unmarked and therefore hidden from every tenant after the deploy. The
script prints their count and a sample of ids so an operator can review
them. Marking is create-safe and idempotent: rows already carrying
``catalog = true`` are never touched, so reruns are harmless.

Usage (defaults to dry run, which changes nothing):
  python3 scripts/backfill_obligation_catalog.py --dry-run
  python3 scripts/backfill_obligation_catalog.py --apply

Connection: NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD from the environment.
"""

from __future__ import annotations

import argparse
import os
import sys

MARK_CANDIDATES_CYPHER = """
MATCH (o:Obligation)
WHERE o.tenant_id IS NULL
  AND (o.catalog IS NULL OR o.catalog <> true)
  AND (o.obligation_id IS NOT NULL OR (o)<-[:REQUIRES]-(:Section))
RETURN count(o) AS n
"""

QUARANTINED_CYPHER = """
MATCH (o:Obligation)
WHERE o.tenant_id IS NULL
  AND (o.catalog IS NULL OR o.catalog <> true)
  AND o.obligation_id IS NULL
  AND NOT (o)<-[:REQUIRES]-(:Section)
RETURN count(o) AS n, collect(o.id)[..25] AS sample_ids
"""

MARK_APPLY_CYPHER = """
MATCH (o:Obligation)
WHERE o.tenant_id IS NULL
  AND (o.catalog IS NULL OR o.catalog <> true)
  AND (o.obligation_id IS NOT NULL OR (o)<-[:REQUIRES]-(:Section))
WITH o LIMIT $batch
SET o.catalog = true
RETURN count(o) AS marked
"""


def _connect():
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    if not password:
        raise SystemExit("NEO4J_PASSWORD is empty; refusing to connect.")
    return GraphDatabase.driver(uri, auth=(user, password))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill catalog = true on Obligation rows.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="Count only; change nothing (default).")
    mode.add_argument("--apply", action="store_true", help="Actually set catalog = true on catalog-shaped rows.")
    parser.add_argument("--batch", type=int, default=1000, help="Rows marked per write transaction.")
    args = parser.parse_args(argv)

    # --apply flips the default dry run off; --dry-run is explicit.
    apply = args.apply
    driver = _connect()
    try:
        with driver.session() as session:
            candidates = session.run(MARK_CANDIDATES_CYPHER).single()["n"]
            left = session.run(QUARANTINED_CYPHER).single()
            print(f"catalog-shaped null-tenant rows to mark: {candidates}")
            print(f"unshaped null-tenant rows left quarantined: {left['n']}")
            if left["n"]:
                print(f"quarantined sample ids: {left['sample_ids']}")
            if not apply:
                print("dry run: no writes made. Rerun with --apply to mark rows.")
                return 0
            total = 0
            while True:
                marked = session.run(MARK_APPLY_CYPHER, batch=args.batch).single()["marked"]
                total += marked
                if marked < args.batch:
                    break
            print(f"marked catalog = true on {total} rows.")
            if total != candidates:
                print("warning: marked count differs from the dry-run count; rerun to converge.")
                return 1
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
