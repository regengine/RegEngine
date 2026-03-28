#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run-migrations.sh — Idempotent Alembic migration runner
#
# Safe for both fresh databases and existing ones:
#   - If alembic_version table exists and is populated → just run upgrade
#   - If tables exist but alembic_version doesn't → stamp + upgrade (adopting Alembic)
#   - If nothing exists → full upgrade from scratch
#
# Usage:  DATABASE_URL=postgresql://... ./scripts/run-migrations.sh
# ---------------------------------------------------------------------------
set -euo pipefail

echo "==> Running Alembic migrations..."

# Check if alembic_version table exists and has a row
STAMPED=$(python -c "
import os, sys
try:
    from sqlalchemy import create_engine, text
    url = os.environ.get('DATABASE_URL', 'postgresql://regengine:regengine@postgres:5432/regengine')
    engine = create_engine(url)
    with engine.connect() as conn:
        # Check if alembic_version table exists
        result = conn.execute(text(
            \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'alembic_version')\"
        ))
        if not result.scalar():
            # Check if any FSMA tables exist (i.e., DB was set up before Alembic)
            result2 = conn.execute(text(
                \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'fsma')\"
            ))
            if result2.scalar():
                print('NEEDS_STAMP')
            else:
                print('FRESH')
        else:
            result3 = conn.execute(text('SELECT count(*) FROM alembic_version'))
            if result3.scalar() > 0:
                print('ALREADY_MANAGED')
            else:
                # alembic_version exists but empty — treat like needs stamp
                result4 = conn.execute(text(
                    \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'fsma')\"
                ))
                if result4.scalar():
                    print('NEEDS_STAMP')
                else:
                    print('FRESH')
except Exception as e:
    print(f'ERROR:{e}', file=sys.stderr)
    print('FRESH')  # safe default: let alembic upgrade handle it
" 2>&1)

echo "    DB state: ${STAMPED}"

case "${STAMPED}" in
    NEEDS_STAMP)
        echo "==> Existing database detected — stamping as baseline..."
        alembic stamp head
        echo "==> Stamped. Running any newer migrations..."
        alembic upgrade head
        ;;
    ALREADY_MANAGED)
        echo "==> Alembic already managing this database — upgrading..."
        alembic upgrade head
        ;;
    FRESH)
        echo "==> Fresh database — running full migration..."
        alembic upgrade head
        ;;
    *)
        echo "==> Unknown state, attempting upgrade..."
        alembic upgrade head
        ;;
esac

echo "==> Migrations complete."
