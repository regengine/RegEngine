"""QA deep-pass: RouterPolicy whitespace handling and mount bookkeeping.

_csv_names strips and lowercases DISABLED_ROUTERS entries, but enable() and
is_enabled() only lowercased, so a padded name silently missed. These tests
pin the consistent behavior. Fast and deterministic, no I/O.
"""

from __future__ import annotations

from server.router_policy import PRODUCTION_ENABLED_ROUTERS, RouterPolicy


def _approved_env() -> dict[str, str]:
    return {"ENABLED_ROUTERS": ",".join(sorted(PRODUCTION_ENABLED_ROUTERS))}


def test_enable_tolerates_surrounding_whitespace():
    policy = RouterPolicy.from_environment(production=True, environ=_approved_env())
    assert policy.enable("  admin  ") is True
    assert policy.mounted_routers == ["admin"]


def test_is_enabled_tolerates_whitespace_and_case():
    policy = RouterPolicy.from_environment(production=True, environ=_approved_env())
    assert policy.is_enabled(" CSV ") is True
    assert policy.is_enabled("Graph") is False


def test_enable_unknown_name_records_no_mount():
    policy = RouterPolicy.from_environment(production=True, environ=_approved_env())
    assert policy.enable("not_a_router") is False
    assert policy.mounted_routers == []


def test_enable_records_each_mount_once():
    policy = RouterPolicy.from_environment(production=True, environ=_approved_env())
    assert policy.enable("admin") is True
    assert policy.enable("admin") is True
    assert policy.mounted_routers == ["admin"]


def test_nonproduction_unknown_disabled_is_reported():
    policy = RouterPolicy.from_environment(production=False, environ={"DISABLED_ROUTERS": "graph,typo_router"})
    assert policy.unknown_disabled == frozenset({"typo_router"})
    assert policy.is_enabled("graph") is False
    assert policy.is_enabled("admin") is True


def test_nonproduction_auto_disabled_is_empty_and_disabled_lists_gap():
    policy = RouterPolicy.from_environment(production=False, environ={"DISABLED_ROUTERS": "graph"})
    assert policy.auto_disabled_routers == frozenset()
    assert "graph" in policy.disabled_routers
    assert "graph" in policy.configured_disabled


def test_production_auto_disabled_covers_everything_unapproved():
    policy = RouterPolicy.from_environment(production=True, environ=_approved_env())
    assert policy.auto_disabled_routers == policy.disabled_routers
    assert "graph" in policy.auto_disabled_routers
