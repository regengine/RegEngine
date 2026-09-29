"""libpq connection-liveness settings for long-lived Postgres engines.

Without these, a thread whose Postgres server dies mid-query can block
forever on a half-open TCP socket: libpq waits in ``recv()`` for a reply
that never comes, and neither the OS nor SQLAlchemy ever times it out.
Railway restarts Postgres for PITR changes and weekend security updates;
on 2026-09-28 one such restart wedged the remediation notification drain
job (``max_instances=1``) until the service was redeployed.

- ``connect_timeout`` bounds each connection attempt (TCP, TLS and auth).
- ``keepalives_*`` make the kernel probe an idle socket and fail it after
  ~60s without a reply (30s idle + 3 probes x 10s).
- ``tcp_user_timeout`` fails a socket whose *sent* data stays
  unacknowledged for 60s. The kernel suspends keepalive probes while data
  is in flight, so this covers a pre-ping or query written to a dead peer
  (Linux otherwise retransmits for ~15 minutes). Ignored where the OS has
  no ``TCP_USER_TIMEOUT`` (macOS).

None of these fire while a live server is merely slow: a long query is
fine as long as the server's kernel keeps acknowledging packets.
"""

from __future__ import annotations

# Same prefixes the readiness probe (server/main.py) treats as libpq URLs.
_LIBPQ_URL_PREFIXES = ("postgresql:", "postgresql+psycopg:", "postgresql+psycopg2:", "postgres:")


def postgres_liveness_connect_args(url: str) -> dict[str, int]:
    """Return libpq ``connect_args`` for a psycopg2/psycopg URL, else ``{}``.

    psycopg2 and psycopg 3 both hand unknown keywords to libpq, so one dict
    serves both drivers. Other dialects (SQLite in tests, asyncpg) reject
    these keywords, so they get nothing.
    """
    if not str(url).startswith(_LIBPQ_URL_PREFIXES):
        return {}
    return {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
        "tcp_user_timeout": 60_000,  # milliseconds
    }
