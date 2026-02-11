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

echo "✅ Additional databases initialized"
