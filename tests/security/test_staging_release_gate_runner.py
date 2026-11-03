from __future__ import annotations

import importlib.util
import json
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "security" / "staging_release_gate.py"
_SPEC = importlib.util.spec_from_file_location("staging_release_gate", SCRIPT)
assert _SPEC and _SPEC.loader
_GATE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _GATE
_SPEC.loader.exec_module(_GATE)

GateError = _GATE.GateError
HttpResult = _GATE.HttpResult
_assert_actor_for_contract = _GATE._assert_actor_for_contract
_assert_actor_for_probe = _GATE._assert_actor_for_probe
_adapter_requirements = _GATE._adapter_requirements
execute_gate = _GATE.execute_gate
validate_gate_configuration = _GATE.validate_gate_configuration

MANIFEST_SHA = "a" * 64


def _operation(
    operation: str,
    method: str,
    path: str,
    classification: str,
    adapter: str,
) -> dict:
    return {
        "operation": operation,
        "owner": operation.split(":", 1)[0],
        "method": method,
        "path": path,
        "classification": classification,
        "authentication": "test-contract",
        "required_permissions": [],
        "storage_boundary": "test-boundary",
        "test_adapter": adapter,
    }


@pytest.fixture
def manifest() -> dict:
    enabled = [
        _operation("health:GET:/health", "GET", "/health", "public", "public_no_auth"),
        _operation(
            "records:GET:/records/{tenant_id}",
            "GET",
            "/records/{tenant_id}",
            "tenant-scoped",
            "tenant_api_key_postgres_rls",
        ),
        _operation(
            "records:POST:/records/{tenant_id}",
            "POST",
            "/records/{tenant_id}",
            "tenant-scoped",
            "tenant_api_key_postgres_rls",
        ),
        _operation(
            "admin:GET:/admin/keys",
            "GET",
            "/admin/keys",
            "global-sysadmin",
            "global_sysadmin_high_assurance",
        ),
        _operation("metrics:GET:/metrics", "GET", "/metrics", "workload-only", "workload_metrics_key"),
    ]
    counts = {
        "global-sysadmin": 1,
        "public": 1,
        "tenant-scoped": 2,
        "workload-only": 1,
    }
    return {
        "schema_version": 1,
        "enabled_operations": enabled,
        "disabled_operations": [],
        "summary": {"enabled_operation_count": len(enabled), "enabled_by_classification": counts},
    }


def _contract(operation: dict, actor: str, *, request: dict | None = None) -> dict:
    return {
        "operation": operation["operation"],
        "classification": operation["classification"],
        "test_adapter": operation["test_adapter"],
        "contract": {"actor": actor, "request": request or {}, "expect": {"status": [200]}},
    }


