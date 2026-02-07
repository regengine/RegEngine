"""Tests for content graph overlay system models."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

from shared.tenant_models import (
    ControlMapping,
    CustomerProduct,
    MappingType,
    ProductControlLink,
    ProductType,
    TenantControl,
)


class TestTenantControl:
    """Tests for TenantControl model."""

    def test_create_tenant_control(self):
        """Test creating a valid tenant control."""
        tenant_id = uuid4()
        control = TenantControl(
            tenant_id=tenant_id,
            control_id="AC-001",
            title="Access Control Policy",
            description="Comprehensive access control policy for all systems",
            framework="NIST CSF",
        )

        assert control.tenant_id == tenant_id
        assert control.control_id == "AC-001"
        assert control.title == "Access Control Policy"
        assert control.framework == "NIST CSF"
        assert isinstance(control.id, UUID)
        assert isinstance(control.created_at, datetime)
        assert isinstance(control.updated_at, datetime)

    def test_control_id_validation(self):
        """Test that control_id must not be empty."""
        with pytest.raises(ValidationError):
            TenantControl(
                tenant_id=uuid4(),
                control_id="",  # Empty string
                title="Test Control",
                description="Test description",
                framework="SOC2",
            )

    def test_to_cypher_create(self):
        """Test Cypher query generation for control creation."""
        tenant_id = uuid4()
        control = TenantControl(
            tenant_id=tenant_id,
            control_id="DM-042",
            title="Data Minimization",
            description="Minimize personal data collection",
            framework="GDPR",
        )

        query, params = control.to_cypher_create()

        assert "CREATE (c:TenantControl" in query
        assert params["tenant_id"] == str(tenant_id)
        assert params["control_id"] == "DM-042"
        assert params["framework"] == "GDPR"
        assert "id" in params
        assert "created_at" in params


class TestCustomerProduct:
    """Tests for CustomerProduct model."""

    def test_create_customer_product(self):
        """Test creating a valid customer product."""
        tenant_id = uuid4()
        product = CustomerProduct(
            tenant_id=tenant_id,
            product_name="Crypto Trading Platform",
            description="Institutional crypto trading and custody",
            product_type=ProductType.TRADING,
            jurisdictions=["US", "EU", "UK"],
        )

        assert product.tenant_id == tenant_id
        assert product.product_name == "Crypto Trading Platform"
        assert product.product_type == ProductType.TRADING
        assert "US" in product.jurisdictions
        assert len(product.jurisdictions) == 3
        assert isinstance(product.id, UUID)

    def test_product_types(self):
        """Test all product type values."""
        tenant_id = uuid4()

        for product_type in ProductType:
            product = CustomerProduct(
                tenant_id=tenant_id,
                product_name=f"Test {product_type.value}",
                description="Test product",
                product_type=product_type,
                jurisdictions=["US"],
            )
            assert product.product_type == product_type

    def test_jurisdictions_required(self):
        """Test that at least one jurisdiction is required."""
        with pytest.raises(ValidationError):
            CustomerProduct(
                tenant_id=uuid4(),
                product_name="Test Product",
                description="Test",
                product_type=ProductType.LENDING,
                jurisdictions=[],  # Empty list
            )

    def test_to_cypher_create(self):
        """Test Cypher query generation for product creation."""
        tenant_id = uuid4()
        product = CustomerProduct(
            tenant_id=tenant_id,
            product_name="DeFi Lending",
            description="Decentralized lending platform",
            product_type=ProductType.LENDING,
            jurisdictions=["US", "SG"],
        )

        query, params = product.to_cypher_create()

        assert "CREATE (p:CustomerProduct" in query
        assert params["product_name"] == "DeFi Lending"
        assert params["product_type"] == "LENDING"
        assert params["jurisdictions"] == ["US", "SG"]


class TestControlMapping:
    """Tests for ControlMapping model."""

    def test_create_control_mapping(self):
        """Test creating a valid control mapping."""
        tenant_id = uuid4()
        control_id = uuid4()
        created_by = uuid4()

        mapping = ControlMapping(
            tenant_id=tenant_id,
            control_id=control_id,
            provision_hash="abc123def456",
            mapping_type=MappingType.IMPLEMENTS,
            confidence=0.95,
            notes="Fully implements this requirement",
            created_by=created_by,
        )

        assert mapping.tenant_id == tenant_id
        assert mapping.control_id == control_id
        assert mapping.provision_hash == "abc123def456"
        assert mapping.mapping_type == MappingType.IMPLEMENTS
        assert mapping.confidence == pytest.approx(0.95)
        assert isinstance(mapping.id, UUID)

    def test_mapping_types(self):
        """Test all mapping type values."""
        tenant_id = uuid4()
        control_id = uuid4()
        created_by = uuid4()

        for mapping_type in MappingType:
            mapping = ControlMapping(
                tenant_id=tenant_id,
                control_id=control_id,
                provision_hash="test_hash",
                mapping_type=mapping_type,
                confidence=0.8,
                created_by=created_by,
            )
            assert mapping.mapping_type == mapping_type

    def test_confidence_bounds(self):
        """Test that confidence must be between 0 and 1."""
        tenant_id = uuid4()
        control_id = uuid4()
        created_by = uuid4()

        # Valid confidence values
        for confidence in [0.0, 0.5, 1.0]:
            mapping = ControlMapping(
                tenant_id=tenant_id,
                control_id=control_id,
                provision_hash="test",
                mapping_type=MappingType.PARTIALLY_IMPLEMENTS,
                confidence=confidence,
                created_by=created_by,
            )
            assert mapping.confidence == confidence

        # Invalid confidence values
        for confidence in [-0.1, 1.1, 2.0]:
            with pytest.raises(ValidationError):
                ControlMapping(
                    tenant_id=tenant_id,
                    control_id=control_id,
                    provision_hash="test",
                    mapping_type=MappingType.PARTIALLY_IMPLEMENTS,
                    confidence=confidence,
                    created_by=created_by,
                )

    def test_to_cypher_create(self):
        """Test Cypher query generation for mapping creation."""
        mapping = ControlMapping(
            tenant_id=uuid4(),
            control_id=uuid4(),
            provision_hash="prov_hash_123",
            mapping_type=MappingType.ADDRESSES,
            confidence=0.75,
            notes="Partially addresses requirement",
            created_by=uuid4(),
        )

        query, params = mapping.to_cypher_create()

        assert "CREATE (mapping:ControlMapping" in query
        assert "MATCH (control:TenantControl" in query
        assert params["provision_hash"] == "prov_hash_123"
        assert params["mapping_type"] == "ADDRESSES"
        assert params["confidence"] == pytest.approx(0.75)


class TestProductControlLink:
    """Tests for ProductControlLink model."""

    def test_create_product_control_link(self):
        """Test creating a product-control link."""
        product_id = uuid4()
        control_id = uuid4()
        tenant_id = uuid4()

        link = ProductControlLink(
            product_id=product_id,
            control_id=control_id,
            tenant_id=tenant_id,
        )

        assert link.product_id == product_id
        assert link.control_id == control_id
        assert link.tenant_id == tenant_id
        assert isinstance(link.created_at, datetime)

    def test_to_cypher_create(self):
        """Test Cypher query generation for link creation."""
        link = ProductControlLink(
            product_id=uuid4(),
            control_id=uuid4(),
            tenant_id=uuid4(),
        )

        query, params = link.to_cypher_create()

        assert "MATCH (product:CustomerProduct" in query
        assert "MATCH (control:TenantControl" in query
        assert "MERGE (control)-[r:MAPS_TO" in query
        assert "product_id" in params
        assert "control_id" in params
        assert "tenant_id" in params


class TestEnums:
    """Tests for enum types."""

    def test_mapping_type_values(self):
        """Test MappingType enum values."""
        assert MappingType.IMPLEMENTS.value == "IMPLEMENTS"
        assert MappingType.PARTIALLY_IMPLEMENTS.value == "PARTIALLY_IMPLEMENTS"
        assert MappingType.ADDRESSES.value == "ADDRESSES"
        assert MappingType.REFERENCES.value == "REFERENCES"

    def test_product_type_values(self):
        """Test ProductType enum values."""
        assert ProductType.TRADING.value == "TRADING"
        assert ProductType.LENDING.value == "LENDING"
        assert ProductType.CUSTODY.value == "CUSTODY"
        assert ProductType.PAYMENTS.value == "PAYMENTS"
        assert ProductType.DERIVATIVES.value == "DERIVATIVES"
        assert ProductType.OTHER.value == "OTHER"
