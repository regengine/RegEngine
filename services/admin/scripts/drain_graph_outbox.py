"""Simple cron entry point for draining the graph_outbox (#1398).

Usage:

    python -m services.admin.scripts.drain_graph_outbox [--batch-size 100]

Intended to be wrapped by whatever scheduler we use (cron, Railway cron,
or the ``fsma.task_queue`` worker). Self-contained so that it can run in
a minimal container image without pulling in the full FastAPI app.

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
        help="Drain a single batch and exit (default). If absent the "
        "caller is expected to re-invoke via cron.",
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
    driver = supplier_graph_sync.current_driver()
    if not supplier_graph_sync.enabled or driver is None:
        logger.warning("neo4j_driver_unavailable_skipping_drain")
        return 0

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
