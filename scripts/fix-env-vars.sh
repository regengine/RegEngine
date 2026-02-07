#!/bin/bash
# Fix RegEngine Environment Variables - Permanent Solution
# Run this script to eliminate Supabase env var conflicts

set -e

echo "=== RegEngine Environment Fix ==="
echo ""

# Step 1: Unset problematic env vars in current shell
echo "Step 1: Unsetting system environment variables..."
unset ADMIN_DATABASE_URL
unset DATABASE_URL
echo "✓ Unset ADMIN_DATABASE_URL and DATABASE_URL"

# Step 2: Add to shell config for persistence
SHELL_RC="${HOME}/.zshrc"
if [ -f "${HOME}/.bashrc" ]; then
    SHELL_RC="${HOME}/.bashrc"
fi

echo ""
echo "Step 2: Adding unset commands to ${SHELL_RC}..."

if ! grep -q "# RegEngine - Unset Supabase env vars" "${SHELL_RC}"; then
    cat >> "${SHELL_RC}" << 'EOF'

# RegEngine - Unset Supabase env vars to use local postgres
unset ADMIN_DATABASE_URL
unset DATABASE_URL
EOF
    echo "✓ Added permanent unset commands to ${SHELL_RC}"
else
    echo "✓ Commands already present in ${SHELL_RC}"
fi

# Step 3: Restart services with correct env vars
echo ""
echo "Step 3: Restarting admin-api with local postgres..."
cd "$(dirname "$0")"

ADMIN_DATABASE_URL="postgresql://regengine:regengine@postgres:5432/regengine_admin" \
DATABASE_URL="postgresql://regengine:regengine@postgres:5432/regengine" \
docker compose up -d --force-recreate admin-api

echo ""
echo "Step 4: Waiting for services to start (15 seconds)..."
sleep 15

# Step 5: Verify health
echo ""
echo "Step 5: Verifying health..."
ADMIN_HEALTH=$(curl -s http://localhost:8400/health 2>&1 || echo "FAILED")

if echo "$ADMIN_HEALTH" | grep -q "healthy"; then
    echo "✓ Admin-API is healthy!"
    echo "$ADMIN_HEALTH" | python3 -m json.tool
else
    echo "✗ Admin-API health check failed:"
    echo "$ADMIN_HEALTH"
    exit 1
fi

echo ""
echo "=== SUCCESS ==="
echo "Environment variables fixed permanently."
echo "Please run 'source ${SHELL_RC}' in all open terminal windows."
echo ""
