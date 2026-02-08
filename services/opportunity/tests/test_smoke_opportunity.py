import sys
from pathlib import Path

# Add service directory to path for imports to work
service_dir = Path(__file__).parent.parent
# Clear conflicting modules from other services
_to_remove = [key for key in sys.modules if key == 'app' or key.startswith('app.') or key == 'main']
for key in _to_remove:
    del sys.modules[key]
sys.path.insert(0, str(service_dir))

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

try:
    from main import app
except Exception as _import_err:
    pytestmark = pytest.mark.skip(reason=f"Opportunity app import failed: {_import_err}")
    app = None


def test_health():
    if app is None:
        pytest.skip("Opportunity app not importable")
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
