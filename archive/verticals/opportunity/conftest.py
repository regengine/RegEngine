"""Test environment configuration for pytest.

Automatically loads test environment variables before any test imports.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
