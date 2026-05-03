"""Tests for shared permission matching helpers."""

from shared.permissions import has_permission, permission_implies


def test_permission_implies_exact_and_separator_normalization() -> None:
    assert permission_implies("fda:export", "fda.export")
    assert permission_implies("exchange.write", "exchange:write")


def test_permission_implies_wildcards() -> None:
    assert permission_implies("*", "fda.export")
    assert permission_implies("fda.*", "fda.export")
    assert permission_implies("admin.*", "simulations.write")
    assert not permission_implies("admin", "simulations.write")


def test_has_permission_with_mixed_grants() -> None:
    grants = ["exchange.read", "simulations.*"]
    assert has_permission(grants, "simulations.export")
    assert not has_permission(grants, "exchange.write")
