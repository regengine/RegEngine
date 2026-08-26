#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run-migrations.sh — Idempotent Alembic migration runner with distributed lock
#
# Uses PostgreSQL advisory lock to prevent concurrent migration execution
# across multiple service instances (e.g. Railway scaling events).
#
# Safe for both fresh databases and existing ones:
#   - alembic_version exists AND holds a revision  → `alembic upgrade head`
#   - no RegEngine schema at all (truly empty DB)  → `alembic upgrade head`
#     (the chain runs from base, so no stamping is involved)
#   - RegEngine schema present but alembic_version missing/EMPTY → AMBIGUOUS.
#     We cannot tell how much of the chain is applied, so we FAIL LOUDLY and
#     require an explicit operator opt-in (REGENGINE_ALLOW_AUTO_STAMP=1).
#
# #2826: this last branch used to be decided purely from "does an `fsma`
# schema exist" — true for every database that ever ran the V002 baseline —
# and then ran `alembic stamp head`, which marks the database as fully
# migrated without applying anything. The following `alembic upgrade head`
# became a no-op and ~70 revisions (RLS policies included) never applied.
# Auto-stamping an unknown database is unsafe in BOTH directions:
#   - stamp too high → migrations silently skipped (the #2826 bug)
#   - stamp too low  → the chain replays DDL over existing objects
# so the ambiguous case is now an operator decision, not a guess. When the
# operator does opt in, we stamp the BASELINE revision
# (REGENGINE_AUTO_STAMP_REVISION, default 97588ba8edf3) so the subsequent
# `alembic upgrade head` actually replays the chain.
#
# Lock acquisition uses pg_try_advisory_xact_lock with bounded retries so a
# blocked deploy fails LOUDLY (stderr, non-zero exit) within
# MIGRATION_LOCK_TIMEOUT_S seconds instead of hanging silently past Railway's
# healthcheck window. Transaction-scoped locks are intentional here: Supavisor
# and other poolers can strand session-level advisory locks after a client
# disconnect, but PostgreSQL automatically releases transaction locks when the
# transaction ends or the backend dies. See incident 2026-04-17 through
# 2026-04-20.
#
# Usage:  DATABASE_URL=postgresql://... ./scripts/run-migrations.sh
# ---------------------------------------------------------------------------
set -euo pipefail

# #2826 operator opt-in for the AMBIGUOUS case (RegEngine schema present but
# alembic_version missing/empty). Unset/0 => refuse to guess and exit non-zero.
REGENGINE_ALLOW_AUTO_STAMP=${REGENGINE_ALLOW_AUTO_STAMP:-0}
# Revision stamped before replaying the chain when auto-stamp is authorised.
# Defaults to the consolidated V002–V042 baseline. An operator who knows the
# database is further along may point this at the revision it really is at.
REGENGINE_AUTO_STAMP_REVISION=${REGENGINE_AUTO_STAMP_REVISION:-97588ba8edf3}  # pragma: allowlist secret
export REGENGINE_ALLOW_AUTO_STAMP REGENGINE_AUTO_STAMP_REVISION

# Advisory lock ID for migrations (distinct from scheduler lock 4294967295)
MIGRATION_LOCK_ID=4294967294

# Max seconds to wait for the migration lock before giving up with a hard error.
# Railway's default healthcheck retry window is 2 minutes, so we give up at 90 s
# to leave room for the actual migration + app boot after the lock is acquired.
MIGRATION_LOCK_TIMEOUT_S=${MIGRATION_LOCK_TIMEOUT_S:-90}

# #2461: after the least-privilege cutover the runtime DATABASE_URL connects
# as the RLS-enforced `regengine` role, which does not own the schema.
# Migrations (DDL) must keep running as the owner role, so when
# MIGRATIONS_DATABASE_URL is set (Railway production) it overrides
# DATABASE_URL for this runner and the alembic subprocesses it spawns. The
# override is scoped to this script's process tree — the app that starts
# after this script still sees the original runtime DATABASE_URL. CI and
# local dev set only DATABASE_URL; behavior there is unchanged.
if [ -n "${MIGRATIONS_DATABASE_URL:-}" ]; then
  DATABASE_URL="${MIGRATIONS_DATABASE_URL}"
  export DATABASE_URL
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "!! DATABASE_URL must be set before running migrations." >&2
  echo "!! Refusing to fall back to development database defaults in deploy/runtime paths." >&2
  exit 64  # EX_USAGE
fi

PYTHON_BIN=${PYTHON_BIN:-python3}
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
  else
    echo "!! Neither python3 nor python is available for migration runner." >&2
    exit 69  # EX_UNAVAILABLE
  fi
