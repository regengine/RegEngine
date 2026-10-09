"""Regression tests for the re-platform audit finding on probes and paging HA.

The defect: infra/k8s/base/ingestion/deployment.yaml had a readiness probe
but no liveness probe, so a wedged ingestion pod never restarted. And
infra/k8s/base/monitoring/alertmanager.yaml ran a single alertmanager
replica with clustering disabled (``--cluster.listen-address=``), so one
node loss dropped paging. These tests pin the liveness probe and the
three-replica clustered alertmanager setup, including the gossip mesh
port, the headless peer-discovery service, and the NetworkPolicy rules
that let the gossip traffic through.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_PATH = REPO_ROOT / "infra" / "k8s" / "base" / "ingestion" / "deployment.yaml"
ALERTMANAGER_PATH = REPO_ROOT / "infra" / "k8s" / "base" / "monitoring" / "alertmanager.yaml"

CLUSTER_PORT = 9094


def _docs(path: Path) -> list[dict]:
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def _ingestion_container() -> dict:
    for doc in _docs(INGESTION_PATH):
        if doc.get("kind") == "Deployment":
            containers = doc["spec"]["template"]["spec"]["containers"]
            assert len(containers) == 1
            return containers[0]
    raise AssertionError(f"no Deployment in {INGESTION_PATH}")


def _alertmanager_docs() -> dict[str, list[dict]]:
    by_kind: dict[str, list[dict]] = {}
    for doc in _docs(ALERTMANAGER_PATH):
        by_kind.setdefault(doc.get("kind", ""), []).append(doc)
    return by_kind


def _statefulset() -> dict:
    docs = _alertmanager_docs()
    assert docs.get("StatefulSet"), "alertmanager StatefulSet is missing"
    return docs["StatefulSet"][0]


def _statefulset_container() -> dict:
    containers = _statefulset()["spec"]["template"]["spec"]["containers"]
    assert len(containers) == 1
    return containers[0]


def test_ingestion_has_liveness_probe():
    """Fails on the old manifest, which had no liveness probe at all."""
    container = _ingestion_container()
    probe = container.get("livenessProbe")
    assert probe, "ingestion container has no livenessProbe, wedged pods never restart"
    assert probe["httpGet"]["path"] == "/health"
    assert probe["httpGet"]["port"] == 8000


def test_ingestion_probes_have_timing():
    """Both probes must poll on an interval instead of firing once."""
    container = _ingestion_container()
    for name in ("livenessProbe", "readinessProbe"):
        probe = container.get(name)
        assert probe, f"ingestion container has no {name}"
        assert probe.get("initialDelaySeconds", 0) > 0, f"{name} has no initial delay"
        assert probe.get("periodSeconds", 0) > 0, f"{name} has no poll period"


def test_alertmanager_runs_three_replicas():
    """Fails on the old manifest, which ran a single replica."""
    assert _statefulset()["spec"].get("replicas") == 3, (
        "alertmanager must run three replicas so one node loss keeps paging up"
    )


def test_alertmanager_clustering_is_enabled():
    """Fails on the old manifest, which passed an empty listen address."""
    args = _statefulset_container().get("args", [])
    listen = [a for a in args if a.startswith("--cluster.listen-address=")]
    assert listen, "alertmanager has no --cluster.listen-address flag"
    value = listen[0].split("=", 1)[1]
    assert value and str(CLUSTER_PORT) in value, f"clustering is disabled or on the wrong port: {listen[0]!r}"
    peers = [a for a in args if a.startswith("--cluster.peer=")]
    assert peers, "alertmanager has no --cluster.peer seed, replicas never join"
    assert "alertmanager-mesh" in peers[0], f"cluster peer must resolve through the headless mesh service: {peers[0]!r}"


def test_alertmanager_exposes_cluster_port():
    ports = {p.get("containerPort"): p for p in _statefulset_container().get("ports", [])}
    assert CLUSTER_PORT in ports, "alertmanager container does not expose the gossip port"


def test_alertmanager_mesh_service_is_headless():
    docs = _alertmanager_docs()
    mesh_name = _statefulset()["spec"]["serviceName"]
    services = {s["metadata"]["name"]: s for s in docs.get("Service", [])}
    assert mesh_name in services, (
        f"StatefulSet serviceName {mesh_name!r} names no Service, per-pod DNS records are never created"
    )
    assert services[mesh_name]["spec"].get("clusterIP") == "None", (
        "the mesh service must be headless so each replica gets a stable DNS record"
    )
    # The client-facing ClusterIP service must still exist for Prometheus traffic.
    assert "alertmanager" in services, "the client-facing alertmanager Service is missing"


def test_alertmanager_netpolicy_allows_gossip():
    docs = _alertmanager_docs()
    policies = docs.get("NetworkPolicy", [])
    assert policies, "alertmanager NetworkPolicy is missing"
    spec = policies[0]["spec"]

    def allows(rules: list[dict], peer_key: str) -> bool:
        for rule in rules:
            for peer in rule.get(peer_key, []):
                selector = peer.get("podSelector", {}).get("matchLabels", {})
                if selector.get("app") != "alertmanager":
                    continue
                for port in rule.get("ports", []):
                    if port.get("port") == CLUSTER_PORT:
                        return True
        return False

    assert allows(spec.get("ingress", []), "from"), "NetworkPolicy blocks gossip ingress between alertmanager replicas"
    assert allows(spec.get("egress", []), "to"), "NetworkPolicy blocks gossip egress between alertmanager replicas"
