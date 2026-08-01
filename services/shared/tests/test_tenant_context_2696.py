"""#2696: tenant-context/RLS plumbing fail-closed follow-ups.

Covers:
* ``check_rls_posture`` under ``REGENGINE_REQUIRE_RLS_ENFORCEMENT=1``:
  a probe failure retries then ABORTS boot instead of silently bypassing
  the one-way guard with ``"unknown"``.
* ``TenantContextMiddleware``: a tenant claim that fails UUID parsing in a
  VALIDATED JWT rejects the request (401) on protected paths instead of
  being treated as an absent claim.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest import mock

import pytest

_SHARED_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SHARED_DIR.parent
for _p in (_SHARED_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# NOTE: Request must be a MODULE-level name — with ``from __future__ import
# annotations`` a route's ``request: Request`` annotation is resolved from
# the function's globals, and a method-local import makes FastAPI misread
# the parameter as a required query param (422).
from fastapi import FastAPI, Request  # noqa: E402


def _posture_cm(rolsuper: bool = False, rolbypassrls: bool = False):
    conn = mock.MagicMock()
    conn.execute.return_value.fetchone.return_value = ("somerole", rolsuper, rolbypassrls)
    cm = mock.MagicMock()
    cm.__enter__.return_value = conn
    cm.__exit__.return_value = False
    return cm


class TestCheckRlsPostureProbeFailure:
    def test_probe_failure_without_require_stays_unknown(self, monkeypatch):
        from shared.database import check_rls_posture

        monkeypatch.delenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", raising=False)
        eng = mock.MagicMock()
        eng.dialect.name = "postgresql"
        eng.connect.side_effect = ConnectionError("db down")

        assert check_rls_posture(eng, label="unit-2696-soft") == "unknown"
        # Without REQUIRE=1 the probe is single-shot (boot must not stall).
        assert eng.connect.call_count == 1

    def test_probe_failure_under_require_retries_then_aborts_boot(self, monkeypatch):
        from shared.database import check_rls_posture

        monkeypatch.setenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", "1")
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        eng = mock.MagicMock()
        eng.dialect.name = "postgresql"
        eng.connect.side_effect = ConnectionError("db down")

        with pytest.raises(RuntimeError, match="refusing to boot blind"):
            check_rls_posture(eng, label="unit-2696-hard")
        assert eng.connect.call_count == 3

    def test_transient_probe_failure_under_require_recovers(self, monkeypatch):
        from shared.database import check_rls_posture

        monkeypatch.setenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", "1")
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        eng = mock.MagicMock()
        eng.dialect.name = "postgresql"
        eng.connect.side_effect = [ConnectionError("blip"), _posture_cm()]

        assert check_rls_posture(eng, label="unit-2696-recover") == "enforced"
        assert eng.connect.call_count == 2


class TestMiddlewareMalformedJwtClaim:
    USER_HOLDER: dict = {}

    def _app(self):
        from shared.middleware.tenant_context import TenantContextMiddleware

        app = FastAPI()
        app.add_middleware(TenantContextMiddleware)
        holder = self.USER_HOLDER

        @app.middleware("http")  # outermost: seeds request.state.user first
        async def _seed_user(request: Request, call_next):
            if "user" in holder:
                request.state.user = holder["user"]
            return await call_next(request)

        @app.get("/protected")
        async def protected(request: Request):
            tid = getattr(request.state, "tenant_id", None)
            return {"tenant_id": str(tid) if tid else None}

        @app.get("/health")
        async def health():
            return {"ok": True}

        return app

    def test_malformed_claim_rejected_on_protected_path(self):
        from fastapi.testclient import TestClient

        self.USER_HOLDER.clear()
        self.USER_HOLDER["user"] = {"tenant_id": "not-a-uuid"}
        client = TestClient(self._app())

        resp = client.get("/protected")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Unable to establish tenant context"

    def test_valid_claim_still_resolves(self):
        from fastapi.testclient import TestClient

        self.USER_HOLDER.clear()
        self.USER_HOLDER["user"] = {"tenant_id": "11111111-1111-1111-1111-111111111111"}
        client = TestClient(self._app())

        resp = client.get("/protected")
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "11111111-1111-1111-1111-111111111111"

    def test_malformed_claim_tolerated_on_exempt_path(self):
        from fastapi.testclient import TestClient

        self.USER_HOLDER.clear()
        self.USER_HOLDER["user"] = {"tenant_id": "not-a-uuid"}
        client = TestClient(self._app())

        resp = client.get("/health")
        assert resp.status_code == 200
