"""Offline regression for the exact post-v144 runtime policy fingerprints.

The fixture contains only pg_policies tuples selected by the startup canary,
in field order schema, table, name, permissive, roles, command, qual, check.
It was regenerated using PostgreSQL (PGlite) from v111's policy DDL plus its
four predecessor FSMA policies, then the exact v144 Supabase upgrade SQL.
Before applying v144, BOTH pre-existing v111 fingerprints matched exactly.
The reverse-delta test below preserves that independent baseline proof.

The live migrated-database suite remains authoritative for catalog drift;
these tests require neither a server nor a mocked production fingerprint.
"""

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("fixtures") / "v144_runtime_policy_catalog.json"
V144_POLICIES = {"tenants_backend_context_read", "tenants_write_own"}
PRE_V144_SHA256 = {
    "regengine": "37a00b9eeb2c2ff127c5c9bc4be6093e6c887a9e783ef891f28d419b0318b329",  # pragma: allowlist secret
    "regengine_sysadmin": "a7bacda65dc495ccaa238d7b01a53b409eb0136efb0f97d86328afe1dc209b41",  # pragma: allowlist secret
}


def _catalog():
    return json.loads(FIXTURE.read_text())


def _expected_fingerprints():
    # Parse the literal without importing shared.database or creating engines.
    module = ast.parse((ROOT / "services/shared/database.py").read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_EXPECTED_RUNTIME_POLICY_MANIFEST_SHA256"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("Runtime policy fingerprints are missing")


def _fingerprint(rows, role):
    """Match the canary's exact sorting, role filter and whitespace handling."""
    selected = sorted(
        (row for row in rows if role in row[4] or "public" in row[4]),
        key=lambda row: (row[0], row[1], row[2], row[5], ",".join(row[4])),
    )
    tuples = []
    for row in selected:
        fields = [*row[:4], ",".join(row[4]), row[5]]
        fields.extend(re.sub(r"\s+", " ", value.strip(" ")) if value is not None else "<NULL>" for value in row[6:])
        tuples.append(chr(31).join(fields))
    return hashlib.sha256(chr(30).join(tuples).encode("utf-8")).hexdigest()


@pytest.mark.parametrize("role", PRE_V144_SHA256)
def test_post_v144_catalog_matches_runtime_fingerprint(role):
    assert _fingerprint(_catalog(), role) == _expected_fingerprints()[role]


@pytest.mark.parametrize("role", PRE_V144_SHA256)
def test_only_v144_backend_policy_delta_changes_the_verified_baseline(role):
    rows = _catalog()
    additions = [row for row in rows if row[2] in V144_POLICIES]
    assert len(additions) == 2
    for row in additions:
        assert row[:2] == ["public", "tenants"]
        assert row[3:5] == ["PERMISSIVE", ["regengine", "regengine_sysadmin"]]
        assert "(id = get_tenant_context())" in row[6]
        assert "app.tenant_id" not in row[6]
    before = [row for row in rows if row[2] not in V144_POLICIES]
    assert _fingerprint(before, role) == PRE_V144_SHA256[role]
    assert _fingerprint(before, role) != _expected_fingerprints()[role]


@pytest.mark.parametrize("role", PRE_V144_SHA256)
@pytest.mark.parametrize("drift", ["missing_update", "public_write", "open_select", "legacy_read"])
def test_policy_drift_still_changes_the_exact_fingerprint(role, drift):
    rows = _catalog()
    assert not {"tenants_read_all", "public_read_product_catalog"} & {row[2] for row in rows}
    update = next(row for row in rows if row[2] == "tenants_write_own")
    select = next(row for row in rows if row[2] == "tenants_backend_context_read")
    if drift == "missing_update":
        rows.remove(update)
    elif drift == "public_write":
        update[4] = ["public"]
    elif drift == "open_select":
        select[6] = "true"
    else:
        rows.append(["public", "tenants", "tenants_read_all", "PERMISSIVE", ["public"], "SELECT", "true", None])
    assert _fingerprint(rows, role) != _expected_fingerprints()[role]
