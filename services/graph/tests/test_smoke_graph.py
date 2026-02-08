import sys
from pathlib import Path

import pytest

try:
    from services.graph.app.main import app
except ImportError:
    # Fallback for running from services/graph directory
    service_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(service_dir))
    from main import app

from fastapi.testclient import TestClient


def test_health():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    if response.status_code == 503:
        pytest.skip("Neo4j is not reachable — skipping health check")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