@pytest.fixture
def plan(manifest: dict) -> dict:
    by_id = {item["operation"]: item for item in manifest["enabled_operations"]}
    tenant_read = "records:GET:/records/{tenant_id}"
    tenant_write = "records:POST:/records/{tenant_id}"
    global_read = "admin:GET:/admin/keys"
    metrics = "metrics:GET:/metrics"
    return {
        "schema_version": 1,
        "manifest_sha256": MANIFEST_SHA,
        "target": {
            "environment": "staging",
            "base_url_env": "STAGING_BASE_URL",
            "expected_origin": "https://staging.example.test",
            "deployment_id": "staging-deployment-123",
        },
        "variables": {
            "TENANT_A_ID": "STAGING_TENANT_A_ID",
            "TENANT_A_MARKER": "STAGING_TENANT_A_MARKER",
            "TENANT_B_ID": "STAGING_TENANT_B_ID",
            "TENANT_B_MARKER": "STAGING_TENANT_B_MARKER",
        },
        "tenant_fixtures": {
            "a": {"id_variable": "TENANT_A_ID", "marker_variables": ["TENANT_A_MARKER"]},
            "b": {"id_variable": "TENANT_B_ID", "marker_variables": ["TENANT_B_MARKER"]},
        },
        "actors": {
            "anonymous": {"kind": "anonymous"},
            "tenant_a": {
                "kind": "tenant-api-key",
                "credential_env": "STAGING_TENANT_A_KEY",
                "tenant": "a",
            },
            "tenant_b": {
                "kind": "tenant-api-key",
                "credential_env": "STAGING_TENANT_B_KEY",
                "tenant": "b",
            },
            "sysadmin_high": {
                "kind": "session",
                "credential_env": "STAGING_SYSADMIN_HIGH_SESSION",
                "csrf_env": "STAGING_SYSADMIN_HIGH_CSRF",
                "tenant": "a",
                "assurance": "high",
                "is_sysadmin": True,
            },
            "sysadmin_low": {
                "kind": "session",
                "credential_env": "STAGING_SYSADMIN_LOW_SESSION",
                "csrf_env": "STAGING_SYSADMIN_LOW_CSRF",
                "tenant": "a",
                "assurance": "low",
                "is_sysadmin": True,
            },
            "staff_high": {
                "kind": "session",
                "credential_env": "STAGING_STAFF_HIGH_SESSION",
                "csrf_env": "STAGING_STAFF_HIGH_CSRF",
                "tenant": "a",
                "assurance": "high",
                "is_sysadmin": False,
            },
            "metrics": {"kind": "metrics-key", "credential_env": "STAGING_METRICS_KEY"},
        },
        "operations": [
            _contract(by_id["health:GET:/health"], "anonymous"),
            _contract(
                by_id[tenant_read],
                "tenant_a",
                request={"path_params": {"tenant_id": "{{TENANT_A_ID}}"}},
            ),
            _contract(
                by_id[tenant_write],
                "tenant_a",
                request={
                    "path_params": {"tenant_id": "{{TENANT_A_ID}}"},
                    "json": {"marker": "{{TENANT_B_MARKER}}"},
                },
            ),
            _contract(by_id[global_read], "sysadmin_high"),
            _contract(by_id[metrics], "metrics"),
        ],
        "adapter_scenarios": [
            {"test_adapter": "public_no_auth", "probes": []},
            {
                "test_adapter": "tenant_api_key_postgres_rls",
                "probes": [
                    {
                        "id": "tenant-unauthenticated",
                        "kind": "unauthenticated",
                        "operation": tenant_read,
                        "actor": "anonymous",
                        "request": {"path_params": {"tenant_id": "{{TENANT_A_ID}}"}},
                        "expect": {"status": [401]},
                    },
                    {
                        "id": "tenant-b-cannot-read-a",
                        "kind": "cross-tenant-read",
                        "operation": tenant_read,
                        "actor": "tenant_b",
                        "protected_tenant": "a",
                        "forbid_variables": ["TENANT_A_MARKER"],
                        "request": {"path_params": {"tenant_id": "{{TENANT_A_ID}}"}},
                        "expect": {"status": [200]},
                    },
                    {
                        "id": "tenant-b-cannot-write-a",
                        "kind": "cross-tenant-write",
                        "operation": tenant_write,
                        "actor": "tenant_b",
                        "protected_tenant": "a",
                        "request": {
                            "path_params": {"tenant_id": "{{TENANT_A_ID}}"},
                            "json": {"marker": "{{TENANT_A_MARKER}}"},
                        },
                        "expect": {"status": [409]},
                        "observe": {
                            "operation": tenant_read,
                            "actor": "tenant_a",
                            "request": {"path_params": {"tenant_id": "{{TENANT_A_ID}}"}},
                            "expect": {"status": [200]},
                            "json_pointers": ["/count"],
                        },
                    },
                ],
            },
            {
                "test_adapter": "global_sysadmin_high_assurance",
                "probes": [
                    {
                        "id": "global-unauthenticated",
                        "kind": "unauthenticated",
                        "operation": global_read,
                        "actor": "anonymous",
                        "request": {},
                        "expect": {"status": [401]},
                    },
                    {
                        "id": "global-low-assurance",
                        "kind": "low-assurance",
                        "operation": global_read,
                        "actor": "sysadmin_low",
                        "request": {},
                        "expect": {"status": [403]},
                    },
                    {
                        "id": "global-non-sysadmin",
                        "kind": "non-sysadmin",
                        "operation": global_read,
                        "actor": "staff_high",
                        "request": {},
                        "expect": {"status": [403]},
                    },
                ],
            },
            {
                "test_adapter": "workload_metrics_key",
                "probes": [
                    {
                        "id": "metrics-unauthenticated",
                        "kind": "unauthenticated",
                        "operation": metrics,
                        "actor": "anonymous",
                        "request": {},
                        "expect": {"status": [403]},
                    },
                    {
                        "id": "metrics-rejects-tenant-key",
                        "kind": "wrong-credential",
                        "operation": metrics,
                        "actor": "tenant_a",
                        "request": {},
                        "expect": {"status": [403]},
                    },
                ],
            },
        ],
    }


@pytest.fixture
def environment(plan: dict) -> dict[str, str]:
    values = {
        "STAGING_BASE_URL": "https://staging.example.test",
        "STAGING_TENANT_A_ID": "11111111-1111-4111-8111-111111111111",
        "STAGING_TENANT_A_MARKER": "tenant-a-only-marker",
        "STAGING_TENANT_B_ID": "22222222-2222-4222-8222-222222222222",
        "STAGING_TENANT_B_MARKER": "tenant-b-only-marker",
    }
    for actor in plan["actors"].values():
        if actor["kind"] != "anonymous":
            values[actor["credential_env"]] = f"value-for-{actor['credential_env'].lower()}"
        if actor["kind"] == "session":
            values[actor["csrf_env"]] = f"value-for-{actor['csrf_env'].lower()}"
    return values


