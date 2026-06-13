#!/bin/bash
# init-postgres.sh — Create additional databases required by services
# The default 'regengine' database is created by POSTGRES_DB env var.
# This script creates any additional databases referenced in docker-compose.yml.

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Admin API database
    SELECT 'CREATE DATABASE regengine_admin'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'regengine_admin')\gexec

    -- Energy vertical database
    SELECT 'CREATE DATABASE energy'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'energy')\gexec

    -- Grant privileges
    GRANT ALL PRIVILEGES ON DATABASE regengine_admin TO regengine;
    GRANT ALL PRIVILEGES ON DATABASE energy TO regengine;
EOSQL

# get_tenant_context() is referenced by V002 (baseline) RLS policies but no
# migration defines it — production Supabase has it from pre-baseline state.
# Seed it on every local DB so `alembic upgrade head` works from a clean
# container. Reads `app.tenant_id` session variable (set via `SET LOCAL`).
for db in regengine regengine_admin energy; do
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-EOSQL
        CREATE OR REPLACE FUNCTION get_tenant_context()
        RETURNS UUID AS \$fn\$
        BEGIN
            RETURN current_setting('app.tenant_id', true)::uuid;
        EXCEPTION WHEN OTHERS THEN
            RETURN NULL;
        END;
        \$fn\$ LANGUAGE plpgsql STABLE;
EOSQL
done

echo "✅ Additional databases initialized"
