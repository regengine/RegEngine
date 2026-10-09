"""Regression tests for data-store NetworkPolicy egress (audit re-platform).

The defect: the admin and graph NetworkPolicies opened data-store ports
with an empty ``to: []`` peer, which admits any destination on that port,
so a compromised pod could reach a rogue database. The graph policy also
opened the plaintext Neo4j HTTP port 7474 even though every service
connects over encrypted Bolt (``NEO4J_URI=bolt+s://neo4j:7687``), leaking
graph data in cleartext.

The invariant below pins data-store egress to named database pods and
bans plaintext Neo4j HTTP from these policies. It fails on the old
manifests and passes once egress is pinned and 7474 is dropped.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# The two policies named by the audit finding.
POLICY_FILES = [
    REPO_ROOT / "infra" / "k8s" / "base" / "admin" / "networkpolicy.yaml",
    REPO_ROOT / "infra" / "k8s" / "base" / "graph" / "networkpolicy.yaml",
]

# Ports that must only reach a named database pod, never anywhere.
DATASTORE_PORTS = {5432, 6379, 7687, 9092, 9644}

# Plaintext Neo4j HTTP: nothing in these pods may use it.
PLAINTEXT_PORTS = {7474}

# Labels the data-store pods are expected to carry.
DATASTORE_APPS = {"postgres", "redis", "neo4j", "redpanda"}


def _load_policy(path):
    for doc in yaml.safe_load_all(path.read_text()):
        if doc and doc.get("kind") == "NetworkPolicy":
            return doc
    raise AssertionError(f"{path}: no NetworkPolicy document found")


def _egress_rules(policy):
    return policy["spec"].get("egress") or []


def _rule_ports(rule):
    return {entry["port"] for entry in rule.get("ports") or [] if isinstance(entry, dict) and "port" in entry}


def _peer_apps(rule):
    """Return the app labels named by the rule's `to` peers."""
    apps = set()
    for peer in rule.get("to") or []:
        if not isinstance(peer, dict):
            continue
        labels = (peer.get("podSelector") or {}).get("matchLabels") or {}
        if "app" in labels:
            apps.add(labels["app"])
    return apps


def check_datastore_egress_pinned(path, policy):
    """Every data-store port must target a named pod, never anywhere."""
    violations = []
    for rule in _egress_rules(policy):
        if not _rule_ports(rule) & DATASTORE_PORTS:
            continue
        if not _peer_apps(rule):
            violations.append(sorted(_rule_ports(rule) & DATASTORE_PORTS))
    assert not violations, (
        f"{path}: egress to data-store ports {violations} has an empty "
        "`to`, admitting any destination; pin it to the database pods"
    )


def check_no_plaintext_ports(path, policy):
    """Plaintext data-store ports must not be opened at all."""
    found = set()
    for rule in _egress_rules(policy):
        found |= _rule_ports(rule) & PLAINTEXT_PORTS
    assert not found, (
        f"{path}: egress opens plaintext ports {sorted(found)}; services must use the encrypted port instead"
    )


def check_pins_name_known_datastores(path, policy):
    """Pinned peers must be recognizable data-store pods, not typos."""
    for rule in _egress_rules(policy):
        if not _rule_ports(rule) & DATASTORE_PORTS:
            continue
        unknown = _peer_apps(rule) - DATASTORE_APPS
        assert not unknown, (
            f"{path}: egress pins data-store ports to unknown apps "
            f"{sorted(unknown)}; expected one of {sorted(DATASTORE_APPS)}"
        )


@pytest.mark.parametrize("path", POLICY_FILES, ids=[p.parent.name for p in POLICY_FILES])
def test_datastore_egress_pinned_to_database_pods(path):
    check_datastore_egress_pinned(path, _load_policy(path))


@pytest.mark.parametrize("path", POLICY_FILES, ids=[p.parent.name for p in POLICY_FILES])
def test_no_plaintext_datastore_ports_in_egress(path):
    check_no_plaintext_ports(path, _load_policy(path))


@pytest.mark.parametrize("path", POLICY_FILES, ids=[p.parent.name for p in POLICY_FILES])
def test_datastore_pins_name_known_datastores(path):
    check_pins_name_known_datastores(path, _load_policy(path))
