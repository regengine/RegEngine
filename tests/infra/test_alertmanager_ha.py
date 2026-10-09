"""Regression tests for the Alertmanager single-replica topology.

The defect (audit re-platform-2-ops, low finding 94):
infra/k8s/base/monitoring/alertmanager.yaml ran one replica with
clustering off and said nothing about it, so the lost-silences and
notification-gap tradeoff was invisible. The accepted fix is a documented
gap: the manifest must say the single replica is intentional, where the
state lives, and what to change for real HA. These tests pin the
documentation, the storage claim behind it, and the replica/clustering
pairing so a future edit cannot half-enable HA (extra replicas with no
gossip mesh would notify twice instead of once).
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ALERTMANAGER_PATH = REPO_ROOT / "infra" / "k8s" / "base" / "monitoring" / "alertmanager.yaml"


def _docs():
    docs = [d for d in yaml.safe_load_all(ALERTMANAGER_PATH.read_text()) if d]
    assert len(docs) == 4, f"expected four documents in {ALERTMANAGER_PATH}"
    return docs


def _statefulset():
    for doc in _docs():
        if doc.get("kind") == "StatefulSet":
            return doc
    raise AssertionError("no StatefulSet found in alertmanager.yaml")


def _container_args():
    containers = _statefulset()["spec"]["template"]["spec"]["containers"]
    assert len(containers) == 1, "expected one alertmanager container"
    return containers[0].get("args", [])


def test_single_replica_gap_is_documented():
    """Fails on the old manifest, which said nothing about the HA tradeoff."""
    text = ALERTMANAGER_PATH.read_text().lower()
    for marker in ("single", "replica", "cluster", "silence"):
        assert marker in text, f"alertmanager.yaml no longer documents the HA gap (missing {marker!r})"


def test_notification_state_is_pvc_backed():
    """The doc comment claims reschedules keep state; the PVC must back it."""
    sts = _statefulset()
    storage_path = None
    for arg in _container_args():
        if arg.startswith("--storage.path="):
            storage_path = arg.split("=", 1)[1]
    assert storage_path, "alertmanager has no --storage.path flag"
    mounts = sts["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]
    assert any(m["mountPath"] == storage_path for m in mounts), (
        f"--storage.path={storage_path} is not mounted, state is ephemeral"
    )
    claims = {c["metadata"]["name"] for c in sts["spec"].get("volumeClaimTemplates", [])}
    mounted_volumes = {m["name"] for m in mounts}
    assert claims & mounted_volumes, (
        "storage mount is not backed by a volumeClaimTemplate, a reschedule loses silences and notification state"
    )


def test_replicas_and_clustering_stay_paired():
    """One replica must keep clustering off; several replicas need the mesh."""
    replicas = _statefulset()["spec"].get("replicas", 1)
    cluster_args = [a for a in _container_args() if a.startswith("--cluster.")]
    mesh_off = any(a == "--cluster.listen-address=" for a in cluster_args)
    if replicas == 1:
        assert mesh_off, (
            "single replica with a cluster listen address joins a mesh of one, which only adds gossip noise"
        )
    else:
        assert not mesh_off, (
            f"{replicas} replicas with clustering disabled would each notify independently instead of deduplicating"
        )
        assert any(a.startswith("--cluster.peer") for a in cluster_args), (
            "multiple replicas must name their --cluster.peer addresses"
        )
