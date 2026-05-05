#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
Direct RLS SQL deployment is retired.

Service-level Flyway SQL migrations were removed in #2004 because Railway
deploys the repository-level Alembic chain. Run from the repository root:

  DATABASE_URL="postgresql://..." alembic upgrade head
EOF

exit 2
