from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

from server.router_policy import PRODUCTION_ENABLED_ROUTERS

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_release_evidence.py"
_SPEC = importlib.util.spec_from_file_location("_validate_release_evidence", _SCRIPT)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
REQUIRED_APPROVAL_CHECKS = _MODULE.REQUIRED_APPROVAL_CHECKS
validate_record = _MODULE.validate_record


def _candidate() -> dict:
    return {
        "schema_version": 1,
        "release_id": "candidate",
        "status": "not_approved",
        "release_approved": False,
        "verification_date": "2026-08-03",
        "frontend": {"git_sha": None, "deployment_id": None},
        "backend": {"git_sha": None, "deployment_id": None},
        "alembic_revision": "not_verified",
        "enabled_routers": sorted(PRODUCTION_ENABLED_ROUTERS),
        "environment_variable_names": ["DATABASE_URL", "REDIS_URL"],
        "checks": [],
    }


def test_non_approved_candidate_can_preserve_explicit_unknown_bindings():
    assert validate_record(_candidate()) == []


def test_approval_requires_immutable_bindings_and_every_release_gate():
    record = _candidate()
    record.update(status="approved", release_approved=True)

    errors = validate_record(record)

    assert any("frontend.git_sha" in error for error in errors)
    assert any("backend.deployment_id" in error for error in errors)
    assert all(any(check_id in error for error in errors) for check_id in REQUIRED_APPROVAL_CHECKS)


def test_duplicate_check_ids_are_rejected():
    record = _candidate()
    record["checks"] = [
        {"id": "route_manifest", "environment": "source", "command": "a", "result": "fail"},
        {"id": "route_manifest", "environment": "source", "command": "b", "result": "pass"},
    ]

    errors = validate_record(record)

    assert any("duplicate check id" in error for error in errors)


def test_secret_values_and_router_drift_are_rejected():
    record = copy.deepcopy(_candidate())
    record["api_key_value"] = "rge_live_should_never_be_recorded"  # pragma: allowlist secret
    record["enabled_routers"].append("graph")
    record["environment_variable_names"] = ["DATABASE_URL=postgresql://user:password@example/db"]  # pragma: allowlist secret

    errors = validate_record(record)

    assert any("secret-bearing field" in error for error in errors)
    assert any("value resembles secret material" in error for error in errors)
    assert any("extra=['graph']" in error for error in errors)
    assert any("names only" in error for error in errors)
