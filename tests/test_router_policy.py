"""Fail-closed router policy for the consolidated production API."""

from __future__ import annotations

from pathlib import Path

import pytest

from server.router_policy import PRODUCTION_ENABLED_ROUTERS, VALID_ROUTER_NAMES, RouterPolicy

EXPECTED_PRODUCTION_ROUTERS = {
    "inflow_workbench",
    "fda_export",
    "csv",
    "edi",
    "epcis_ingestion",
    "score",
    "portal",
    "billing",
    "onboarding",
    "recall",
    "proof_verify",
    "proof_recall",
    "canonical_records",
    "rules",
    "exceptions",
    "request_workflow",
    "auditor",
    "compliance_metrics",
    "readiness",
    "chain_verification",
    "audit_export_log",
    "sla_tracking",
    "export_monitoring",
    "admin",
    "fsma_compliance",
}


def _approved_env() -> dict[str, str]:
    return {"ENABLED_ROUTERS": ",".join(sorted(EXPECTED_PRODUCTION_ROUTERS))}


def test_release_approved_set_is_exact_and_reviewable():
    assert PRODUCTION_ENABLED_ROUTERS == EXPECTED_PRODUCTION_ROUTERS


def test_env_example_matches_release_approved_router_set():
    repo_root = Path(__file__).resolve().parents[1]
    enabled_line = next(
        line
        for line in (repo_root / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.startswith("ENABLED_ROUTERS=")
    )
    configured = {name for name in enabled_line.partition("=")[2].split(",") if name}

    assert configured == EXPECTED_PRODUCTION_ROUTERS


def test_production_requires_enabled_routers():
    with pytest.raises(RuntimeError, match="ENABLED_ROUTERS is required"):
        RouterPolicy.from_environment(production=True, environ={})


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    [
        ({"remove": "admin"}, "missing"),
        ({"add": "graph"}, "extra"),
        ({"add": "not_a_router"}, "unknown"),
    ],
)
def test_production_rejects_missing_extra_and_unknown_routers(mutation, expected_message):
    enabled = set(EXPECTED_PRODUCTION_ROUTERS)
    if name := mutation.get("remove"):
        enabled.remove(name)
    if name := mutation.get("add"):
        enabled.add(name)

    with pytest.raises(RuntimeError, match=expected_message):
        RouterPolicy.from_environment(
            production=True,
            environ={"ENABLED_ROUTERS": ",".join(sorted(enabled))},
        )


def test_production_rejects_legacy_denylist_and_experimental_bypass():
    with pytest.raises(RuntimeError, match="rejects DISABLED_ROUTERS"):
        RouterPolicy.from_environment(
            production=True,
            environ={**_approved_env(), "DISABLED_ROUTERS": "graph"},
        )

    with pytest.raises(RuntimeError, match="rejects ENABLE_EXPERIMENTAL_ROUTERS"):
        RouterPolicy.from_environment(
            production=True,
            environ={**_approved_env(), "ENABLE_EXPERIMENTAL_ROUTERS": "true"},
        )


def test_production_mounts_only_approved_routers():
    policy = RouterPolicy.from_environment(production=True, environ=_approved_env())

    assert {name for name in VALID_ROUTER_NAMES if policy.enable(name)} == EXPECTED_PRODUCTION_ROUTERS
    assert policy.disabled_routers == VALID_ROUTER_NAMES - EXPECTED_PRODUCTION_ROUTERS
    assert not policy.is_enabled("graph")
    assert not policy.is_enabled("nlp")
    assert not policy.is_enabled("sandbox")
    assert not policy.is_enabled("recall_simulations")
    assert not policy.is_enabled("supplier_validation")


def test_nonproduction_retains_broad_behavior_and_denylist():
    policy = RouterPolicy.from_environment(
        production=False,
        environ={"DISABLED_ROUTERS": "graph,nlp", "ENABLE_EXPERIMENTAL_ROUTERS": "true"},
    )

    assert not policy.is_enabled("graph")
    assert not policy.is_enabled("nlp")
    assert policy.is_enabled("sandbox")
    assert policy.is_enabled("admin")
    assert policy.experimental_bypass_enabled is True


def test_nonproduction_compliance_guard_is_preserved():
    with pytest.raises(RuntimeError, match="ALLOW_DISABLE_COMPLIANCE_ROUTERS"):
        RouterPolicy.from_environment(production=False, environ={"DISABLED_ROUTERS": "fda_export"})

    policy = RouterPolicy.from_environment(
        production=False,
        environ={"DISABLED_ROUTERS": "fda_export", "ALLOW_DISABLE_COMPLIANCE_ROUTERS": "true"},
    )
    assert not policy.is_enabled("fda_export")
