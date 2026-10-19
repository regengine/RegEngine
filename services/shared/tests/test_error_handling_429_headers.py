"""``HTTPException.headers`` must survive ``install_exception_handlers``.

``_http_exception_handler`` built its JSONResponse from the status code and
detail only, so every header a route attached to an ``HTTPException`` was
silently dropped: ``Retry-After`` and ``X-RateLimit-*`` on 429, and also
``WWW-Authenticate`` on 401. Starlette's own default handler forwards
``exc.headers``; the custom handler must too, without touching the
``{"error": {"type", "message"}}`` envelope.
"""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from shared.error_handling import install_exception_handlers
from starlette.exceptions import HTTPException as StarletteHTTPException

_RATE_LIMIT_HEADERS = {
    "Retry-After": "42",
    "X-RateLimit-Limit": "60",
    "X-RateLimit-Remaining": "0",
    "X-RateLimit-Reset": "1790000000",
    "X-RateLimit-Tenant": "11111111-2222-3333-4444-555555555555",
    "X-RateLimit-Scope": "records.read",
}


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/limited")
    async def limited():
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers=dict(_RATE_LIMIT_HEADERS))

    @app.get("/limited-no-headers")
    async def limited_no_headers():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    @app.get("/limited-empty-headers")
    async def limited_empty_headers():
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={})

    @app.get("/limited-dict-detail")
    async def limited_dict_detail():
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Slow down", "retry_after": 42},
            headers={"Retry-After": "42"},
        )

    @app.get("/starlette")
    async def starlette_exc():
        raise StarletteHTTPException(status_code=429, detail="Too many", headers={"Retry-After": "7"})

    @app.get("/unauthorized")
    async def unauthorized():
        raise HTTPException(status_code=401, detail="Invalid API key", headers={"WWW-Authenticate": "ApiKey"})

    @app.get("/unavailable")
    async def unavailable():
        raise HTTPException(
            status_code=503,
            detail="Traceback: connect to postgresql://user:pass@postgres.internal/app failed",  # pragma: allowlist secret
            headers={"Retry-After": "30"},
        )

    install_exception_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


def test_429_headers_survive_and_the_error_envelope_is_unchanged() -> None:
    response = _client().get("/limited")

    assert response.status_code == 429
    for name, value in _RATE_LIMIT_HEADERS.items():
        assert response.headers.get(name) == value, f"{name} was dropped"
    assert response.json() == {"error": {"type": "http_429", "message": "Rate limit exceeded"}}
    assert response.headers["content-type"] == "application/json"


def test_429_without_headers_is_unchanged() -> None:
    response = _client().get("/limited-no-headers")

    assert response.status_code == 429
    assert response.json() == {"error": {"type": "http_429", "message": "Rate limit exceeded"}}
    assert "retry-after" not in response.headers
    assert not [name for name in response.headers if name.lower().startswith("x-ratelimit")]


def test_429_with_empty_headers_is_unchanged() -> None:
    response = _client().get("/limited-empty-headers")

    assert response.status_code == 429
    assert response.json() == {"error": {"type": "http_429", "message": "Rate limit exceeded"}}
    assert "retry-after" not in response.headers


def test_dict_detail_keeps_its_normalized_envelope_and_the_headers() -> None:
    response = _client().get("/limited-dict-detail")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"
    assert response.json() == {
        "error": {"type": "rate_limited", "message": "Slow down", "code": "rate_limited", "retry_after": 42}
    }


def test_starlette_http_exception_headers_survive() -> None:
    response = _client().get("/starlette")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "7"
    assert response.json() == {"error": {"type": "http_429", "message": "Too many"}}


def test_unknown_route_404_is_unchanged() -> None:
    response = _client().get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"type": "http_404", "message": "Not Found"}}
    assert "retry-after" not in response.headers


def test_401_keeps_www_authenticate() -> None:
    response = _client().get("/unauthorized")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "ApiKey"
    assert response.json() == {"error": {"type": "http_401", "message": "Invalid API key"}}


def test_5xx_body_stays_sanitized_while_retry_after_survives() -> None:
    response = _client().get("/unavailable")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert response.json() == {"error": {"type": "http_503", "message": "An internal error occurred"}}
    serialized = response.text + str(dict(response.headers))
    assert "postgres.internal" not in serialized
    assert "postgresql://" not in serialized
