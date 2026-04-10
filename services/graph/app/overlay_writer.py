"""Utilities for writing tenant overlay data to Neo4j.

This module provides functions to create and manage tenant-specific data
in the content graph overlay system.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

import structlog

from shared.schemas import Jurisdiction
from shared.tenant_models import (
    ControlMapping,
    CustomerProduct,
    ProductControlLink,
    TenantControl,
)

from .graph_event_publisher import GraphEventPublisher
from .neo4j_utils import Neo4jClient

logger = structlog.get_logger("overlay-writer")


class OverlayWriter:
    """Write operations for tenant overlay data."""

    def __init__(self, tenant_id: UUID):
        """Initialize overlay writer for a specific tenant.

        Args:
            tenant_id: Tenant UUID for database routing
        """
        self.tenant_id = tenant_id
        self.db_name = Neo4jClient.get_tenant_database_name(tenant_id)
        self.publisher = (
            GraphEventPublisher()
        )  # Initialize Kafka publisher for audit events
        logger.info(
            "overlay_writer_initialized",
            tenant_id=str(tenant_id),
            database=self.db_name,
        )

    async def create_jurisdiction_node(self, jurisdiction: Jurisdiction) -> None:
        """Create or update a Jurisdiction node and BELONGS_TO link to its parent."""
        query = """
        MERGE (j:Jurisdiction {code: $code})
        SET j.name = $name, j.scope = $scope

        WITH j, $parent_code AS parent_code
        CALL {
          WITH parent_code
          OPTIONAL MATCH (parent:Jurisdiction {code: parent_code})
          RETURN parent
        }
        WITH j, parent
        WHERE parent IS NOT NULL
        MERGE (j)-[:BELONGS_TO]->(parent)
        """
        params = {
            "code": jurisdiction.code,
            "name": jurisdiction.name,
            "scope": (
                jurisdiction.scope.value
                if hasattr(jurisdiction.scope, "value")
                else jurisdiction.scope
            ),
            "parent_code": jurisdiction.parent_code,
        }
        client = Neo4jClient(database=self.db_name)
        try:
            async with client.session() as session:
                result = await session.run(query, params)
                await result.consume()
                logger.info(
                    "jurisdiction_upserted",
                    tenant_id=str(self.tenant_id),
                    code=jurisdiction.code,
                )
        finally:
            await client.close()

    async def create_tenant_control(self, control: TenantControl) -> TenantControl:
        """Create a tenant control in the tenant's database.

        Args:
            control: TenantControl model to create

        Returns:
            Created TenantControl with ID

        Raises:
            ValueError: If tenant_id doesn't match
        """
        if control.tenant_id != self.tenant_id:
            raise ValueError(
                f"Control tenant_id {control.tenant_id} does not match writer tenant_id {self.tenant_id}"
            )

        query, params = control.to_cypher_create()

        client = Neo4jClient(database=self.db_name)
        try:
            async with client.session() as session:
                result = await session.run(query, params)
                await result.consume()  # Ensure query completes

                logger.info(
                    "tenant_control_created",
                    tenant_id=str(self.tenant_id),
                    control_id=control.control_id,
                    id=str(control.id),
                    framework=control.framework,
                )

                # Emit Kafka audit event for control creation
                self.publisher.publish_control_event(
                    tenant_id=str(self.tenant_id), control_data=control.dict()
                )

                return control
        finally:
            await client.close()

    async def create_customer_product(self, product: CustomerProduct) -> CustomerProduct:
        """Create a customer product in the tenant's database.

        Args:
            product: CustomerProduct model to create

        Returns:
            Created CustomerProduct with ID

        Raises:
            ValueError: If tenant_id doesn't match
        """
        if product.tenant_id != self.tenant_id:
            raise ValueError(
                f"Product tenant_id {product.tenant_id} does not match writer tenant_id {self.tenant_id}"
            )

        query, params = product.to_cypher_create()

        client = Neo4jClient(database=self.db_name)
        try:
            async with client.session() as session:
                result = await session.run(query, params)
                await result.consume()  # Ensure query completes

                logger.info(
                    "customer_product_created",
                    tenant_id=str(self.tenant_id),
                    product_name=product.product_name,
                    id=str(product.id),
                    product_type=product.product_type.value,
                    jurisdictions=product.jurisdictions,
                )

                return product
        finally:
            await client.close()

    async def map_control_to_provision(self, mapping: ControlMapping) -> ControlMapping:
        """Create a mapping between a tenant control and a global provision.

        This creates a ControlMapping node and relationships in the tenant database.
        The provision reference uses the provision_hash to link to global data.

        Args:
            mapping: ControlMapping model to create

        Returns:
            Created ControlMapping with ID

        Raises:
            ValueError: If tenant_id doesn't match or control doesn't exist
        """
        if mapping.tenant_id != self.tenant_id:
            raise ValueError(
                f"Mapping tenant_id {mapping.tenant_id} does not match writer tenant_id {self.tenant_id}"
            )

        query, params = mapping.to_cypher_create()

        client = Neo4jClient(database=self.db_name)
        try:
            async with client.session() as session:
                result = await session.run(query, params)
                created = await result.single()

                if not created:
                    raise ValueError(
                        f"Failed to create mapping - control {mapping.control_id} may not exist"
                    )

                logger.info(
                    "control_mapping_created",
                    tenant_id=str(self.tenant_id),
                    control_id=str(mapping.control_id),
                    provision_hash=mapping.provision_hash,
                    mapping_type=mapping.mapping_type.value,
                    confidence=mapping.confidence,
                )

                # Emit Kafka audit event for mapping creation
                self.publisher.publish_mapping_event(
                    tenant_id=str(self.tenant_id), mapping_data=mapping.dict()
                )

                return mapping
        finally:
            await client.close()

    async def link_control_to_product(self, link: ProductControlLink) -> ProductControlLink:
        """Link a tenant control to a customer product.

        Args:
            link: ProductControlLink model to create

        Returns:
            Created ProductControlLink

        Raises:
            ValueError: If tenant_id doesn't match or nodes don't exist
        """
        if link.tenant_id != self.tenant_id:
            raise ValueError(
                f"Link tenant_id {link.tenant_id} does not match writer tenant_id {self.tenant_id}"
            )

        query, params = link.to_cypher_create()

        client = Neo4jClient(database=self.db_name)
        try:
            async with client.session() as session:
                result = await session.run(query, params)
                created = await result.single()

                if not created:
                    raise ValueError(
                        f"Failed to link control {link.control_id} to product {link.product_id} - nodes may not exist"
                    )

                logger.info(
                    "product_control_linked",
                    tenant_id=str(self.tenant_id),
                    product_id=str(link.product_id),
                    control_id=str(link.control_id),
                )

                return link
        finally:
            await client.close()

    async def get_control(self, control_id: UUID) -> Optional[dict]:
        """Retrieve a tenant control by ID.

        Args:
            control_id: UUID of the control

        Returns:
            Control data as dict, or None if not found
        """
        query = """
        MATCH (c:TenantControl {id: $control_id, tenant_id: $tenant_id})
        RETURN c
        """
        params = {"control_id": str(control_id), "tenant_id": str(self.tenant_id)}

        client = Neo4jClient(database=self.db_name)
        try:
            async with client.session() as session:
                result = await session.run(query, params)
                record = await result.single()
                return dict(record["c"]) if record else None
        finally:
            await client.close()

    async def get_product(self, product_id: UUID) -> Optional[dict]:
        """Retrieve a customer product by ID.

        Args:
            product_id: UUID of the product

        Returns:
            Product data as dict, or None if not found
        """
        query = """
        MATCH (p:CustomerProduct {id: $product_id, tenant_id: $tenant_id})
        RETURN p
        """
        params = {"product_id": str(product_id), "tenant_id": str(self.tenant_id)}

        client = Neo4jClient(database=self.db_name)
        try:
            async with client.session() as session:
                result = await session.run(query, params)
                record = await result.single()
                return dict(record["p"]) if record else None
        finally:
            await client.close()

    async def list_controls(
        self,
        framework: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """List tenant controls with pagination, optionally filtered by framework.

        Args:
            framework: Optional framework filter (e.g., "NIST CSF", "SOC2")
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            Tuple of (list of control dicts, total count)
        """
        match_clause = "MATCH (c:TenantControl {tenant_id: $tenant_id})"
        params: dict = {"tenant_id": str(self.tenant_id), "skip": skip, "limit": limit}
        if framework:
            match_clause = "MATCH (c:TenantControl {tenant_id: $tenant_id, framework: $framework})"
            params["framework"] = framework

        count_query = f"{match_clause} RETURN count(c) AS total"
        data_query = f"{match_clause} RETURN c ORDER BY c.control_id SKIP $skip LIMIT $limit"

        client = Neo4jClient(database=self.db_name)
        try:
            async with client.session() as session:
                count_result = await session.run(count_query, params)
                count_record = await count_result.single()
                total = count_record["total"] if count_record else 0

                result = await session.run(data_query, params)
                items = [dict(record["c"]) async for record in result]
                return items, total
        finally:
            await client.close()

    async def list_products(
        self,
        product_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """List customer products with pagination, optionally filtered by type.

        Args:
            product_type: Optional product type filter (e.g., "TRADING", "LENDING")
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            Tuple of (list of product dicts, total count)
        """
        match_clause = "MATCH (p:CustomerProduct {tenant_id: $tenant_id})"
        params: dict = {"tenant_id": str(self.tenant_id), "skip": skip, "limit": limit}
        if product_type:
            match_clause = "MATCH (p:CustomerProduct {tenant_id: $tenant_id, product_type: $product_type})"
            params["product_type"] = product_type

        count_query = f"{match_clause} RETURN count(p) AS total"
        data_query = f"{match_clause} RETURN p ORDER BY p.product_name SKIP $skip LIMIT $limit"

        client = Neo4jClient(database=self.db_name)
        try:
            async with client.session() as session:
                count_result = await session.run(count_query, params)
                count_record = await count_result.single()
                total = count_record["total"] if count_record else 0

                result = await session.run(data_query, params)
                items = [dict(record["p"]) async for record in result]
                return items, total
        finally:
            await client.close()


async def create_tenant_control(tenant_id: UUID, control: TenantControl) -> TenantControl:
    """Convenience function to create a tenant control.

    Args:
        tenant_id: Tenant UUID
        control: TenantControl model to create

    Returns:
        Created TenantControl
    """
    writer = OverlayWriter(tenant_id)
    return await writer.create_tenant_control(control)


async def create_customer_product(
    tenant_id: UUID, product: CustomerProduct
) -> CustomerProduct:
    """Convenience function to create a customer product.

    Args:
        tenant_id: Tenant UUID
        product: CustomerProduct model to create

    Returns:
        Created CustomerProduct
    """
    writer = OverlayWriter(tenant_id)
    return await writer.create_customer_product(product)


async def map_control_to_provision(
    tenant_id: UUID, mapping: ControlMapping
) -> ControlMapping:
    """Convenience function to map a control to a provision.

    Args:
        tenant_id: Tenant UUID
        mapping: ControlMapping model to create

    Returns:
        Created ControlMapping
    """
    writer = OverlayWriter(tenant_id)
    return await writer.map_control_to_provision(mapping)
