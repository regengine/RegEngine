"""Regression tests for NetworkPolicy egress symmetry.

The defect: several ingress rules admitted in-namespace callers while the
caller's own egress policy denied the same flow on the way out. Two
shapes of this existed:

- admin's egress lumped ingestion, compliance and scheduler under one
  port-8000 rule, but scheduler listens on 8600, so admin to scheduler
  calls were denied.
- nlp and graph ingress admitted ingestion pods, but ingestion's egress
  had no rule to nlp:8100 or graph:8200, so those calls were denied.

The invariant below derives the intended flows from the ingress side:
every in-namespace pod peer admitted on a port must have a matching
egress rule in the caller's policy. It fails on the old manifests and
passes once egress mirrors ingress.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "infra" / "k8s" / "base"


def _network_policies():
    for path in sorted(BASE.rglob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if doc and doc.get("kind") == "NetworkPolicy":
                yield path, doc


def _policies_by_app():
    mapping = {}
    for path, doc in _network_policies():
        app = (doc["spec"].get("podSelector") or {}).get("matchLabels", {}).get("app")
        if app:
            mapping[app] = (path, doc)
    return mapping


POLICIES_BY_APP = _policies_by_app()


def _caller_app(peer):
    """Return the in-namespace app label of a from-peer, or None to skip."""
    if not isinstance(peer, dict) or "namespaceSelector" in peer:
        return None
    labels = (peer.get("podSelector") or {}).get("matchLabels") or {}
    return labels.get("app")


def _rule_covers_egress(rule, target_app, port):
    peers = rule.get("to")
    # An empty or missing `to` means every destination in Kubernetes, so it
    # must never count as a deliberate flow to the target app. A later edit
    # that opens one of these ports to the world must turn the flow test red.
    if not peers:
        return False
    named = False
    for peer in peers:
        if not isinstance(peer, dict) or "namespaceSelector" in peer:
            continue
        labels = (peer.get("podSelector") or {}).get("matchLabels") or {}
        if labels.get("app") == target_app:
            named = True
    if not named:
        return False
    ports = rule.get("ports")
    if not ports:
        return True
    return any(
        isinstance(entry, dict) and entry.get("port") == port and entry.get("protocol", "TCP") == "TCP"
        for entry in ports
    )


def _egress_covers(policy, target_app, port):
    return any(_rule_covers_egress(rule, target_app, port) for rule in policy["spec"].get("egress") or [])


def _intended_flows():
    """Yield (caller_app, callee_app, port) derived from ingress rules."""
    flows = []
    for _, callee in _network_policies():
        callee_app = (callee["spec"].get("podSelector") or {}).get("matchLabels", {}).get("app")
        for rule in callee["spec"].get("ingress") or []:
            ports = [entry["port"] for entry in rule.get("ports") or [] if isinstance(entry, dict) and "port" in entry]
            for peer in rule.get("from") or []:
                caller = _caller_app(peer)
                if caller is None or caller not in POLICIES_BY_APP:
                    continue
                for port in ports:
                    flows.append((caller, callee_app, port))
    return sorted(set(flows))


INTENDED_FLOWS = _intended_flows()


def test_ingress_implies_at_least_one_in_namespace_flow():
    assert INTENDED_FLOWS, "no in-namespace flows derived, the test is vacuous"


@pytest.mark.parametrize(
    "caller,callee,port",
    INTENDED_FLOWS,
    ids=[f"{caller}->{callee}:{port}" for caller, callee, port in INTENDED_FLOWS],
)
def test_egress_allows_every_ingress_intended_flow(caller, callee, port):
    """The caller's egress must permit what the callee's ingress admits."""
    _, policy = POLICIES_BY_APP[caller]
    assert _egress_covers(policy, callee, port), (
        f"{callee} ingress admits {caller} on TCP {port}, but {caller}'s "
        "egress policy has no matching rule, so the flow is denied"
    )


def _container_ports_by_app():
    """Map each in-namespace app label to its Deployment containerPort."""
    mapping = {}
    for path in sorted(BASE.rglob("deployment.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc or doc.get("kind") != "Deployment":
                continue
            try:
                app = doc["spec"]["selector"]["matchLabels"]["app"]
                containers = doc["spec"]["template"]["spec"]["containers"]
            except (KeyError, TypeError):
                continue
            ports = [p["containerPort"] for c in containers for p in c.get("ports", []) if "containerPort" in p]
            if ports:
                mapping[app] = ports
    return mapping


@pytest.mark.parametrize(
    "caller,callee,port",
    INTENDED_FLOWS,
    ids=[f"{caller}->{callee}:{port}" for caller, callee, port in INTENDED_FLOWS],
)
def test_intended_flow_port_matches_callee_container_port(caller, callee, port):
    """Two policies agreeing on the wrong port still pass the egress test.

    The flow port must equal the callee's containerPort, or the allowed
    traffic hits a closed container port.
    """
    container_ports = _container_ports_by_app()
    assert callee in container_ports, f"no Deployment containerPort found for {callee}"
    assert port in container_ports[callee], (
        f"{caller}->{callee}:{port} is allowed by policy but {callee} listens on {container_ports[callee]}"
    )
