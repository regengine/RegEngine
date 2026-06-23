"""Backfill keyed email fingerprints for existing user_emails rows.

Usage:

    python -m services.admin.scripts.backfill_email_fingerprints --batch-size 500

The fingerprint must be produced by AuthCryptoService so login challenge rows
can resolve existing users without storing or comparing plaintext email.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

_SERVICE_DIR = Path(__file__).resolve().parents[1]
_SERVICES_DIR = _SERVICE_DIR.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))


def backfill_email_fingerprints(
    *,
    batch_size: int = 500,
    dry_run: bool = False,
    session_factory: Callable[[], Session] | None = None,
    crypto_service=None,
) -> int:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    if session_factory is None:
        from app.database import SessionLocal

        session_factory = SessionLocal
    if crypto_service is None:
        from app.auth_crypto import AuthCryptoService

        crypto_service = AuthCryptoService()

    from app.sqlalchemy_models import UserEmailModel

    total = 0
    session = session_factory()
    try:
        while True:
            rows = (
                session.execute(
                    select(UserEmailModel)
                    .where(UserEmailModel.email_fingerprint.is_(None))
                    .order_by(UserEmailModel.id)
                    .limit(batch_size)
                )
                .scalars()
                .all()
            )
            if not rows:
                break

            for row in rows:
                row.email_fingerprint = crypto_service.fingerprint_email(row.email)

            total += len(rows)
            if dry_run:
                session.rollback()
                break
            session.commit()
        return total
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    total = backfill_email_fingerprints(batch_size=args.batch_size, dry_run=args.dry_run)
    mode = "would backfill" if args.dry_run else "backfilled"
    print(f"{mode} {total} user_emails row(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
