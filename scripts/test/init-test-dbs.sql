-- Mirrors the database creation step in backend-ci.yml
-- Rerunnable: each statement is a no-op when the database already exists.
-- (PostgreSQL has no CREATE DATABASE IF NOT EXISTS, so guard via pg_database.)
SELECT 'CREATE DATABASE regengine_admin' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'regengine_admin')\gexec
SELECT 'CREATE DATABASE energy' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'energy')\gexec
SELECT 'CREATE DATABASE test_db' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'test_db')\gexec