def _validate(manifest: dict, plan: dict):
    return validate_gate_configuration(
        manifest,
        plan,
        manifest_sha256=MANIFEST_SHA,
        plan_dir=Path.cwd(),
    )


def _with_identity_isolation(manifest: dict, plan: dict) -> tuple[dict, dict]:
    manifest = deepcopy(manifest)
    plan = deepcopy(plan)
    erasure_id = "admin:POST:/v1/account/erasure"
    erasure = _operation(
        erasure_id,
        "POST",
        "/v1/account/erasure",
        "tenant-scoped",
        "tenant_identity_global_self_erasure",
    )
    auth_me = _operation(
        "admin:GET:/auth/me",
        "GET",
        "/auth/me",
        "tenant-scoped",
        "tenant_opaque_session",
    )
    manifest["enabled_operations"].extend((auth_me, erasure))
    manifest["summary"]["enabled_operation_count"] += 2
    manifest["summary"]["enabled_by_classification"]["tenant-scoped"] += 2

    plan["actors"].update(
        {
            "erasure_contract": {
                "kind": "session",
                "credential_env": "STAGING_ERASURE_CONTRACT_SESSION",
                "csrf_env": "STAGING_ERASURE_CONTRACT_CSRF",
                "tenant": "a",
                "assurance": "high",
                "is_sysadmin": False,
            },
            "erasure_actor_a": {
                "kind": "session",
                "credential_env": "STAGING_ERASURE_ACTOR_A_SESSION",
                "csrf_env": "STAGING_ERASURE_ACTOR_A_CSRF",
                "tenant": "a",
                "assurance": "high",
                "is_sysadmin": False,
            },
            "erasure_observer_b": {
                "kind": "session",
                "credential_env": "STAGING_ERASURE_OBSERVER_B_SESSION",
                "csrf_env": "STAGING_ERASURE_OBSERVER_B_CSRF",
                "tenant": "a",
                "assurance": "high",
                "is_sysadmin": False,
            },
            "erasure_outsider": {
                "kind": "session",
                "credential_env": "STAGING_ERASURE_OUTSIDER_SESSION",
                "csrf_env": "STAGING_ERASURE_OUTSIDER_CSRF",
                "tenant": "b",
                "assurance": "high",
                "is_sysadmin": False,
            },
        }
    )
    erasure_request = {"json": {"confirm": True, "reason": "staging-identity-isolation"}}
    plan["operations"].append(_contract(auth_me, "erasure_observer_b"))
    plan["operations"].append(_contract(erasure, "erasure_contract", request=erasure_request))
    plan["adapter_scenarios"].append(
        {
            "test_adapter": "tenant_opaque_session",
            "probes": [
                {
                    "id": "auth-me-unauthenticated",
                    "kind": "unauthenticated",
                    "operation": "admin:GET:/auth/me",
                    "actor": "anonymous",
                    "request": {},
                    "expect": {"status": [401]},
                },
                {
                    "id": "auth-me-outsider-cannot-read-a",
                    "kind": "cross-tenant-read",
                    "operation": "admin:GET:/auth/me",
                    "actor": "erasure_outsider",
                    "protected_tenant": "a",
                    "forbid_variables": ["TENANT_A_MARKER"],
                    "request": {},
                    "expect": {"status": [200]},
                },
            ],
        }
    )
    plan["adapter_scenarios"].append(
        {
            "test_adapter": "tenant_identity_global_self_erasure",
            "probes": [
                {
                    "id": "erasure-unauthenticated",
                    "kind": "unauthenticated",
                    "operation": erasure_id,
                    "actor": "anonymous",
                    "request": erasure_request,
                    "expect": {"status": [401]},
                },
                {
                    "id": "erasure-missing-csrf",
                    "kind": "csrf",
                    "operation": erasure_id,
                    "actor": "erasure_actor_a",
                    "request": {**erasure_request, "omit_csrf": True},
                    "expect": {"status": [403]},
                },
                {
                    "id": "erasure-a-cannot-change-b",
                    "kind": "identity-isolation-write",
                    "operation": erasure_id,
                    "actor": "erasure_actor_a",
                    "protected_tenant": "a",
                    "request": erasure_request,
                    "expect": {"status": [200]},
                    "mutator_observe": {
                        "operation": "admin:GET:/auth/me",
                        "request": {},
                        "expect": {"status": [200]},
                        "post_expect": {"status": [401]},
                    },
                    "observe": {
                        "operation": "admin:GET:/auth/me",
                        "actor": "erasure_observer_b",
                        "request": {},
                        "expect": {"status": [200]},
                        "json_pointers": [
                            "/user_id",
                            "/email",
                            "/tenant_id",
                            "/role",
                            "/is_sysadmin",
                        ],
                    },
                },
            ],
        }
    )
    return manifest, plan


def _identity_probe(plan: dict) -> dict:
    return plan["adapter_scenarios"][-1]["probes"][-1]


