-- Create a non-superuser for application verification
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user WITH LOGIN PASSWORD 'app_password';
    END IF;
END $$;

GRANT CONNECT ON DATABASE regengine_admin TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_user;

-- Ensure RLS is active (already done in V6, but good to be sure)
ALTER TABLE review_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_items FORCE ROW LEVEL SECURITY;
