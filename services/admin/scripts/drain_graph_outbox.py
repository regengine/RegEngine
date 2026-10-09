"""Simple cron entry point for draining the graph_outbox (#1398).

Usage:

    python -m services.admin.scripts.drain_graph_outbox [--batch-size 100]

Intended to be wrapped by whatever scheduler we use (cron, Railway cron,
or the ``fsma.task_queue`` worker). Self-contained so that it can run in
a minimal container image without pulling in the full FastAPI app.

Exit codes: 0 means the cycle completed (or Neo4j sync is intentionally
disabled in this environment, so there was nothing to drain). 1 means
the drainer could not run because Neo4j is configured but the driver
was unavailable, so cron alerting fires instead of silently reporting
success. 2 means the cycle ran but left terminally failed rows behind.

The drainer is idempotent — a row is only marked ``drained`` after the
Neo4j write succeeds, so running it twice in parallel is safe at the
cost of some wasted work. If we outgrow single-worker throughput, swap
``_claim_pending`` over to ``FOR UPDATE SKIP LOCKED`` — see the comments
in ``graph_outbox.py``.
"""

from __future__ import annotations

import argparse
import sys

import structlog


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Drain a single batch and exit (default). If absent the caller is expected to re-invoke via cron.",
    )
    args = parser.parse_args(argv)

    # Delayed imports so `--help` works without hitting DB / Neo4j envs.
    from app.database import SessionLocal
    from app.graph_outbox import GraphOutboxDrainer
    from app.supplier_graph_sync import supplier_graph_sync  # module-level driver
    from shared.neo4j_tenant_context import session_with_tenant

    logger = structlog.get_logger("drain_graph_outbox")

    # Resolve the current (possibly hot-reloaded) driver via the public
    # accessor — reads the latest credentials from
    # ``shared.secrets_manager`` and rebuilds the driver on rotation. See
    # issue #1410.
    if not supplier_graph_sync.enabled:
        # Neo4j sync is intentionally not configured in this environment,
        # so there is nothing to drain. Exit 0 to keep cron quiet.
        logger.info("neo4j_sync_disabled_skipping_drain")
        return 0
    driver = supplier_graph_sync.current_driver()
    if driver is None:
        # Neo4j is configured but unreachable (or credentials are
        # unusable). Rows stay pending for the next cycle, and the
        # non-zero exit makes cron alerting fire instead of reporting
        # a success that drained nothing.
        logger.error("neo4j_driver_unavailable_drain_aborted")
        return 1

    def factory(tenant_id: str):
        return session_with_tenant(driver, tenant_id)

    session = SessionLocal()
    try:
        drainer = GraphOutboxDrainer(session, neo4j_session_factory=factory)
        summary = drainer.drain_once(batch_size=args.batch_size)
        logger.info("drain_graph_outbox_cycle_complete", **summary)
        # Non-zero exit if there are still-failing rows the drainer gave up
        # on in this cycle so cron alerting fires.
        return 0 if summary.get("failed", 0) == 0 else 2
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
