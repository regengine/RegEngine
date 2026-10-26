#!/usr/bin/env python3
"""Count events whose stored timestamp and EDI event date disagree.

Read-only data check for the EDI two-clocks bug (regengine-ds, sweep P2 5).
An event disagrees when ``fsma.cte_events.event_timestamp`` is more than one
day away from its ``ship_date`` / ``event_date`` KDE.

Safety:
* The query runs inside ``SET TRANSACTION READ ONLY`` and is rolled back.
* Refuses to run when the database URL or ``REGENGINE_ENV`` / ``ENVIRONMENT``
  names production. Point it at a local or scratch database only.
* Never prints the database URL.

Usage: python scripts/check_edi_event_time_mismatch.py --database-url URL
       (or set DATABASE_URL). Prints one integer: the disagreeing count.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

TOLERANCE = timedelta(days=1)
DATE_KDE_KEYS = ("ship_date", "event_date")

MISMATCH_SQL = """
SELECT COUNT(DISTINCT e.id)
  FROM fsma.cte_events e
  JOIN fsma.cte_kdes k
    ON k.cte_event_id = e.id
   AND k.tenant_id = e.tenant_id
   AND k.kde_key IN ('ship_date', 'event_date')
 WHERE k.kde_value ~ '^\\d{4}-\\d{2}-\\d{2}$'
   AND (e.event_timestamp < (CAST(k.kde_value AS date)::timestamp AT TIME ZONE 'UTC') - INTERVAL '1 day'
        OR e.event_timestamp > (CAST(k.kde_value AS date)::timestamp AT TIME ZONE 'UTC') + INTERVAL '2 days')
"""
# The event date is a calendar day (UTC); its timestamp may fall anywhere in
# it, so a mismatch is more than one day before its start or after its end.
# Mirrors is_mismatch() below. COUNT(DISTINCT e.id) counts each event once
# even when it carries both a ship_date and an event_date KDE.

_PROD_MARKERS = ("prod", "production")


def is_mismatch(event_timestamp: datetime, event_date: date, tolerance: timedelta = TOLERANCE) -> bool:
    """True when the timestamp is more than ``tolerance`` outside ``event_date``."""
    day_start = datetime(event_date.year, event_date.month, event_date.day, tzinfo=event_timestamp.tzinfo)
    day_end = day_start + timedelta(days=1)
    return event_timestamp < day_start - tolerance or event_timestamp > day_end + tolerance


def count_mismatches(rows: Iterable[tuple[datetime, date]], tolerance: timedelta = TOLERANCE) -> int:
    return sum(1 for ts, d in rows if is_mismatch(ts, d, tolerance))


def refuse_production(database_url: str, env: Optional[dict] = None) -> Optional[str]:
    env = os.environ if env is None else env
    for name in ("REGENGINE_ENV", "ENVIRONMENT", "ENV"):
        if str(env.get(name, "")).lower() in _PROD_MARKERS:
            return f"{name} names production"
    if any(marker in database_url.lower() for marker in _PROD_MARKERS):
        return "database URL looks like production"
    return None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    args = parser.parse_args(argv)
    if not args.database_url:
        print("error: --database-url or DATABASE_URL required", file=sys.stderr)
        return 2
    reason = refuse_production(args.database_url)
    if reason:
        print(f"refusing to run: {reason}", file=sys.stderr)
        return 3

    from sqlalchemy import create_engine, text

    engine = create_engine(args.database_url)
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            count = conn.execute(text(MISMATCH_SQL)).scalar_one()
        finally:
            trans.rollback()
    print(int(count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
