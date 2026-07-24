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

# get_tenant_context() is referenced by V002 (baseline) RLS policies, created
# before any migration defines it — production Supabase has it from pre-baseline
# state. This MUST stay fail-hard (RAISE on unset app.tenant_id) and STABLE, in
# lockstep with alembic v097 (e4d7b2a9c561). It previously returned NULL, which
# silently defeated the #2461 fail-closed guarantee: `tenant_id = NULL` is NULL,
# so ungated queries returned ZERO ROWS instead of erroring. STABLE is equally
# load-bearing — a VOLATILE function cannot be used as an index-qual value, so
# every tenant RLS predicate degrades to a per-row filter (measured 38x).
# `alembic upgrade head` is unaffected: migrations run as a BYPASSRLS superuser,
# so the function is never evaluated during the upgrade.
# Seed it on every local DB so `alembic upgrade head` works from a clean
# container. Reads `app.tenant_id` session variable (set via `SET LOCAL`).
for db in regengine regengine_admin energy; do
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-EOSQL
        CREATE OR REPLACE FUNCTION get_tenant_context()
        RETURNS UUID AS \$fn\$
        DECLARE
            tid TEXT;
        BEGIN
            tid := NULLIF(current_setting('app.tenant_id', TRUE), '');
            IF tid IS NULL THEN
                RAISE EXCEPTION 'app.tenant_id not set - tenant context required for RLS';
            END IF;
            RETURN tid::UUID;
        END;
        \$fn\$ LANGUAGE plpgsql STABLE;
EOSQL
done

echo "✅ Additional databases initialized"
