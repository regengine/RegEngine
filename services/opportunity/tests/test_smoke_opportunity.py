import sys
from pathlib import Path

# Add service directory to path for imports to work
service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from main import app


def test_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
