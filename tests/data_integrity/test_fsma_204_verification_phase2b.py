"""Phase 2b FSMA-204 ingestion verification — in-process contract tests (#2503).

The previous version of this module drove live HTTP services
(``localhost:8400`` / ``localhost:8002``) behind a ``_service_available()``
health gate that skipped the whole test when the stack was down — which was
always, since no CI job booted it. Its polling flow also targeted
``/pcos/authorities`` routes that do not exist on any RegEngine entrypoint,
so even a booted stack could never pass it, and its one hard assertion was
``assert len(facts) >= 0`` (vacuous).

This rewrite splits the coverage in two:

1. ``TestIngestionPipelineContract`` — in-process, CI-blocking. Exercises
   the real ingestion submission surface (``POST /v1/ingest/url``) and the
   job-status surface on the consolidated monolith via TestClient: auth is
   required, the SSRF guard fails closed (#991), and job status is
   tenant-scoped (a foreign tenant's job reads as 404). Requires Redis
   (provided by the backend-ci ``repo-root-suite`` job; locally
   ``localhost:6379`` or ``REDIS_URL``). No Postgres needed.

2. ``TestGoldenCorpusLiveSmoke`` — the end-to-end FDA golden-corpus run
   against a deployed stack. Opt-in via ``REGENGINE_LIVE_SMOKE=1``; when
   the flag is set an unreachable service FAILS the test (never skips).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Ensure repo root and services/ are importable (mirrors tests/security/conftest.py —
# this package has no conftest of its own).
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "services")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The official FDA FSMA 204 Final Rule page — the "golden corpus" source.
FDA_RULE_URL = (
    "https://www.fda.gov/food/food-safety-modernization-act-fsma/"
    "fsma-final-rule-requirements-additional-traceability-records-certain-foods"
)


# ---------------------------------------------------------------------------
# In-process contract tests (CI-blocking)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def monolith():
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

    from services.ingestion.app.config import get_settings as ingestion_settings

    ingestion_settings.cache_clear()

    import server.main as server_main

    return server_main


@pytest.fixture(scope="module")
def client(monolith):
    from fastapi.testclient import TestClient

    # No context manager: the lifespan (DB init, workers) must not run.
    return TestClient(monolith.app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def bypass_tenant():
    return os.getenv("AUTH_TEST_BYPASS_TENANT_ID", "11111111-1111-1111-1111-111111111111")


@pytest.fixture(scope="module")
def auth_headers(bypass_tenant):
    return {
        "X-RegEngine-API-Key": os.environ["AUTH_TEST_BYPASS_TOKEN"],
        "X-Tenant-ID": bypass_tenant,
    }


class TestIngestionPipelineContract:
    """The FSMA-204 ingestion spine's API contract, verified in-process."""

    def test_ingest_url_requires_auth(self, client):
        response = client.post(
            "/v1/ingest/url",
            json={"url": FDA_RULE_URL, "source_system": "fda"},
        )

        assert response.status_code in (401, 403), (
            f"Unauthenticated ingestion submission must be rejected, got {response.status_code}"
        )

    @pytest.mark.parametrize(
        "ssrf_url",
        [
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "http://127.0.0.1:8080/internal",  # loopback
            "http://10.0.0.8/admin",  # RFC1918
            "http://192.168.1.10/router",  # RFC1918
        ],
    )
    def test_ssrf_private_targets_rejected(self, client, auth_headers, ssrf_url):
        """The SSRF guard (#991) must fail closed on private/loopback targets.

        IP-literal targets only, so no DNS resolution happens in the test.
        """
        response = client.post(
            "/v1/ingest/url",
            headers=auth_headers,
            json={"url": ssrf_url, "source_system": "fda"},
        )

        assert 400 <= response.status_code < 500, (
            f"SSRF target {ssrf_url} must be rejected 4xx, got {response.status_code}: {response.text[:300]}"
        )

    def test_ssrf_credentialed_url_rejected(self, client, auth_headers):
        response = client.post(
            "/v1/ingest/url",
            headers=auth_headers,
            json={
                "url": "http://user:secret@93.184.216.34/doc",  # pragma: allowlist secret
                "source_system": "fda",
            },
        )

        assert 400 <= response.status_code < 500, (
            f"Credential-embedded URL must be rejected 4xx, got {response.status_code}"
        )

    def test_ssrf_disallowed_port_rejected(self, client, auth_headers):
        response = client.post(
            "/v1/ingest/url",
            headers=auth_headers,
            json={"url": "http://93.184.216.34:2222/doc", "source_system": "fda"},
        )

        assert 400 <= response.status_code < 500, f"Disallowed port must be rejected 4xx, got {response.status_code}"

    def test_unknown_job_status_is_not_found(self, client, auth_headers):
        response = client.get(f"/v1/ingest/status/{uuid4()}", headers=auth_headers)

        assert response.status_code == 404, (
            f"Unknown job id must read as 404, got {response.status_code}: {response.text[:300]}"
        )

    def test_job_status_is_tenant_scoped(self, client, auth_headers, bypass_tenant):
        """A job owned by another tenant must be indistinguishable from absent."""
        import redis as redis_lib

        r = redis_lib.from_url(os.environ["REDIS_URL"])
        own_job = f"phase2b-own-{uuid4()}"
        foreign_job = f"phase2b-foreign-{uuid4()}"
        try:
            r.set(f"ingest:owner:{own_job}", bypass_tenant, ex=120)
            r.set(f"ingest:status:{own_job}", "completed", ex=120)
            r.set(f"ingest:owner:{foreign_job}", str(uuid4()), ex=120)
            r.set(f"ingest:status:{foreign_job}", "completed", ex=120)

            own = client.get(f"/v1/ingest/status/{own_job}", headers=auth_headers)
            foreign = client.get(f"/v1/ingest/status/{foreign_job}", headers=auth_headers)
        finally:
            r.delete(
                f"ingest:owner:{own_job}",
                f"ingest:status:{own_job}",
                f"ingest:owner:{foreign_job}",
                f"ingest:status:{foreign_job}",
            )

        assert own.status_code == 200, f"Owner must read their own job, got {own.status_code}: {own.text[:300]}"
        assert own.json()["status"] == "completed"
        assert foreign.status_code == 404, (
            f"Foreign tenant's job must read as 404, got {foreign.status_code} — cross-tenant status leak"
        )


