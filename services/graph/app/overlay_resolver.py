"""Query resolver for merging global regulatory data with tenant overlays.

This module provides unified query interfaces that combine:
- Global regulatory provisions (from reg_global database)
- Tenant-specific controls and mappings (from reg_tenant_<uuid> database)
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

import structlog

from .neo4j_utils import Neo4jClient

logger = structlog.get_logger("overlay-resolver")


class OverlayResolver:
    """Merges global regulatory data with tenant-specific overlays."""

    def __init__(self, tenant_id: UUID):
        """Initialize overlay resolver for a specific tenant.

        Args:
            tenant_id: Tenant UUID for database routing
        """
        self.tenant_id = tenant_id
        self.global_db = Neo4jClient.get_global_database_name()
        self.tenant_db = Neo4jClient.get_tenant_database_name(tenant_id)

        logger.info(
            "overlay_resolver_initialized",
            tenant_id=str(tenant_id),
            global_db=self.global_db,
            tenant_db=self.tenant_db,
        )

    async def get_regulatory_requirements(self, product_id: UUID) -> dict[str, Any]:
        """Get all regulatory requirements for a customer product.

        This merges:
        1. Product information from tenant database
        2. Controls mapped to the product
        3. Provisions linked to those controls from global database

        Args:
            product_id: UUID of the customer product

        Returns:
            Dict with product, controls, and provisions data
        """
        tenant_client = Neo4jClient(database=self.tenant_db)
        global_client = Neo4jClient(database=self.global_db)

        try:
            # Step 1: Get product and its controls from tenant database
            product_controls_query = """
            MATCH (product:CustomerProduct {id: $product_id, tenant_id: $tenant_id})
            OPTIONAL MATCH (product)<-[:MAPS_TO]-(control:TenantControl)
            RETURN product, collect(control) as controls
            """
            async with tenant_client.session() as session:
                result = await session.run(
                    product_controls_query,
                    {"product_id": str(product_id), "tenant_id": str(self.tenant_id)},
                )
                record = await result.single()

                if not record or not record["product"]:
                    logger.warning(
                        "product_not_found",
                        product_id=str(product_id),
                        tenant_id=str(self.tenant_id),
                    )
                    return {"error": "Product not found", "product_id": str(product_id)}

                product_data = dict(record["product"])
                controls_data = [
                    dict(control) for control in record["controls"] if control
                ]

            # Step 2: Get provision mappings for these controls
            provision_hashes = []
            control_mappings = []

            if controls_data:
                for control in controls_data:
                    control_id = control["id"]
                    mapping_query = """
                    MATCH (control:TenantControl {id: $control_id})-[:HAS_MAPPING]->(mapping:ControlMapping)
                    RETURN mapping
                    """
                    async with tenant_client.session() as session:
                        mapping_result = await session.run(
                            mapping_query, {"control_id": control_id}
                        )
                        async for mapping_record in mapping_result:
                            mapping_data = dict(mapping_record["mapping"])
                            control_mappings.append(mapping_data)
                            provision_hashes.append(mapping_data["provision_hash"])

            # Step 3: Fetch full provision data from global database
            provisions_data = []
            if provision_hashes:
                # Remove duplicates
                unique_hashes = list(set(provision_hashes))

                global_query = """
                MATCH (prov:Provision)
                WHERE prov.hash IN $hashes
                OPTIONAL MATCH (prov)-[:IN_DOCUMENT]->(doc:Document)
                RETURN prov, doc
                """
                async with global_client.session() as session:
                    prov_result = await session.run(global_query, {"hashes": unique_hashes})
                    async for prov_record in prov_result:
                        provision = dict(prov_record["prov"])
                        document = (
                            dict(prov_record["doc"]) if prov_record["doc"] else None
                        )
                        provisions_data.append(
                            {
                                "provision": provision,
                                "document": document,
                            }
                        )

            logger.info(
                "regulatory_requirements_retrieved",
                product_id=str(product_id),
                tenant_id=str(self.tenant_id),
                num_controls=len(controls_data),
                num_provisions=len(provisions_data),
            )

            return {
                "product_id": str(product_id),
                "product": product_data,
                "controls": controls_data,
                "mappings": control_mappings,
                "provisions": provisions_data,
                "summary": {
                    "total_controls": len(controls_data),
                    "total_mappings": len(control_mappings),
                    "total_provisions": len(provisions_data),
                },
            }

        finally:
            await tenant_client.close()
            await global_client.close()

    async def get_provision_with_overlays(self, provision_hash: str) -> dict[str, Any]:
        """Get a provision with all tenant-specific overlays.

        This shows how a specific regulatory provision is addressed
        by the tenant's controls.

        Args:
            provision_hash: Hash of the provision to retrieve

        Returns:
            Dict with provision data and tenant controls
        """
        global_client = Neo4jClient(database=self.global_db)
        tenant_client = Neo4jClient(database=self.tenant_db)

        try:
            # Step 1: Fetch provision from global database
            global_query = """
            MATCH (prov:Provision {hash: $hash})
            OPTIONAL MATCH (prov)-[:IN_DOCUMENT]->(doc:Document)
            OPTIONAL MATCH (prov)-[:ABOUT]->(concept:Concept)
            OPTIONAL MATCH (prov)-[:APPLIES_TO]->(jurisdiction:Jurisdiction)
            RETURN prov, doc, collect(DISTINCT concept) as concepts, collect(DISTINCT jurisdiction) as jurisdictions
            """
            async with global_client.session() as session:
                result = await session.run(global_query, {"hash": provision_hash})
                record = await result.single()

                if not record or not record["prov"]:
                    logger.warning("provision_not_found", provision_hash=provision_hash)
                    return {
                        "error": "Provision not found",
                        "provision_hash": provision_hash,
                    }

                provision_data = dict(record["prov"])
                document_data = dict(record["doc"]) if record["doc"] else None
                concepts_data = [dict(c) for c in record["concepts"] if c]
                jurisdictions_data = [dict(j) for j in record["jurisdictions"] if j]

            # Step 2: Fetch tenant controls that reference this provision
            tenant_query = """
            MATCH (mapping:ControlMapping {provision_hash: $provision_hash, tenant_id: $tenant_id})
            MATCH (control:TenantControl)-[:HAS_MAPPING]->(mapping)
            OPTIONAL MATCH (control)-[:MAPS_TO]->(product:CustomerProduct)
            RETURN control, mapping, collect(DISTINCT product) as products
            """
            tenant_controls = []
            async with tenant_client.session() as session:
                result = await session.run(
                    tenant_query,
                    {
                        "provision_hash": provision_hash,
                        "tenant_id": str(self.tenant_id),
                    },
                )
                async for record in result:
                    control_data = dict(record["control"])
                    mapping_data = dict(record["mapping"])
                    products_data = [dict(p) for p in record["products"] if p]

                    tenant_controls.append(
                        {
                            "control": control_data,
                            "mapping": mapping_data,
                            "products": products_data,
                        }
                    )

            logger.info(
                "provision_overlays_retrieved",
                provision_hash=provision_hash,
                tenant_id=str(self.tenant_id),
                num_controls=len(tenant_controls),
            )

            return {
                "provision_hash": provision_hash,
                "provision": provision_data,
                "document": document_data,
                "concepts": concepts_data,
                "jurisdictions": jurisdictions_data,
                "tenant_controls": tenant_controls,
                "summary": {
                    "total_tenant_controls": len(tenant_controls),
                    "coverage": "FULL" if tenant_controls else "NONE",
                },
            }

        finally:
            await global_client.close()
            await tenant_client.close()

    async def get_control_details(self, control_id: UUID) -> dict[str, Any]:
        """Get detailed information about a tenant control.

        Args:
            control_id: UUID of the tenant control

        Returns:
            Dict with control data, mapped provisions, and products
        """
        tenant_client = Neo4jClient(database=self.tenant_db)
        global_client = Neo4jClient(database=self.global_db)

        try:
            # Get control with its mappings and products
            query = """
            MATCH (control:TenantControl {id: $control_id, tenant_id: $tenant_id})
            OPTIONAL MATCH (control)-[:HAS_MAPPING]->(mapping:ControlMapping)
            OPTIONAL MATCH (control)-[:MAPS_TO]->(product:CustomerProduct)
            RETURN control,
                   collect(DISTINCT mapping) as mappings,
                   collect(DISTINCT product) as products
            """
            async with tenant_client.session() as session:
                result = await session.run(
                    query,
                    {"control_id": str(control_id), "tenant_id": str(self.tenant_id)},
                )
                record = await result.single()

                if not record or not record["control"]:
                    logger.warning(
                        "control_not_found",
                        control_id=str(control_id),
                        tenant_id=str(self.tenant_id),
                    )
                    return {"error": "Control not found", "control_id": str(control_id)}

                control_data = dict(record["control"])
                mappings_data = [dict(m) for m in record["mappings"] if m]
                products_data = [dict(p) for p in record["products"] if p]

            # Fetch provisions from global database
            provision_hashes = [m["provision_hash"] for m in mappings_data]
            provisions_data = []

            if provision_hashes:
                global_query = """
                MATCH (prov:Provision)
                WHERE prov.hash IN $hashes
                RETURN prov
                """
                async with global_client.session() as session:
                    result = await session.run(global_query, {"hashes": provision_hashes})
                    provisions_data = [dict(record["prov"]) async for record in result]

            return {
                "control_id": str(control_id),
                "control": control_data,
                "mappings": mappings_data,
                "products": products_data,
                "provisions": provisions_data,
                "summary": {
                    "total_mappings": len(mappings_data),
                    "total_products": len(products_data),
                    "total_provisions": len(provisions_data),
                },
            }

        finally:
            await tenant_client.close()
            await global_client.close()

    async def get_compliance_gaps(
        self, product_id: UUID, jurisdiction: str
    ) -> dict[str, Any]:
        """Identify regulatory provisions not yet mapped to controls for a product.

        Args:
            product_id: UUID of the customer product
            jurisdiction: Jurisdiction to check (e.g., "US", "EU")

        Returns:
            Dict with unmapped provisions (potential compliance gaps)
        """
        global_client = Neo4jClient(database=self.global_db)
        tenant_client = Neo4jClient(database=self.tenant_db)

        try:
            # Get all provisions for jurisdiction from global database
            global_query = """
            MATCH (prov:Provision)-[:APPLIES_TO]->(j:Jurisdiction {name: $jurisdiction})
            RETURN prov
            """
            all_provisions = []
            async with global_client.session() as session:
                result = await session.run(global_query, {"jurisdiction": jurisdiction})
                all_provisions = [dict(record["prov"]) async for record in result]

            # Get mapped provision hashes for this product
            tenant_query = """
            MATCH (product:CustomerProduct {id: $product_id, tenant_id: $tenant_id})<-[:MAPS_TO]-(control:TenantControl)
            MATCH (control)-[:HAS_MAPPING]->(mapping:ControlMapping)
            RETURN collect(DISTINCT mapping.provision_hash) as mapped_hashes
            """
            mapped_hashes = []
            async with tenant_client.session() as session:
                result = await session.run(
                    tenant_query,
                    {"product_id": str(product_id), "tenant_id": str(self.tenant_id)},
                )
                record = await result.single()
                if record:
                    mapped_hashes = record["mapped_hashes"] or []

            # Identify gaps
            unmapped_provisions = [
                p for p in all_provisions if p.get("hash") not in mapped_hashes
            ]

            logger.info(
                "compliance_gaps_identified",
                product_id=str(product_id),
                jurisdiction=jurisdiction,
                total_provisions=len(all_provisions),
                mapped=len(all_provisions) - len(unmapped_provisions),
                unmapped=len(unmapped_provisions),
            )

            return {
                "product_id": str(product_id),
                "jurisdiction": jurisdiction,
                "total_provisions": len(all_provisions),
                "mapped_provisions": len(all_provisions) - len(unmapped_provisions),
                "unmapped_provisions": unmapped_provisions,
                "coverage_percentage": (
                    (
                        (len(all_provisions) - len(unmapped_provisions))
                        / len(all_provisions)
                        * 100
                    )
                    if all_provisions
                    else 0
                ),
            }

        finally:
            await global_client.close()
            await tenant_client.close()
