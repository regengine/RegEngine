"""Cron entry point for draining the webhook_outbox (#1408).

Usage:

    python -m services.admin.scripts.drain_webhook_outbox [--batch-size 100]

Wrapped by whatever scheduler we use (cron, Railway cron, the
``fsma.task_queue`` worker). Self-contained so it can run in a minimal
container image without mounting the full FastAPI app.

The drainer is idempotent — a row is only marked ``delivered`` after a
2xx response, so running it twice in parallel is safe at the cost of
some wasted work. If we outgrow single-worker throughput, swap
``_claim_pending`` over to ``FOR UPDATE SKIP LOCKED`` — see the
comments in ``webhook_outbox.py``.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Tuple

import structlog


logger = structlog.get_logger("drain_webhook_outbox")


def _build_secret_lookup():
    """Return a callable ``tenant_id -> (url, secret)`` backed by the DB.

    The drainer does NOT reuse the per-request tenant-scoped session;
    it opens its own session as the sysadmin DB role so it can read
    every tenant's settings. Each row is dispatched with the row's
    own tenant_id in the HMAC header.
    """
    from app.database import SessionLocal
    from app.sqlalchemy_models import TenantModel
    from app.metrics import (
        _TENANT_SETTINGS_WEBHOOK_URL_KEY,
        _TENANT_SETTINGS_WEBHOOK_SECRET_KEY,
    )

    def lookup(tenant_id: str) -> Tuple[Optional[str], Optional[str]]:
        session = SessionLocal()
        try:
            tenant = session.get(TenantModel, tenant_id)
            if tenant is None:
                return None, None
            settings = tenant.settings or {}
            url = settings.get(_TENANT_SETTINGS_WEBHOOK_URL_KEY)
            secret = settings.get(_TENANT_SETTINGS_WEBHOOK_SECRET_KEY)
            return url, secret
        finally:
            session.close()

    return lookup


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Drain a single batch and exit (default). If absent the "
            "caller is expected to re-invoke via cron."
        ),
    )
    args = parser.parse_args(argv)

    from app.database import SessionLocal
    from app.webhook_outbox import WebhookOutboxDrainer

    secret_lookup = _build_secret_lookup()

    session = SessionLocal()
    try:
        drainer = WebhookOutboxDrainer(session, secret_lookup=secret_lookup)
        summary = drainer.drain_once(batch_size=args.batch_size)
        logger.info("drain_webhook_outbox_cycle_complete", **summary)
        # Non-zero exit if this cycle produced terminal failures so cron
        # alerting fires.
        return 0 if summary.get("failed", 0) == 0 else 2
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
