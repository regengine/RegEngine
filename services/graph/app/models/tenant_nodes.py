"""
Tenant Overlay Graph Node Models for Neo4j.

Defines keys and nodes for tenant-specific overrides of regulatory rules.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class TenantOverlay:
    """
    A tenant-specific overlay configuration node.

    Neo4j Label: TenantOverlay
    """

    tenant_id: str
    name: str
    description: Optional[str] = None

    @property
    def node_properties(self) -> Dict[str, Any]:
        props = {"tenant_id": self.tenant_id, "name": self.name}
        if self.description:
            props["description"] = self.description
        return props

    @staticmethod
    def merge_cypher() -> str:
        return """
        MERGE (t:TenantOverlay {tenant_id: $tenant_id})
        ON CREATE SET t += $properties, t.created_at = datetime()
        ON MATCH SET t += $properties
        RETURN t
        """


@dataclass
class RegulationOverride:
    """
    Specific rule overrides for a tenant.

    Neo4j Label: RegulationOverride
    """

    override_id: str
    rule_id: str
    parameter: str
    value: str
    tenant_id: str

    @property
    def node_properties(self) -> Dict[str, Any]:
        return {
            "override_id": self.override_id,
            "rule_id": self.rule_id,
            "parameter": self.parameter,
            "value": self.value,
            "tenant_id": self.tenant_id,
        }

    @staticmethod
    def merge_cypher() -> str:
        # ON MATCH sets only the mutable rule fields. tenant_id and
        # override_id stay in the MERGE key; copying them from $properties
        # would let a caller retag a node onto another tenant.
        return """
        MERGE (r:RegulationOverride {override_id: $override_id, tenant_id: $tenant_id})
        ON CREATE SET r += $properties, r.created_at = datetime()
        ON MATCH SET r.rule_id = $properties.rule_id, r.parameter = $properties.parameter, r.value = $properties.value
        RETURN r
        """


class OverlayRelationships:
    """Cypher templates for Overlay relationships."""

    # Tenant HAS_OVERLAY -> RegulationOverride
    # Both ends carry tenant_id so a tenant cannot link its overlay to
    # another tenant's override node when override_id values collide.
    TENANT_HAS_OVERRIDE = """
    MATCH (t:TenantOverlay {tenant_id: $tenant_id})
    MATCH (r:RegulationOverride {override_id: $override_id, tenant_id: $tenant_id})
    MERGE (t)-[:HAS_OVERRIDE]->(r)
    """
