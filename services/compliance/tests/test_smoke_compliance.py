import sys
from pathlib import Path
from uuid import uuid4

# Add service directory to path for imports to work
service_dir = Path(__file__).parent.parent
_to_remove = [key for key in sys.modules if key == 'app' or key.startswith('app.') or key == 'main']
for key in _to_remove:
    del sys.modules[key]
sys.path.insert(0, str(service_dir))

import pytest
from fastapi.testclient import TestClient

from main import app


def _tenant_headers() -> dict:
    return {"X-Tenant-Id": str(uuid4())}


def test_health_and_root() -> None:
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "compliance-api"

    root = client.get("/")
    assert root.status_code == 200
    payload = root.json()
    assert payload["service"] == "compliance-api"
    # key_endpoints now uses industry/checklist/validate/audit schema
    assert "key_endpoints" in payload
    key_endpoints = payload["key_endpoints"]
    assert "industries" in key_endpoints or "validate" in key_endpoints


# test_fair_lending_end_to_end_flow was removed because it depended on the
# /v1/models route which has been deleted. The model registration step was
# required before fair-lending analysis could run, making the entire test
# flow unreachable.
