"""Test environment configuration for pytest.

Automatically loads test environment variables before any test imports.
"""
import os

# Set test environment variables BEFORE pydantic tries to validate
os.environ.setdefault("ADMIN_MASTER_KEY", "admin-master-key-dev")
os.environ.setdefault("DATABASE_URL", "postgresql://regengine:regengine@localhost:5433/regengine_admin")
os.environ.setdefault("ADMIN_DATABASE_URL", "postgresql://regengine:regengine@localhost:5433/regengine_admin")
os.environ.setdefault("ENTERTAINMENT_DATABASE_URL", "postgresql://regengine:regengine@localhost:5433/entertainment")
os.environ.setdefault("ENABLE_DB_API_KEYS", "true")
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "admin")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("AUTH_SECRET_KEY", "dev_secret_key_change_me")