def test_checked_in_manifest_adapters_have_explicit_runtime_obligations():
    manifest = json.loads(Path("docs/security/route-security-manifest.json").read_text(encoding="utf-8"))
    by_adapter = defaultdict(list)
    for operation in manifest["enabled_operations"]:
        by_adapter[operation["test_adapter"]].append(operation)

    requirements = {adapter: _adapter_requirements(adapter, operations) for adapter, operations in by_adapter.items()}

    assert requirements == {
        "global_sysadmin_high_assurance": {"csrf", "low-assurance", "non-sysadmin", "unauthenticated"},
        "public_no_auth": set(),
        "public_optional_tenant_checkout": {
            "invalid-credential",
            "tenant-mismatch",
            "workload-credential",
        },
        "tenant_api_key_ingestion_postgres_filter": {"cross-tenant-read", "unauthenticated"},
        "tenant_api_key_mixed_storage": {"cross-tenant-read", "cross-tenant-write", "unauthenticated"},
        "tenant_api_key_no_persistence": {"cross-tenant-write", "unauthenticated"},
        "tenant_api_key_postgres_rls": {"cross-tenant-read", "cross-tenant-write", "unauthenticated"},
        "tenant_api_key_redis_job_owner": {"cross-tenant-read", "unauthenticated"},
        "tenant_dual_session_csrf": {"cross-tenant-read", "cross-tenant-write", "csrf", "unauthenticated"},
        "tenant_high_assurance_session": {
            "cross-tenant-write",
            "csrf",
            "low-assurance",
            "unauthenticated",
        },
        "tenant_identity_global_self_erasure": {
            "csrf",
            "identity-isolation-write",
            "unauthenticated",
        },
        "tenant_opaque_session": {"cross-tenant-read", "cross-tenant-write", "csrf", "unauthenticated"},
        "tenant_review_session": {"cross-tenant-read", "cross-tenant-write", "csrf", "unauthenticated"},
        "workload_metrics_key": {"unauthenticated", "wrong-credential"},
        "workload_stripe_signature": {"invalid-signature", "unsigned"},
        "workload_tenant_provisioner": {
            "expired",
            "revoked",
            "tenant-credential",
            "unauthenticated",
            "wrong-scope",
        },
    }


def test_tenant_high_assurance_adapter_rejects_api_keys_and_low_assurance_sessions():
    operation = _operation(
        "auth:POST:/auth/webauthn/register/verify",
        "POST",
        "/auth/webauthn/register/verify",
        "tenant-scoped",
        "tenant_high_assurance_session",
    )

    with pytest.raises(GateError, match="must use session"):
        _assert_actor_for_contract(
            {"kind": "tenant-api-key", "state": "active", "tenant": "a"},
            operation,
        )

    with pytest.raises(GateError, match="requires a high-assurance session"):
        _assert_actor_for_contract(
            {"kind": "session", "state": "active", "tenant": "a", "assurance": "low"},
            operation,
        )

    _assert_actor_for_contract(
        {"kind": "session", "state": "active", "tenant": "a", "assurance": "high"},
        operation,
    )


def test_tenant_high_assurance_adapter_low_assurance_probe_uses_tenant_session():
    _assert_actor_for_probe(
        {"kind": "session", "state": "active", "tenant": "a", "assurance": "low"},
        kind="low-assurance",
        request={},
        protected_tenant=None,
        adapter="tenant_high_assurance_session",
    )

    with pytest.raises(GateError, match="low-assurance session"):
        _assert_actor_for_probe(
            {"kind": "session", "state": "active", "tenant": "a", "assurance": "high"},
            kind="low-assurance",
            request={},
            protected_tenant=None,
            adapter="tenant_high_assurance_session",
        )


def test_complete_manifest_and_adapter_coverage_is_accepted(manifest: dict, plan: dict):
    coverage = _validate(manifest, plan)

    assert coverage.operation_count == 5
    assert coverage.adapter_count == 4
    assert coverage.request_count == 15
    assert coverage.classification_counts == {
        "global-sysadmin": 1,
        "public": 1,
        "tenant-scoped": 2,
        "workload-only": 1,
    }


def test_identity_isolation_write_requires_successful_distinct_same_tenant_sessions(
    manifest: dict,
    plan: dict,
):
    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)

    coverage = _validate(identity_manifest, identity_plan)

    assert coverage.operation_count == 7
    assert coverage.adapter_count == 6
    assert coverage.request_count == 26


def test_identity_isolation_write_rejects_denied_or_vacuous_status(
    manifest: dict,
    plan: dict,
):
    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    _identity_probe(identity_plan)["expect"]["status"] = [403]

    with pytest.raises(GateError, match="not valid for identity-isolation-write"):
        _validate(identity_manifest, identity_plan)


def test_identity_isolation_write_rejects_reusing_erased_contract_actor(
    manifest: dict,
    plan: dict,
):
    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    _identity_probe(identity_plan)["actor"] = "erasure_contract"

    with pytest.raises(GateError, match="must differ from the already-erased operation contract actor"):
        _validate(identity_manifest, identity_plan)


