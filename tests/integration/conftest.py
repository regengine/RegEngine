"""
Integration Test Configuration
Manages test fixtures, authentication, and service setup
"""

import pytest
import httpx
import os
from typing import AsyncGenerator

# Service URLs from environment or defaults
ADMIN_URL = os.getenv("TEST_ADMIN_URL", "http://localhost:8400")
ENERGY_URL = os.getenv("TEST_ENERGY_URL", "http://localhost:8002")
OPPORTUNITY_URL = os.getenv("TEST_OPPORTUNITY_URL", "http://localhost:8002")
GRAPH_URL = os.getenv("TEST_GRAPH_URL", "http://localhost:8200")

# Test credentials
TEST_USER_EMAIL = os.getenv("TEST_USER_EMAIL", "integration@test.com")
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", "testpass123")

# Alternative tenant users for isolation testing
TEST_TENANT_A_EMAIL = os.getenv("TEST_TENANT_A_EMAIL", "tenant-a@test.com")
TEST_TENANT_A_PASSWORD = os.getenv("TEST_TENANT_A_PASSWORD", "testpass")

TEST_TENANT_B_EMAIL = os.getenv("TEST_TENANT_B_EMAIL", "tenant-b@test.com")
TEST_TENANT_B_PASSWORD = os.getenv("TEST_TENANT_B_PASSWORD", "testpass")


@pytest.fixture(scope="session")
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Shared HTTP client for all tests"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
async def auth_token():
    """Get authentication token - session scoped for performance"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{ADMIN_URL}/auth/login",
                json={
                    "email": TEST_USER_EMAIL,
                    "password": TEST_USER_PASSWORD
                }
            )
            
            if response.status_code == 200:
                return response.json()["access_token"]
            else:
                pytest.skip(f"Authentication failed: {response.status_code}")
                
        except httpx.ConnectError:
            pytest.skip("Admin service not available for integration tests")


@pytest.fixture
async def tenant_id(auth_token):
    """Get tenant ID for current user"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{ADMIN_URL}/v1/users/me",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            
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
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ADMIN_URL}/auth/login",
            json={
                "email": TEST_TENANT_A_EMAIL,
                "password": TEST_TENANT_A_PASSWORD
            }
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        return None


@pytest.fixture
async def tenant_b_token():
    """Authentication token for tenant B"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ADMIN_URL}/auth/login",
            json={
                "email": TEST_TENANT_B_EMAIL,
                "password": TEST_TENANT_B_PASSWORD
            }
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        return None


@pytest.fixture
def auth_headers(auth_token, tenant_id):
    """Standard authentication headers"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "X-Tenant-ID": tenant_id
    }


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
        "--integration",
        action="store_true",
        default=False,
        help="run integration tests (requires services running)"
    )


def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test (requires services)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --integration flag is provided"""
    if config.getoption("--integration"):
        return
    
    skip_integration = pytest.mark.skip(reason="need --integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
