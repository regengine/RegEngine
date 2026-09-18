"""#2847 — the DB fallback in ``get_ingestion_principal`` must not swallow a 429.

``get_ingestion_principal`` wraps ``require_api_key`` in a bare
``except HTTPException`` and, on *any* HTTPException, re-validates the same
key directly against the ``api_keys`` table via ``_lookup_scoped_key_from_db``
— a path that performs no rate-limit check at all
(``services/ingestion/app/authz.py``). ``require_api_key`` signals rate-limit
denial by raising **429** (``services/shared/auth.py``), so the denial was
caught and converted into a successful authentication.

Two controls were nullified by that:

* the per-key ``rate_limit_per_minute`` budget on ``DatabaseAPIKeyStore``,
  which is the billing-tier and abuse control for ingestion; and
* the store's deliberate Redis-down posture —
  ``DatabaseAPIKeyStore.check_rate_limit`` returns ``allowed=False`` with the
  comment "Fail closed: no Redis means no distributed rate limiting", and that
  fail-closed 429 was being inverted into fail-open precisely when the control
  was designed to be most conservative.

The legacy second lookup has been removed. Every authentication or rate-limit
failure must remain terminal, including 401, in both deployed and test modes.
"""

from __future__ import annotations

import pytest
from services.ingestion.app import authz
from services.ingestion.app.authz import IngestionPrincipal, get_ingestion_principal
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

_TENANT = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _reset_auth_failures(monkeypatch):
    from shared.rate_limit import BruteForceLimiter

    limiter = BruteForceLimiter(
        namespace="test-authz-2847",
        max_failures=authz._AUTH_FAIL_MAX,
        window_seconds=authz._AUTH_FAIL_WINDOW,
        redis_client=None,
    )
    limiter._redis = None  # ignore any env-provided Redis
    monkeypatch.setattr(authz, "_auth_limiter", limiter)


@pytest.fixture(autouse=True)
def _strip_env(monkeypatch):
    for var in ("REGENGINE_ENV", "ENV", "DATABASE_URL", "API_KEY"):
        monkeypatch.delenv(var, raising=False)


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    async def _whoami(principal: IngestionPrincipal = Depends(get_ingestion_principal)):
        return {"key_id": principal.key_id, "auth_mode": principal.auth_mode}

    return app


def _arm(monkeypatch, status_code: int, *, detail: str = "denied", headers=None):
    """Make ``require_api_key`` fail with ``status_code`` while the DB lookup
    would happily hand back a principal."""

    async def _fake_require(request, x_regengine_api_key):
        raise HTTPException(status_code=status_code, detail=detail, headers=headers)

    monkeypatch.setattr(authz, "require_api_key", _fake_require)


# ---------------------------------------------------------------------------
# Configured-API_KEY branch (the production-relevant one)
# ---------------------------------------------------------------------------