def test_identity_isolation_write_rejects_cross_tenant_or_same_actor_observation(
    manifest: dict,
    plan: dict,
):
    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    identity_plan["actors"]["erasure_actor_a"]["tenant"] = "b"

    with pytest.raises(GateError, match="active non-sysadmin session in the protected tenant"):
        _validate(identity_manifest, identity_plan)

    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    identity_plan["actors"]["erasure_observer_b"]["tenant"] = "b"

    with pytest.raises(GateError, match="observe actor must belong to the protected tenant"):
        _validate(identity_manifest, identity_plan)

    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    _identity_probe(identity_plan)["observe"]["actor"] = "erasure_actor_a"

    with pytest.raises(GateError, match="mutation and observation actors must use distinct sessions"):
        _validate(identity_manifest, identity_plan)


def test_identity_isolation_write_rejects_non_mutation_operation(
    manifest: dict,
    plan: dict,
):
    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    erasure = next(
        operation
        for operation in identity_manifest["enabled_operations"]
        if operation["operation"] == "admin:POST:/v1/account/erasure"
    )
    erasure["method"] = "GET"

    with pytest.raises(GateError, match="must reference a mutation operation"):
        _validate(identity_manifest, identity_plan)


def test_identity_isolation_write_rejects_missing_observation_or_read_success(
    manifest: dict,
    plan: dict,
):
    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    _identity_probe(identity_plan).pop("observe")

    with pytest.raises(GateError, match="observe is required for identity-isolation-write"):
        _validate(identity_manifest, identity_plan)

    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    _identity_probe(identity_plan)["observe"]["expect"]["status"] = [204]

    with pytest.raises(GateError, match=r"must be exactly \[200\]"):
        _validate(identity_manifest, identity_plan)


def test_identity_isolation_write_requires_canonical_mutator_preflight_and_post_401(
    manifest: dict,
    plan: dict,
):
    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    _identity_probe(identity_plan).pop("mutator_observe")

    with pytest.raises(GateError, match="mutator_observe is required"):
        _validate(identity_manifest, identity_plan)

    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    _identity_probe(identity_plan)["mutator_observe"]["operation"] = "admin:GET:/admin/keys"

    with pytest.raises(GateError, match="canonical authenticated identity read admin:GET:/auth/me"):
        _validate(identity_manifest, identity_plan)

    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    _identity_probe(identity_plan)["mutator_observe"]["post_expect"]["status"] = [403]

    with pytest.raises(GateError, match=r"post_expect.status must be exactly \[401\]"):
        _validate(identity_manifest, identity_plan)


def test_identity_isolation_write_rejects_declared_sysadmin_mutator(
    manifest: dict,
    plan: dict,
):
    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    identity_plan["actors"]["erasure_actor_a"]["is_sysadmin"] = True

    with pytest.raises(GateError, match="active non-sysadmin session in the protected tenant"):
        _validate(identity_manifest, identity_plan)


def test_identity_isolation_write_rejects_unrelated_observer_operation(
    manifest: dict,
    plan: dict,
):
    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    _identity_probe(identity_plan)["observe"]["operation"] = "admin:GET:/admin/keys"

    with pytest.raises(GateError, match="canonical authenticated identity read admin:GET:/auth/me"):
        _validate(identity_manifest, identity_plan)


def test_missing_operation_contract_fails_closed(manifest: dict, plan: dict):
    plan["operations"].pop()

    with pytest.raises(GateError, match="operation contract coverage is incomplete"):
        _validate(manifest, plan)


def test_missing_negative_adapter_probe_fails_closed(manifest: dict, plan: dict):
    plan["adapter_scenarios"][1]["probes"].pop()

    with pytest.raises(GateError, match="negative coverage must be exact"):
        _validate(manifest, plan)


def test_literal_credential_header_is_rejected(manifest: dict, plan: dict):
    plan["operations"][0]["contract"]["request"] = {"headers": {"Authorization": "not-a-credential"}}

    with pytest.raises(GateError, match="credential"):
        _validate(manifest, plan)


def test_vacuous_route_status_cannot_satisfy_gate(manifest: dict, plan: dict):
    plan["operations"][0]["contract"]["expect"]["status"] = [404]

    with pytest.raises(GateError, match="cannot accept 404"):
        _validate(manifest, plan)


def test_all_environment_inputs_are_checked_before_network(
    manifest: dict,
    plan: dict,
    environment: dict[str, str],
):
    _validate(manifest, plan)
    environment.pop("STAGING_TENANT_B_KEY")
    calls: list[str] = []

    def transport(*args, **kwargs):
        calls.append("called")
        raise AssertionError("network must not be reached")

    with pytest.raises(GateError, match="STAGING_TENANT_B_KEY"):
        execute_gate(
            manifest,
            plan,
            plan_dir=Path.cwd(),
            environ=environment,
            confirmed_deployment_id="staging-deployment-123",
            timeout=1,
            transport=transport,
        )

    assert calls == []


