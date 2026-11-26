"""Regression tests for the k8s NetworkPolicy ingress peers (#2959).

The defect: every NetworkPolicy under infra/k8s/base declares
``policyTypes: [Ingress, Egress]`` — making its pods default-deny on ingress —
and then admitted the NGINX ingress controller with a **bare** ``podSelector``
and no ``namespaceSelector``.

Per the NetworkPolicy API, a ``from`` entry containing only a ``podSelector``
selects pods in the *policy's own namespace*. The production overlay pins
everything to ``regengine-prod`` while the ingress controller conventionally
runs in its own ``ingress-nginx`` namespace (and no such namespace exists
anywhere in this tree). The one rule written to let traffic in therefore
matched zero pods, so applying the overlay would take every Ingress-routed
service offline.

The fix places ``namespaceSelector`` and ``podSelector`` inside **one** list
element so they AND together. Two separate list elements would OR them and
admit every pod in the ingress-nginx namespace, so the nesting is the whole
point — these tests check the nesting, not merely the presence of the key.

Note: these manifests are not currently applied by any pipeline (nothing in
the repo builds the ``ghcr.io/regengine/*`` images they reference, and no
workflow runs ``kubectl apply``). The tests guard correctness of config that
would otherwise fail the first time it is used.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "infra" / "k8s" / "base"

# Peers that live outside the application namespace and therefore require a
# namespaceSelector. Keyed by the label that identifies them.
CROSS_NAMESPACE_PEERS = {
    ("app.kubernetes.io/name", "ingress-nginx"): "ingress-nginx",
}


def _network_policies():
    """Yield (path, policy_document) for every NetworkPolicy under base/."""
    for path in sorted(BASE.rglob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if doc and doc.get("kind") == "NetworkPolicy":
                yield path, doc


def _policy_ids():
    return [
        f"{p.relative_to(BASE)}::{d['metadata']['name']}" for p, d in _network_policies()
    ]


ALL_POLICIES = list(_network_policies())


def test_base_contains_the_expected_network_policies():
    """Guard against the file set silently shrinking."""
    names = sorted(d["metadata"]["name"] for _, d in ALL_POLICIES)
    assert names == [
        "admin-service",
        "alertmanager",
        "compliance-service",
        "graph-service",
        "ingestion-service",
        "nlp-service",
        "scheduler-service",
    ], names


@pytest.mark.parametrize("path,policy", ALL_POLICIES, ids=_policy_ids())
def test_cross_namespace_peers_and_both_selectors_in_one_element(path, policy):
    """A cross-namespace peer must AND namespaceSelector with podSelector.

    Fails against the pre-#2959 manifests, where the ingress-controller peer
    was a bare podSelector scoped to the policy's own namespace.
    """
    for direction in ("ingress", "egress"):
        for rule in policy["spec"].get(direction) or []:
            for peer in rule.get("from" if direction == "ingress" else "to") or []:
                if not isinstance(peer, dict):
                    continue
                labels = (peer.get("podSelector") or {}).get("matchLabels") or {}
                for (key, value), namespace in CROSS_NAMESPACE_PEERS.items():
                    if labels.get(key) != value:
                        continue
                    ns_sel = peer.get("namespaceSelector")
                    assert ns_sel is not None, (
                        f"{path.relative_to(REPO_ROOT)}: peer selecting {value} has a "
                        "bare podSelector, which matches only the policy's own "
                        "namespace and admits nothing"
                    )
                    assert (
                        ns_sel.get("matchLabels", {}).get("kubernetes.io/metadata.name")
                        == namespace
                    ), f"{path.relative_to(REPO_ROOT)}: namespaceSelector must target {namespace}"


def test_ingress_controller_peer_is_never_split_into_two_elements():
    """A lone namespaceSelector element would OR, admitting the whole namespace."""
    for path, policy in ALL_POLICIES:
        for rule in policy["spec"].get("ingress") or []:
            for peer in rule.get("from") or []:
                if not isinstance(peer, dict):
                    continue
                ns_sel = peer.get("namespaceSelector") or {}
                if (
                    ns_sel.get("matchLabels", {}).get("kubernetes.io/metadata.name")
                    == "ingress-nginx"
                ):
                    assert peer.get("podSelector"), (
                        f"{path.relative_to(REPO_ROOT)}: namespaceSelector for "
                        "ingress-nginx appears without a podSelector in the same "
                        "list element - this admits every pod in that namespace"
                    )


@pytest.mark.parametrize("path,policy", ALL_POLICIES, ids=_policy_ids())
def test_default_deny_policies_admit_something_on_ingress(path, policy):
    """A default-deny policy with no usable ingress peer is a silent outage."""
    if "Ingress" not in policy["spec"].get("policyTypes", []):
        return
    rules = policy["spec"].get("ingress") or []
    assert rules, (
        f"{path.relative_to(REPO_ROOT)}: policyTypes includes Ingress but no "
        "ingress rule exists, so the pod is unreachable"
    )
    assert any(rule.get("from") for rule in rules), (
        f"{path.relative_to(REPO_ROOT)}: no ingress rule names any peer"
    )
