"""Regression tests for the k8s Ingress TLS section.

The defect: infra/k8s/base/ingress.yaml carried a cert-manager
cluster-issuer annotation but no ``tls`` block, so the annotation alone
did nothing and the host would have served plaintext if applied. These
tests pin the tls block, the secret name, the host coverage, and the
SSL redirect annotation.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
INGRESS_PATH = REPO_ROOT / "infra" / "k8s" / "base" / "ingress.yaml"


def _ingress():
    docs = [d for d in yaml.safe_load_all(INGRESS_PATH.read_text()) if d]
    assert len(docs) == 1, f"expected one document in {INGRESS_PATH}"
    return docs[0]


def test_ingress_has_tls_block_with_secret():
    """Fails on the old manifest, which had no tls section at all."""
    spec = _ingress()["spec"]
    tls = spec.get("tls")
    assert tls, "ingress spec has no tls block, the host serves plaintext"
    for entry in tls:
        assert entry.get("hosts"), "tls entry must list hosts"
        assert entry.get("secretName"), "tls entry must name a secretName"


def test_tls_hosts_cover_every_rule_host():
    """Every rule host must be covered by a tls entry, or it stays plaintext."""
    spec = _ingress()["spec"]
    tls_hosts = {h for entry in spec.get("tls", []) for h in entry.get("hosts", [])}
    rule_hosts = [r["host"] for r in spec.get("rules", []) if r.get("host")]
    assert rule_hosts, "ingress has no rule hosts to check"
    for host in rule_hosts:
        assert host in tls_hosts, f"rule host {host} is not covered by any tls entry"


def test_force_ssl_redirect_annotation_is_set():
    annotations = _ingress()["metadata"].get("annotations", {})
    assert annotations.get("nginx.ingress.kubernetes.io/force-ssl-redirect") == "true", (
        "plaintext HTTP must redirect to HTTPS once TLS terminates"
    )
