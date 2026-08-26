"""The unused legacy email-code pair stays off the public auth surface."""

from services.admin.app import auth_routes


def test_legacy_email_code_routes_are_not_mounted() -> None:
    paths = {route.path for route in auth_routes.router.routes}

    assert "/auth/email-code/request" not in paths
    assert "/auth/email-code/confirm" not in paths
    assert "/auth/challenges" in paths