class TestRateLimitDenialIsTerminal:
    def test_429_from_require_api_key_is_not_converted_into_a_principal(self, monkeypatch):
        """The bypass: 429 → caught → same key re-validated → admitted."""
        from services.ingestion.app import config as cfg

        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")
        _arm(monkeypatch, 429, detail="Rate limit exceeded", headers={"Retry-After": "60"})

        resp = TestClient(_build_app()).get("/whoami", headers={"X-RegEngine-API-Key": "rge_valid.key"})

        assert resp.status_code == 429, (
            "RATE-LIMIT BYPASS: a 429 from require_api_key was swallowed and the "
            f"key re-admitted via the DB fallback ({resp.status_code} {resp.text!r})"
        )

    def test_429_preserves_retry_after_header(self, monkeypatch):
        from services.ingestion.app import config as cfg

        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")
        _arm(monkeypatch, 429, detail="Rate limit exceeded", headers={"Retry-After": "60"})

        resp = TestClient(_build_app()).get("/whoami", headers={"X-RegEngine-API-Key": "rge_valid.key"})
        assert resp.headers.get("Retry-After") == "60"

    def test_redis_down_fail_closed_denial_reaches_the_caller(self, monkeypatch):
        """``DatabaseAPIKeyStore.check_rate_limit`` denies when Redis is absent.

        That denial surfaces as a 429 from ``require_api_key``. It must stay a
        denial: admitting the request here is the exact inversion of the
        store's documented fail-closed behaviour.
        """
        from services.ingestion.app import config as cfg

        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")
        _arm(monkeypatch, 429, detail="Rate limit exceeded")

        resp = TestClient(_build_app()).get("/whoami", headers={"X-RegEngine-API-Key": "rge_valid.key"})
        assert resp.status_code == 429
        assert resp.json()["detail"] == "Rate limit exceeded"

    @pytest.mark.parametrize("status_code", [402, 403, 429, 500, 503])
    def test_no_non_401_status_is_converted_into_success(self, monkeypatch, status_code):
        from services.ingestion.app import config as cfg

        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")
        _arm(monkeypatch, status_code)

        resp = TestClient(_build_app()).get("/whoami", headers={"X-RegEngine-API-Key": "rge_valid.key"})
        assert resp.status_code == status_code, resp.text

    def test_429_does_not_count_as_an_auth_failure(self, monkeypatch):
        """A throttled valid key is not a bad credential — it must not feed
        the brute-force IP blocklist."""
        from services.ingestion.app import config as cfg

        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")
        _arm(monkeypatch, 429)

        TestClient(_build_app()).get("/whoami", headers={"X-RegEngine-API-Key": "rge_valid.key"})
        assert authz._auth_limiter._mem_failures.get("testclient", []) == []


class TestGenuineAuthFailureIsTerminal:
    def test_401_stays_denied_without_a_second_lookup(self, monkeypatch):
        """A rejected credential cannot be revived by a weaker lookup."""
        from services.ingestion.app import config as cfg

        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")
        _arm(monkeypatch, 401, detail="Invalid API key")

        resp = TestClient(_build_app()).get("/whoami", headers={"X-RegEngine-API-Key": "rge_valid.key"})
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == "Invalid API key"

    def test_401_with_no_matching_row_still_401s(self, monkeypatch):
        from services.ingestion.app import config as cfg

        cfg.get_settings.cache_clear()
        monkeypatch.setenv("API_KEY", "master-secret")

        async def _fake_require(request, x_regengine_api_key):
            raise HTTPException(status_code=401, detail="Invalid API key")

        monkeypatch.setattr(authz, "require_api_key", _fake_require)

        resp = TestClient(_build_app()).get("/whoami", headers={"X-RegEngine-API-Key": "nope"})
        assert resp.status_code == 401
        assert len(authz._auth_limiter._mem_failures.get("testclient", [])) == 1


# ---------------------------------------------------------------------------
# API_KEY-unset (dev) branch — must not drift from the branch above
# ---------------------------------------------------------------------------


class TestDevBranchDoesNotDrift:
    def test_dev_branch_429_is_terminal(self, monkeypatch):
        from services.ingestion.app import config as cfg

        cfg.get_settings.cache_clear()
        monkeypatch.setenv("REGENGINE_ENV", "development")
        _arm(monkeypatch, 429, detail="Rate limit exceeded")

        resp = TestClient(_build_app()).get("/whoami", headers={"X-RegEngine-API-Key": "rge_valid.key"})
        assert resp.status_code == 429, (
            f"dev branch still swallows 429 — the two fallbacks have drifted: {resp.status_code} {resp.text!r}"
        )

    def test_dev_branch_401_stays_denied(self, monkeypatch):
        from services.ingestion.app import config as cfg

        cfg.get_settings.cache_clear()
        monkeypatch.setenv("REGENGINE_ENV", "development")
        _arm(monkeypatch, 401, detail="Invalid API key")

        resp = TestClient(_build_app()).get("/whoami", headers={"X-RegEngine-API-Key": "rge_valid.key"})
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == "Invalid API key"
