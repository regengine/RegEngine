"""Test environment configuration for pytest.

Automatically loads test environment variables before any test imports.
"""
import os

# Set test environment variables BEFORE any imports
os.environ.setdefault("ADMIN_SERVICE_URL", "http://localhost:8000")
os.environ.setdefault("NLP_SERVICE_URL", "http://localhost:8002")  
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("S3_BUCKET", "test-ingestion-bucket")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test-key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test-secret")
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
