"""CORS origin hardening regressions for SEC-12 and SEC-13."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

from shared.cors import get_allowed_origins, should_allow_credentials
from shared.middleware.security import add_security

FastAPI = fastapi.FastAPI
TestClient = testclient.TestClient

_ENV_VARS = (
    "CORS_ALLOWED_HEADERS",
    "CORS_ALLOWED_ORIGINS",
    "CORS_ALLOWED_PREVIEW_ORIGINS",
    "CORS_ALLOW_CREDENTIALS",
    "DATABASE_URL",
    "ENV",
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_PROJECT_ID",
    "RAILWAY_SERVICE_NAME",
    "REGENGINE_ENV",
    "VERCEL_ENV",
    "VERCEL_URL",
)


@pytest.fixture(autouse=True)
def clean_cors_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    add_security(app)
    return TestClient(app)


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/ping",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )


@pytest.mark.parametrize(
    "allowed_origin",
    [
        "https://regengine-pr-123.vercel.app",
        "https://regengine-feature-42.up.railway.app",
    ],
)
def test_configured_preview_origins_are_allowed(
    monkeypatch: pytest.MonkeyPatch,
    allowed_origin: str,
) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    monkeypatch.setenv(
        "CORS_ALLOWED_PREVIEW_ORIGINS",
        ",".join(
            [
                "https://regengine-pr-123.vercel.app",
                "https://regengine-feature-42.up.railway.app",
            ]
        ),
    )

    response = _preflight(_client(), allowed_origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == allowed_origin
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.parametrize(
    "attacker_origin",
    [
        "https://regengine-attacker.vercel.app",
        "https://regengine-attacker.up.railway.app",
    ],
)
def test_unconfigured_preview_origins_are_denied(
    monkeypatch: pytest.MonkeyPatch,
    attacker_origin: str,
) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    monkeypatch.setenv(
        "CORS_ALLOWED_PREVIEW_ORIGINS",
        "https://regengine-pr-123.vercel.app",
    )

    response = _preflight(_client(), attacker_origin)

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_preview_origin_allowlist_rejects_wildcard_patterns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_PREVIEW_ORIGINS", "https://*.vercel.app")

    with pytest.raises(ValueError, match="exact http"):
        get_allowed_origins()


def test_wildcard_origin_rejected_in_production_with_credentials_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")

    with pytest.raises(ValueError, match=r"wildcard .* production or cloud"):
        get_allowed_origins()


def test_wildcard_origin_rejected_in_cloud_like_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")

    with pytest.raises(ValueError, match=r"wildcard .* production or cloud"):
        should_allow_credentials()


def test_cloud_like_defaults_omit_localhost_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")

    origins = get_allowed_origins()

    assert origins == [
        "https://regengine.co",
        "https://www.regengine.co",
        "https://app.regengine.co",
    ]


def test_development_wildcard_forces_credentials_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")

    assert should_allow_credentials() is False
