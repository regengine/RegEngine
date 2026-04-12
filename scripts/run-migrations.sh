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
# Usage:  DATABASE_URL=postgresql://... ./scripts/run-migrations.sh
# ---------------------------------------------------------------------------
set -euo pipefail

# Advisory lock ID for migrations (distinct from scheduler lock 4294967295)
MIGRATION_LOCK_ID=4294967294

echo "==> Acquiring migration advisory lock (id=${MIGRATION_LOCK_ID})..."

# Wrap entire migration in a Python script that holds an advisory lock
# pg_advisory_lock() blocks until the lock is available — safe for concurrent deploys
python -c "
import os, sys, subprocess

from sqlalchemy import create_engine, text

url = os.environ.get('DATABASE_URL', 'postgresql://regengine:regengine@postgres:5432/regengine')
engine = create_engine(url)

with engine.connect() as conn:
    conn.execution_options(isolation_level='AUTOCOMMIT')

    # Block until we acquire the advisory lock
    conn.execute(text('SELECT pg_advisory_lock(${MIGRATION_LOCK_ID})'))
    print('==> Migration lock acquired', flush=True)

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
