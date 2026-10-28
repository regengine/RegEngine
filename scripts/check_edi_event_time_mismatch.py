#!/usr/bin/env python3
"""Count EDI events whose stored timestamp and EDI event date disagree.

Read-only data check for the EDI two-clocks bug (regengine-ds, sweep P2 5).
An event disagrees when ``fsma.cte_events.event_timestamp`` is more than one
day away from its ``ship_date`` / ``event_date`` KDE. Only rows whose
``source`` starts with ``edi`` are counted (EDI ingest paths).

Safety:
* The query runs inside ``SET TRANSACTION READ ONLY`` and is rolled back.
* Fail-closed host allow-list: only localhost / loopback / local compose
  hosts run by default. Pass ``--allow-host HOST`` for a remote scratch DB.
  ``REGENGINE_ENV`` / ``ENVIRONMENT`` / ``ENV`` naming production always
  refuses. Never prints the database URL.
* Bare ``postgresql://`` URLs are rewritten to ``postgresql+psycopg://``
  (psycopg 3; psycopg2 is not installed).
* Tenant scope: pass ``--tenant-id UUID`` (sets ``app.tenant_id``) or
  ``--all-tenants`` (requires a role that bypasses RLS). Ordinary
  ``DATABASE_URL`` (``regengine`` role) cannot scan all tenants.

Usage: python scripts/check_edi_event_time_mismatch.py --database-url URL \\
           --tenant-id UUID
       (or set DATABASE_URL). Prints one integer on stdout: the disagreeing
       count. Calendar-invalid date KDEs are skipped and reported on stderr.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional, Sequence
from urllib.parse import parse_qs, urlsplit

# ``shared.*`` lives under services/
_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "services"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.db_url import sync_postgres_url  # noqa: E402

TOLERANCE = timedelta(days=1)
DATE_KDE_KEYS = ("ship_date", "event_date")

# Affirmative allow-list of hosts this diagnostic may touch by default.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DEV_COMPOSE_HOSTS = frozenset({"postgres", "host.docker.internal"})
LOCAL_HOSTS = LOOPBACK_HOSTS | DEV_COMPOSE_HOSTS

_PROD_ENV_VALUES = frozenset({"prod", "production"})

# ISO-looking scalar that survives to_date round-trip (rejects 2026-02-30).
_VALID_ISO_DATE = (
    "(k.kde_value #>> '{}') ~ '^\\d{4}-\\d{2}-\\d{2}$' "
    "AND to_char(to_date((k.kde_value #>> '{}'), 'YYYY-MM-DD'), 'YYYY-MM-DD') "
    "= (k.kde_value #>> '{}')"
)

MISMATCH_SQL = f"""
SELECT COUNT(DISTINCT e.id)
  FROM fsma.cte_events e
  JOIN fsma.cte_kdes k
    ON k.cte_event_id = e.id
   AND k.tenant_id = e.tenant_id
   AND k.kde_key IN ('ship_date', 'event_date')
 WHERE e.source LIKE 'edi%'
   AND {_VALID_ISO_DATE}
   AND (e.event_timestamp < (to_date((k.kde_value #>> '{{}}'), 'YYYY-MM-DD')::timestamp AT TIME ZONE 'UTC') - INTERVAL '1 day'
        OR e.event_timestamp > (to_date((k.kde_value #>> '{{}}'), 'YYYY-MM-DD')::timestamp AT TIME ZONE 'UTC') + INTERVAL '2 days')
"""
# fsma.cte_kdes.kde_value is JSONB (since v078); ``#>> '{{}}'`` extracts the
# scalar as text before matching and casting, as compliance_score.py does.
# ``to_date`` + round-trip equality drops calendar-invalid strings (e.g.
# 2026-02-30) so the query returns a count instead of aborting.
# ``e.source LIKE 'edi%'`` keeps this EDI-only (edi_inbound, edi_856_inbound, …).
# COUNT(DISTINCT e.id) counts each event once even when it carries both a
# ship_date and an event_date KDE.

INVALID_DATE_SQL = f"""
SELECT COUNT(*)
  FROM fsma.cte_kdes k
  JOIN fsma.cte_events e
    ON e.id = k.cte_event_id
   AND e.tenant_id = k.tenant_id
 WHERE e.source LIKE 'edi%'
   AND k.kde_key IN ('ship_date', 'event_date')
   AND (k.kde_value #>> '{{}}') ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$'
   AND NOT (
     to_char(to_date((k.kde_value #>> '{{}}'), 'YYYY-MM-DD'), 'YYYY-MM-DD')
     = (k.kde_value #>> '{{}}')
   )
"""


def is_mismatch(event_timestamp: datetime, event_date: date, tolerance: timedelta = TOLERANCE) -> bool:
    """True when the timestamp is more than ``tolerance`` outside ``event_date``."""
    day_start = datetime(event_date.year, event_date.month, event_date.day, tzinfo=event_timestamp.tzinfo)
    day_end = day_start + timedelta(days=1)
    return event_timestamp < day_start - tolerance or event_timestamp > day_end + tolerance


def count_mismatches(rows: Iterable[tuple[datetime, date]], tolerance: timedelta = TOLERANCE) -> int:
    return sum(1 for ts, d in rows if is_mismatch(ts, d, tolerance))


def _effective_db_hosts(database_url: str) -> list[str]:
    """Authority host plus any libpq ``host`` / ``hostaddr`` query values."""
    hosts: list[str] = []
    try:
        parts = urlsplit(database_url)
    except ValueError:
        return [""]
    if parts.hostname:
        hosts.append(parts.hostname.lower())
    try:
        query = parse_qs(parts.query)
    except ValueError:
        return hosts or [""]
    for key in ("host", "hostaddr"):
        for value in query.get(key, []):
            hosts.extend(h.strip().lower() for h in value.split(",") if h.strip())
    return hosts or [""]


def refuse_production(
    database_url: str,
    env: Optional[dict] = None,
    allowed_hosts: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Return a refusal reason, or None when the target is allowed.

    Fail-closed allow-list: every effective host must be in LOCAL_HOSTS or in
    ``allowed_hosts`` (from ``--allow-host``). Env vars naming production
    always refuse, even for localhost.
    """
    env = os.environ if env is None else env
    for name in ("REGENGINE_ENV", "ENVIRONMENT", "ENV"):
        if str(env.get(name, "")).lower() in _PROD_ENV_VALUES:
            return f"{name} names production"
    permit = set(LOCAL_HOSTS)
    if allowed_hosts:
        permit.update(h.strip().lower() for h in allowed_hosts if h and h.strip())
    hosts = _effective_db_hosts(database_url)
    if not hosts or any(not h for h in hosts):
        return "database URL host could not be parsed"
    bad = [h for h in hosts if h not in permit]
    if bad:
        shown = ", ".join(bad)
        return f"host(s) not on the local allow-list: {shown} (pass --allow-host for a remote scratch database)"
    return None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument(
        "--allow-host",
        action="append",
        default=[],
        metavar="HOST",
        help="Permit a non-local host (repeatable). For remote scratch DBs only.",
    )
    parser.add_argument(
        "--tenant-id",
        default=None,
        metavar="UUID",
        help="Scope the count to one tenant (sets app.tenant_id for RLS).",
    )
    parser.add_argument(
        "--all-tenants",
        action="store_true",
        help="Scan every tenant. Requires a role that bypasses RLS (not the ordinary DATABASE_URL / regengine role).",
    )
    args = parser.parse_args(argv)
    if not args.database_url:
        print("error: --database-url or DATABASE_URL required", file=sys.stderr)
        return 2
    if bool(args.tenant_id) == bool(args.all_tenants):
        print(
            "error: pass exactly one of --tenant-id UUID or --all-tenants",
            file=sys.stderr,
        )
        return 2
    reason = refuse_production(args.database_url, allowed_hosts=args.allow_host)
    if reason:
        print(f"refusing to run: {reason}", file=sys.stderr)
        return 3

    from sqlalchemy import create_engine, text

    engine = create_engine(sync_postgres_url(args.database_url))
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            if args.tenant_id:
                conn.execute(
                    text("SELECT set_config('app.tenant_id', :tid, true)"),
                    {"tid": args.tenant_id},
                )
            try:
                count = conn.execute(text(MISMATCH_SQL)).scalar_one()
                invalid = conn.execute(text(INVALID_DATE_SQL)).scalar_one()
            except Exception as exc:  # noqa: BLE001 - surface RLS hint, then re-raise path
                message = str(exc)
                if "app.tenant_id not set" in message or "insufficient_privilege" in message:
                    print(
                        "error: row-level security blocked the query. "
                        "Pass --tenant-id UUID, or connect with a role that "
                        "bypasses RLS and pass --all-tenants.",
                        file=sys.stderr,
                    )
                    return 4
                raise
        finally:
            trans.rollback()
    if int(invalid) > 0:
        print(f"invalid_date_kdes: {int(invalid)}", file=sys.stderr)
    print(int(count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
