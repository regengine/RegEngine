"""Boundary-surface evidence for the authorization report matrix."""

from __future__ import annotations

from fastapi.routing import APIRoute

from services.admin.main import app


def _api_routes() -> list[APIRoute]:
    return [route for route in app.routes if isinstance(route, APIRoute)]


def test_no_users_me_mutation_surface_exists() -> None:
    """There is no generic self-service mutation route for mass assignment."""
    users_me_paths = {
        "/users/me",
        "/v1/users/me",
        "/admin/users/me",
        "/v1/admin/users/me",
    }
    mutating_methods = {"POST", "PUT", "PATCH", "DELETE"}

    matches = [
        (route.path, route.methods)
        for route in _api_routes()
        if route.path in users_me_paths and route.methods and route.methods & mutating_methods
    ]

    assert matches == []


def test_no_graphql_surface_is_mounted() -> None:
    """The report's GraphQL row is not applicable unless a GraphQL route exists."""
    graphql_routes = [
        (route.path, route.methods)
        for route in _api_routes()
        if "graphql" in route.path.lower()
    ]

    assert graphql_routes == []
