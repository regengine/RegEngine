import sys
from pathlib import Path

import pytest

try:
    from services.graph.app.main import app
except ImportError:
    # Fallback for running from services/graph directory
    import os
    service_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(service_dir))
    
    # Debug paths
    print(f"DEBUG: sys.path[0] = {sys.path[0]}")
    try:
        import app as app_module
        print(f"DEBUG: app_module file = {getattr(app_module, '__file__', 'No __file__')}")
    except Exception as e:
        print(f"DEBUG: Failed to import app: {e}")
        
    from main import app

from fastapi.testclient import TestClient


def test_health():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    if response.status_code == 503:
        pytest.skip("Neo4j is not reachable — skipping health check")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "graph-service"
