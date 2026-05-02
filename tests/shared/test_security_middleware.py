from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.middleware.security import add_security


def _app() -> FastAPI:
    app = FastAPI()
    add_security(app)

    @app.get("/readiness")
    def readiness():
        return {"status": "ready"}

    @app.get("/private")
    def private():
        return {"status": "ok"}

    return app


def test_readiness_bypasses_trusted_host_for_infra_probe_host():
    client = TestClient(_app(), headers={"host": "100.64.0.2"})

    response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_non_probe_paths_still_enforce_trusted_host():
    client = TestClient(_app(), headers={"host": "100.64.0.2"})

    response = client.get("/private")

    assert response.status_code == 400
