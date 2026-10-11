"""Regression tests for #2893 — /api/v1/fsma stub endpoints.

Two defects, both named in the issue:

1. **Empty 200s.** ``GET /api/v1/fsma/export-jobs`` and ``/mappings``
   returned ``200 {"jobs": []}``. For a traceability compliance product
   that is an affirmative claim that the tenant has no FSMA export jobs.
   A client that checks ``response.ok`` — which is most of them — cannot
   tell "no data" from "not implemented"; the distinguishing signal was
   buried in ``meta.status``. The FDA export paths deliberately avoid the
   same ambiguity by returning 404.
2. **Ungatable.** The router was mounted outside ``_router_enabled``, so
   it had no name in ``_VALID_ROUTER_NAMES`` and no operator who noticed
   the confusion had any lever to remove it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from app.fsma_readiness_compat import router as fsma_readiness_compat_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.router_policy import PRODUCTION_ENABLED_ROUTERS

REPO_ROOT = Path(__file__).resolve().parents[3]

ENDPOINTS = ("/api/v1/fsma/export-jobs", "/api/v1/fsma/mappings")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(fsma_readiness_compat_router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Honest status line
# ---------------------------------------------------------------------------


class TestNotImplementedStatus:
    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_returns_501_not_an_empty_200(self, path: str) -> None:
        resp = _client().get(path)
        assert resp.status_code == 501, (
            f"{path} returned {resp.status_code}: an empty 200 asserts the tenant "
            "has no records, which is a false claim while the capability is unwired"
        )

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_status_line_alone_is_enough_to_tell_unimplemented(self, path: str) -> None:
        """The signal must not require reading meta.status.

        ``response.ok`` is what a generated client checks; that check has
        to be sufficient on its own.
        """
        resp = _client().get(path)
        response_ok = 200 <= resp.status_code < 300
        assert not response_ok

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_body_still_explains_why(self, path: str) -> None:
        """The frontend BFF falls through on non-ok, but anything reading the
        body still gets the same not_connected marker and human message."""
        body = _client().get(path).json()
        assert body["meta"]["status"] == "not_connected"
        assert body["meta"]["message"]

    def test_no_longer_claims_an_empty_result_set(self) -> None:
        export_jobs = _client().get("/api/v1/fsma/export-jobs")
        mappings = _client().get("/api/v1/fsma/mappings")
        for resp in (export_jobs, mappings):
            assert resp.status_code == 501
        # The empty collections may remain in the body for shape
        # compatibility, but they are no longer served under a success
        # status, which is what made them an assertion of fact.
        assert export_jobs.json()["jobs"] == []
        assert mappings.json()["items"] == []


# ---------------------------------------------------------------------------
# 2. Operator gate
# ---------------------------------------------------------------------------


def _synthetic_fernet_key() -> str:
    """Fresh Fernet key per parent process for the strict-auth MFA gate.

    Generated at runtime so no key material lives in the file. The child
    boots under production posture, which is always strict, and strict
    runtimes refuse to boot without a valid MFA_ENCRYPTION_KEY (#3238).
    """
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


_PROD_ENV = {
    "REGENGINE_ENV": "production",
    "ENVIRONMENT": "production",
    "EVENT_BACKBONE": "pg",
    "ENABLED_ROUTERS": ",".join(sorted(PRODUCTION_ENABLED_ROUTERS)),
    "REDIS_URL": "redis://localhost:6379/15",
    "DATABASE_URL": "postgresql://localhost:5432/regengine_test",
    "ADMIN_DATABASE_URL": "postgresql+psycopg://localhost:5432/regengine_admin_test",
    "AUTH_SECRET_KEY": "test-secret-key-with-enough-length",  # pragma: allowlist secret
    "TOOL_ACCESS_SECRET": "tool-access-secret-distinct-and-long-enough",  # pragma: allowlist secret
    "MFA_ENCRYPTION_KEY": _synthetic_fernet_key(),
}

_ENUMERATE = r"""
import json, os, server.main as m
print(json.dumps({
    "paths": sorted({
        r.path for r in m.app.routes
        if getattr(r, "path", "") in {"/api/v1/fsma/export-jobs", "/api/v1/fsma/mappings"}
    }),
    "valid_names": sorted(m.VALID_ROUTER_NAMES),
}))
"""


def _enumerate_production_routes(disabled: str | None = None) -> dict:
    env = {**os.environ, **_PROD_ENV}
    # The pytest session exports test-only knobs that server.main refuses to
    # boot with under REGENGINE_ENV=production, plus placeholder storage keys
    # (services/ingestion/conftest.py) that the secrets gate rejects as
    # insecure whenever set.
    for test_only in (
        "AUTH_TEST_BYPASS_TOKEN",
        "ENABLE_EXPERIMENTAL_ROUTERS",
        "DISABLED_ROUTERS",
        "NEO4J_URI",
        "NEO4J_URL",
        "NEO4J_PASSWORD",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    ):
        env.pop(test_only, None)
    if disabled is not None:
        env["REGENGINE_ENV"] = "test"
        env["ENVIRONMENT"] = "test"
        env.pop("ENABLED_ROUTERS", None)
        env["DISABLED_ROUTERS"] = disabled
    proc = subprocess.run(
        [sys.executable, "-c", _ENUMERATE],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    # server.main logs to stdout; the payload is the last JSON object printed.
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and '"paths"' in line:
            return json.loads(line)
    raise AssertionError(f"no route payload in stdout:\n{proc.stdout[-3000:]}")


class TestOperatorGate:
    def test_router_has_a_name_operators_can_reference(self) -> None:
        result = _enumerate_production_routes()
        assert "readiness" in result["valid_names"], (
            "the readiness owner has no entry in VALID_ROUTER_NAMES, so DISABLED_ROUTERS cannot address it"
        )

    def test_mounted_under_approved_readiness_owner(self) -> None:
        """Compatibility routes inherit the approved readiness owner."""
        result = _enumerate_production_routes()
        assert result["paths"] == list(ENDPOINTS)

    def test_disabled_routers_removes_the_stubs(self) -> None:
        result = _enumerate_production_routes(disabled="readiness")
        assert result["paths"] == []
