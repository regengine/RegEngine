#!/bin/bash
# init-postgres.sh — Create additional databases required by services
# The default 'regengine' database is created by POSTGRES_DB env var.
# This script creates any additional databases referenced in docker-compose.yml.

set -e

: "${POSTGRES_USER:?Set POSTGRES_USER before running this script}"
: "${POSTGRES_DB:?Set POSTGRES_DB before running this script}"
: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD before running this script}"

# Quote the password as a SQL string literal in shell so it travels to psql
# over stdin. The old code passed it with psql -v flags, which exposes the
# value in the process list. Only single quotes need doubling when
# standard_conforming_strings is on (the default); the expanded value is
# used literally, so $, backticks and backslashes in the password are safe.
pg_pw_literal=${POSTGRES_PASSWORD//\'/\'\'}

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Independent application logins. Local development reuses the container
    -- password for convenience; production provisions unrelated secrets in
    -- the provider control plane.
    SELECT format(
        'CREATE ROLE regengine LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION',
        '${pg_pw_literal}'
    )
    WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine')\gexec
    ALTER ROLE regengine LOGIN PASSWORD '${pg_pw_literal}'
      NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;

    SELECT format(
        'CREATE ROLE regengine_sysadmin LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION',
        '${pg_pw_literal}'
    )
    WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin')\gexec
    ALTER ROLE regengine_sysadmin LOGIN PASSWORD '${pg_pw_literal}'
      NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;

    -- Admin API database
    SELECT 'CREATE DATABASE regengine_admin'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'regengine_admin')\gexec

    -- Energy vertical database
    SELECT 'CREATE DATABASE energy'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'energy')\gexec

    -- Runtime object grants are migration-owned (v111), never bootstrapped
    -- with blanket database privileges here.
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
