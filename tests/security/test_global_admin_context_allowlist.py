"""Closed inventory for transaction-local global RLS authority.

Every direct ``arm_global_admin_context`` call is a privileged boundary.  A
new call must be reviewed and classified here; moving an existing call within
its function does not create noisy line-number churn, while adding another
call in an already-approved function still changes the expected count.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# (relative path, enclosing function): (classification, expected call count)
APPROVED_GLOBAL_ADMIN_ARMS = {
    # Pre-tenant identity/session resolution. Each helper disarms again before
    # returning route-level authority.
    ("services/admin/app/privileged_auth.py", "_load_active_session"): (
        "auth-bootstrap",
        1,
    ),
    ("services/admin/app/privileged_auth.py", "_require_review_permission"): (
        "auth-bootstrap",
        1,
    ),
    ("services/admin/app/auth_routes.py", "get_me"): ("auth-bootstrap", 1),
    ("services/admin/app/dependencies.py", "get_current_user"): (
        "auth-bootstrap",
        2,
    ),
    (
        "services/admin/app/auth/session_auth.py",
        "get_scoped_active_session_context",
    ): ("auth-bootstrap", 1),
    (
        "services/admin/app/auth/challenges_router.py",
        "create_auth_challenge",
    ): ("auth-bootstrap", 1),
    (
        "services/admin/app/auth/challenges_router.py",
        "verify_auth_challenge",
    ): ("auth-bootstrap", 1),
    (
        "services/admin/app/auth/webauthn_router.py",
        "generate_webauthn_registration_options",
    ): ("auth-bootstrap", 1),
    (
        "services/admin/app/auth/webauthn_router.py",
        "verify_webauthn_registration",
    ): ("auth-bootstrap", 1),
    (
        "services/admin/app/auth/webauthn_router.py",
        "generate_webauthn_login_options",
    ): ("auth-bootstrap", 1),
    (
        "services/admin/app/auth/webauthn_router.py",
        "verify_webauthn_login",
    ): ("auth-bootstrap", 1),
    ("services/admin/app/auth/refresh_router.py", "refresh_session"): (
        "auth-bootstrap",
        2,
    ),
    # Human/workload routes whose dependencies establish the actor before the
    # classified control-plane transaction is armed.
    ("services/admin/app/routes.py", "_create_tenant_for_actor"): (
        "global-human-or-workload",
        1,
    ),
    (
        "services/admin/app/admin/organizations_router.py",
        "update_organization_sso_policy",
    ): ("global-human", 1),
    (
        "services/admin/app/admin/organizations_router.py",
        "update_organization",
    ): ("global-human", 1),
    (
        "services/admin/app/tenant_settings_routes.py",
        "update_partner_status",
    ): ("global-human", 1),
    ("services/admin/app/system_routes.py", "replay_dlq_messages"): (
        "global-human",
        1,
    ),
    # Reviewed identity-global self-service. The route actor is tenant-bound,
    # and the armed transaction may affect only the immutable authenticated
    # user ID across that user's own tenant history.
    ("services/admin/app/erasure_routes.py", "request_erasure"): (
        "identity-global-self-service",
        1,
    ),
    # Tenant-scoped directory under PermissionChecker("users.read").
    # Arm unlocks users_self_or_admin peer rows; MembershipModel.tenant_id
    # still filters. SET LOCAL via arm/disarm (try/finally).
    ("services/admin/app/user_routes.py", "list_users"): (
        "tenant-scoped-directory",
        1,
    ),
    # Background coordination paths. These run only on ADMIN_DATABASE_URL and
    # do not derive global authority from request metadata.
    ("services/shared/task_queue.py", "_arm_global_queue_transaction"): (
        "worker-maintenance",
        1,
    ),
    ("services/graph/app/audit_buffer_reconciler.py", "_open_session"): (
        "worker-maintenance",
        1,
    ),
    ("services/scheduler/service.py", "purge_old_tasks"): (
        "worker-maintenance",
        1,
    ),
    ("services/scheduler/service.py", "enforce_kde_retention"): (
        "worker-maintenance",
        1,
    ),
    ("server/workers/task_processor.py", "_execute_claim"): (
        "worker-maintenance",
        1,
    ),
    ("server/workers/task_processor.py", "_complete_task"): (
        "worker-maintenance",
        1,
    ),
    ("server/workers/task_processor.py", "_heartbeat_extend"): (
        "worker-maintenance",
        1,
    ),
    ("server/workers/task_processor.py", "_fail_task_inner"): (
        "worker-maintenance",
        1,
    ),
    ("server/workers/task_processor.py", "_release_abandoned_task_lock"): (
        "worker-maintenance",
        1,
    ),
}


def _production_python_files():
    for root_name in ("services", "server"):
        for path in (REPO_ROOT / root_name).rglob("*.py"):
            if "tests" not in path.parts:
                yield path


def _global_admin_arm_calls() -> Counter[tuple[str, str]]:
    calls: Counter[tuple[str, str]] = Counter()
    for path in _production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_names = {"arm_global_admin_context"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for imported in node.names:
                    if imported.name == "arm_global_admin_context":
                        imported_names.add(imported.asname or imported.name)

        relative_path = path.relative_to(REPO_ROOT).as_posix()
        function_stack: list[str] = []

        class Visitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                function_stack.append(node.name)
                self.generic_visit(node)
                function_stack.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, node: ast.Call) -> None:
                direct = isinstance(node.func, ast.Name) and node.func.id in imported_names
                attribute = isinstance(node.func, ast.Attribute) and node.func.attr == "arm_global_admin_context"
                if direct or attribute:
                    function_name = function_stack[-1] if function_stack else "<module>"
                    calls[(relative_path, function_name)] += 1
                self.generic_visit(node)

        Visitor().visit(tree)
    return calls


def test_every_global_admin_arm_is_classified_with_exact_call_count():
    actual = _global_admin_arm_calls()
    expected = Counter(
        {
            callsite: expected_count
            for callsite, (_classification, expected_count) in (APPROVED_GLOBAL_ADMIN_ARMS.items())
        }
    )
    assert actual == expected


def test_allowlist_uses_only_reviewed_authority_classes():
    assert {classification for classification, _count in APPROVED_GLOBAL_ADMIN_ARMS.values()} == {
        "auth-bootstrap",
        "global-human",
        "global-human-or-workload",
        "identity-global-self-service",
        "tenant-scoped-directory",
        "worker-maintenance",
    }
