#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run-migrations.sh — Idempotent Alembic migration runner with distributed lock
#
# Uses PostgreSQL advisory lock to prevent concurrent migration execution
# across multiple service instances (e.g. Railway scaling events).
#
# Safe for both fresh databases and existing ones:
#   - If alembic_version table exists and is populated → just run upgrade
#   - If tables exist but alembic_version doesn't → stamp + upgrade (adopting Alembic)
#   - If nothing exists → full upgrade from scratch
#
# Lock acquisition uses pg_try_advisory_lock with bounded retries so a
# zombie lock held by a crashed prior deploy fails LOUDLY (stderr, non-zero exit)
# within MIGRATION_LOCK_TIMEOUT_S seconds instead of hanging silently past
# Railway's healthcheck window. See incident 2026-04-17 through 2026-04-20.
#
# Usage:  DATABASE_URL=postgresql://... ./scripts/run-migrations.sh
# ---------------------------------------------------------------------------
set -euo pipefail

# Advisory lock ID for migrations (distinct from scheduler lock 4294967295)
MIGRATION_LOCK_ID=4294967294

# Max seconds to wait for the migration lock before giving up with a hard error.
# Railway's default healthcheck retry window is 2 minutes, so we give up at 90 s
# to leave room for the actual migration + app boot after the lock is acquired.
MIGRATION_LOCK_TIMEOUT_S=${MIGRATION_LOCK_TIMEOUT_S:-90}

echo "==> Acquiring migration advisory lock (id=${MIGRATION_LOCK_ID}, timeout=${MIGRATION_LOCK_TIMEOUT_S}s)..."

# Wrap entire migration in a Python script that holds an advisory lock.
# pg_try_advisory_lock returns immediately with true/false — we poll with
# exponential backoff so a zombie holder causes a loud failure, not a silent hang.
python -c "
import os, sys, subprocess, time

from sqlalchemy import create_engine, text

url = os.environ.get('DATABASE_URL', 'postgresql://regengine:regengine@postgres:5432/regengine')
timeout_s = int(os.environ.get('MIGRATION_LOCK_TIMEOUT_S', '${MIGRATION_LOCK_TIMEOUT_S}'))
engine = create_engine(url)

with engine.connect() as conn:
    conn.execution_options(isolation_level='AUTOCOMMIT')

    # Poll pg_try_advisory_lock with exponential backoff up to timeout_s.
    # This is the key behavior change vs pg_advisory_lock: we never block
    # the container past the healthcheck window — we either get the lock
    # or exit non-zero with a diagnostic so Railway shows a real error.
    deadline = time.monotonic() + timeout_s
    delay = 0.5
    attempt = 0
    while True:
        attempt += 1
        got = conn.execute(text('SELECT pg_try_advisory_lock(${MIGRATION_LOCK_ID})')).scalar()
        if got:
            print(f'==> Migration lock acquired (attempt {attempt})', flush=True)
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # Surface the holder so the operator can kill it or unlock manually.
            holder = conn.execute(text(
                \"SELECT pid, application_name, state, state_change \"
                \"FROM pg_stat_activity a JOIN pg_locks l ON l.pid = a.pid \"
                \"WHERE l.locktype = 'advisory' AND l.objid = ${MIGRATION_LOCK_ID}\"
            )).fetchall()
            print(
                f'!! Could not acquire migration lock within {timeout_s}s after {attempt} attempts.',
                file=sys.stderr, flush=True,
            )
            print(f'!! Current holder(s): {holder!r}', file=sys.stderr, flush=True)
            print(
                '!! Remediation: connect to Postgres and run '
                'SELECT pg_advisory_unlock(${MIGRATION_LOCK_ID}); '
                'or terminate the zombie backend with pg_terminate_backend(pid).',
                file=sys.stderr, flush=True,
            )
            sys.exit(75)  # EX_TEMPFAIL — Railway will mark deploy failed, ops can retry
        sleep_for = min(delay, remaining)
        print(f'    lock busy, retrying in {sleep_for:.1f}s (attempt {attempt}, {remaining:.0f}s left)', flush=True)
        time.sleep(sleep_for)
        delay = min(delay * 1.5, 5.0)

    try:
        # ---- Detect DB state ----
        result = conn.execute(text(
            \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'alembic_version')\"
        ))
        has_alembic = result.scalar()

        if not has_alembic:
            result2 = conn.execute(text(
                \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'fsma')\"
            ))
            state = 'NEEDS_STAMP' if result2.scalar() else 'FRESH'
        else:
            result3 = conn.execute(text('SELECT count(*) FROM alembic_version'))
            if result3.scalar() > 0:
                state = 'ALREADY_MANAGED'
            else:
                result4 = conn.execute(text(
                    \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'fsma')\"
                ))
                state = 'NEEDS_STAMP' if result4.scalar() else 'FRESH'

        print(f'    DB state: {state}', flush=True)

        # ---- Run migrations ----
        if state == 'NEEDS_STAMP':
            print('==> Existing database detected — stamping as baseline...', flush=True)
            subprocess.check_call(['alembic', 'stamp', 'head'])
            print('==> Stamped. Running any newer migrations...', flush=True)
            subprocess.check_call(['alembic', 'upgrade', 'head'])
        elif state == 'ALREADY_MANAGED':
            print('==> Alembic already managing this database — upgrading...', flush=True)
            subprocess.check_call(['alembic', 'upgrade', 'head'])
        else:
            print('==> Fresh database — running full migration...', flush=True)
            subprocess.check_call(['alembic', 'upgrade', 'head'])

        print('==> Migrations complete.', flush=True)

    finally:
        conn.execute(text('SELECT pg_advisory_unlock(${MIGRATION_LOCK_ID})'))
        print('==> Migration lock released', flush=True)
"
