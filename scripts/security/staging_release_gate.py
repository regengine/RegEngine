#!/usr/bin/env python3
"""Run the manifest-bound RegEngine staging security release gate.

The checked-in route manifest is source evidence.  This runner consumes a
separate, sanitized staging plan containing only fixture descriptions and
environment-variable names.  It refuses to contact a target until the plan is
complete, every referenced environment value exists, and the operator confirms
the exact staging deployment ID.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "docs" / "security" / "route-security-manifest.json"
CLASSIFICATIONS = frozenset({"public", "tenant-scoped", "global-sysadmin", "workload-only"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
DISALLOWED_GATE_STATUSES = frozenset({404, 405, 422})
IDENTITY_OBSERVER_OPERATION = "admin:GET:/auth/me"
IDENTITY_OBSERVER_POINTERS = frozenset({"/email", "/is_sysadmin", "/role", "/tenant_id", "/user_id"})
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
PLACEHOLDER_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
PATH_PARAMETER_RE = re.compile(r"\{([^}:]+)(?::([^}]+))?\}")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
SECRET_VALUE_RE = re.compile(r"(?i)^(?:bearer\s+\S+|rge_[A-Za-z0-9_-]{16,}|sk_(?:live|test)_\S+|whsec_\S+)$")
SENSITIVE_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "host",
        "stripe-signature",
        "x-admin-key",
        "x-csrf-token",
        "x-metrics-key",
        "x-regengine-api-key",
        "x-regengine-proxy-ip",
        "x-regengine-proxy-signature",
        "x-regengine-proxy-timestamp",
    }
)
ACTOR_KINDS = frozenset(
    {
        "anonymous",
        "metrics-key",
        "session",
        "stripe-signature",
        "tenant-api-key",
        "workload-api-key",
    }
)
ACTOR_STATES = frozenset({"active", "expired", "invalid", "revoked", "wrong-scope"})
KNOWN_PROBE_KINDS = frozenset(
    {
        "cross-tenant-read",
        "cross-tenant-write",
        "csrf",
        "expired",
        "invalid-credential",
        "invalid-signature",
        "identity-isolation-write",
        "low-assurance",
        "non-sysadmin",
        "revoked",
        "tenant-credential",
        "tenant-mismatch",
        "unauthenticated",
        "unsigned",
        "workload-credential",
        "wrong-credential",
        "wrong-scope",
    }
)


class GateError(RuntimeError):
    """A sanitized, release-blocking validation or execution error."""


@dataclass(frozen=True)
class Coverage:
    operation_count: int
    adapter_count: int
    classification_counts: dict[str, int]
    request_count: int


@dataclass(frozen=True)
class HttpResult:
    status: int
    headers: Mapping[str, str]
    body: bytes
    duration_ms: int


Transport = Callable[[str, str, Mapping[str, str], bytes | None, float], HttpResult]
Sleeper = Callable[[float], None]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_file(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GateError(f"Unable to read {label}: {path}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GateError(f"{label} is not valid JSON: line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(payload, dict):
        raise GateError(f"{label} must be a JSON object")
    return payload, _sha256_bytes(raw)


def _exact_keys(value: Mapping[str, Any], allowed: set[str], *, location: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise GateError(f"{location} has unknown fields: {unknown}")


def _nonempty_string(value: Any, *, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GateError(f"{location} must be a non-empty string")
    return value.strip()


def _environment_name(value: Any, *, location: str) -> str:
    name = _nonempty_string(value, location=location)
    if not ENV_NAME_RE.fullmatch(name):
        raise GateError(f"{location} must be an uppercase environment-variable name")
    return name


def _identifier(value: Any, *, location: str) -> str:
    identifier = _nonempty_string(value, location=location)
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise GateError(f"{location} contains unsupported characters")
    return identifier


def _reject_secret_literals(value: Any, *, location: str = "plan") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_secret_literals(child, location=f"{location}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_literals(child, location=f"{location}[{index}]")
        return
    if not isinstance(value, str):
        return
    lowered = value.lower()
    if SECRET_VALUE_RE.fullmatch(value) or "__host-regengine_session=" in lowered:
        raise GateError(f"{location} appears to contain a credential; reference an environment variable instead")


def _validate_manifest(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if manifest.get("schema_version") != 1:
        raise GateError("route manifest schema_version must be 1")
    enabled = manifest.get("enabled_operations")
    if not isinstance(enabled, list) or not enabled:
        raise GateError("route manifest enabled_operations must be a non-empty list")

    operations: dict[str, dict[str, Any]] = {}
    classification_counts = {classification: 0 for classification in CLASSIFICATIONS}
    for index, raw in enumerate(enabled):
        location = f"manifest.enabled_operations[{index}]"
        if not isinstance(raw, dict):
            raise GateError(f"{location} must be an object")
        for field in ("operation", "owner", "method", "path", "classification", "test_adapter"):
            _nonempty_string(raw.get(field), location=f"{location}.{field}")
        operation = raw["operation"]
        if operation in operations:
            raise GateError(f"route manifest contains duplicate operation {operation}")
        classification = raw["classification"]
        if classification not in CLASSIFICATIONS:
            raise GateError(f"{operation} has unknown classification {classification}")
        method = raw["method"]
        if method != method.upper():
            raise GateError(f"{operation} method must be uppercase")
        if not raw["path"].startswith("/"):
            raise GateError(f"{operation} path must be absolute")
        operations[operation] = raw
        classification_counts[classification] += 1

    if any(count == 0 for count in classification_counts.values()):
        raise GateError(
            "route manifest must contain public, tenant-scoped, global-sysadmin, and workload-only operations"
        )
    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        raise GateError("route manifest summary is missing")
    if summary.get("enabled_operation_count") != len(operations):
        raise GateError("route manifest enabled_operation_count is inconsistent")
    if summary.get("enabled_by_classification") != dict(sorted(classification_counts.items())):
        raise GateError("route manifest classification summary is inconsistent")
    return operations


def _validate_variables(plan: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    variables_raw = plan.get("variables")
    if not isinstance(variables_raw, dict) or not variables_raw:
        raise GateError("plan.variables must map sanitized names to environment-variable names")
    variables: dict[str, str] = {}
    for name, env_name in variables_raw.items():
        variable = _environment_name(name, location="plan.variables key")
        variables[variable] = _environment_name(env_name, location=f"plan.variables.{variable}")

    fixtures_raw = plan.get("tenant_fixtures")
    if not isinstance(fixtures_raw, dict) or len(fixtures_raw) < 2:
        raise GateError("plan.tenant_fixtures must define at least two disposable tenants")
    fixtures: dict[str, dict[str, Any]] = {}
    for label, raw in fixtures_raw.items():
        tenant_label = _identifier(label, location="plan.tenant_fixtures key")
        if not isinstance(raw, dict):
            raise GateError(f"plan.tenant_fixtures.{tenant_label} must be an object")
        _exact_keys(raw, {"id_variable", "marker_variables"}, location=f"plan.tenant_fixtures.{tenant_label}")
        id_variable = _environment_name(
            raw.get("id_variable"), location=f"plan.tenant_fixtures.{tenant_label}.id_variable"
        )
        markers = raw.get("marker_variables")
        if not isinstance(markers, list) or not markers:
            raise GateError(f"plan.tenant_fixtures.{tenant_label}.marker_variables must be non-empty")
        marker_variables = [
            _environment_name(item, location=f"plan.tenant_fixtures.{tenant_label}.marker_variables")
            for item in markers
        ]
        if id_variable not in variables or any(marker not in variables for marker in marker_variables):
            raise GateError(f"plan.tenant_fixtures.{tenant_label} references undeclared variables")
        fixtures[tenant_label] = {"id_variable": id_variable, "marker_variables": marker_variables}
    return variables, fixtures


def _validate_actors(plan: Mapping[str, Any], fixtures: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    actors_raw = plan.get("actors")
    if not isinstance(actors_raw, dict) or not actors_raw:
        raise GateError("plan.actors must be a non-empty object")
    actors: dict[str, dict[str, Any]] = {}
    credential_owners: dict[str, str] = {}
    csrf_owners: dict[str, str] = {}
    for name, raw in actors_raw.items():
        actor_name = _identifier(name, location="plan.actors key")
        if not isinstance(raw, dict):
            raise GateError(f"plan.actors.{actor_name} must be an object")
        _exact_keys(
            raw,
            {"assurance", "credential_env", "csrf_env", "is_sysadmin", "kind", "scopes", "state", "tenant"},
            location=f"plan.actors.{actor_name}",
        )
        kind = raw.get("kind")
        if kind not in ACTOR_KINDS:
            raise GateError(f"plan.actors.{actor_name}.kind is unsupported")
        state = raw.get("state", "active")
        if state not in ACTOR_STATES:
            raise GateError(f"plan.actors.{actor_name}.state is unsupported")
        if kind == "anonymous":
            if set(raw) != {"kind"}:
                raise GateError(f"anonymous actor {actor_name} cannot contain credential metadata")
        else:
            credential_env = _environment_name(
                raw.get("credential_env"), location=f"plan.actors.{actor_name}.credential_env"
            )
            previous = credential_owners.setdefault(credential_env, actor_name)
            if previous != actor_name:
                raise GateError(f"actors {previous} and {actor_name} cannot share credential_env {credential_env}")
        tenant = raw.get("tenant")
        if tenant is not None and tenant not in fixtures:
            raise GateError(f"plan.actors.{actor_name}.tenant is not a declared tenant fixture")
        if kind in {"tenant-api-key", "session"} and tenant is None:
            raise GateError(f"plan.actors.{actor_name} must name its credential-bound tenant")
        if kind == "session":
            assurance = raw.get("assurance")
            if assurance not in {"low", "high"}:
                raise GateError(f"plan.actors.{actor_name}.assurance must be low or high")
            if not isinstance(raw.get("is_sysadmin"), bool):
                raise GateError(f"plan.actors.{actor_name}.is_sysadmin must be boolean")
            csrf_env = _environment_name(raw.get("csrf_env"), location=f"plan.actors.{actor_name}.csrf_env")
            if csrf_env == raw["credential_env"]:
                raise GateError(f"session actor {actor_name} must use separate credential and CSRF variables")
            previous = csrf_owners.setdefault(csrf_env, actor_name)
            if previous != actor_name:
                raise GateError(f"session actors {previous} and {actor_name} cannot share csrf_env {csrf_env}")
        scopes = raw.get("scopes", [])
        if not isinstance(scopes, list) or any(not isinstance(scope, str) or not scope for scope in scopes):
            raise GateError(f"plan.actors.{actor_name}.scopes must be a string list")
        actors[actor_name] = dict(raw)
        actors[actor_name]["state"] = state
    return actors


def _validate_expected_statuses(expect: Any, *, kind: str, location: str) -> list[int]:
    if not isinstance(expect, dict):
        raise GateError(f"{location} must be an object")
    _exact_keys(expect, {"header_equals", "json_equals", "status"}, location=location)
    statuses = expect.get("status")
    if not isinstance(statuses, list) or not statuses or any(type(status) is not int for status in statuses):
        raise GateError(f"{location}.status must contain exact integer statuses")
    if len(statuses) != len(set(statuses)) or any(status < 100 or status > 599 for status in statuses):
        raise GateError(f"{location}.status contains invalid or duplicate statuses")
    if DISALLOWED_GATE_STATUSES.intersection(statuses):
        raise GateError(f"{location}.status cannot accept 404, 405, or 422 as release-gate evidence")

    allowed: set[int]
    if kind == "contract":
        allowed = set(range(200, 300))
    elif kind in {"unauthenticated", "low-assurance", "non-sysadmin", "wrong-credential"}:
        allowed = {401, 403}
    elif kind == "identity-isolation-write":
        allowed = set(range(200, 300))
    elif kind == "cross-tenant-read":
        allowed = {200, 401, 403, 409}
    elif kind in {
        "cross-tenant-write",
        "expired",
        "invalid-credential",
        "revoked",
        "tenant-credential",
        "workload-credential",
        "wrong-scope",
    }:
        allowed = {401, 403, 409}
    elif kind in {"invalid-signature", "unsigned"}:
        allowed = {400, 401, 403}
    elif kind == "tenant-mismatch":
        allowed = {403, 409}
    elif kind == "csrf":
        allowed = {403}
    else:
        raise GateError(f"{location} has unsupported probe kind {kind}")
    if not set(statuses).issubset(allowed):
        raise GateError(f"{location}.status is not valid for {kind}: {statuses}")
    if kind == "identity-isolation-write" and len(statuses) != 1:
        raise GateError(f"{location}.status must name exactly one successful 2xx status")

    for field in ("header_equals", "json_equals"):
        assertions = expect.get(field, {})
        if not isinstance(assertions, dict):
            raise GateError(f"{location}.{field} must be an object")
    if any(not isinstance(header, str) or not header for header in expect.get("header_equals", {})):
        raise GateError(f"{location}.header_equals contains an invalid header name")
    if any(
        not isinstance(pointer, str) or (pointer != "" and not pointer.startswith("/"))
        for pointer in expect.get("json_equals", {})
    ):
        raise GateError(f"{location}.json_equals contains an invalid RFC 6901 pointer")
    return statuses


def _require_identity_observer_operation(
    operation_id: str,
    operation: Mapping[str, Any] | None,
    *,
    location: str,
) -> Mapping[str, Any]:
    if not (
        operation_id == IDENTITY_OBSERVER_OPERATION
        and operation is not None
        and operation["owner"] == "admin"
        and operation["method"] == "GET"
        and operation["path"] == "/auth/me"
    ):
        raise GateError(f"{location} must use the canonical authenticated identity read {IDENTITY_OBSERVER_OPERATION}")
    return operation


def _referenced_placeholders(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_referenced_placeholders(child) for child in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_referenced_placeholders(child) for child in value), set())
    if isinstance(value, str):
        return set(PLACEHOLDER_RE.findall(value))
    return set()


def _validate_request(
    request: Any,
    operation: Mapping[str, Any],
    variables: Mapping[str, str],
    *,
    plan_dir: Path,
    location: str,
) -> set[str]:
    if not isinstance(request, dict):
        raise GateError(f"{location} must be an object")
    _exact_keys(
        request,
        {"body_file", "content_type", "headers", "json", "omit_csrf", "path_params", "query"},
        location=location,
    )
    path_params = request.get("path_params", {})
    if not isinstance(path_params, dict):
        raise GateError(f"{location}.path_params must be an object")
    required_params = {match.group(1) for match in PATH_PARAMETER_RE.finditer(operation["path"])}
    if set(path_params) != required_params:
        raise GateError(
            f"{location}.path_params must exactly match {sorted(required_params)} for {operation['operation']}"
        )
    query = request.get("query", {})
    headers = request.get("headers", {})
    if not isinstance(query, dict) or not isinstance(headers, dict):
        raise GateError(f"{location}.query and headers must be objects")
    if any(not isinstance(key, str) or not key for key in query):
        raise GateError(f"{location}.query contains an invalid parameter name")
    if any(not isinstance(key, str) or not key for key in headers):
        raise GateError(f"{location}.headers contains an invalid header name")
    forbidden = sorted(header for header in headers if header.lower() in SENSITIVE_REQUEST_HEADERS)
    if forbidden:
        raise GateError(f"{location}.headers cannot contain credential headers: {forbidden}")
    if "json" in request and "body_file" in request:
        raise GateError(f"{location} cannot set both json and body_file")
    body_file = request.get("body_file")
    if body_file is not None:
        relative = Path(_nonempty_string(body_file, location=f"{location}.body_file"))
        if relative.is_absolute() or ".." in relative.parts:
            raise GateError(f"{location}.body_file must stay below the external plan directory")
        fixture_path = (plan_dir / relative).resolve()
        try:
            fixture_path.relative_to(plan_dir.resolve())
        except ValueError as exc:
            raise GateError(f"{location}.body_file escapes the external plan directory") from exc
        if not fixture_path.is_file():
            raise GateError(f"{location}.body_file does not exist")
    if "content_type" in request:
        _nonempty_string(request["content_type"], location=f"{location}.content_type")
    if not isinstance(request.get("omit_csrf", False), bool):
        raise GateError(f"{location}.omit_csrf must be boolean")
    referenced = _referenced_placeholders(request)
    unknown_variables = sorted(referenced - set(variables))
    if unknown_variables:
        raise GateError(f"{location} references undeclared variables: {unknown_variables}")
    return referenced


def _validate_placeholder_references(value: Any, variables: Mapping[str, str], *, location: str) -> set[str]:
    referenced = _referenced_placeholders(value)
    unknown = sorted(referenced - set(variables))
    if unknown:
        raise GateError(f"{location} references undeclared variables: {unknown}")
    return referenced


def _adapter_requirements(adapter: str, operations: list[Mapping[str, Any]]) -> set[str]:
    methods = {operation["method"] for operation in operations}
    has_read = bool(methods & SAFE_METHODS)
    has_write = bool(methods - SAFE_METHODS)
    if adapter == "public_no_auth":
        return set()
    if adapter == "public_optional_tenant_checkout":
        return {"invalid-credential", "tenant-mismatch", "workload-credential"}
    if adapter == "tenant_identity_global_self_erasure":
        return {"csrf", "identity-isolation-write", "unauthenticated"}
    if adapter.startswith("tenant_"):
        required = {"unauthenticated"}
        if has_read:
            required.add("cross-tenant-read")
        if has_write:
            required.add("cross-tenant-write")
        if has_write and adapter in {
            "tenant_dual_session_csrf",
            "tenant_high_assurance_session",
            "tenant_opaque_session",
            "tenant_review_session",
        }:
            required.add("csrf")
        if adapter == "tenant_high_assurance_session":
            required.add("low-assurance")
        return required
    if adapter == "global_sysadmin_high_assurance":
        required = {"low-assurance", "non-sysadmin", "unauthenticated"}
        if has_write:
            required.add("csrf")
        return required
    if adapter == "workload_metrics_key":
        return {"unauthenticated", "wrong-credential"}
    if adapter == "workload_stripe_signature":
        return {"invalid-signature", "unsigned"}
    if adapter == "workload_tenant_provisioner":
        return {"expired", "revoked", "tenant-credential", "unauthenticated", "wrong-scope"}
    raise GateError(f"manifest uses unknown staging test adapter {adapter}")


def _assert_actor_for_contract(actor: Mapping[str, Any], operation: Mapping[str, Any]) -> None:
    classification = operation["classification"]
    adapter = operation["test_adapter"]
    if actor["state"] != "active":
        raise GateError(f"contract actor for {operation['operation']} must be active")
    if classification == "public" and actor["kind"] != "anonymous":
        raise GateError(f"public contract {operation['operation']} must use an anonymous actor")
    if classification == "tenant-scoped":
        expected_kind = (
            "session"
            if adapter
            in {
                "tenant_dual_session_csrf",
                "tenant_high_assurance_session",
                "tenant_identity_global_self_erasure",
                "tenant_opaque_session",
                "tenant_review_session",
            }
            else "tenant-api-key"
        )
        if actor["kind"] != expected_kind:
            raise GateError(f"tenant contract {operation['operation']} must use {expected_kind}")
        if adapter == "tenant_high_assurance_session" and actor.get("assurance") != "high":
            raise GateError(f"tenant contract {operation['operation']} requires a high-assurance session")
    if classification == "global-sysadmin" and not (
        actor["kind"] == "session" and actor.get("assurance") == "high" and actor.get("is_sysadmin") is True
    ):
        raise GateError(f"global contract {operation['operation']} requires a high-assurance sysadmin session")
    if classification == "workload-only":
        expected_kind = {
            "workload_metrics_key": "metrics-key",
            "workload_stripe_signature": "stripe-signature",
            "workload_tenant_provisioner": "workload-api-key",
        }[adapter]
        if actor["kind"] != expected_kind:
            raise GateError(f"workload contract {operation['operation']} must use {expected_kind}")
        if adapter == "workload_tenant_provisioner" and actor.get("scopes") != ["internal.tenants.create"]:
            raise GateError("tenant-provisioner contract actor must have only internal.tenants.create")


def _assert_actor_for_probe(
    actor: Mapping[str, Any],
    *,
    kind: str,
    request: Mapping[str, Any],
    protected_tenant: str | None,
    adapter: str,
) -> None:
    if kind in {"unauthenticated", "unsigned"} and actor["kind"] != "anonymous":
        raise GateError(f"{kind} probe must use the anonymous actor")
    if kind in {"cross-tenant-read", "cross-tenant-write"}:
        if protected_tenant is None or actor.get("tenant") is None or actor.get("tenant") == protected_tenant:
            raise GateError(f"{kind} probe must use a credential bound to a different disposable tenant")
        expected_kind = (
            "session"
            if adapter
            in {
                "tenant_dual_session_csrf",
                "tenant_high_assurance_session",
                "tenant_identity_global_self_erasure",
                "tenant_opaque_session",
                "tenant_review_session",
            }
            else "tenant-api-key"
        )
        if actor["kind"] != expected_kind or actor["state"] != "active":
            raise GateError(f"{kind} probe must use an active {expected_kind}")
    if kind == "identity-isolation-write" and not (
        actor["kind"] == "session"
        and actor["state"] == "active"
        and actor.get("is_sysadmin") is False
        and protected_tenant is not None
        and actor.get("tenant") == protected_tenant
    ):
        raise GateError(
            "identity-isolation-write probe must use an active non-sysadmin session in the protected tenant"
        )
    if kind == "tenant-mismatch" and not (
        actor["kind"] == "tenant-api-key"
        and actor["state"] == "active"
        and protected_tenant is not None
        and actor.get("tenant") != protected_tenant
    ):
        raise GateError("tenant-mismatch probe must use an active tenant key and declare the asserted tenant")
    if kind == "csrf" and not (
        actor["kind"] == "session" and actor["state"] == "active" and request.get("omit_csrf") is True
    ):
        raise GateError("csrf probe must use an active session and explicitly omit CSRF")
    if kind == "low-assurance":
        valid_low_assurance_actor = actor["kind"] == "session" and actor.get("assurance") == "low"
        if adapter == "global_sysadmin_high_assurance":
            valid_low_assurance_actor = valid_low_assurance_actor and actor.get("is_sysadmin") is True
        if not valid_low_assurance_actor:
            expected = (
                "low-assurance sysadmin session"
                if adapter == "global_sysadmin_high_assurance"
                else "low-assurance session"
            )
            raise GateError(f"low-assurance probe must use a {expected}")
    if kind == "non-sysadmin" and not (
        actor["kind"] == "session" and actor.get("assurance") == "high" and actor.get("is_sysadmin") is False
    ):
        raise GateError("non-sysadmin probe must use a high-assurance non-sysadmin session")
    required_states = {
        "expired": "expired",
        "invalid-credential": "invalid",
        "invalid-signature": "invalid",
        "revoked": "revoked",
        "wrong-scope": "wrong-scope",
    }
    if kind in required_states and actor["state"] != required_states[kind]:
        raise GateError(f"{kind} probe actor must declare state {required_states[kind]}")
    required_kinds = {
        "invalid-credential": "tenant-api-key",
        "invalid-signature": "stripe-signature",
        "tenant-credential": "tenant-api-key",
        "workload-credential": "workload-api-key",
        "wrong-credential": "tenant-api-key",
        "wrong-scope": "workload-api-key",
        "expired": "workload-api-key",
        "revoked": "workload-api-key",
    }
    if kind in required_kinds and actor["kind"] != required_kinds[kind]:
        raise GateError(f"{kind} probe must use {required_kinds[kind]}")
    if kind in {"tenant-credential", "workload-credential", "wrong-credential"} and actor["state"] != "active":
        raise GateError(f"{kind} probe must use an active credential from the wrong realm")
    if kind == "wrong-scope" and "internal.tenants.create" in actor.get("scopes", []):
        raise GateError("wrong-scope actor cannot include internal.tenants.create")


def validate_gate_configuration(
    manifest: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    manifest_sha256: str,
    plan_dir: Path,
) -> Coverage:
    """Validate complete route/adapter coverage without reading credentials or making requests."""

    _reject_secret_literals(plan)
    _exact_keys(
        plan,
        {
            "actors",
            "adapter_scenarios",
            "manifest_sha256",
            "operations",
            "schema_version",
            "target",
            "tenant_fixtures",
            "variables",
        },
        location="plan",
    )
    if plan.get("schema_version") != 1:
        raise GateError("staging plan schema_version must be 1")
    if plan.get("manifest_sha256") != manifest_sha256:
        raise GateError("staging plan is not bound to the exact route manifest SHA-256")
    operations = _validate_manifest(manifest)
    variables, fixtures = _validate_variables(plan)
    actors = _validate_actors(plan, fixtures)

    target = plan.get("target")
    if not isinstance(target, dict):
        raise GateError("plan.target must be an object")
    _exact_keys(target, {"base_url_env", "deployment_id", "environment", "expected_origin"}, location="plan.target")
    if target.get("environment") != "staging":
        raise GateError("plan.target.environment must be exactly staging")
    _environment_name(target.get("base_url_env"), location="plan.target.base_url_env")
    _identifier(target.get("deployment_id"), location="plan.target.deployment_id")
    _validate_expected_origin(target.get("expected_origin"))

    plan_operations = plan.get("operations")
    if not isinstance(plan_operations, list):
        raise GateError("plan.operations must be a list")
    seen_operations: set[str] = set()
    contract_actors: dict[str, str] = {}
    used_actors: set[str] = set()
    used_variables: set[str] = {
        variable for fixture in fixtures.values() for variable in [fixture["id_variable"], *fixture["marker_variables"]]
    }
    request_count = 0
    for index, raw in enumerate(plan_operations):
        location = f"plan.operations[{index}]"
        if not isinstance(raw, dict):
            raise GateError(f"{location} must be an object")
        _exact_keys(raw, {"classification", "contract", "operation", "test_adapter"}, location=location)
        operation_id = _nonempty_string(raw.get("operation"), location=f"{location}.operation")
        operation = operations.get(operation_id)
        if operation is None:
            raise GateError(f"{location} references an operation absent from the manifest")
        if operation_id in seen_operations:
            raise GateError(f"plan contains duplicate operation contract {operation_id}")
        seen_operations.add(operation_id)
        if (
            raw.get("classification") != operation["classification"]
            or raw.get("test_adapter") != operation["test_adapter"]
        ):
            raise GateError(f"{operation_id} classification/test_adapter does not match the manifest")
        contract = raw.get("contract")
        if not isinstance(contract, dict):
            raise GateError(f"{location}.contract must be an object")
        _exact_keys(contract, {"actor", "expect", "request"}, location=f"{location}.contract")
        actor_name = _nonempty_string(contract.get("actor"), location=f"{location}.contract.actor")
        actor = actors.get(actor_name)
        if actor is None:
            raise GateError(f"{location}.contract references undeclared actor {actor_name}")
        _assert_actor_for_contract(actor, operation)
        _validate_expected_statuses(contract.get("expect"), kind="contract", location=f"{location}.contract.expect")
        used_variables |= _validate_request(
            contract.get("request", {}),
            operation,
            variables,
            plan_dir=plan_dir,
            location=f"{location}.contract.request",
        )
        used_variables |= _validate_placeholder_references(
            contract.get("expect"), variables, location=f"{location}.contract.expect"
        )
        used_actors.add(actor_name)
        contract_actors[operation_id] = actor_name
        request_count += 1
    missing = sorted(set(operations) - seen_operations)
    extra = sorted(seen_operations - set(operations))
    if missing or extra:
        raise GateError(f"operation contract coverage is incomplete: missing={missing}, extra={extra}")

    by_adapter: dict[str, list[dict[str, Any]]] = {}
    for operation in operations.values():
        by_adapter.setdefault(operation["test_adapter"], []).append(operation)
    scenarios = plan.get("adapter_scenarios")
    if not isinstance(scenarios, list):
        raise GateError("plan.adapter_scenarios must be a list")
    seen_adapters: set[str] = set()
    seen_probe_ids: set[str] = set()
    for index, raw in enumerate(scenarios):
        location = f"plan.adapter_scenarios[{index}]"
        if not isinstance(raw, dict):
            raise GateError(f"{location} must be an object")
        _exact_keys(raw, {"probes", "test_adapter"}, location=location)
        adapter = _nonempty_string(raw.get("test_adapter"), location=f"{location}.test_adapter")
        if adapter not in by_adapter:
            raise GateError(f"{location} references an adapter absent from the manifest")
        if adapter in seen_adapters:
            raise GateError(f"plan contains duplicate adapter scenario {adapter}")
        seen_adapters.add(adapter)
        probes = raw.get("probes")
        if not isinstance(probes, list):
            raise GateError(f"{location}.probes must be a list")
        observed_kinds: set[str] = set()
        for probe_index, probe in enumerate(probes):
            probe_location = f"{location}.probes[{probe_index}]"
            if not isinstance(probe, dict):
                raise GateError(f"{probe_location} must be an object")
            _exact_keys(
                probe,
                {
                    "actor",
                    "expect",
                    "forbid_variables",
                    "id",
                    "kind",
                    "mutator_observe",
                    "observe",
                    "operation",
                    "protected_tenant",
                    "request",
                },
                location=probe_location,
            )
            probe_id = _identifier(probe.get("id"), location=f"{probe_location}.id")
            if probe_id in seen_probe_ids:
                raise GateError(f"duplicate staging probe id {probe_id}")
            seen_probe_ids.add(probe_id)
            kind = probe.get("kind")
            if kind not in KNOWN_PROBE_KINDS:
                raise GateError(f"{probe_location}.kind is unsupported")
            if kind in observed_kinds:
                raise GateError(f"adapter {adapter} contains duplicate required probe kind {kind}")
            observed_kinds.add(kind)
            operation_id = _nonempty_string(probe.get("operation"), location=f"{probe_location}.operation")
            operation = operations.get(operation_id)
            if operation is None or operation["test_adapter"] != adapter:
                raise GateError(f"{probe_location}.operation is not owned by adapter {adapter}")
            if kind == "cross-tenant-read" and operation["method"] not in SAFE_METHODS:
                raise GateError(f"{probe_location} must reference a read operation")
            if (
                kind in {"cross-tenant-write", "identity-isolation-write", "csrf"}
                and operation["method"] in SAFE_METHODS
            ):
                raise GateError(f"{probe_location} must reference a mutation operation")
            actor_name = _nonempty_string(probe.get("actor"), location=f"{probe_location}.actor")
            actor = actors.get(actor_name)
            if actor is None:
                raise GateError(f"{probe_location} references undeclared actor {actor_name}")
            request = probe.get("request", {})
            protected_tenant = probe.get("protected_tenant")
            if protected_tenant is not None and protected_tenant not in fixtures:
                raise GateError(f"{probe_location}.protected_tenant is undeclared")
            if protected_tenant is not None and kind not in {
                "cross-tenant-read",
                "cross-tenant-write",
                "identity-isolation-write",
                "tenant-mismatch",
            }:
                raise GateError(f"{probe_location}.protected_tenant is not valid for {kind}")
            _assert_actor_for_probe(
                actor, kind=kind, request=request, protected_tenant=protected_tenant, adapter=adapter
            )
            if kind == "identity-isolation-write" and actor_name == contract_actors[operation_id]:
                raise GateError(f"{probe_location}.actor must differ from the already-erased operation contract actor")
            _validate_expected_statuses(probe.get("expect"), kind=kind, location=f"{probe_location}.expect")
            used_variables |= _validate_request(
                request, operation, variables, plan_dir=plan_dir, location=f"{probe_location}.request"
            )
            if kind == "tenant-mismatch":
                asserted = next(
                    (value for header, value in request.get("headers", {}).items() if header.lower() == "x-tenant-id"),
                    None,
                )
                expected_assertion = f"{{{{{fixtures[protected_tenant]['id_variable']}}}}}"
                if asserted != expected_assertion:
                    raise GateError(f"{probe_location} must assert the protected tenant through X-Tenant-ID")
            used_variables |= _validate_placeholder_references(
                probe.get("expect"), variables, location=f"{probe_location}.expect"
            )
            used_actors.add(actor_name)
            forbid_variables = probe.get("forbid_variables", [])
            if not isinstance(forbid_variables, list) or any(
                variable not in variables for variable in forbid_variables
            ):
                raise GateError(f"{probe_location}.forbid_variables references undeclared variables")
            if kind == "cross-tenant-read":
                if protected_tenant is None:
                    raise GateError(f"{probe_location} must declare protected_tenant")
                required_markers = set(fixtures[protected_tenant]["marker_variables"])
                if not required_markers.issubset(forbid_variables):
                    raise GateError(f"{probe_location} must forbid every protected-tenant marker variable")
            elif forbid_variables:
                raise GateError(f"{probe_location}.forbid_variables is only valid for cross-tenant-read")
            used_variables.update(forbid_variables)

            observe = probe.get("observe")
            mutator_observe = probe.get("mutator_observe")
            if kind in {"cross-tenant-write", "identity-isolation-write"}:
                if not isinstance(observe, dict):
                    raise GateError(f"{probe_location}.observe is required for {kind}")
                _exact_keys(
                    observe,
                    {"actor", "expect", "json_pointers", "operation", "request"},
                    location=f"{probe_location}.observe",
                )
                observe_operation_id = _nonempty_string(
                    observe.get("operation"), location=f"{probe_location}.observe.operation"
                )
                observe_operation = operations.get(observe_operation_id)
                if observe_operation is None or observe_operation["method"] not in SAFE_METHODS:
                    raise GateError(f"{probe_location}.observe must use an enabled read operation")
                observe_actor_name = _nonempty_string(observe.get("actor"), location=f"{probe_location}.observe.actor")
                observe_actor = actors.get(observe_actor_name)
                if observe_actor is None or observe_actor.get("tenant") != protected_tenant:
                    raise GateError(f"{probe_location}.observe actor must belong to the protected tenant")
                observe_statuses = _validate_expected_statuses(
                    observe.get("expect"), kind="contract", location=f"{probe_location}.observe.expect"
                )
                if kind == "identity-isolation-write":
                    _require_identity_observer_operation(
                        observe_operation_id,
                        observe_operation,
                        location=f"{probe_location}.observe",
                    )
                    if not (
                        observe_actor["kind"] == "session"
                        and observe_actor["state"] == "active"
                        and observe_actor.get("is_sysadmin") is False
                    ):
                        raise GateError(
                            f"{probe_location}.observe actor must be an active non-sysadmin session "
                            "in the protected tenant"
                        )
                    if observe_actor_name == actor_name or observe_actor["credential_env"] == actor["credential_env"]:
                        raise GateError(f"{probe_location} mutation and observation actors must use distinct sessions")
                    if observe_actor_name == contract_actors[operation_id]:
                        raise GateError(
                            f"{probe_location}.observe actor must differ from the already-erased "
                            "operation contract actor"
                        )
                    if observe_statuses != [200]:
                        raise GateError(f"{probe_location}.observe.expect.status must be exactly [200]")
                    _assert_actor_for_contract(observe_actor, observe_operation)
                pointers = observe.get("json_pointers")
                if (
                    not isinstance(pointers, list)
                    or not pointers
                    or any(
                        not isinstance(pointer, str) or (pointer != "" and not pointer.startswith("/"))
                        for pointer in pointers
                    )
                ):
                    raise GateError(f"{probe_location}.observe.json_pointers must be a non-empty string list")
                if kind == "identity-isolation-write" and not IDENTITY_OBSERVER_POINTERS.issubset(pointers):
                    raise GateError(
                        f"{probe_location}.observe.json_pointers must include the observer identity fields "
                        f"{sorted(IDENTITY_OBSERVER_POINTERS)}"
                    )
                used_variables |= _validate_request(
                    observe.get("request", {}),
                    observe_operation,
                    variables,
                    plan_dir=plan_dir,
                    location=f"{probe_location}.observe.request",
                )
                used_variables |= _validate_placeholder_references(
                    observe.get("expect"), variables, location=f"{probe_location}.observe.expect"
                )
                used_actors.add(observe_actor_name)
                request_count += 2
            elif observe is not None:
                raise GateError(
                    f"{probe_location}.observe is only valid for cross-tenant-write or identity-isolation-write"
                )
            if kind == "identity-isolation-write":
                if not isinstance(mutator_observe, dict):
                    raise GateError(f"{probe_location}.mutator_observe is required for identity-isolation-write")
                _exact_keys(
                    mutator_observe,
                    {"expect", "operation", "post_expect", "request"},
                    location=f"{probe_location}.mutator_observe",
                )
                mutator_operation_id = _nonempty_string(
                    mutator_observe.get("operation"),
                    location=f"{probe_location}.mutator_observe.operation",
                )
                mutator_operation = _require_identity_observer_operation(
                    mutator_operation_id,
                    operations.get(mutator_operation_id),
                    location=f"{probe_location}.mutator_observe",
                )
                _assert_actor_for_contract(actor, mutator_operation)
                mutator_statuses = _validate_expected_statuses(
                    mutator_observe.get("expect"),
                    kind="contract",
                    location=f"{probe_location}.mutator_observe.expect",
                )
                if mutator_statuses != [200]:
                    raise GateError(f"{probe_location}.mutator_observe.expect.status must be exactly [200]")
                mutator_post_statuses = _validate_expected_statuses(
                    mutator_observe.get("post_expect"),
                    kind="unauthenticated",
                    location=f"{probe_location}.mutator_observe.post_expect",
                )
                if mutator_post_statuses != [401]:
                    raise GateError(f"{probe_location}.mutator_observe.post_expect.status must be exactly [401]")
                used_variables |= _validate_request(
                    mutator_observe.get("request", {}),
                    mutator_operation,
                    variables,
                    plan_dir=plan_dir,
                    location=f"{probe_location}.mutator_observe.request",
                )
                used_variables |= _validate_placeholder_references(
                    mutator_observe.get("expect"),
                    variables,
                    location=f"{probe_location}.mutator_observe.expect",
                )
                used_variables |= _validate_placeholder_references(
                    mutator_observe.get("post_expect"),
                    variables,
                    location=f"{probe_location}.mutator_observe.post_expect",
                )
                request_count += 2
            elif mutator_observe is not None:
                raise GateError(f"{probe_location}.mutator_observe is only valid for identity-isolation-write")
            request_count += 1

        required = _adapter_requirements(adapter, by_adapter[adapter])
        if observed_kinds != required:
            raise GateError(
                f"adapter {adapter} negative coverage must be exact: required={sorted(required)}, "
                f"observed={sorted(observed_kinds)}"
            )
    missing_adapters = sorted(set(by_adapter) - seen_adapters)
    if missing_adapters:
        raise GateError(f"adapter scenario coverage is incomplete: missing={missing_adapters}")

    unused_actors = sorted(set(actors) - used_actors)
    unused_variables = sorted(set(variables) - used_variables)
    if unused_actors or unused_variables:
        raise GateError(f"plan contains unused inputs: actors={unused_actors}, variables={unused_variables}")

    counts = {classification: 0 for classification in sorted(CLASSIFICATIONS)}
    for operation in operations.values():
        counts[operation["classification"]] += 1
    return Coverage(len(operations), len(by_adapter), counts, request_count)


def _validate_expected_origin(value: Any) -> str:
    origin = _nonempty_string(value, location="plan.target.expected_origin").rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
    ):
        raise GateError("plan.target.expected_origin must be a credential-free HTTPS origin")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise GateError("staging origin must be externally reachable, not localhost or an internal hostname")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise GateError("staging origin must use a reviewed DNS hostname, not an IP literal")
    return origin


def _render(value: Any, resolved_variables: Mapping[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _render(child, resolved_variables) for key, child in value.items()}
    if isinstance(value, list):
        return [_render(child, resolved_variables) for child in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        return resolved_variables[match.group(1)]

    rendered = PLACEHOLDER_RE.sub(replace, value)
    if "{{" in rendered or "}}" in rendered:
        raise GateError("request contains a malformed variable placeholder")
    return rendered


def _path_for(operation: Mapping[str, Any], request: Mapping[str, Any], resolved: Mapping[str, str]) -> str:
    path_params = _render(request.get("path_params", {}), resolved)

    def replace(match: re.Match[str]) -> str:
        name, converter = match.group(1), match.group(2)
        raw = str(path_params[name])
        return quote(raw, safe="/" if converter == "path" else "")

    path = PATH_PARAMETER_RE.sub(replace, operation["path"])
    query = _render(request.get("query", {}), resolved)
    if query:
        path = f"{path}?{urlencode(query, doseq=True)}"
    return path


def _request_body(
    request: Mapping[str, Any], resolved: Mapping[str, str], plan_dir: Path
) -> tuple[bytes | None, str | None]:
    if "json" in request:
        body = json.dumps(_render(request["json"], resolved), separators=(",", ":")).encode()
        content_type = request.get("content_type", "application/json")
    elif "body_file" in request:
        try:
            body = (plan_dir / request["body_file"]).read_bytes()
        except OSError as exc:
            raise GateError("staging body fixture became unavailable before execution") from exc
        content_type = request.get("content_type", "application/octet-stream")
    else:
        return None, request.get("content_type")
    if len(body) > 16 * 1024 * 1024:
        raise GateError("staging request body exceeded the 16 MiB safety limit")
    return body, content_type


def _render_request_headers(
    operation: Mapping[str, Any], request: Mapping[str, Any], resolved: Mapping[str, str]
) -> dict[str, str]:
    headers = {key: str(value) for key, value in _render(request.get("headers", {}), resolved).items()}
    if any("\r" in value or "\n" in value for value in headers.values()):
        raise GateError(f"{operation['operation']} request headers contain invalid newline bytes")
    return headers


def _actor_headers(
    actor: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    environ: Mapping[str, str],
    body: bytes | None,
) -> dict[str, str]:
    kind = actor["kind"]
    if kind == "anonymous":
        return {}
    credential = environ[actor["credential_env"]]
    if any(character in credential for character in "\r\n"):
        raise GateError(f"credential environment variable {actor['credential_env']} contains invalid header bytes")
    if kind in {"tenant-api-key", "workload-api-key"}:
        return {"X-RegEngine-API-Key": credential}
    if kind == "metrics-key":
        return {"X-Metrics-Key": credential}
    if kind == "session":
        if any(character in credential for character in ";, "):
            raise GateError(f"session environment variable {actor['credential_env']} is not an opaque cookie value")
        headers = {"Cookie": f"__Host-regengine_session={credential}"}
        if not request.get("omit_csrf", False):
            csrf = environ[actor["csrf_env"]]
            if any(character in csrf for character in "\r\n"):
                raise GateError(f"CSRF environment variable {actor['csrf_env']} contains invalid header bytes")
            headers["X-CSRF-Token"] = csrf
        return headers
    if kind == "stripe-signature":
        timestamp = str(int(time.time()))
        signed = timestamp.encode() + b"." + (body or b"")
        signature = hmac.new(credential.encode(), signed, hashlib.sha256).hexdigest()
        return {"Stripe-Signature": f"t={timestamp},v1={signature}"}
    raise GateError(f"unsupported actor kind {kind}")


def _json_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise GateError("observation JSON pointers must be RFC 6901 paths")
    current = value
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        try:
            current = current[int(token)] if isinstance(current, list) else current[token]
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise GateError(f"observation JSON pointer {pointer} was absent") from exc
    return current


def _observation_value_bytes(value: Any) -> bytes:
    """Return a type-preserving, deterministic encoding for JSON observations."""

    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _identity_payload(result: HttpResult, *, label: str, phase: str = "preflight") -> Mapping[str, Any]:
    try:
        payload = json.loads(result.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"{label} /auth/me {phase} did not return JSON") from exc
    if not isinstance(payload, dict):
        raise GateError(f"{label} /auth/me {phase} must return a JSON object")
    return payload


def _assert_identity_isolation_preflight(
    mutator: Mapping[str, Any],
    observer: Mapping[str, Any],
    *,
    protected_tenant_id: str,
) -> None:
    identities = (("mutator", mutator), ("observer", observer))
    for label, identity_response in identities:
        user_id = identity_response.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise GateError(f"identity-isolation-write {label} /auth/me must return a non-empty user_id")
        if identity_response.get("tenant_id") != protected_tenant_id:
            raise GateError(
                f"identity-isolation-write {label} /auth/me tenant_id did not match "
                "the resolved protected tenant fixture"
            )
        if identity_response.get("is_sysadmin") is not False:
            raise GateError(f"identity-isolation-write {label} /auth/me must report is_sysadmin false")
    if mutator["user_id"] == observer["user_id"]:
        raise GateError(
            "identity-isolation-write mutator and observer /auth/me responses must have distinct user_id values"
        )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


def _urllib_transport(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
) -> HttpResult:
    opener = build_opener(_NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))
    request = Request(url, data=body, headers=dict(headers), method=method)
    started = time.monotonic()
    try:
        response = opener.open(request, timeout=timeout)
    except HTTPError as exc:
        response = exc
    except (OSError, URLError) as exc:
        raise GateError("staging request failed before an HTTP response was received") from exc
    try:
        body_bytes = response.read(16 * 1024 * 1024 + 1)
        if len(body_bytes) > 16 * 1024 * 1024:
            raise GateError("staging response exceeded the 16 MiB evidence limit")
        response_headers = {key.lower(): value for key, value in response.headers.items()}
        status = int(response.status)
    finally:
        response.close()
    return HttpResult(status, response_headers, body_bytes, int((time.monotonic() - started) * 1000))


def _perform(
    operation: Mapping[str, Any],
    actor: Mapping[str, Any],
    request: Mapping[str, Any],
    expect: Mapping[str, Any],
    *,
    origin: str,
    environ: Mapping[str, str],
    resolved_variables: Mapping[str, str],
    plan_dir: Path,
    timeout: float,
    transport: Transport,
    forbid_values: list[str] | None = None,
) -> HttpResult:
    path = _path_for(operation, request, resolved_variables)
    body, content_type = _request_body(request, resolved_variables, plan_dir)
    headers = {"Accept": "application/json", "User-Agent": "RegEngine-Staging-Security-Gate/1"}
    headers.update(_render_request_headers(operation, request, resolved_variables))
    headers.update(_actor_headers(actor, request, environ=environ, body=body))
    if content_type:
        headers["Content-Type"] = content_type
    result = transport(operation["method"], origin + path, headers, body, timeout)
    if result.status not in expect["status"]:
        raise GateError(
            f"{operation['operation']} returned HTTP {result.status}; expected exact status {expect['status']}"
        )
    for header, expected in expect.get("header_equals", {}).items():
        actual = result.headers.get(header.lower())
        if actual != _render(expected, resolved_variables):
            raise GateError(f"{operation['operation']} response header assertion failed for {header}")
    if expect.get("json_equals"):
        try:
            payload = json.loads(result.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GateError(f"{operation['operation']} did not return JSON required by the plan") from exc
        for pointer, expected in expect["json_equals"].items():
            if _json_pointer(payload, pointer) != _render(expected, resolved_variables):
                raise GateError(f"{operation['operation']} JSON assertion failed at {pointer}")
    for forbidden in forbid_values or []:
        if forbidden.encode() in result.body:
            raise GateError(f"{operation['operation']} disclosed a protected-tenant marker")
    return result


def _all_environment_names(plan: Mapping[str, Any]) -> set[str]:
    names = {plan["target"]["base_url_env"]}
    names.update(plan["variables"].values())
    for actor in plan["actors"].values():
        if actor["kind"] != "anonymous":
            names.add(actor["credential_env"])
        if actor["kind"] == "session":
            names.add(actor["csrf_env"])
    return names


def _execute_case(
    operation: Mapping[str, Any],
    actor_name: str,
    request: Mapping[str, Any],
    expect: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    origin: str,
    environ: Mapping[str, str],
    resolved: Mapping[str, str],
    plan_dir: Path,
    timeout: float,
    transport: Transport,
    forbid_variables: list[str] | None = None,
) -> HttpResult:
    forbidden_values = [resolved[name] for name in forbid_variables or []]
    return _perform(
        operation,
        plan["actors"][actor_name],
        request,
        expect,
        origin=origin,
        environ=environ,
        resolved_variables=resolved,
        plan_dir=plan_dir,
        timeout=timeout,
        transport=transport,
        forbid_values=forbidden_values,
    )


def execute_gate(
    manifest: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    plan_dir: Path,
    environ: Mapping[str, str],
    confirmed_deployment_id: str,
    timeout: float,
    transport: Transport = _urllib_transport,
    results: list[dict[str, Any]] | None = None,
    negative_probe_interval_seconds: float = 0.0,
    sleeper: Sleeper = time.sleep,
) -> list[dict[str, Any]]:
    """Execute a previously validated plan and return sanitized per-probe evidence."""

    target = plan["target"]
    if confirmed_deployment_id != target["deployment_id"]:
        raise GateError("operator confirmation does not match the staging deployment ID in the plan")
    missing_env = sorted(name for name in _all_environment_names(plan) if not environ.get(name, "").strip())
    if missing_env:
        raise GateError(f"required staging environment variables are missing or empty: {missing_env}")
    credential_names = [actor["credential_env"] for actor in plan["actors"].values() if actor["kind"] != "anonymous"]
    if len({environ[name] for name in credential_names}) != len(credential_names):
        raise GateError("staging actors must use distinct credential values")
    csrf_names = [actor["csrf_env"] for actor in plan["actors"].values() if actor["kind"] == "session"]
    if len({environ[name] for name in csrf_names}) != len(csrf_names):
        raise GateError("staging session actors must use distinct CSRF values")
    expected_origin = _validate_expected_origin(target["expected_origin"])
    actual_origin = _validate_expected_origin(environ[target["base_url_env"]])
    if actual_origin != expected_origin:
        raise GateError("staging base URL does not exactly match the reviewed expected origin")
    resolved = {name: environ[env_name] for name, env_name in plan["variables"].items()}
    if len(set(resolved.values())) != len(resolved):
        raise GateError("disposable staging variable values must be distinct")
    operations = {operation["operation"]: operation for operation in manifest["enabled_operations"]}

    # Pre-render every request before the first network call.  A late missing
    # placeholder or fixture cannot leave the matrix partially executed.
    for item in plan["operations"]:
        contract = item["contract"]
        operation = operations[item["operation"]]
        _path_for(operation, contract["request"], resolved)
        body, _ = _request_body(contract["request"], resolved, plan_dir)
        _render_request_headers(operation, contract["request"], resolved)
        _actor_headers(plan["actors"][contract["actor"]], contract["request"], environ=environ, body=body)
    for scenario in plan["adapter_scenarios"]:
        for probe in scenario["probes"]:
            operation = operations[probe["operation"]]
            _path_for(operation, probe["request"], resolved)
            body, _ = _request_body(probe["request"], resolved, plan_dir)
            _render_request_headers(operation, probe["request"], resolved)
            _actor_headers(plan["actors"][probe["actor"]], probe["request"], environ=environ, body=body)
            if probe.get("mutator_observe"):
                mutator_observe = probe["mutator_observe"]
                mutator_operation = operations[mutator_observe["operation"]]
                _path_for(mutator_operation, mutator_observe["request"], resolved)
                body, _ = _request_body(mutator_observe["request"], resolved, plan_dir)
                _render_request_headers(mutator_operation, mutator_observe["request"], resolved)
                _actor_headers(
                    plan["actors"][probe["actor"]],
                    mutator_observe["request"],
                    environ=environ,
                    body=body,
                )
            if probe.get("observe"):
                observe = probe["observe"]
                observe_operation = operations[observe["operation"]]
                _path_for(observe_operation, observe["request"], resolved)
                body, _ = _request_body(observe["request"], resolved, plan_dir)
                _render_request_headers(observe_operation, observe["request"], resolved)
                _actor_headers(plan["actors"][observe["actor"]], observe["request"], environ=environ, body=body)

    if results is None:
        results = []
    for item in plan["operations"]:
        contract = item["contract"]
        operation = operations[item["operation"]]
        response = _execute_case(
            operation,
            contract["actor"],
            contract["request"],
            contract["expect"],
            plan=plan,
            origin=actual_origin,
            environ=environ,
            resolved=resolved,
            plan_dir=plan_dir,
            timeout=timeout,
            transport=transport,
        )
        results.append(
            {
                "operation": operation["operation"],
                "test_adapter": operation["test_adapter"],
                "probe_id": "contract",
                "kind": "contract",
                "status": response.status,
                "duration_ms": response.duration_ms,
            }
        )

    last_adapter_probe_finished: float | None = None
    for scenario in plan["adapter_scenarios"]:
        for probe in scenario["probes"]:
            if last_adapter_probe_finished is not None and negative_probe_interval_seconds:
                elapsed = time.monotonic() - last_adapter_probe_finished
                remaining = negative_probe_interval_seconds - elapsed
                if remaining > 0:
                    sleeper(remaining)
            operation = operations[probe["operation"]]
            mutator_observe = probe.get("mutator_observe")
            observe = probe.get("observe")
            mutator_preflight: HttpResult | None = None
            mutator_payload: Mapping[str, Any] | None = None
            if mutator_observe:
                mutator_operation = operations[mutator_observe["operation"]]
                mutator_preflight = _execute_case(
                    mutator_operation,
                    probe["actor"],
                    mutator_observe["request"],
                    mutator_observe["expect"],
                    plan=plan,
                    origin=actual_origin,
                    environ=environ,
                    resolved=resolved,
                    plan_dir=plan_dir,
                    timeout=timeout,
                    transport=transport,
                )
                mutator_payload = _identity_payload(mutator_preflight, label="mutator")

            observer_preflight: HttpResult | None = None
            observer_payload: Mapping[str, Any] | None = None
            before: list[bytes] | None = None
            if observe:
                observe_operation = operations[observe["operation"]]
                observer_preflight = _execute_case(
                    observe_operation,
                    observe["actor"],
                    observe["request"],
                    observe["expect"],
                    plan=plan,
                    origin=actual_origin,
                    environ=environ,
                    resolved=resolved,
                    plan_dir=plan_dir,
                    timeout=timeout,
                    transport=transport,
                )
                if probe["kind"] == "identity-isolation-write":
                    observer_payload = _identity_payload(observer_preflight, label="observer")
                    payload: Any = observer_payload
                else:
                    try:
                        payload = json.loads(observer_preflight.body)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise GateError(f"{operation['operation']} mutation observation did not return JSON") from exc
                before = [
                    _observation_value_bytes(_json_pointer(payload, pointer)) for pointer in observe["json_pointers"]
                ]

            if probe["kind"] == "identity-isolation-write":
                if mutator_payload is None or observer_payload is None:
                    raise GateError("identity-isolation-write requires both /auth/me preflight responses")
                fixture = plan["tenant_fixtures"][probe["protected_tenant"]]
                _assert_identity_isolation_preflight(
                    mutator_payload,
                    observer_payload,
                    protected_tenant_id=resolved[fixture["id_variable"]],
                )

            response = _execute_case(
                operation,
                probe["actor"],
                probe["request"],
                probe["expect"],
                plan=plan,
                origin=actual_origin,
                environ=environ,
                resolved=resolved,
                plan_dir=plan_dir,
                timeout=timeout,
                transport=transport,
                forbid_variables=probe.get("forbid_variables"),
            )

            mutator_postflight: HttpResult | None = None
            if mutator_observe:
                mutator_operation = operations[mutator_observe["operation"]]
                mutator_postflight = _execute_case(
                    mutator_operation,
                    probe["actor"],
                    mutator_observe["request"],
                    mutator_observe["post_expect"],
                    plan=plan,
                    origin=actual_origin,
                    environ=environ,
                    resolved=resolved,
                    plan_dir=plan_dir,
                    timeout=timeout,
                    transport=transport,
                )

            observer_postflight: HttpResult | None = None
            if observe:
                observe_operation = operations[observe["operation"]]
                observer_postflight = _execute_case(
                    observe_operation,
                    observe["actor"],
                    observe["request"],
                    observe["expect"],
                    plan=plan,
                    origin=actual_origin,
                    environ=environ,
                    resolved=resolved,
                    plan_dir=plan_dir,
                    timeout=timeout,
                    transport=transport,
                )
                if probe["kind"] == "identity-isolation-write":
                    payload = _identity_payload(observer_postflight, label="observer", phase="postflight")
                else:
                    try:
                        payload = json.loads(observer_postflight.body)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise GateError(f"{operation['operation']} mutation observation did not return JSON") from exc
                after = [
                    _observation_value_bytes(_json_pointer(payload, pointer)) for pointer in observe["json_pointers"]
                ]
                if before != after:
                    if probe["kind"] == "identity-isolation-write":
                        raise GateError(
                            f"{operation['operation']} changed the observer identity during successful self-erasure"
                        )
                    raise GateError(f"{operation['operation']} changed protected-tenant state during a denied mutation")

            probe_result = {
                "operation": operation["operation"],
                "test_adapter": operation["test_adapter"],
                "probe_id": probe["id"],
                "kind": probe["kind"],
                "status": response.status,
                "duration_ms": response.duration_ms,
            }
            if mutator_preflight is not None and mutator_postflight is not None:
                probe_result["mutator_preflight_status"] = mutator_preflight.status
                probe_result["mutator_postflight_status"] = mutator_postflight.status
            if observer_preflight is not None and observer_postflight is not None:
                probe_result["observer_preflight_status"] = observer_preflight.status
                probe_result["observer_postflight_status"] = observer_postflight.status
            results.append(probe_result)
            last_adapter_probe_finished = time.monotonic()
    return results


def _write_evidence(
    path: Path,
    *,
    status: str,
    manifest_sha256: str,
    plan_sha256: str,
    plan: Mapping[str, Any],
    coverage: Coverage,
    results: list[dict[str, Any]],
    failure: str | None,
    negative_probe_interval_seconds: float,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "verification_date": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": manifest_sha256,
        "plan_sha256": plan_sha256,
        "target": {
            "environment": "staging",
            "expected_origin": plan["target"]["expected_origin"],
            "deployment_id": plan["target"]["deployment_id"],
        },
        "referenced_environment_variables": sorted(_all_environment_names(plan)),
        "coverage": {
            "operation_count": coverage.operation_count,
            "adapter_count": coverage.adapter_count,
            "classification_counts": coverage.classification_counts,
            "request_count": coverage.request_count,
            "negative_probe_interval_seconds": negative_probe_interval_seconds,
        },
        "results": results,
    }
    if failure is not None:
        payload["failure"] = failure
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--plan", type=Path, required=True, help="Sanitized external staging plan JSON")
    parser.add_argument(
        "--validate-only", action="store_true", help="Validate coverage without reading env values or making requests"
    )
    parser.add_argument("--confirm-staging-deployment", help="Exact deployment ID from the reviewed staging plan")
    parser.add_argument("--evidence-out", type=Path, help="Sanitized JSON evidence output (required for execution)")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--negative-probe-interval",
        type=float,
        default=13.0,
        help="Seconds between adapter probes; release evidence requires at least 13",
    )
    args = parser.parse_args()

    try:
        manifest, manifest_sha256 = _json_file(args.manifest, label="route manifest")
        plan, plan_sha256 = _json_file(args.plan, label="staging plan")
        coverage = validate_gate_configuration(
            manifest,
            plan,
            manifest_sha256=manifest_sha256,
            plan_dir=args.plan.resolve().parent,
        )
        if args.validate_only:
            print(
                "Staging plan verified offline: "
                f"{coverage.operation_count} operations, {coverage.adapter_count} adapters, "
                f"{coverage.request_count} planned requests."
            )
            return 0
        if not args.confirm_staging_deployment:
            raise GateError("--confirm-staging-deployment is required for live staging execution")
        if args.evidence_out is None:
            raise GateError("--evidence-out is required for live staging execution")
        if not 1 <= args.timeout <= 60:
            raise GateError("--timeout must be between 1 and 60 seconds")
        if not 13 <= args.negative_probe_interval <= 60:
            raise GateError("--negative-probe-interval must be between 13 and 60 seconds")

        results: list[dict[str, Any]] = []
        try:
            results = execute_gate(
                manifest,
                plan,
                plan_dir=args.plan.resolve().parent,
                environ=os.environ,
                confirmed_deployment_id=args.confirm_staging_deployment,
                timeout=args.timeout,
                results=results,
                negative_probe_interval_seconds=args.negative_probe_interval,
            )
        except GateError as exc:
            _write_evidence(
                args.evidence_out,
                status="failed",
                manifest_sha256=manifest_sha256,
                plan_sha256=plan_sha256,
                plan=plan,
                coverage=coverage,
                results=results,
                failure=str(exc),
                negative_probe_interval_seconds=args.negative_probe_interval,
            )
            raise
        _write_evidence(
            args.evidence_out,
            status="passed",
            manifest_sha256=manifest_sha256,
            plan_sha256=plan_sha256,
            plan=plan,
            coverage=coverage,
            results=results,
            failure=None,
            negative_probe_interval_seconds=args.negative_probe_interval,
        )
        print(
            "PASS: staging security release gate executed "
            f"{coverage.operation_count} route contracts and {len(results) - coverage.operation_count} adapter probes."
        )
        return 0
    except GateError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
