#!/bin/bash
set -e

# Initialize entertainment vertical database

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create entertainment database
    CREATE DATABASE entertainment;
    
    -- Create regengine_admin database if not exists (for Admin service)
    SELECT 'CREATE DATABASE regengine_admin'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'regengine_admin')\gexec
    
    -- Create energy database if not exists
    SELECT 'CREATE DATABASE energy'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'energy')\gexec
EOSQL

# Connect to entertainment DB and run migrations
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "entertainment" <<-EOSQL
    -- Run initial migration
    \i /docker-entrypoint-initdb.d/migrations/V001__create_pcos_schema.sql
EOSQL

echo "Entertainment database initialized successfully"
