#!/usr/bin/env python3
"""
RegEngine Demo Data Loader

Loads a complete demo dataset for investor demonstrations and tenant onboarding.
Includes regulatory documents, provisions, tenant controls, products, and mappings.

Usage:
    python scripts/demo/load_demo_data.py --tenant-id <uuid>
    python scripts/demo/load_demo_data.py --tenant-id <uuid> --framework nist
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID, uuid4
from datetime import datetime
from typing import List, Dict

# Calculate project root relative to this script
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.graph.app.neo4j_utils import Neo4jClient
from shared.tenant_models import (
    TenantControl,
    CustomerProduct,
    ControlMapping,
    ProductControlLink,
    MappingType,
    ProductType,
)
from services.graph.app.overlay_writer import OverlayWriter


class DemoDataLoader:
    """Loads comprehensive demo data for RegEngine demonstrations."""

    def __init__(self, tenant_id: UUID):
        """
        Initialize demo data loader.

        Args:
            tenant_id: UUID of tenant to load data for
        """
        self.tenant_id = tenant_id
        self.writer = OverlayWriter(tenant_id)
        self.global_client = Neo4jClient(database="reg_global")

        # Track created entities for reporting
        self.created_controls = []
        self.created_products = []
        self.created_mappings = []

    async def load_all(self, framework: str = "nist", profile: str = "retailer"):
        """
        Load complete demo dataset.

        Args:
            framework: Control framework to use (nist, soc2, iso27001)
            profile: Tenant profile (retailer, supplier)
        """
        print(f"🚀 Loading demo data for tenant: {self.tenant_id}")
        print(f"   Framework: {framework.upper()}")
        print(f"   Profile:   {profile.upper()}")
        print()

        # Load tenant controls
        print("[1/4] Loading tenant controls...")
        await self.load_controls(framework)
        print(f"      ✓ Created {len(self.created_controls)} controls")

        # Load customer products
        print("[2/4] Loading customer products...")
        await self.load_products(profile)
        print(f"      ✓ Created {len(self.created_products)} products")

        # Map controls to provisions
        print("[3/4] Creating control-to-provision mappings...")
        await self.create_control_mappings()
        print(f"      ✓ Created {len(self.created_mappings)} mappings")

        # Link controls to products
        print("[4/4] Linking controls to products...")
        await self.link_controls_to_products()
        print(f"      ✓ Linked controls to products")

        print()
        print("✅ Demo data loaded successfully!")
        self._print_summary()

    async def load_controls(self, framework: str = "nist"):
        """
        Load tenant controls based on specified framework.

        Args:
            framework: Control framework (nist, soc2, iso27001)
        """
        if framework.lower() == "nist":
            controls = self._get_nist_csf_controls()
        elif framework.lower() == "soc2":
            controls = self._get_soc2_controls()
        elif framework.lower() == "iso27001":
            controls = self._get_iso27001_controls()
        else:
            raise ValueError(f"Unknown framework: {framework}")

        for control_data in controls:
            control = TenantControl(
                id=uuid4(),
                tenant_id=self.tenant_id,
                control_id=control_data["control_id"],
                title=control_data["title"],
                description=control_data["description"],
                framework=control_data["framework"],
            )

            created = await self.writer.create_tenant_control(control)
            self.created_controls.append(created)

    async def load_products(self, profile: str = "retailer"):
        """Load customer products catalog based on profile."""
        
        if profile == "retailer":
            products_data = [
                {
                    "product_name": "Private Label Frozen Shrimp",
                    "description": "Imported frozen shrimp (aquaculture) - Critical Tracking Event Monitoring",
                    "product_type": ProductType.TRADING, # Mapped to Retail
                    "jurisdictions": ["US-FDA", "EU-EFSA"],
                },
                {
                    "product_name": "Store Brand Leafy Greens",
                    "description": "Fresh cut salad mix - High Risk FSMA 204 Category",
                    "product_type": ProductType.CUSTODY, # Mapped to Storage
                    "jurisdictions": ["US-FDA", "CA-CFIA"],
                },
                {
                    "product_name": "Deli Counter Operations",
                    "description": "In-store prepared foods compliance",
                    "product_type": ProductType.LENDING, # Mapped to Operations
                    "jurisdictions": ["US-FDA"],
                },
            ]
        else: # Supplier
            products_data = [
                {
                    "product_name": "Harvest Crew #12 (Salinas)",
                    "description": "Field harvesting unit - First Land-Based Receiver",
                    "product_type": ProductType.TRADING,
                    "jurisdictions": ["US-FDA"],
                },
                {
                    "product_name": "Processing Line A",
                    "description": "Wash and pack facility line",
                    "product_type": ProductType.CUSTODY,
                    "jurisdictions": ["US-FDA"],
                },
                {
                    "product_name": "Cold Storage Unit 4",
                    "description": "Temperature controlled distribution center",
                    "product_type": ProductType.LENDING,
                    "jurisdictions": ["US-FDA"],
                },
            ]

        for product_data in products_data:
            product = CustomerProduct(
                id=uuid4(),
                tenant_id=self.tenant_id,
                **product_data
            )

            created = await self.writer.create_customer_product(product)
            self.created_products.append(created)

    async def create_control_mappings(self):
        """
        Create mappings between tenant controls and regulatory provisions.

        Note: This creates sample mappings to demo provisions.
        In production, these would be based on actual provision hashes.
        """
        # Sample provision hashes (these would come from ingested NYDFS, DORA, SEC SCI content)
        sample_provisions = [
            "abc123def456",  # Sample NYDFS § 500.02 (Cybersecurity Program)
            "def789ghi012",  # Sample NYDFS § 500.04 (CISO)
            "ghi345jkl678",  # Sample NYDFS § 500.09 (Risk Assessment)
            "jkl901mno234",  # Sample SEC SCI Rule 1001 (Capacity)
            "mno567pqr890",  # Sample DORA Article 5 (ICT Risk Management)
        ]

        # Map first 5 controls to provisions
        for i, control in enumerate(self.created_controls[:5]):
            if i < len(sample_provisions):
                mapping = ControlMapping(
                    id=uuid4(),
                    tenant_id=self.tenant_id,
                    control_id=control.id,
                    provision_hash=sample_provisions[i],
                    mapping_type=MappingType.IMPLEMENTS,
                    confidence=0.85 + (i * 0.02),  # Varying confidence scores
                    notes=f"Demo mapping for {control.control_id}",
                    created_by=self.tenant_id,  # Using tenant_id as creator
                )

                created = await self.writer.map_control_to_provision(mapping)
                self.created_mappings.append(created)

    async def link_controls_to_products(self):
        """Link tenant controls to customer products."""
        if not self.created_products or not self.created_controls:
            return

        # Trading Platform gets first 6 controls
        trading_platform = self.created_products[0]
        for control in self.created_controls[:6]:
            link = ProductControlLink(
                product_id=trading_platform.id,
                control_id=control.id,
                tenant_id=self.tenant_id,
            )
            await self.writer.link_control_to_product(link)

        # Digital Wallet gets controls 3-8
        if len(self.created_products) > 1:
            wallet = self.created_products[1]
            for control in self.created_controls[3:8]:
                link = ProductControlLink(
                    product_id=wallet.id,
                    control_id=control.id,
                    tenant_id=self.tenant_id,
                )
                await self.writer.link_control_to_product(link)

        # Lending Protocol gets controls 5-10
        if len(self.created_products) > 2 and len(self.created_controls) >= 10:
            lending = self.created_products[2]
            for control in self.created_controls[5:10]:
                link = ProductControlLink(
                    product_id=lending.id,
                    control_id=control.id,
                    tenant_id=self.tenant_id,
                )
                await self.writer.link_control_to_product(link)

    def _print_summary(self):
        """Print summary of loaded data."""
        print("\n📊 Demo Data Summary")
        print("=" * 50)
        print(f"Tenant ID:        {self.tenant_id}")
        print(f"Controls:         {len(self.created_controls)}")
        print(f"Products:         {len(self.created_products)}")
        print(f"Mappings:         {len(self.created_mappings)}")
        print("=" * 50)

        print("\n🎯 Next Steps:")
        print("1. View controls:  GET /overlay/controls")
        print("2. View products:  GET /overlay/products")
        print("3. View mappings:  GET /overlay/products/{id}/requirements")
        print("4. Gap analysis:   GET /overlay/products/{id}/compliance-gaps")

    # Control framework definitions

    def _get_nist_csf_controls(self) -> List[Dict]:
        """Get NIST Cybersecurity Framework sample controls."""
        return [
            {
                "control_id": "FSMA.204.1",
                "title": "Traceability Lot Code Assignment",
                "description": "Assign Traceability Lot Codes (TLC) to all Food Protocol Foods at first land-based receiving",
                "framework": "FSMA 204",
            },
            {
                "control_id": "FSMA.204.2",
                "title": "Critical Tracking Event (CTE) Capture",
                "description": "Capture and maintain Key Data Elements (KDEs) for all Critical Tracking Events",
                "framework": "FSMA 204",
            },
            {
                "control_id": "FSMA.117.1",
                "title": "Hazard Analysis",
                "description": "Conduct a hazard analysis to identify and evaluate known or reasonably foreseeable hazards",
                "framework": "FSMA 204",
            },
            {
                "control_id": "FSMA.117.2",
                "title": "Preventive Controls",
                "description": "Implement preventive controls to provide assurances that hazards will be significantly minimized",
                "framework": "FSMA 204",
            },
            {
                "control_id": "FSMA.117.3",
                "title": "Recall Plan",
                "description": "Establish a written recall plan for food with a hazard requiring a preventive control",
                "framework": "FSMA 204",
            },
            {
                "control_id": "GFSI.1",
                "title": "Supplier Approval Program",
                "description": "Maintain a documented supplier approval program based on risk",
                "framework": "GFSI",
            },
            {
                "control_id": "GFSI.2",
                "title": "Environmental Monitoring",
                "description": "Implement an environmental monitoring program for pathogens (e.g., Listeria)",
                "framework": "GFSI",
            },
             {
                "control_id": "ID.AM-1", # Keep some Cyber controls for IT
                "title": "Supply Chain System Inventory",
                "description": "Physical devices and systems within the supply chain are inventoried",
                "framework": "NIST CSF",
            },
        ]

    def _get_soc2_controls(self) -> List[Dict]:
        """Get SOC 2 Trust Services Criteria sample controls."""
        return [
            {
                "control_id": "CC1.1",
                "title": "CISO Designation",
                "description": "The entity demonstrates commitment to integrity and ethical values",
                "framework": "SOC 2",
            },
            {
                "control_id": "CC2.1",
                "title": "Communication of Responsibilities",
                "description": "The entity communicates information security responsibilities",
                "framework": "SOC 2",
            },
            {
                "control_id": "CC6.1",
                "title": "Logical and Physical Access Controls",
                "description": "The entity implements logical and physical access controls",
                "framework": "SOC 2",
            },
            {
                "control_id": "CC6.6",
                "title": "Encryption of Data",
                "description": "The entity implements encryption to protect data",
                "framework": "SOC 2",
            },
            {
                "control_id": "CC7.2",
                "title": "Security Incident Detection",
                "description": "The entity monitors system components and data for security incidents",
                "framework": "SOC 2",
            },
            {
                "control_id": "CC7.3",
                "title": "Security Incident Response",
                "description": "The entity evaluates security events to determine if they require response",
                "framework": "SOC 2",
            },
            {
                "control_id": "A1.2",
                "title": "System Availability",
                "description": "The entity maintains system availability commitments",
                "framework": "SOC 2",
            },
            {
                "control_id": "PI1.4",
                "title": "Data Privacy Processing",
                "description": "The entity processes personal information as described in privacy notice",
                "framework": "SOC 2",
            },
        ]

    def _get_iso27001_controls(self) -> List[Dict]:
        """Get ISO 27001 sample controls."""
        return [
            {
                "control_id": "A.5.1.1",
                "title": "Information Security Policies",
                "description": "Policies for information security shall be defined and approved",
                "framework": "ISO 27001",
            },
            {
                "control_id": "A.6.1.2",
                "title": "Segregation of Duties",
                "description": "Conflicting duties and areas of responsibility shall be segregated",
                "framework": "ISO 27001",
            },
            {
                "control_id": "A.9.2.3",
                "title": "Management of Privileged Access Rights",
                "description": "The allocation and use of privileged access rights shall be restricted",
                "framework": "ISO 27001",
            },
            {
                "control_id": "A.10.1.1",
                "title": "Cryptographic Controls Policy",
                "description": "A policy on the use of cryptographic controls shall be developed",
                "framework": "ISO 27001",
            },
            {
                "control_id": "A.12.4.1",
                "title": "Event Logging",
                "description": "Event logs recording user activities shall be produced and kept",
                "framework": "ISO 27001",
            },
            {
                "control_id": "A.16.1.1",
                "title": "Information Security Incident Management",
                "description": "Responsibilities and procedures shall be established for incident management",
                "framework": "ISO 27001",
            },
            {
                "control_id": "A.17.1.2",
                "title": "Business Continuity Procedures",
                "description": "Business continuity procedures shall be implemented",
                "framework": "ISO 27001",
            },
            {
                "control_id": "A.18.1.3",
                "title": "Protection of Records",
                "description": "Records shall be protected from loss, destruction, and falsification",
                "framework": "ISO 27001",
            },
        ]


def main():
    """Main entry point for demo data loader."""
    parser = argparse.ArgumentParser(
        description="Load RegEngine demo data for tenant demonstrations"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        required=True,
        help="UUID of tenant to load data for"
    )
    parser.add_argument(
        "--framework",
        type=str,
        default="nist",
        choices=["nist", "soc2", "iso27001"],
        help="Control framework to use (default: nist)"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="retailer",
        choices=["retailer", "supplier"],
        help="Tenant profile (retailer, supplier)"
    )

    args = parser.parse_args()

    try:
        tenant_id = UUID(args.tenant_id)
    except ValueError:
        print(f"❌ Error: Invalid tenant UUID: {args.tenant_id}")
        sys.exit(1)

    try:
        loader = DemoDataLoader(tenant_id)
        asyncio.run(loader.load_all(framework=args.framework, profile=args.profile))
    except Exception as e:
        print(f"\n❌ Error loading demo data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
