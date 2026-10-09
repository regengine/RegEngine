"""Regression tests for the admin Deployment seccomp profile.

The defect: infra/k8s/base/admin/deployment.yaml set strict pod and
container hardening (runAsNonRoot, readOnlyRootFilesystem, drop ALL
capabilities) but no seccomp profile, so it missed the restricted
baseline. These tests pin the RuntimeDefault profile.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT_PATH = REPO_ROOT / "infra" / "k8s" / "base" / "admin" / "deployment.yaml"


def _deployment():
    docs = [d for d in yaml.safe_load_all(DEPLOYMENT_PATH.read_text()) if d]
    for doc in docs:
        if doc.get("kind") == "Deployment":
            return doc
    raise AssertionError(f"no Deployment document in {DEPLOYMENT_PATH}")


def test_pod_security_context_sets_runtimedefault_seccomp():
    """Fails on the old manifest, which had no seccompProfile at all."""
    pod_ctx = _deployment()["spec"]["template"]["spec"].get("securityContext", {})
    profile = pod_ctx.get("seccompProfile")
    assert profile, "pod securityContext has no seccompProfile"
    assert profile.get("type") == "RuntimeDefault", (
        f"pod seccompProfile type must be RuntimeDefault, got {profile.get('type')!r}"
    )


def test_no_container_overrides_seccomp_with_unconfined():
    """No container may opt back out to Unconfined."""
    containers = _deployment()["spec"]["template"]["spec"]["containers"]
    assert containers, "Deployment has no containers to check"
    for container in containers:
        profile = (container.get("securityContext") or {}).get("seccompProfile")
        if profile is not None:
            assert profile.get("type") != "Unconfined", (
                f"container {container.get('name')} overrides seccomp to Unconfined"
            )
