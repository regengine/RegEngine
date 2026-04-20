"""Tenant-scope regression tests for services/shared/tenant_models.py -- #1413.

Verifies that every to_cypher_create method that emits a MATCH clause includes
tenant_id in the inline property map, so cross-tenant node access is impossible.

Covered models:
  - ControlMapping.to_cypher_create  (previously missing tenant_id on MATCH)
  - ProductControlLink.to_cypher_create  (already correct -- pinned as regression)
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest

# Ensure services/shared is importable regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.shared.tenant_models import (
    ControlMapping,
    MappingType,
    ProductControlLink,
    TenantControl,
)

TENANT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _control_mapping(tenant_id: str) -> ControlMapping:
    return ControlMapping(
        tenant_id=UUID(tenant_id),
        control_id=uuid4(),
        provision_hash="abc123",
        mapping_type=MappingType.IMPLEMENTS,
        confidence=0.9,
        created_by=uuid4(),
    )


def _product_control_link(tenant_id: str) -> ProductControlLink:
    return ProductControlLink(
        product_id=uuid4(),
        control_id=uuid4(),
        tenant_id=UUID(tenant_id),
    )


# ---------------------------------------------------------------------------
# ControlMapping -- MATCH must carry tenant_id (#1413)
# ---------------------------------------------------------------------------


def test_control_mapping_match_includes_tenant_id():
    """MATCH on TenantControl must include tenant_id to prevent cross-tenant reads."""
    cypher, _params = _control_mapping(TENANT_A).to_cypher_create()
    assert "tenant_id: $tenant_id" in cypher, (
        "ControlMapping.to_cypher_create MATCH clause missing tenant_id -- "
        "without it, a caller can retrieve a control belonging to another tenant (#1413)"
    )


def test_control_mapping_match_tenant_id_is_parameterised():
    """tenant_id must come from the params dict, never string-formatted into Cypher."""
    cypher, params = _control_mapping(TENANT_A).to_cypher_create()

    # Confirm $tenant_id placeholder is in the Cypher text.
    assert "$tenant_id" in cypher

    # Confirm the actual tenant UUID is in the params dict, not the raw Cypher.
    assert params["tenant_id"] == TENANT_A
    assert TENANT_A not in cypher, (
        "tenant_id UUID must NOT be interpolated directly into the Cypher string "
        "-- use $tenant_id parameter binding only"
    )


def test_control_mapping_cypher_no_unscoped_match():
    """No MATCH clause in the emitted Cypher may omit tenant_id."""
    cypher, _params = _control_mapping(TENANT_A).to_cypher_create()
    lines = [l.strip() for l in cypher.splitlines() if "MATCH" in l.upper()]
    for line in lines:
        assert "tenant_id" in line, (
            f"MATCH clause without tenant_id found: {line!r}"
        )


def test_control_mapping_create_still_contains_tenant_id():
    """CREATE node must also carry tenant_id so new mapping is attributable."""
    cypher, _params = _control_mapping(TENANT_A).to_cypher_create()
    # The CREATE block sets tenant_id on the ControlMapping node.
    create_section = cypher[cypher.upper().index("CREATE"):]
    assert "tenant_id" in create_section


# ---------------------------------------------------------------------------
# ProductControlLink -- regression: scoping was already correct, keep it pinned
# ---------------------------------------------------------------------------


def test_product_control_link_both_matches_scoped():
    """Both MATCH clauses in ProductControlLink must include tenant_id (regression pin)."""
    cypher, _params = _product_control_link(TENANT_A).to_cypher_create()

    assert "CustomerProduct" in cypher
    assert "TenantControl" in cypher

    # Count occurrences: both MATCHes must carry tenant_id inline.
    match_lines = [l.strip() for l in cypher.splitlines() if "MATCH" in l.upper()]
    assert len(match_lines) >= 2, "Expected at least two MATCH clauses"
    for line in match_lines:
        assert "tenant_id: $tenant_id" in line, (
            f"MATCH clause without tenant_id: {line!r}"
        )


def test_product_control_link_params_contain_tenant_id():
    cypher, params = _product_control_link(TENANT_A).to_cypher_create()
    assert params["tenant_id"] == TENANT_A
    assert TENANT_A not in cypher


# ---------------------------------------------------------------------------
# TenantControl CREATE -- has no MATCH, but pinning that it stays correct
# ---------------------------------------------------------------------------


def test_tenant_control_create_no_unscoped_match():
    """TenantControl.to_cypher_create uses only CREATE; no MATCH to scope."""
    control = TenantControl(
        tenant_id=UUID(TENANT_A),
        control_id="AC-001",
        title="Access Control",
        description="Restricts access",
        framework="NIST CSF",
    )
    cypher, params = control.to_cypher_create()

    assert "MATCH" not in cypher.upper(), (
        "TenantControl.to_cypher_create should not emit any MATCH clauses"
    )
    assert params["tenant_id"] == TENANT_A


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
