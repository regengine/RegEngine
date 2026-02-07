"""Pydantic models for tenant-specific graph nodes in the overlay system.

These models represent tenant-specific data that lives in tenant databases (reg_tenant_<uuid>)
and can reference global regulatory provisions from the reg_global database.

This module is shared between admin and graph services.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MappingType(str, Enum):
    """Types of control-to-provision mappings."""

    IMPLEMENTS = "IMPLEMENTS"
    PARTIALLY_IMPLEMENTS = "PARTIALLY_IMPLEMENTS"
    ADDRESSES = "ADDRESSES"
    REFERENCES = "REFERENCES"


class ProductType(str, Enum):
    """Types of customer products."""

    TRADING = "TRADING"
    LENDING = "LENDING"
    CUSTODY = "CUSTODY"
    PAYMENTS = "PAYMENTS"
    DERIVATIVES = "DERIVATIVES"
    OTHER = "OTHER"


class TenantControl(BaseModel):
    """Tenant-specific control mapped to regulatory provisions.

    Represents internal controls that tenants implement to address regulatory requirements.
    Lives in tenant database (reg_tenant_<uuid>).
    """

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    control_id: str = Field(..., min_length=1, max_length=100, description="Internal control identifier (e.g., AC-001)")
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1)
    framework: str = Field(..., description="Control framework (e.g., NIST CSF, SOC2, ISO27001)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[UUID] = None

    def to_cypher_create(self) -> tuple[str, dict]:
        """Generate Cypher query and parameters for creating this control.

        Returns:
            Tuple of (query_string, parameters_dict)
        """
        query = """
        CREATE (c:TenantControl {
            id: $id,
            tenant_id: $tenant_id,
            control_id: $control_id,
            title: $title,
            description: $description,
            framework: $framework,
            created_at: datetime($created_at),
            updated_at: datetime($updated_at),
            created_by: $created_by
        })
        RETURN c
        """
        params = {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "control_id": self.control_id,
            "title": self.title,
            "description": self.description,
            "framework": self.framework,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": str(self.created_by) if self.created_by else None,
        }
        return query, params


class ControlMapping(BaseModel):
    """Mapping between a tenant control and a regulatory provision.

    Provides explicit relationship with metadata about how a control
    addresses a specific regulatory requirement.
    """

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    control_id: UUID = Field(..., description="ID of TenantControl")
    provision_hash: str = Field(..., description="Hash of Provision from global database")
    mapping_type: MappingType
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in mapping (0-1)")
    notes: Optional[str] = None
    created_by: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_cypher_create(self) -> tuple[str, dict]:
        """Generate Cypher query to create mapping between control and provision.

        Returns:
            Tuple of (query_string, parameters_dict)
        """
        query = """
        MATCH (control:TenantControl {id: $control_id})
        CREATE (mapping:ControlMapping {
            id: $id,
            tenant_id: $tenant_id,
            provision_hash: $provision_hash,
            mapping_type: $mapping_type,
            confidence: $confidence,
            notes: $notes,
            created_by: $created_by,
            created_at: datetime($created_at)
        })
        CREATE (control)-[:HAS_MAPPING]->(mapping)
        CREATE (mapping)-[:TARGETS {hash: $provision_hash}]->(:Provision {hash: $provision_hash})
        RETURN mapping
        """
        params = {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "control_id": str(self.control_id),
            "provision_hash": self.provision_hash,
            "mapping_type": self.mapping_type.value,
            "confidence": self.confidence,
            "notes": self.notes,
            "created_by": str(self.created_by),
            "created_at": self.created_at.isoformat(),
        }
        return query, params


class CustomerProduct(BaseModel):
    """Tenant's product catalog entry.

    Represents a product/service offered by the tenant that needs
    to comply with regulatory requirements.
    """

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    product_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    product_type: ProductType
    jurisdictions: list[str] = Field(..., min_length=1, description="Jurisdictions where product operates (e.g., US, EU, UK)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[UUID] = None

    def to_cypher_create(self) -> tuple[str, dict]:
        """Generate Cypher query and parameters for creating this product.

        Returns:
            Tuple of (query_string, parameters_dict)
        """
        query = """
        CREATE (p:CustomerProduct {
            id: $id,
            tenant_id: $tenant_id,
            product_name: $product_name,
            description: $description,
            product_type: $product_type,
            jurisdictions: $jurisdictions,
            created_at: datetime($created_at),
            updated_at: datetime($updated_at),
            created_by: $created_by
        })
        RETURN p
        """
        params = {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "product_name": self.product_name,
            "description": self.description,
            "product_type": self.product_type.value,
            "jurisdictions": self.jurisdictions,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": str(self.created_by) if self.created_by else None,
        }
        return query, params


class ProductControlLink(BaseModel):
    """Link between a customer product and a tenant control."""

    product_id: UUID
    control_id: UUID
    tenant_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_cypher_create(self) -> tuple[str, dict]:
        """Generate Cypher query to link product and control.

        Returns:
            Tuple of (query_string, parameters_dict)
        """
        query = """
        MATCH (product:CustomerProduct {id: $product_id, tenant_id: $tenant_id})
        MATCH (control:TenantControl {id: $control_id, tenant_id: $tenant_id})
        MERGE (control)-[r:MAPS_TO {created_at: datetime($created_at)}]->(product)
        RETURN r
        """
        params = {
            "product_id": str(self.product_id),
            "control_id": str(self.control_id),
            "tenant_id": str(self.tenant_id),
            "created_at": self.created_at.isoformat(),
        }
        return query, params
