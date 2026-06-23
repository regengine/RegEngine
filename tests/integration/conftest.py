"""
Integration Test Configuration
Manages test fixtures, authentication, and service setup
"""

import os
from typing import AsyncGenerator

import httpx
import pytest

# Service URLs from environment or defaults
ADMIN_URL = os.getenv("TEST_ADMIN_URL", "http://localhost:8400")
ENERGY_URL = os.getenv("TEST_ENERGY_URL", "http://localhost:8002")
OPPORTUNITY_URL = os.getenv("TEST_OPPORTUNITY_URL", "http://localhost:8002")
GRAPH_URL = os.getenv("TEST_GRAPH_URL", "http://localhost:8200")

# Pre-provisioned tokens for environments that run live integration tests.
TEST_AUTH_TOKEN = os.getenv("TEST_AUTH_TOKEN")

# Alternative tenant users for isolation testing
TEST_TENANT_A_AUTH_TOKEN = os.getenv("TEST_TENANT_A_AUTH_TOKEN")

TEST_TENANT_B_AUTH_TOKEN = os.getenv("TEST_TENANT_B_AUTH_TOKEN")


@pytest.fixture(scope="session")
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Shared HTTP client for all tests"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
async def auth_token():
    """Return a pre-provisioned token for live integration tests."""
    if not TEST_AUTH_TOKEN:
        pytest.skip("TEST_AUTH_TOKEN is required for passwordless integration tests")
    return TEST_AUTH_TOKEN


@pytest.fixture
async def tenant_id(auth_token):
    """Get tenant ID for current user"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{ADMIN_URL}/v1/users/me", headers={"Authorization": f"Bearer {auth_token}"})

            if response.status_code == 200:
                user_data = response.json()
                return user_data["tenant_id"]
            else:
                return "default-tenant"

        except Exception:
            return "default-tenant"


@pytest.fixture
async def tenant_a_token():
    """Authentication token for tenant A"""
    return TEST_TENANT_A_AUTH_TOKEN


@pytest.fixture
async def tenant_b_token():
    """Authentication token for tenant B"""
    return TEST_TENANT_B_AUTH_TOKEN


@pytest.fixture
def auth_headers(auth_token, tenant_id):
    """Standard authentication headers"""
    return {"Authorization": f"Bearer {auth_token}", "X-Tenant-ID": tenant_id}


@pytest.fixture(autouse=True)
async def check_services_health():
    """Check that required services are running before tests"""
    services = {
        "Admin": ADMIN_URL,
        "Energy": ENERGY_URL,
        "Opportunity": OPPORTUNITY_URL,
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in services.items():
            try:
                response = await client.get(f"{url}/health")
                if response.status_code != 200:
                    pytest.skip(f"{name} service not healthy")
            except httpx.ConnectError:
                pytest.skip(f"{name} service not available at {url}")


# Pytest configuration
def pytest_addoption(parser):
    """Add custom pytest command line options"""
    parser.addoption(
        "--integration", action="store_true", default=False, help="run integration tests (requires services running)"
    )


def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line("markers", "integration: mark test as integration test (requires services)")


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --integration flag is provided.

    Tests explicitly marked ``@pytest.mark.unit`` (i.e. offline / no live
    services required) are always run regardless of the --integration flag.
    This lets offline pipeline tests live in the integration/ directory for
    discoverability while still running in the standard fast CI suite.
    """
    if config.getoption("--integration"):
        return

    skip_integration = pytest.mark.skip(reason="need --integration option to run")
    for item in items:
        if "unit" in item.keywords:
            # Explicitly offline tests — never skip them for service-health reasons.
            continue
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