fi

echo "==> Acquiring migration advisory lock (id=${MIGRATION_LOCK_ID}, timeout=${MIGRATION_LOCK_TIMEOUT_S}s)..."

# Wrap entire migration in a Python script that holds an advisory transaction
# lock. pg_try_advisory_xact_lock returns immediately with true/false — we poll
# with exponential backoff so a busy holder causes a loud failure, not a silent
# hang.
${PYTHON_BIN} -c "
import os, sys, subprocess, time

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

url = os.environ['DATABASE_URL']
timeout_s = int(os.environ.get('MIGRATION_LOCK_TIMEOUT_S', '${MIGRATION_LOCK_TIMEOUT_S}'))
# NullPool: closing a connection really disconnects it instead of parking an
# idle backend in the pool for the whole alembic run — the probe connection
# below must be physically gone, not just checked in, before migrations start.
engine = create_engine(url, pool_pre_ping=True, poolclass=NullPool)

conn = engine.connect()
tx = conn.begin()
lock_acquired = False

try:
    # Poll pg_try_advisory_xact_lock with exponential backoff up to timeout_s.
    # This is the key behavior change vs pg_advisory_lock: we never block
    # the container past the healthcheck window — we either get the lock
    # or exit non-zero with a diagnostic so Railway shows a real error.
    deadline = time.monotonic() + timeout_s
    delay = 0.5
    attempt = 0
    while True:
        attempt += 1
        got = conn.execute(text('SELECT pg_try_advisory_xact_lock(${MIGRATION_LOCK_ID})')).scalar()
        if got:
            lock_acquired = True
            print(f'==> Migration lock acquired (attempt {attempt})', flush=True)
            # This backend now sits idle-in-transaction while alembic runs in a
            # subprocess. A server-side idle_in_transaction_session_timeout (or
            # transaction_timeout, PG 17+) would terminate it and silently
            # release the advisory lock mid-migration — disable both for this
            # session. SET takes no relation locks.
            conn.execute(text(\"SET idle_in_transaction_session_timeout = 0\"))
            if int(conn.execute(text('SHOW server_version_num')).scalar()) >= 170000:
                conn.execute(text(\"SET transaction_timeout = 0\"))
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # Surface the holder so the operator can terminate the stale backend.
            # A 1-arg bigint advisory lock shows its high 32 bits in classid and
            # low 32 bits in objid with objsubid=1; filter on all three plus
            # granted, or waiters and unrelated 2-arg locks get reported (and
            # the remediation below would terminate an innocent backend).
            holder = conn.execute(text(
                \"SELECT a.pid, a.application_name, a.state, a.state_change \"
                \"FROM pg_stat_activity a JOIN pg_locks l ON l.pid = a.pid \"
                \"WHERE l.locktype = 'advisory' AND l.granted \"
                \"  AND l.classid = ((${MIGRATION_LOCK_ID}::bigint >> 32) & 4294967295)::oid \"
                \"  AND l.objid = (${MIGRATION_LOCK_ID}::bigint & 4294967295)::oid \"
                \"  AND l.objsubid = 1\"
            )).fetchall()
            print(
                f'!! Could not acquire migration lock within {timeout_s}s after {attempt} attempts.',
                file=sys.stderr, flush=True,
            )
            print(f'!! Current holder(s): {holder!r}', file=sys.stderr, flush=True)
            print(
                '!! Remediation: connect to Postgres and run '
                'SELECT pg_terminate_backend(pid) for any stale holder shown above, '
                'then retry the Railway deployment.',
                file=sys.stderr, flush=True,
            )
            tx.rollback()
            sys.exit(75)  # EX_TEMPFAIL — Railway will mark deploy failed, ops can retry
        sleep_for = min(delay, remaining)
        print(f'    lock busy, retrying in {sleep_for:.1f}s (attempt {attempt}, {remaining:.0f}s left)', flush=True)
        time.sleep(sleep_for)
        delay = min(delay * 1.5, 5.0)

    # Keep this transaction open while Alembic runs in its own process. The
    # transaction exists only to own the advisory lock, and PostgreSQL releases
    # it automatically on commit, rollback, disconnect, or process death.
    #
    # The lock-holder transaction must never touch application relations:
    # any SELECT here holds ACCESS SHARE until the transaction ends, and a
    # migration that takes ACCESS EXCLUSIVE on the same relation (v092 runs
    # ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY) then
    # waits on this very connection forever — the runner deadlocks itself
    # (2026-07-15 deploy incident). State probes run on a separate
    # connection that is CLOSED before Alembic starts.
    # ---- Detect DB state (dedicated probe connection) ----
    #
    # #2826: three facts, kept separate, because the old code collapsed them
    # into one 'NEEDS_STAMP' verdict:
    #   has_alembic   — the alembic_version table exists
    #   stamped_rows  — how many revisions it records (0 == knows nothing)
    #   has_schema    — RegEngine relations already exist in this database
    # The presence of the fsma schema proves only that SOMETHING ran (the
    # V002 baseline creates it); it says nothing about how far the chain got.
    probe = engine.connect()
    try:
        has_alembic = bool(probe.execute(text(
            \"SELECT to_regclass('alembic_version') IS NOT NULL\"
        )).scalar())

        stamped_rows = 0
        if has_alembic:
            stamped_rows = probe.execute(text('SELECT count(*) FROM alembic_version')).scalar() or 0

        has_schema = bool(probe.execute(text(
            \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'fsma') \"
            \"    OR to_regclass('public.regulations') IS NOT NULL \"
            \"    OR to_regclass('public.obligations') IS NOT NULL\"
        )).scalar())
    finally:
        probe.close()

    if stamped_rows > 0:
        state = 'ALREADY_MANAGED'
    elif not has_schema:
        state = 'FRESH'
    else:
        state = 'AMBIGUOUS'

    print(
        f'    DB state: {state} '
        f'(alembic_version={has_alembic}, revisions_recorded={stamped_rows}, regengine_schema={has_schema})',
        flush=True,
    )

    # ---- Run migrations ----
    if state == 'ALREADY_MANAGED':
        print('==> Alembic already managing this database — upgrading to head...', flush=True)
        subprocess.check_call(['alembic', 'upgrade', 'head'])
    elif state == 'FRESH':
        print('==> Fresh database — running the full migration chain from base...', flush=True)
        subprocess.check_call(['alembic', 'upgrade', 'head'])
    else:
        # AMBIGUOUS — RegEngine relations exist but alembic_version is absent
        # or empty (partial restore, pre-Alembic bootstrap, manual DELETE).
        # There is no safe guess here, so require an explicit decision.
        allow_auto_stamp = os.environ.get('REGENGINE_ALLOW_AUTO_STAMP', '0')
        # 97588ba8edf3 is the baseline alembic revision id, not a credential.
        stamp_revision = os.environ.get('REGENGINE_AUTO_STAMP_REVISION', '97588ba8edf3')  # pragma: allowlist secret
        if allow_auto_stamp != '1':
            print(
                '!! AMBIGUOUS database state: RegEngine relations exist but the '
                'alembic_version table is missing or holds no revision.',
                file=sys.stderr, flush=True,
            )
            print(
                '!! Refusing to guess. Stamping the wrong revision either skips '
                'migrations silently (the #2826 regression: ~70 revisions, RLS '
                'policies included, never applied) or replays DDL over existing '
                'objects.',
                file=sys.stderr, flush=True,
            )
            print(
                '!! Remediation — establish the real state, then re-deploy:\n'
                '!!   1. Inspect the database and decide which revision it is '
                'actually at (alembic history, compared against the schema).\n'
                '!!   2. Stamp it explicitly:  alembic stamp <revision>\n'
                '!!      then re-deploy so this runner takes the ALREADY_MANAGED '
                'path.\n'
                '!!   3. OR, if the database is known to hold only the '
                'V002-V042 baseline, authorise the automatic path by setting '
                'REGENGINE_ALLOW_AUTO_STAMP=1 (optionally with '
                'REGENGINE_AUTO_STAMP_REVISION=<revision>, default '
                f'{stamp_revision}). The runner then stamps that revision and '
                'replays the remainder of the chain.',
                file=sys.stderr, flush=True,
            )
            tx.rollback()
            sys.exit(78)  # EX_CONFIG — operator decision required
        print(
            f'==> REGENGINE_ALLOW_AUTO_STAMP=1 — stamping baseline revision '
            f'{stamp_revision} (NOT head) so the chain actually replays...',
            flush=True,
        )
        subprocess.check_call(['alembic', 'stamp', stamp_revision])
        print('==> Baseline stamped. Applying every revision after it...', flush=True)
        subprocess.check_call(['alembic', 'upgrade', 'head'])

    print('==> Migrations complete.', flush=True)
    tx.commit()

except BaseException:
    if tx.is_active:
        tx.rollback()
    raise
finally:
    conn.close()
    engine.dispose()
    if lock_acquired:
        print('==> Migration lock transaction closed', flush=True)
"
