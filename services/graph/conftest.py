"""Test environment configuration for pytest.

Automatically loads test environment variables before any test imports.
"""
import os

# Set test environment variables BEFORE any imports  
os.environ.setdefault("ADMIN_SERVICE_URL", "http://localhost:8000")
os.environ.setdefault("NLP_SERVICE_URL", "http://localhost:8002")
os.environ.setdefault("GRAPH_SERVICE_URL", "http://localhost:8003")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "test-password")
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
