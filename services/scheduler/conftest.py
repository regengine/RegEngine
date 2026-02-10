"""Test environment configuration for pytest.

Automatically loads test environment variables before any test imports.
"""
import os

# Set test environment variables BEFORE pydantic tries to validate
os.environ.setdefault("DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
