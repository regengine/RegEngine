import uuid

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from shared.middleware.tenant_context import TenantContextMiddleware, get_current_tenant_id

app = FastAPI()
app.add_middleware(TenantContextMiddleware)

@app.get("/test-isolation")
async def isolation_endpoint(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return {"tenant_id": str(tenant_id)}

client = TestClient(app)


def test_unauthenticated_header_rejected():
    """X-RegEngine-Tenant-ID without a valid internal secret must be rejected."""
    malicious_tenant = str(uuid.uuid4())

    response = client.get(
        "/test-isolation",
        headers={"X-RegEngine-Tenant-ID": malicious_tenant}
    )

    assert response.status_code == 401
    assert "Tenant ID not found" in response.json()["detail"]


def test_wrong_secret_rejected(monkeypatch):
    """X-RegEngine-Tenant-ID with an incorrect internal secret must be rejected."""
    monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", "real-secret")

    response = client.get(
        "/test-isolation",
        headers={
            "X-RegEngine-Tenant-ID": str(uuid.uuid4()),
            "X-RegEngine-Internal-Secret": "wrong-secret",
        }
    )

    assert response.status_code == 401
    assert "Tenant ID not found" in response.json()["detail"]


def test_missing_env_secret_rejected(monkeypatch):
    """Even a matching header pair must fail when the env var is unset."""
    monkeypatch.delenv("REGENGINE_INTERNAL_SECRET", raising=False)

    response = client.get(
        "/test-isolation",
        headers={
            "X-RegEngine-Tenant-ID": str(uuid.uuid4()),
            "X-RegEngine-Internal-Secret": "anything",
        }
    )

    assert response.status_code == 401
    assert "Tenant ID not found" in response.json()["detail"]


def test_authenticated_internal_header_accepted(monkeypatch):
    """Internal service-to-service calls work when the secret matches the env var."""
    secret = "trusted-internal-v1"
    monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", secret)

    valid_tenant = str(uuid.uuid4())

    response = client.get(
        "/test-isolation",
        headers={
            "X-RegEngine-Tenant-ID": valid_tenant,
            "X-RegEngine-Internal-Secret": secret,
        }
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == valid_tenant


def test_tenant_extraction_errors_fail_closed_on_protected_paths(monkeypatch):
    """Unexpected extraction errors must not silently continue as tenant=None."""

    async def _boom(self, request):
        raise ValueError("bad tenant material")

    monkeypatch.setattr(TenantContextMiddleware, "_extract_tenant_id", _boom)

    protected_app = FastAPI()
    protected_app.add_middleware(TenantContextMiddleware)

    @protected_app.get("/protected")
    async def protected():
        return {"ok": True}

    response = TestClient(protected_app, raise_server_exceptions=False).get("/protected")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unable to establish tenant context"


def test_tenant_extraction_errors_continue_on_exempt_paths(monkeypatch):
    """Health/probe paths may proceed without tenant context."""

    async def _boom(self, request):
        raise ValueError("bad tenant material")

    monkeypatch.setattr(TenantContextMiddleware, "_extract_tenant_id", _boom)

    exempt_app = FastAPI()
    exempt_app.add_middleware(TenantContextMiddleware)

    @exempt_app.get("/health")
    async def health():
        return {"ok": True}

    response = TestClient(exempt_app, raise_server_exceptions=False).get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
