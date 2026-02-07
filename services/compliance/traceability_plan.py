#!/usr/bin/env python3
"""
FSMA 204 Traceability Plan Model.

Defines the structure for a facility's traceability plan per FDA requirements.
A traceability plan must contain:
- Procedures for maintaining traceability records
- Description of records maintained
- Supply chain map
- Point of contact information
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("traceability-plan")


@dataclass
class ContactInfo:
    """Point of contact for traceability inquiries."""
    name: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    available_24_7: bool = False


@dataclass
class RecordDescription:
    """Description of a traceability record type maintained by the facility."""
    record_type: str
    description: str
    retention_period_years: int = 2
    format: str = "electronic"  # electronic, paper, hybrid
    storage_location: Optional[str] = None


@dataclass
class SupplyChainNode:
    """A node in the supply chain map."""
    name: str
    role: str  # FARM, PROCESSOR, DISTRIBUTOR, RETAILER
    gln: Optional[str] = None
    fda_registration: Optional[str] = None
    address: Optional[str] = None
    upstream_nodes: List[str] = field(default_factory=list)
    downstream_nodes: List[str] = field(default_factory=list)


@dataclass
class Procedure:
    """A traceability procedure defined in the plan."""
    id: str
    name: str
    description: str
    responsible_party: str
    frequency: Optional[str] = None  # per_event, daily, weekly, etc.
    cte_type: Optional[str] = None  # SHIPPING, RECEIVING, TRANSFORMATION, etc.
    sop_reference: Optional[str] = None  # Link to SOP document


@dataclass
class TraceabilityPlan:
    """
    FSMA 204 Traceability Plan for a facility.
    
    Per FDA requirements, a traceability plan must include:
    1. Description of procedures for maintaining records
    2. Description of the records maintained
    3. Points of contact available 24/7
    4. Statement identifying farm that will assign TLC (if applicable)
    """
    facility_name: str
    facility_gln: Optional[str] = None
    facility_fda_reg: Optional[str] = None
    plan_version: str = "1.0"
    effective_date: Optional[str] = None
    last_updated: Optional[str] = None
    
    # FDA Required Elements
    procedures: List[Procedure] = field(default_factory=list)
    record_descriptions: List[RecordDescription] = field(default_factory=list)
    supply_chain_map: List[SupplyChainNode] = field(default_factory=list)
    contacts: List[ContactInfo] = field(default_factory=list)
    
    # Optional metadata
    product_scope: List[str] = field(default_factory=list)
    training_program: Optional[str] = None
    audit_schedule: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "facility_name": self.facility_name,
            "facility_gln": self.facility_gln,
            "facility_fda_reg": self.facility_fda_reg,
            "plan_version": self.plan_version,
            "effective_date": self.effective_date,
            "last_updated": self.last_updated,
            "procedures": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "responsible_party": p.responsible_party,
                    "frequency": p.frequency,
                    "cte_type": p.cte_type,
                    "sop_reference": p.sop_reference,
                }
                for p in self.procedures
            ],
            "record_descriptions": [
                {
                    "record_type": r.record_type,
                    "description": r.description,
                    "retention_period_years": r.retention_period_years,
                    "format": r.format,
                    "storage_location": r.storage_location,
                }
                for r in self.record_descriptions
            ],
            "supply_chain_map": [
                {
                    "name": n.name,
                    "role": n.role,
                    "gln": n.gln,
                    "fda_registration": n.fda_registration,
                    "address": n.address,
                    "upstream_nodes": n.upstream_nodes,
                    "downstream_nodes": n.downstream_nodes,
                }
                for n in self.supply_chain_map
            ],
            "contacts": [
                {
                    "name": c.name,
                    "role": c.role,
                    "email": c.email,
                    "phone": c.phone,
                    "available_24_7": c.available_24_7,
                }
                for c in self.contacts
            ],
            "product_scope": self.product_scope,
            "training_program": self.training_program,
            "audit_schedule": self.audit_schedule,
        }
    
    def validate(self) -> List[str]:
        """
        Validate the traceability plan against FSMA 204 requirements.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Check required elements
        if not self.facility_name:
            errors.append("Facility name is required")
        
        if not self.procedures:
            errors.append("At least one procedure must be defined")
        
        if not self.record_descriptions:
            errors.append("At least one record description must be defined")
        
        if not self.contacts:
            errors.append("At least one point of contact is required")
        else:
            # Check for 24/7 contact
            has_24_7 = any(c.available_24_7 for c in self.contacts)
            if not has_24_7:
                errors.append("At least one contact must be available 24/7 for FDA inquiries")
        
        return errors


def create_sample_traceability_plan(facility_name: str) -> TraceabilityPlan:
    """Create a sample traceability plan for demonstration."""
    return TraceabilityPlan(
        facility_name=facility_name,
        plan_version="1.0",
        effective_date=datetime.utcnow().strftime("%Y-%m-%d"),
        procedures=[
            Procedure(
                id="PROC-001",
                name="Receiving Documentation",
                description="Record all inbound shipments with TLC, quantity, and supplier information",
                responsible_party="Receiving Manager",
                frequency="per_event",
                cte_type="RECEIVING",
            ),
            Procedure(
                id="PROC-002",
                name="Shipping Documentation",
                description="Record all outbound shipments with TLC, quantity, and customer information",
                responsible_party="Shipping Manager",
                frequency="per_event",
                cte_type="SHIPPING",
            ),
        ],
        record_descriptions=[
            RecordDescription(
                record_type="Bill of Lading",
                description="Shipping document with TLC, quantity, ship-from/to",
                retention_period_years=2,
                format="electronic",
            ),
            RecordDescription(
                record_type="Receiving Log",
                description="Inbound shipment log with supplier TLC and quantity",
                retention_period_years=2,
                format="electronic",
            ),
        ],
        contacts=[
            ContactInfo(
                name="Food Safety Director",
                role="Primary Contact",
                email="safety@example.com",
                phone="555-123-4567",
                available_24_7=True,
            ),
        ],
        product_scope=["Fresh-cut produce", "Ready-to-eat salads"],
    )