def test_identity_mutator_observation_is_prerendered_before_network(
    manifest: dict,
    plan: dict,
    environment: dict[str, str],
):
    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    identity_plan["variables"]["MUTATOR_PREFLIGHT_NONCE"] = "STAGING_MUTATOR_PREFLIGHT_NONCE"
    _identity_probe(identity_plan)["mutator_observe"]["request"] = {"query": {"nonce": "{{MUTATOR_PREFLIGHT_NONCE}}"}}
    _validate(identity_manifest, identity_plan)
    identity_environment = dict(environment)
    identity_environment["STAGING_MUTATOR_PREFLIGHT_NONCE"] = "{{MALFORMED_AT_RUNTIME}}"
    for actor in identity_plan["actors"].values():
        if actor["kind"] != "anonymous":
            identity_environment.setdefault(
                actor["credential_env"],
                f"value-for-{actor['credential_env'].lower()}",
            )
        if actor["kind"] == "session":
            identity_environment.setdefault(
                actor["csrf_env"],
                f"value-for-{actor['csrf_env'].lower()}",
            )
    calls: list[str] = []

    def transport(*args, **kwargs):
        calls.append("called")
        raise AssertionError("network must not be reached")

    with pytest.raises(GateError, match="malformed variable placeholder"):
        execute_gate(
            identity_manifest,
            identity_plan,
            plan_dir=Path.cwd(),
            environ=identity_environment,
            confirmed_deployment_id="staging-deployment-123",
            timeout=1,
            transport=transport,
        )

    assert calls == []


def test_cross_tenant_mutation_compares_protected_state(
    manifest: dict,
    plan: dict,
    environment: dict[str, str],
):
    _validate(manifest, plan)
    queued = [
        (200, b"{}"),
        (200, b"{}"),
        (200, b"{}"),
        (200, b"{}"),
        (200, b"{}"),
        (401, b"{}"),
        (200, b'{"items":["tenant-b-only-marker"]}'),
        (200, b'{"count":1}'),
        (409, b"{}"),
        (200, b'{"count":1}'),
        (401, b"{}"),
        (403, b"{}"),
        (403, b"{}"),
        (403, b"{}"),
        (403, b"{}"),
    ]
    calls: list[tuple[str, str]] = []
    sleeps: list[float] = []

    def transport(method, url, headers, body, timeout):
        calls.append((method, url))
        status, response_body = queued.pop(0)
        return HttpResult(status, {"content-type": "application/json"}, response_body, 1)

    results = execute_gate(
        manifest,
        plan,
        plan_dir=Path.cwd(),
        environ=environment,
        confirmed_deployment_id="staging-deployment-123",
        timeout=1,
        transport=transport,
        negative_probe_interval_seconds=13,
        sleeper=sleeps.append,
    )

    assert len(results) == 13
    assert len(calls) == 15
    assert queued == []
    assert all(url.startswith("https://staging.example.test/") for _, url in calls)
    assert len(sleeps) == 7
    assert all(12.9 < delay <= 13 for delay in sleeps)


def test_changed_protected_state_blocks_release(
    manifest: dict,
    plan: dict,
    environment: dict[str, str],
):
    _validate(manifest, plan)
    queued = [
        (200, b"{}"),
        (200, b"{}"),
        (200, b"{}"),
        (200, b"{}"),
        (200, b"{}"),
        (401, b"{}"),
        (200, b"{}"),
        (200, b'{"count":1}'),
        (409, b"{}"),
        (200, b'{"count":2}'),
    ]

    def transport(method, url, headers, body, timeout):
        status, response_body = queued.pop(0)
        return HttpResult(status, {}, response_body, 1)

    with pytest.raises(GateError, match="changed protected-tenant state"):
        execute_gate(
            manifest,
            plan,
            plan_dir=Path.cwd(),
            environ=environment,
            confirmed_deployment_id="staging-deployment-123",
            timeout=1,
            transport=transport,
        )


