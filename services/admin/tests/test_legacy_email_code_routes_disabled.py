"""The unused legacy email-code pair stays off the public auth surface."""

from services.admin.app import auth_routes


def test_legacy_email_code_routes_are_not_mounted() -> None:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(auth_routes.router)
    paths = set(app.openapi()["paths"])

    assert "/auth/email-code/request" not in paths
    assert "/auth/email-code/confirm" not in paths
    assert "/auth/challenges" in paths
