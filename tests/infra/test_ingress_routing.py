"""Regression tests for the k8s Ingress routing table.

The defect: infra/k8s/base/ingress.yaml used only the deprecated
``kubernetes.io/ingress.class`` annotation, its paths matched neither the
gateway routes in infra/gateway/nginx.conf (which uses /admin/, /ingest/,
/nlp/, /graph/, /fsma/, /compliance/) nor covered the scheduler, and no
path had authentication or IP limits.

These tests pin the fix: an explicit ``spec.ingressClassName``, a path
table that mirrors the gateway locations plus the scheduler, backends
that exist in this tree, and a documented app-level auth owner per path.
IP allowlisting is deliberately not pinned: the permitted source ranges
are a production-network decision and must not be invented here.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
INGRESS_PATH = REPO_ROOT / "infra" / "k8s" / "base" / "ingress.yaml"
GATEWAY_PATH = REPO_ROOT / "infra" / "gateway" / "nginx.conf"
AUTH_MANIFEST_PATH = REPO_ROOT / "docs" / "security" / "route-security-manifest.json"

# Ingress path prefix -> backend Service name. Mirrors the gateway
# locations, plus /scheduler for the scheduler Service, which has no
# gateway route but exists in this tree.
EXPECTED_PATHS = {
    "/admin": "admin-service",
    "/ingest": "ingestion-service",
    "/graph": "graph-service",
    "/fsma": "graph-service",
    "/nlp": "nlp-service",
    "/compliance": "compliance-service",
    "/scheduler": "scheduler-service",
}

# Backend Service name -> (source file, symbol) proving app-level auth.
# The metrics/health endpoints that stay open are probes, not data paths.
APP_AUTH_EVIDENCE = {
    "admin-service": ("services/admin/app/dependencies.py", "get_current_user"),
    "ingestion-service": ("services/ingestion/app/authz.py", "require_api_key"),
    "graph-service": ("services/graph/app/routes.py", "require_api_key"),
    "nlp-service": ("services/nlp/app/routes.py", "require_api_key"),
    "compliance-service": ("services/compliance/app/routes.py", "require_api_key"),
    "scheduler-service": ("services/scheduler/main.py", "X-Metrics-Key"),
}


def _ingress():
    docs = [d for d in yaml.safe_load_all(INGRESS_PATH.read_text()) if d]
    assert len(docs) == 1, f"expected one document in {INGRESS_PATH}"
    return docs[0]


def _paths():
    rules = _ingress()["spec"].get("rules", [])
    assert rules, "ingress has no rules"
    paths = {}
    for rule in rules:
        for entry in rule.get("http", {}).get("paths", []):
            assert entry.get("pathType") == "Prefix", f"path {entry.get('path')} must stay a Prefix match"
            service = entry["backend"]["service"]
            paths[entry["path"]] = service["name"]
            assert service["port"]["number"] == 80, f"path {entry['path']} must target the Service port 80"
    return paths


def test_ingress_class_name_is_explicit():
    """Fails on the old manifest, which set no spec.ingressClassName."""
    assert _ingress()["spec"].get("ingressClassName") == "nginx", "ingress must set spec.ingressClassName explicitly"


def test_deprecated_class_annotation_is_gone():
    """The old annotation must not linger beside the modern field."""
    annotations = _ingress()["metadata"].get("annotations", {})
    assert "kubernetes.io/ingress.class" not in annotations, (
        "deprecated kubernetes.io/ingress.class annotation must be removed so the two settings cannot disagree"
    )


def test_paths_mirror_gateway_and_cover_scheduler():
    """Fails on the old /api/* table, which matched no gateway location."""
    assert _paths() == EXPECTED_PATHS, (
        f"ingress paths must mirror the gateway locations plus the scheduler, got {sorted(_paths())}"
    )
    gateway = GATEWAY_PATH.read_text()
    for prefix in EXPECTED_PATHS:
        if prefix == "/scheduler":
            continue
        assert f"location {prefix}/" in gateway, f"gateway no longer exposes {prefix}/, reconcile the tables"


def test_backends_exist_as_services_in_tree():
    for service in set(EXPECTED_PATHS.values()):
        matches = [
            p
            for p in (REPO_ROOT / "infra" / "k8s" / "base").rglob("*.yaml")
            if p.name != "ingress.yaml" and f"name: {service}" in p.read_text()
        ]
        assert matches, f"backend {service} has no manifest in this tree"


def test_app_auth_covers_every_path():
    """Every exposed path must trace to enforced app-level auth."""
    assert AUTH_MANIFEST_PATH.exists(), "route security manifest is missing"
    assert "route-security-manifest.json" in INGRESS_PATH.read_text(), (
        "ingress must document the auth owner of every path"
    )
    for service, (rel, symbol) in APP_AUTH_EVIDENCE.items():
        text = (REPO_ROOT / rel).read_text()
        assert symbol in text, f"{service} auth evidence missing: {symbol} not in {rel}"