def _identity_execution_inputs(
    manifest: dict,
    plan: dict,
    environment: dict[str, str],
    *,
    observer_after: bytes,
    mutator_before: bytes | None = None,
    observer_before: bytes | None = None,
    mutator_after_status: int = 401,
) -> tuple[dict, dict, dict[str, str], list[tuple[int, bytes]]]:
    identity_manifest, identity_plan = _with_identity_isolation(manifest, plan)
    identity_environment = dict(environment)
    for actor in identity_plan["actors"].values():
        if actor["kind"] != "anonymous":
            identity_environment.setdefault(
                actor["credential_env"],
                f"value-for-{actor['credential_env'].lower()}",
            )
        if actor["kind"] == "session":
            identity_environment.setdefault(
                actor["csrf_env"],
                f"value-for-{actor['csrf_env'].lower()}",
            )
    protected_tenant_id = identity_environment["STAGING_TENANT_A_ID"]
    mutator_before = mutator_before or (
        b'{"user_id":"a","email":"a@example.test","tenant_id":"'
        + protected_tenant_id.encode()
        + b'","role":"member","is_sysadmin":false}'
    )
    observer_before = observer_before or (
        b'{"user_id":"b","email":"b@example.test","tenant_id":"'
        + protected_tenant_id.encode()
        + b'","role":"member","is_sysadmin":false}'
    )
    queued = [
        (200, b"{}"),
        (200, b"{}"),
        (200, b"{}"),
        (200, b"{}"),
        (200, b"{}"),
        (200, observer_before),
        (200, b"{}"),
        (401, b"{}"),
        (200, b'{"items":["tenant-b-only-marker"]}'),
        (200, b'{"count":1}'),
        (409, b"{}"),
        (200, b'{"count":1}'),
        (401, b"{}"),
        (403, b"{}"),
        (403, b"{}"),
        (403, b"{}"),
        (403, b"{}"),
        (401, b"{}"),
        (
            200,
            b'{"user_id":"outsider","email":"outsider@example.test",'
            b'"tenant_id":"b","role":"member","is_sysadmin":false}',
        ),
        (401, b"{}"),
        (403, b"{}"),
        (200, mutator_before),
        (200, observer_before),
        (200, b'{"status":"accepted"}'),
        (mutator_after_status, b"{}"),
        (200, observer_after),
    ]
    return identity_manifest, identity_plan, identity_environment, queued


def test_identity_isolation_write_compares_observer_values_after_successful_mutation(
    manifest: dict,
    plan: dict,
    environment: dict[str, str],
):
    identity_manifest, identity_plan, identity_environment, queued = _identity_execution_inputs(
        manifest,
        plan,
        environment,
        observer_after=(
            b'{"is_sysadmin":false,"role":"member",'
            b'"tenant_id":"11111111-1111-4111-8111-111111111111",'
            b'"email":"b@example.test","user_id":"b"}'
        ),
    )
    _validate(identity_manifest, identity_plan)
    calls: list[tuple[str, str]] = []

    def transport(method, url, headers, body, timeout):
        calls.append((method, url))
        status, response_body = queued.pop(0)
        return HttpResult(status, {"content-type": "application/json"}, response_body, 1)

    results = execute_gate(
        identity_manifest,
        identity_plan,
        plan_dir=Path.cwd(),
        environ=identity_environment,
        confirmed_deployment_id="staging-deployment-123",
        timeout=1,
        transport=transport,
    )

    assert len(results) == 20
    assert len(calls) == 26
    assert calls[-5:] == [
        ("GET", "https://staging.example.test/auth/me"),
        ("GET", "https://staging.example.test/auth/me"),
        ("POST", "https://staging.example.test/v1/account/erasure"),
        ("GET", "https://staging.example.test/auth/me"),
        ("GET", "https://staging.example.test/auth/me"),
    ]
    assert queued == []
    assert results[-1]["kind"] == "identity-isolation-write"
    assert results[-1]["status"] == 200
    assert results[-1]["mutator_preflight_status"] == 200
    assert results[-1]["mutator_postflight_status"] == 401
    assert results[-1]["observer_preflight_status"] == 200
    assert results[-1]["observer_postflight_status"] == 200


def test_identity_isolation_write_changed_observer_blocks_release(
    manifest: dict,
    plan: dict,
    environment: dict[str, str],
):
    identity_manifest, identity_plan, identity_environment, queued = _identity_execution_inputs(
        manifest,
        plan,
        environment,
        observer_after=(
            b'{"user_id":"b","email":"erased@example.test",'
            b'"tenant_id":"11111111-1111-4111-8111-111111111111",'
            b'"role":"member","is_sysadmin":false}'
        ),
    )
    _validate(identity_manifest, identity_plan)

    def transport(method, url, headers, body, timeout):
        status, response_body = queued.pop(0)
        return HttpResult(status, {"content-type": "application/json"}, response_body, 1)

    with pytest.raises(GateError, match="changed the observer identity during successful self-erasure"):
        execute_gate(
            identity_manifest,
            identity_plan,
            plan_dir=Path.cwd(),
            environ=identity_environment,
            confirmed_deployment_id="staging-deployment-123",
            timeout=1,
            transport=transport,
        )

    assert queued == []


