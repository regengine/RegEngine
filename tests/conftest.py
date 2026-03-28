"""Global test configuration for RegEngine verification suite."""
import os

# Set database URLs to point to local Docker instance
os.environ.setdefault("ADMIN_DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine_admin")
os.environ.setdefault("DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine_admin")
os.environ.setdefault("ENTERTAINMENT_DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/entertainment")
os.environ.setdefault("AUTH_SECRET_KEY", "dev_secret_key_change_me")
os.environ.setdefault("ADMIN_MASTER_KEY", "admin-master-key-dev")
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-ci-only-not-for-production")
os.environ.setdefault("ENVIRONMENT", "development")