# ---------------------------------------------------------------------------
# Live golden-corpus smoke (opt-in; FAILS — never skips — once opted in)
# ---------------------------------------------------------------------------

_LIVE_SMOKE = os.getenv("REGENGINE_LIVE_SMOKE", "").strip().lower() in {"1", "true", "yes"}


class TestGoldenCorpusLiveSmoke:
    """End-to-end FDA FSMA-204 rule ingestion against a live stack.

    Once REGENGINE_LIVE_SMOKE=1 is set, an unreachable service is a hard
    failure: this class can never go green by skipping.
    """

    # This is a separate opt-in deployment smoke, not part of the in-process
    # security gate that imports this file.  Exclude it from collection when
    # not requested instead of reporting a green skip in the release suite.
    __test__ = _LIVE_SMOKE

    def test_fda_rule_ingestion_live(self):
        import requests

        base_url = os.getenv("INGEST_SERVICE_URL") or os.getenv("API_BASE_URL") or "http://localhost:8000"
        headers = {
            "X-RegEngine-API-Key": os.environ.get("REGENGINE_TEST_API_KEY", ""),
            "X-Tenant-ID": os.environ.get("AUTH_TEST_BYPASS_TENANT_ID", "11111111-1111-1111-1111-111111111111"),
            "Content-Type": "application/json",
        }

        try:
            health = requests.get(f"{base_url}/health", timeout=5)
        except requests.RequestException as exc:
            pytest.fail(f"REGENGINE_LIVE_SMOKE=1 but {base_url} is unreachable: {exc}")
        assert health.status_code < 500, f"{base_url}/health returned {health.status_code}"

        response = requests.post(
            f"{base_url}/v1/ingest/url",
            json={"url": FDA_RULE_URL, "source_system": "fda", "vertical": "food"},
            headers=headers,
            timeout=120,
        )

        assert response.status_code in (200, 202), (
            f"Golden-corpus submission failed: {response.status_code} {response.text[:500]}"
        )
        data = response.json()
        assert data, "Ingestion returned an empty body"
        # The synchronous path returns a NormalizedEvent — it must carry a
        # document identity the downstream pipeline can trace.
        assert any(k in data for k in ("event_id", "document_id", "id")), (
            f"Ingestion response carries no traceable identity: {sorted(data.keys())}"
        )
