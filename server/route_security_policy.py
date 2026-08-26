"""Operation-level security classification and executable route adapters."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from server.router_policy import PRODUCTION_ENABLED_ROUTERS, VALID_ROUTER_NAMES

Classification = Literal["public", "tenant-scoped", "global-sysadmin", "workload-only"]

ALWAYS_MOUNTED_OWNERS = frozenset(
    {"core_ingest", "features", "health", "metrics", "root", "scheduler", "status", "webhook"}
)
PRODUCTION_OWNERS = PRODUCTION_ENABLED_ROUTERS | ALWAYS_MOUNTED_OWNERS
OMITTED_ROUTER_OWNERS = VALID_ROUTER_NAMES - PRODUCTION_ENABLED_ROUTERS
ALL_ROUTE_OWNERS = VALID_ROUTER_NAMES | ALWAYS_MOUNTED_OWNERS

# Public operations are approved one at a time. Owner is part of the key so a
# move between subsystems is security-review-visible too.
PUBLIC_OPERATIONS = frozenset(
    {
        ("health", "GET", "/api/health"),
        ("health", "GET", "/health"),
        ("health", "GET", "/health/live"),
        ("health", "GET", "/healthz"),
        ("health", "GET", "/readiness"),
        ("root", "GET", "/"),
        ("proof_verify", "POST", "/api/v1/proof/verify"),
        ("proof_recall", "POST", "/api/v1/proof/recall-drill"),
        ("csv", "GET", "/api/v1/templates"),
        ("csv", "GET", "/api/v1/templates/{cte_type}"),
        ("portal", "GET", "/api/v1/portal/{portal_id}"),
        ("portal", "POST", "/api/v1/portal/{portal_id}/preflight"),
        ("portal", "POST", "/api/v1/portal/{portal_id}/submit"),
        ("billing", "GET", "/api/v1/billing/plans"),
        ("billing", "POST", "/api/v1/billing/checkout"),
        ("billing", "GET", "/billing/plans"),
        ("onboarding", "GET", "/api/v1/onboarding/steps"),
        ("readiness", "GET", "/api/v1/fsma/export-jobs"),
        ("readiness", "GET", "/api/v1/fsma/mappings"),
        ("admin", "GET", "/health/deep"),
        ("admin", "GET", "/ready"),
        ("admin", "POST", "/auth/challenges"),
        ("admin", "POST", "/auth/challenges/{challenge_id}/verify"),
        ("admin", "POST", "/auth/refresh"),
        ("admin", "POST", "/auth/webauthn/login/generate-options"),
        ("admin", "POST", "/auth/webauthn/login/verify"),
        ("admin", "POST", "/v1/auth/accept-invite"),
        ("admin", "POST", "/api/v1/tools/verify-email"),
        ("admin", "POST", "/api/v1/tools/confirm-code"),
        ("admin", "POST", "/api/v1/tools/lead-erasure/request"),
        ("admin", "POST", "/api/v1/tools/lead-erasure/confirm"),
    }
)

OPTIONAL_TENANT_API_KEY_PUBLIC_OPERATIONS = frozenset(
    {
        ("billing", "POST", "/api/v1/billing/checkout"),
    }
)

# These authenticate inside the endpoint rather than FastAPI's dependency
# graph. Their adapter validates the declared header and handler delegation.
STRIPE_WEBHOOK_OPERATIONS = frozenset(
    {
        ("billing", "POST", "/api/v1/billing/webhooks"),
        ("billing", "POST", "/api/v1/billing/webhook/stripe"),
    }
)

# Tenant-bound actors whose reviewed operation has an identity-global storage
# effect. These routes remain tenant-scoped at the HTTP authority boundary,
# while their dedicated adapters prove that the broader transaction target is
# derived only from the authenticated identity.
IDENTITY_GLOBAL_SELF_SERVICE_OPERATIONS = frozenset(
    {
        ("admin", "POST", "/v1/account/erasure"),
    }
)


@dataclass(frozen=True)
class TenantApiKeyRoutePolicy:
    """Reviewed storage/test contract for tenant API-key operations."""

    storage_boundary: str
    test_adapter: str


# Tenant API-key routes do not receive a generic fallback. Each production
# owner must select an explicit storage boundary and executable adapter here;
# promoting an optional owner therefore fails manifest generation until its
# storage model and test adapter have been reviewed. Exact operation policies
# below override an owner contract when a router spans storage systems.
TENANT_API_KEY_OWNER_POLICIES: dict[str, TenantApiKeyRoutePolicy] = {
    "audit_export_log": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "auditor": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "billing": TenantApiKeyRoutePolicy(
        "stripe+postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "canonical_records": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "chain_verification": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "compliance_metrics": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "core_ingest": TenantApiKeyRoutePolicy(
        "postgres-rls+redis+object-storage:credential-bound-tenant",
        "tenant_api_key_mixed_storage",
    ),
    "csv": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "edi": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "epcis_ingestion": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "exceptions": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "export_monitoring": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "fda_export": TenantApiKeyRoutePolicy(
        "postgres-rls+generated-artifact:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "fsma_compliance": TenantApiKeyRoutePolicy(
        "postgres-rls+generated-artifact:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "inflow_workbench": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "onboarding": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "portal": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "readiness": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "recall": TenantApiKeyRoutePolicy(
        "postgres-rls+generated-artifact:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "request_workflow": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "rules": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "score": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "sla_tracking": TenantApiKeyRoutePolicy(
        "postgres-rls:credential-bound-tenant",
        "tenant_api_key_postgres_rls",
    ),
    "status": TenantApiKeyRoutePolicy(
        "ingestion-postgres:explicit-tenant-filter",
        "tenant_api_key_ingestion_postgres_filter",
    ),
    "webhook": TenantApiKeyRoutePolicy(
        "postgres-rls+webhook-ledger:credential-bound-tenant",
        "tenant_api_key_mixed_storage",
    ),
}

TENANT_API_KEY_OPERATION_POLICIES: dict[tuple[str, str, str], TenantApiKeyRoutePolicy] = {
    (
        "status",
        "GET",
        "/v1/ingest/status/{job_id}",
    ): TenantApiKeyRoutePolicy(
        "redis:tenant-owner-key",
        "tenant_api_key_redis_job_owner",
    ),
    (
        "status",
        "GET",
        "/v1/ingest/documents/{document_id}/analysis",
    ): TenantApiKeyRoutePolicy(
        "redis:tenant-owner-key",
        "tenant_api_key_redis_job_owner",
    ),
}

# Independent of the mutable policy mapping so deleting a security-critical
# exact override cannot silently fall back to its owner's generic storage
# contract during manifest generation.
REQUIRED_EXACT_TENANT_API_KEY_POLICIES = frozenset(
    {
        ("status", "GET", "/v1/ingest/status/{job_id}"),
        ("status", "GET", "/v1/ingest/documents/{document_id}/analysis"),
    }
)

_METRICS_DEP = "shared.observability.metrics_auth:require_metrics_key"
_WORKLOAD_DEP = "services.admin.app.privileged_auth:require_tenant_provisioner_key"
_HIGH_ASSURANCE_SYSADMIN_DEPS = frozenset(
    {
        "services.admin.app.privileged_auth:require_sysadmin_high_assurance",
    }
)
_HIGH_ASSURANCE_SESSION_DEPS = frozenset(
    {
        "services.admin.app.auth.session_auth:require_high_assurance_session",
    }
)
_SCOPED_OPAQUE_SESSION_DEP = (
    "services.admin.app.auth.session_auth:get_scoped_active_session_context"
)
_REVIEW_DEPS = frozenset(
    {
        "services.admin.app.privileged_auth:require_review_read",
        "services.admin.app.privileged_auth:require_review_decide",
    }
)
_OPAQUE_SESSION_DEPS = frozenset(
    {
        _SCOPED_OPAQUE_SESSION_DEP,
        "services.admin.app.auth.session_auth:get_current_active_user",
    }
)
_DUAL_SESSION_DEP = "services.admin.app.dependencies:get_current_user"
_TENANT_API_KEY_DEPS = frozenset(
    {
        "shared.auth:require_api_key",
        "services.ingestion.app.authz:get_ingestion_principal",
        "services.ingestion.app.webhook_compat:require_tenant_context",
        "services.ingestion.app.webhook_compat:_verify_api_key",
    }
)
_OPTIONAL_TENANT_API_KEY_DEP = "services.ingestion.app.authz:get_optional_ingestion_principal"  # pragma: allowlist secret
_CHECKOUT_RATE_LIMIT_DEP = (
    "services.ingestion.app.stripe_billing.rate_limiting:_check_stripe_checkout_rate_limit"
)
_ALL_AUTH_DEPS = (
    {_METRICS_DEP, _WORKLOAD_DEP}
    | _HIGH_ASSURANCE_SYSADMIN_DEPS
    | _HIGH_ASSURANCE_SESSION_DEPS
    | _REVIEW_DEPS
    | _OPAQUE_SESSION_DEPS
    | {_DUAL_SESSION_DEP}
    | _TENANT_API_KEY_DEPS
    | {_OPTIONAL_TENANT_API_KEY_DEP}
)


class RouteManifestError(RuntimeError):
    """Raised when the production route contract is incomplete or inconsistent."""


def operation_key(owner: str, method: str, path: str) -> tuple[str, str, str]:
    return owner, method.upper(), path


def operation_id(owner: str, method: str, path: str) -> str:
    return f"{owner}:{method.upper()}:{path}"


def _callable_key(call: Any) -> str:
    module = getattr(call, "__module__", None) or call.__class__.__module__
    name = getattr(call, "__name__", None) or call.__class__.__name__
    return f"{module}:{name}"


def _dependency_calls(dependant: Dependant) -> list[Any]:
    calls: list[Any] = []
    for child in dependant.dependencies:
        calls.append(child.call)
        calls.extend(_dependency_calls(child))
    return calls


def _dependency_keys(route: APIRoute) -> set[str]:
    return {_callable_key(call) for call in _dependency_calls(route.dependant)}


def _closure_strings(call: Any) -> list[str]:
    values: list[str] = []
    for cell in getattr(call, "__closure__", None) or ():
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        if isinstance(value, str) and "." in value and value not in values:
            values.append(value)
    return values


def _required_permissions(route: APIRoute, dependency_keys: set[str]) -> tuple[str, ...]:
    permissions: list[str] = []
    for call in _dependency_calls(route.dependant):
        explicit = getattr(call, "required_permission", None)
        if isinstance(explicit, str) and explicit not in permissions:
            permissions.append(explicit)
        if _callable_key(call) in {
            "services.ingestion.app.authz:_dependency",
            "services.ingestion.app.routes_ingest:_check",
        }:
            permissions.extend(value for value in _closure_strings(call) if value not in permissions)

    special = (
        (_WORKLOAD_DEP, "internal.tenants.create"),
        (_METRICS_DEP, "metrics.read"),
        ("services.admin.app.privileged_auth:require_review_read", "review.read"),
        ("services.admin.app.privileged_auth:require_review_decide", "review.decide"),
    )
    for dependency, permission in special:
        if dependency in dependency_keys and permission not in permissions:
            permissions.append(permission)
    if dependency_keys & _HIGH_ASSURANCE_SYSADMIN_DEPS and "sysadmin" not in permissions:
        permissions.append("sysadmin")
    if not permissions and dependency_keys & (
        _TENANT_API_KEY_DEPS
        | _OPAQUE_SESSION_DEPS
        | _HIGH_ASSURANCE_SESSION_DEPS
        | {_DUAL_SESSION_DEP}
    ):
        permissions.append("authenticated")
    return tuple(sorted(permissions))


def _public_storage_boundary(owner: str, path: str) -> str:
    if owner == "portal":
        return "postgres-rls:opaque-portal-capability"
    if owner in {"proof_verify", "proof_recall"}:
        return "public-proof-store:non-secret"
    if owner == "admin" and path.startswith(("/auth/", "/v1/auth/", "/api/v1/tools/")):
        return "admin-postgres:identity-bound-public-flow"
    return "public-static-or-health:no-tenant-secret"


def _tenant_api_key_policy(
    *,
    owner: str,
    method: str,
    path: str,
) -> TenantApiKeyRoutePolicy:
    key = operation_key(owner, method, path)
    policy = TENANT_API_KEY_OPERATION_POLICIES.get(key)
    if policy is not None:
        return policy
    if key in REQUIRED_EXACT_TENANT_API_KEY_POLICIES:
        raise RouteManifestError(
            f"Required exact tenant API-key policy is missing for {operation_id(owner, method, path)}"
        )
    policy = TENANT_API_KEY_OWNER_POLICIES.get(owner)
    if policy is not None:
        return policy
    raise RouteManifestError(
        f"No explicit tenant API-key storage/test policy for {operation_id(owner, method, path)}. "
        "Add a reviewed owner or exact-operation policy before enabling this router."
    )


def classify_operation(
    route: APIRoute,
    *,
    owner: str,
    method: str,
) -> tuple[Classification, str, tuple[str, ...], str, str]:
    """Classify one operation, execute its adapter, and return its contract."""

    key = operation_key(owner, method, route.path)
    dependencies = _dependency_keys(route)
    permissions = _required_permissions(route, dependencies)

    if key in STRIPE_WEBHOOK_OPERATIONS:
        result = (
            "workload-only",
            "stripe-signature",
            ("stripe.webhook.deliver",),
            "stripe-event-to-credential-bound-tenant",
            "workload_stripe_signature",
        )
    elif key in OPTIONAL_TENANT_API_KEY_PUBLIC_OPERATIONS:
        result = (
            "public",
            "optional-x-regengine-api-key",
            (),
            "stripe+redis:anonymous-or-credential-bound-tenant",
            "public_optional_tenant_checkout",
        )
    elif key in PUBLIC_OPERATIONS:
        result = ("public", "none", (), _public_storage_boundary(owner, route.path), "public_no_auth")
    elif _WORKLOAD_DEP in dependencies:
        result = (
            "workload-only",
            "x-regengine-api-key:database-workload",
            permissions,
            "admin-postgres:tenantless-workload",
            "workload_tenant_provisioner",
        )
    elif _METRICS_DEP in dependencies:
        result = (
            "workload-only",
            "x-metrics-key",
            permissions,
            "process-observability:no-tenant-data",
            "workload_metrics_key",
        )
    elif key in IDENTITY_GLOBAL_SELF_SERVICE_OPERATIONS:
        result = (
            "tenant-scoped",
            "bearer-token-or-opaque-session-cookie",
            permissions,
            "admin-postgres+graph-outbox:authenticated-user-global-identity",
            "tenant_identity_global_self_erasure",
        )
    elif dependencies & _HIGH_ASSURANCE_SYSADMIN_DEPS:
        result = (
            "global-sysadmin",
            "opaque-session-cookie:webauthn-or-sso",
            permissions,
            "admin-postgres:audited-global",
            "global_sysadmin_high_assurance",
        )
    elif dependencies & _HIGH_ASSURANCE_SESSION_DEPS:
        result = (
            "tenant-scoped",
            "opaque-session-cookie:webauthn-or-sso",
            permissions,
            "admin-postgres:session-membership-tenant",
            "tenant_high_assurance_session",
        )
    elif dependencies & _REVIEW_DEPS:
        high_assurance = "services.admin.app.privileged_auth:require_review_decide" in dependencies
        result = (
            "tenant-scoped",
            "opaque-session-cookie:webauthn-or-sso" if high_assurance else "opaque-session-cookie",
            permissions,
            "admin-postgres:session-membership-tenant",
            "tenant_review_session",
        )
    elif dependencies & _OPAQUE_SESSION_DEPS:
        result = (
            "tenant-scoped",
            "opaque-session-cookie",
            permissions,
            "admin-postgres:session-membership-tenant",
            "tenant_opaque_session",
        )
    elif _DUAL_SESSION_DEP in dependencies:
        result = (
            "tenant-scoped",
            "bearer-token-or-opaque-session-cookie",
            permissions,
            "admin-postgres:jwt-tenant-or-session-membership-tenant",
            "tenant_dual_session_csrf",
        )
    elif dependencies & _TENANT_API_KEY_DEPS:
        policy = _tenant_api_key_policy(owner=owner, method=method, path=route.path)
        signed = "services.ingestion.app.webhook_router_v2.security:_verify_webhook_signature" in dependencies
        result = (
            "tenant-scoped",
            "x-regengine-api-key+hmac-signature" if signed else "x-regengine-api-key",
            permissions,
            policy.storage_boundary,
            policy.test_adapter,
        )
    else:
        observed = sorted(dependencies & _ALL_AUTH_DEPS)
        raise RouteManifestError(
            f"Unclassified production operation {operation_id(owner, method, route.path)}; "
            f"recognized auth dependencies={observed}. Add an exact rule or an authenticated adapter."
        )

    adapter = TEST_ADAPTERS.get(result[4])
    if adapter is None:
        raise RouteManifestError(
            f"Missing executable test adapter {result[4]!r} for {operation_id(owner, method, route.path)}"
        )
    adapter(route)
    return result


def _assert_dependencies(route: APIRoute, *, required_any=(), forbidden=()) -> None:
    observed = _dependency_keys(route)
    required = set(required_any)
    if required and not observed & required:
        raise RouteManifestError(
            f"Adapter for {route.path} expected one of {sorted(required)}, observed {sorted(observed)}"
        )
    overlap = observed & set(forbidden)
    if overlap:
        raise RouteManifestError(f"Adapter for {route.path} found forbidden dependencies {sorted(overlap)}")


def _adapt_public_no_auth(route: APIRoute) -> None:
    _assert_dependencies(route, forbidden=_ALL_AUTH_DEPS)


def _adapt_public_optional_tenant_checkout(route: APIRoute) -> None:
    _assert_dependencies(
        route,
        required_any={_OPTIONAL_TENANT_API_KEY_DEP},
        forbidden=_ALL_AUTH_DEPS - {_OPTIONAL_TENANT_API_KEY_DEP},
    )
    _assert_dependencies(route, required_any={_CHECKOUT_RATE_LIMIT_DEP})

    source = textwrap.dedent(inspect.getsource(route.endpoint))
    tree = ast.parse(source)

    def catches_auth_failure(exception_type: ast.expr | None) -> bool:
        if exception_type is None:
            return True
        if isinstance(exception_type, ast.Name):
            return exception_type.id in {"BaseException", "Exception", "HTTPException"}
        if isinstance(exception_type, ast.Attribute):
            return exception_type.attr == "HTTPException"
        if isinstance(exception_type, ast.Tuple):
            return any(catches_auth_failure(item) for item in exception_type.elts)
        return False

    catches_auth_failure_exception = any(
        isinstance(node, ast.ExceptHandler) and catches_auth_failure(node.type)
        for node in ast.walk(tree)
    )
    if catches_auth_failure_exception:
        raise RouteManifestError(
            f"Optional-auth checkout {route.path} catches an auth failure and could downgrade a rejected credential"
        )

    def is_authenticated_principal_guard(node: ast.If) -> bool:
        test = node.test
        return (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "safe_principal"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.IsNot)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None
        )

    tenant_resolution_is_guarded = any(
        is_authenticated_principal_guard(node)
        and any(
            isinstance(descendant, ast.Call)
            and isinstance(descendant.func, ast.Attribute)
            and descendant.func.attr == "_resolve_tenant_context"
            for descendant in ast.walk(node)
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
    )
    if not tenant_resolution_is_guarded:
        raise RouteManifestError(
            f"Optional-auth checkout {route.path} no longer gates tenant resolution on an authenticated principal"
        )


def _adapt_tenant_api_key_dependency(route: APIRoute) -> None:
    _assert_dependencies(route, required_any=_TENANT_API_KEY_DEPS, forbidden={_METRICS_DEP, _WORKLOAD_DEP})


def _adapt_tenant_api_key_postgres_rls(route: APIRoute) -> None:
    _adapt_tenant_api_key_dependency(route)


def _adapt_tenant_api_key_mixed_storage(route: APIRoute) -> None:
    _adapt_tenant_api_key_dependency(route)


def _adapt_tenant_api_key_ingestion_postgres_filter(route: APIRoute) -> None:
    _adapt_tenant_api_key_dependency(route)
    if route.endpoint.__module__ != "services.ingestion.app.routes_status":
        raise RouteManifestError(f"Ingestion PostgreSQL adapter is not bound to the status owner: {route.path}")
    if "api_key.tenant_id" not in inspect.getsource(route.endpoint):
        raise RouteManifestError(
            f"Ingestion PostgreSQL operation {route.path} no longer passes the credential-bound tenant filter"
        )


def _adapt_tenant_api_key_redis_job_owner(route: APIRoute) -> None:
    _adapt_tenant_api_key_dependency(route)
    if route.endpoint.__module__ != "services.ingestion.app.routes_status":
        raise RouteManifestError(f"Redis job-owner adapter is not bound to the status owner: {route.path}")
    source = textwrap.dedent(inspect.getsource(route.endpoint))
    tree = ast.parse(source)
    resource_parameter = "document_id" if "{document_id}" in route.path else "job_id"

    def is_expected_owner_call(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            return False
        if node.func.id != "_job_owned_by_tenant" or len(node.args) != 3:
            return False
        redis_arg, resource_arg, tenant_arg = node.args
        return (
            isinstance(redis_arg, ast.Name)
            and redis_arg.id == "r"
            and isinstance(resource_arg, ast.Name)
            and resource_arg.id == resource_parameter
            and isinstance(tenant_arg, ast.Attribute)
            and isinstance(tenant_arg.value, ast.Name)
            and tenant_arg.value.id == "api_key"
            and tenant_arg.attr == "tenant_id"
        )

    def raises_not_found(node: ast.If) -> bool:
        for child in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if not isinstance(child, ast.Raise) or not isinstance(child.exc, ast.Call):
                continue
            if not isinstance(child.exc.func, ast.Name) or child.exc.func.id != "HTTPException":
                continue
            for keyword in child.exc.keywords:
                if (
                    keyword.arg == "status_code"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value == 404
                ):
                    return True
        return False

    guarded = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and is_expected_owner_call(node.test.operand)
        and raises_not_found(node)
        for node in ast.walk(tree)
    )
    if not guarded:
        raise RouteManifestError(
            f"Redis operation {route.path} no longer denies a failed credential-bound owner check with 404"
        )


def _adapt_tenant_dual_session_csrf(route: APIRoute) -> None:
    _assert_dependencies(route, required_any={_DUAL_SESSION_DEP}, forbidden={_METRICS_DEP, _WORKLOAD_DEP})
    if route.methods & {"POST", "PUT", "PATCH", "DELETE"}:
        repo_root = Path(__file__).resolve().parents[1]
        try:
            proxy_source = (repo_root / "frontend" / "src" / "proxy.ts").read_text(encoding="utf-8")
            csrf_source = (repo_root / "frontend" / "src" / "lib" / "csrf.ts").read_text(encoding="utf-8")
        except OSError as exc:
            raise RouteManifestError("Frontend CSRF sources are missing; cookie mutations fail closed") from exc
        if "CSRF_PROTECTED_METHODS.has(request.method)" not in proxy_source:
            raise RouteManifestError("Frontend proxy no longer gates cookie-authenticated mutation methods with CSRF")
        for method in route.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            if f"'{method}'" not in csrf_source and f'"{method}"' not in csrf_source:
                raise RouteManifestError(f"Frontend CSRF method set no longer covers {method}")


def _adapt_tenant_identity_global_self_erasure(route: APIRoute) -> None:
    """Prove that the identity-global erasure target is authenticated-user bound."""

    _adapt_tenant_dual_session_csrf(route)
    if route.endpoint.__name__ != "request_erasure":
        raise RouteManifestError(
            f"Identity-global self-erasure adapter is not bound to request_erasure: {route.path}"
        )

    source = textwrap.dedent(inspect.getsource(route.endpoint))
    tree = ast.parse(source)
    assignments: dict[str, ast.expr] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            assignments[node.targets[0].id] = node.value

    raw_user_id = assignments.get("user_id")
    authenticated_user_binding = (
        isinstance(raw_user_id, ast.Attribute)
        and raw_user_id.attr == "id"
        and isinstance(raw_user_id.value, ast.Name)
        and raw_user_id.value.id == "current_user"
    )

    normalized_user_id = assignments.get("user_uuid")
    normalized_authenticated_user = (
        isinstance(normalized_user_id, ast.Call)
        and isinstance(normalized_user_id.func, ast.Attribute)
        and isinstance(normalized_user_id.func.value, ast.Name)
        and normalized_user_id.func.value.id == "uuid"
        and normalized_user_id.func.attr == "UUID"
        and len(normalized_user_id.args) == 1
        and isinstance(normalized_user_id.args[0], ast.Call)
        and isinstance(normalized_user_id.args[0].func, ast.Name)
        and normalized_user_id.args[0].func.id == "str"
        and len(normalized_user_id.args[0].args) == 1
        and isinstance(normalized_user_id.args[0].args[0], ast.Name)
        and normalized_user_id.args[0].args[0].id == "user_id"
    )

    erasure_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_apply_account_erasure"
    ]
    erasure_target_is_normalized_user = (
        len(erasure_calls) == 1
        and any(
            keyword.arg == "user_id"
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "user_uuid"
            for keyword in erasure_calls[0].keywords
        )
    )

    if not (
        authenticated_user_binding
        and normalized_authenticated_user
        and erasure_target_is_normalized_user
    ):
        raise RouteManifestError(
            "Identity-global self-erasure must normalize current_user.id and bind it "
            "as _apply_account_erasure(..., user_id=...)"
        )


def _adapt_tenant_opaque_session(route: APIRoute) -> None:
    _assert_dependencies(
        route,
        required_any={_SCOPED_OPAQUE_SESSION_DEP},
        forbidden={_METRICS_DEP, _WORKLOAD_DEP},
    )


def _adapt_tenant_high_assurance_session(route: APIRoute) -> None:
    _assert_dependencies(
        route,
        required_any=_HIGH_ASSURANCE_SESSION_DEPS,
        forbidden={_METRICS_DEP, _WORKLOAD_DEP},
    )
    _assert_dependencies(route, required_any={_SCOPED_OPAQUE_SESSION_DEP})


def _adapt_tenant_review_session(route: APIRoute) -> None:
    _assert_dependencies(route, required_any=_REVIEW_DEPS, forbidden={_METRICS_DEP, _WORKLOAD_DEP})


def _adapt_global_sysadmin_high_assurance(route: APIRoute) -> None:
    _assert_dependencies(route, required_any=_HIGH_ASSURANCE_SYSADMIN_DEPS, forbidden={_METRICS_DEP, _WORKLOAD_DEP})


def _adapt_workload_metrics_key(route: APIRoute) -> None:
    _assert_dependencies(route, required_any={_METRICS_DEP}, forbidden=_TENANT_API_KEY_DEPS | {_WORKLOAD_DEP})


def _adapt_workload_tenant_provisioner(route: APIRoute) -> None:
    _assert_dependencies(route, required_any={_WORKLOAD_DEP}, forbidden=_TENANT_API_KEY_DEPS | {_METRICS_DEP})


def _adapt_workload_stripe_signature(route: APIRoute) -> None:
    aliases = {str(getattr(field, "alias", "")).lower() for field in route.dependant.header_params}
    if "stripe-signature" not in aliases:
        raise RouteManifestError(f"Stripe webhook {route.path} does not declare the Stripe-Signature header")
    if not route.endpoint.__module__.startswith("services.ingestion.app.stripe_billing"):
        raise RouteManifestError(f"Stripe webhook {route.path} is not owned by the billing implementation")
    if "_process_stripe_webhook" not in inspect.getsource(route.endpoint):
        raise RouteManifestError(f"Stripe webhook {route.path} no longer delegates to signature validation")


TEST_ADAPTERS: dict[str, Callable[[APIRoute], None]] = {
    "public_no_auth": _adapt_public_no_auth,
    "public_optional_tenant_checkout": _adapt_public_optional_tenant_checkout,
    "tenant_api_key_postgres_rls": _adapt_tenant_api_key_postgres_rls,
    "tenant_api_key_mixed_storage": _adapt_tenant_api_key_mixed_storage,
    "tenant_api_key_ingestion_postgres_filter": _adapt_tenant_api_key_ingestion_postgres_filter,
    "tenant_api_key_redis_job_owner": _adapt_tenant_api_key_redis_job_owner,
    "tenant_dual_session_csrf": _adapt_tenant_dual_session_csrf,
    "tenant_identity_global_self_erasure": _adapt_tenant_identity_global_self_erasure,
    "tenant_opaque_session": _adapt_tenant_opaque_session,
    "tenant_high_assurance_session": _adapt_tenant_high_assurance_session,
    "tenant_review_session": _adapt_tenant_review_session,
    "global_sysadmin_high_assurance": _adapt_global_sysadmin_high_assurance,
    "workload_metrics_key": _adapt_workload_metrics_key,
    "workload_tenant_provisioner": _adapt_workload_tenant_provisioner,
    "workload_stripe_signature": _adapt_workload_stripe_signature,
}


__all__ = [
    "ALL_ROUTE_OWNERS",
    "ALWAYS_MOUNTED_OWNERS",
    "Classification",
    "IDENTITY_GLOBAL_SELF_SERVICE_OPERATIONS",
    "OMITTED_ROUTER_OWNERS",
    "OPTIONAL_TENANT_API_KEY_PUBLIC_OPERATIONS",
    "PRODUCTION_OWNERS",
    "PUBLIC_OPERATIONS",
    "REQUIRED_EXACT_TENANT_API_KEY_POLICIES",
    "RouteManifestError",
    "STRIPE_WEBHOOK_OPERATIONS",
    "TENANT_API_KEY_OPERATION_POLICIES",
    "TENANT_API_KEY_OWNER_POLICIES",
    "TenantApiKeyRoutePolicy",
    "classify_operation",
    "operation_id",
    "operation_key",
]