def test_identity_isolation_write_rejects_same_runtime_identity(
    manifest: dict,
    plan: dict,
    environment: dict[str, str],
):
    tenant_id = environment["STAGING_TENANT_A_ID"]
    same_identity = (
        b'{"user_id":"same","email":"same@example.test","tenant_id":"'
        + tenant_id.encode()
        + b'","role":"member","is_sysadmin":false}'
    )
    identity_manifest, identity_plan, identity_environment, queued = _identity_execution_inputs(
        manifest,
        plan,
        environment,
        mutator_before=same_identity,
        observer_before=same_identity,
        observer_after=same_identity,
    )
    _validate(identity_manifest, identity_plan)

    def transport(method, url, headers, body, timeout):
        status, response_body = queued.pop(0)
        return HttpResult(status, {"content-type": "application/json"}, response_body, 1)

    with pytest.raises(GateError, match="must have distinct user_id values"):
        execute_gate(
            identity_manifest,
            identity_plan,
            plan_dir=Path.cwd(),
            environ=identity_environment,
            confirmed_deployment_id="staging-deployment-123",
            timeout=1,
            transport=transport,
        )


@pytest.mark.parametrize("identity_label", ["mutator", "observer"])
def test_identity_isolation_write_rejects_runtime_identity_from_wrong_tenant(
    identity_label: str,
    manifest: dict,
    plan: dict,
    environment: dict[str, str],
):
    wrong_tenant = (
        b'{"user_id":"wrong-tenant","email":"wrong@example.test",'
        b'"tenant_id":"22222222-2222-4222-8222-222222222222",'
        b'"role":"member","is_sysadmin":false}'
    )
    kwargs = {f"{identity_label}_before": wrong_tenant}
    identity_manifest, identity_plan, identity_environment, queued = _identity_execution_inputs(
        manifest,
        plan,
        environment,
        observer_after=(
            b'{"user_id":"b","email":"b@example.test",'
            b'"tenant_id":"11111111-1111-4111-8111-111111111111",'
            b'"role":"member","is_sysadmin":false}'
        ),
        **kwargs,
    )
    _validate(identity_manifest, identity_plan)

    def transport(method, url, headers, body, timeout):
        status, response_body = queued.pop(0)
        return HttpResult(status, {"content-type": "application/json"}, response_body, 1)

    with pytest.raises(GateError, match=f"{identity_label} /auth/me tenant_id did not match"):
        execute_gate(
            identity_manifest,
            identity_plan,
            plan_dir=Path.cwd(),
            environ=identity_environment,
            confirmed_deployment_id="staging-deployment-123",
            timeout=1,
            transport=transport,
        )


@pytest.mark.parametrize("identity_label", ["mutator", "observer"])
def test_identity_isolation_write_rejects_runtime_sysadmin_identity(
    identity_label: str,
    manifest: dict,
    plan: dict,
    environment: dict[str, str],
):
    tenant_id = environment["STAGING_TENANT_A_ID"]
    sysadmin_identity = (
        b'{"user_id":"runtime-sysadmin","email":"sysadmin@example.test","tenant_id":"'
        + tenant_id.encode()
        + b'","role":"admin","is_sysadmin":true}'
    )
    kwargs = {f"{identity_label}_before": sysadmin_identity}
    identity_manifest, identity_plan, identity_environment, queued = _identity_execution_inputs(
        manifest,
        plan,
        environment,
        observer_after=(
            b'{"user_id":"b","email":"b@example.test",'
            b'"tenant_id":"11111111-1111-4111-8111-111111111111",'
            b'"role":"member","is_sysadmin":false}'
        ),
        **kwargs,
    )
    _validate(identity_manifest, identity_plan)

    def transport(method, url, headers, body, timeout):
        status, response_body = queued.pop(0)
        return HttpResult(status, {"content-type": "application/json"}, response_body, 1)

    with pytest.raises(GateError, match=f"{identity_label} /auth/me must report is_sysadmin false"):
        execute_gate(
            identity_manifest,
            identity_plan,
            plan_dir=Path.cwd(),
            environ=identity_environment,
            confirmed_deployment_id="staging-deployment-123",
            timeout=1,
            transport=transport,
        )


def test_identity_isolation_write_rejects_noop_erasure_that_still_returns_200(
    manifest: dict,
    plan: dict,
    environment: dict[str, str],
):
    observer = (
        b'{"user_id":"b","email":"b@example.test",'
        b'"tenant_id":"11111111-1111-4111-8111-111111111111",'
        b'"role":"member","is_sysadmin":false}'
    )
    identity_manifest, identity_plan, identity_environment, queued = _identity_execution_inputs(
        manifest,
        plan,
        environment,
        observer_after=observer,
        mutator_after_status=200,
    )
    _validate(identity_manifest, identity_plan)

    def transport(method, url, headers, body, timeout):
        status, response_body = queued.pop(0)
        return HttpResult(status, {"content-type": "application/json"}, response_body, 1)

    with pytest.raises(GateError, match=r"returned HTTP 200; expected exact status \[401\]"):
        execute_gate(
            identity_manifest,
            identity_plan,
            plan_dir=Path.cwd(),
            environ=identity_environment,
            confirmed_deployment_id="staging-deployment-123",
            timeout=1,
            transport=transport,
        )
