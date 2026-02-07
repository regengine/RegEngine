#!/bin/bash

# Tenant IDs
DEMO_TENANT="40e74bc9-4087-4612-8d94-215347138a68"
ADVERSARY_TENANT="9f6ceefc-05d6-43a3-83c6-77cd5f954a2e"

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
