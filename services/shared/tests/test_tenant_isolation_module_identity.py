"""Tenant-isolation test collection must preserve existing route dependencies."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_collection_preserves_shared_dependency_identity() -> None:
    script = """
        import runpy
        import sys
        import uuid
        from pathlib import Path

        sys.path.insert(0, str(Path.cwd() / "services"))
        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient
        import shared.middleware as middleware
        import shared.middleware.tenant_context as tenant_context
        import shared.validators as validators
        import shared.validators.tenant_validator as tenant_validator

        originals = (middleware, tenant_context, validators, tenant_validator)
        app = FastAPI()

        @app.get("/tenant")
        async def tenant(tenant_id=Depends(middleware.get_current_tenant_id)):
            return str(tenant_id)

        runpy.run_path("services/shared/tests/test_tenant_isolation.py")

        for module in originals:
            assert sys.modules[module.__name__] is module, module.__name__

        from shared.middleware import get_current_tenant_id

        expected = uuid.UUID("11111111-1111-1111-1111-111111111111")
        app.dependency_overrides[get_current_tenant_id] = lambda: expected
        with TestClient(app) as client:
            response = client.get("/tenant")
        assert response.status_code == 200, response.text
        assert response.json() == str(expected)
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
