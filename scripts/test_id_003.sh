#!/bin/bash
#
# ID-003: Direct SQL Bypass Attempt
#
# Attempts to read another tenant's rows from vertical_projects while posing
# as an adversary tenant. If rows from more than one tenant come back, RLS
# is NOT enforced.
#
# Tenant IDs must come from the environment so this test always exercises
# the tenants the current fixtures actually created. The IDs used to be
# hardcoded here, which meant the test silently exercised the wrong tenants
# after fixture rotation instead of failing.
#
# Usage:
#   DEMO_TENANT_ID=<uuid> ADVERSARY_TENANT_ID=<uuid> ./scripts/test_id_003.sh
#
# Both variables are required and must be UUIDs. The script exits non-zero
# before touching the database when either is absent, malformed, or when
# both name the same tenant (which would make the bypass check vacuous).

set -euo pipefail

DEMO_TENANT="${DEMO_TENANT_ID:-}"
ADVERSARY_TENANT="${ADVERSARY_TENANT_ID:-}"

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

[ -n "$DEMO_TENANT" ] || fail "DEMO_TENANT_ID is not set. Export the demo fixture tenant UUID first, e.g. DEMO_TENANT_ID=<uuid> ADVERSARY_TENANT_ID=<uuid> $0."
[ -n "$ADVERSARY_TENANT" ] || fail "ADVERSARY_TENANT_ID is not set. Export the adversary fixture tenant UUID first, e.g. DEMO_TENANT_ID=<uuid> ADVERSARY_TENANT_ID=<uuid> $0."

UUID_RE='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
[[ "$DEMO_TENANT" =~ $UUID_RE ]] || fail "DEMO_TENANT_ID is not a valid UUID: '$DEMO_TENANT'."
[[ "$ADVERSARY_TENANT" =~ $UUID_RE ]] || fail "ADVERSARY_TENANT_ID is not a valid UUID: '$ADVERSARY_TENANT'."

[ "$DEMO_TENANT" != "$ADVERSARY_TENANT" ] || fail "DEMO_TENANT_ID and ADVERSARY_TENANT_ID must differ; identical tenants cannot prove cross-tenant isolation."

echo "Executing ID-003: Direct SQL Bypass Attempt"
echo "-------------------------------------------"

# 1. Attempt to query project for another tenant while posing as Adversary
echo "Attempting to query projects while posing as Adversary Tenant ($ADVERSARY_TENANT)..."

docker exec regengine-postgres-1 psql -U regengine -d regengine_admin -c "
SET app.tenant_id = '$ADVERSARY_TENANT';
SELECT id, name, tenant_id FROM vertical_projects;
"

echo "-------------------------------------------"
echo "If multiple rows are returned (including DemoProject $DEMO_TENANT), RLS is NOT enforced."
