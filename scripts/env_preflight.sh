#!/usr/bin/env bash
# RegEngine Environment Preflight Check
# Enforces environment invariants before docker compose operations
# Run this before `docker compose up`

set -e

echo "=== RegEngine Environment Preflight Check ==="
echo ""

# Check for prohibited environment variables
FAILED=0

if env | grep -q "^ADMIN_DATABASE_URL="; then
    echo "❌ ADMIN_DATABASE_URL is set in shell environment"
    echo "   Run: unset ADMIN_DATABASE_URL"
    FAILED=1
fi

if env | grep -q "^DATABASE_URL="; then
    echo "❌ DATABASE_URL is set in shell environment"
    echo "   Run: unset DATABASE_URL"
    FAILED=1
fi

# Check for Supabase URLs in local env (should not exist)
if env | grep -q "supabase.co"; then
    echo "⚠️  WARNING: Supabase URLs detected in environment"
    echo "   Local development should use postgres service"
    FAILED=1
fi

if [ $FAILED -eq 1 ]; then
    echo ""
    echo "=== PREFLIGHT FAILED ==="
    echo "Fix the above issues before running docker compose"
    echo ""
    echo "Quick fix:"
    echo "  unset ADMIN_DATABASE_URL DATABASE_URL"
    echo "  source ~/.zshrc  # or ~/.bashrc"
    exit 1
fi

echo "✅ Environment clean"
echo "✅ No prohibited variables detected"
echo "✅ Safe to proceed with docker compose"
echo ""
