"""
FSMA 204 Traceability Plan Builder.

Generates template-based compliance plans for food businesses.
A Traceability Plan is required by FSMA 204 and must document:
1. How the firm will maintain required records
2. Procedures for identifying foods on the Food Traceability List (FTL)
3. How TLCs are assigned and maintained
4. Point of contact for traceability questions
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("fsma-plan-builder")


class FirmType(str, Enum):
    """Types of firms under FSMA 204."""
    GROWER = "grower"
    MANUFACTURER = "manufacturer"
    PROCESSOR = "processor"
    PACKER = "packer"
    HOLDER = "holder"
    DISTRIBUTOR = "distributor"
    RETAILER = "retailer"
    RESTAURANT = "restaurant"


class RecordRetentionPeriod(str, Enum):
    """Record retention requirements."""
    TWO_YEARS = "2_years"
    STANDARD = "standard"  # As required by existing FDA regulations


@dataclass
class FirmInfo:
    """Information about the food business."""
    name: str
    address: str
    firm_type: FirmType
    gln: Optional[str] = None  # Global Location Number
    fda_registration: Optional[str] = None
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "firm_type": self.firm_type.value,
            "gln": self.gln,
            "fda_registration": self.fda_registration,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
        }


@dataclass
class FTLCommodity:
    """Food Traceability List commodity handled by the firm."""
    name: str
    category: str  # e.g., "Leafy Greens", "Fresh-cut Fruits"
    cte_types: List[str] = field(default_factory=list)  # CTEs performed
    tlc_assignment_method: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "cte_types": self.cte_types,
            "tlc_assignment_method": self.tlc_assignment_method,
        }


@dataclass
class RecordLocation:
    """Where traceability records are stored."""
    location_type: str  # "electronic", "paper", "hybrid"
    system_name: Optional[str] = None
    physical_address: Optional[str] = None
    backup_procedure: str = ""
    retention_period: RecordRetentionPeriod = RecordRetentionPeriod.TWO_YEARS


@dataclass
class TraceabilityPlan:
    """Complete FSMA 204 Traceability Plan."""
    plan_id: str
    firm: FirmInfo
    version: str
    created_date: str
    last_updated: str
    
    # Required plan elements
    commodities: List[FTLCommodity] = field(default_factory=list)
    record_locations: List[RecordLocation] = field(default_factory=list)
    
    # Procedures
    receiving_procedure: str = ""
    shipping_procedure: str = ""
    transformation_procedure: str = ""
    
    # TLC Assignment
    tlc_format: str = ""
    tlc_assignment_procedure: str = ""
    
    # Training
    training_procedure: str = ""
    
    # 24-hour recall response
    recall_procedure: str = ""
    recall_contact: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "firm": self.firm.to_dict(),
            "version": self.version,
            "created_date": self.created_date,
            "last_updated": self.last_updated,
            "commodities": [c.to_dict() for c in self.commodities],
            "record_locations": [
                {
                    "location_type": r.location_type,
                    "system_name": r.system_name,
                    "physical_address": r.physical_address,
                    "backup_procedure": r.backup_procedure,
                    "retention_period": r.retention_period.value,
                }
                for r in self.record_locations
            ],
            "procedures": {
                "receiving": self.receiving_procedure,
                "shipping": self.shipping_procedure,
                "transformation": self.transformation_procedure,
                "tlc_assignment": self.tlc_assignment_procedure,
                "training": self.training_procedure,
                "recall": self.recall_procedure,
            },
            "tlc_format": self.tlc_format,
            "recall_contact": self.recall_contact,
        }


# =============================================================================
# PLAN TEMPLATES
# =============================================================================

RECEIVING_PROCEDURE_TEMPLATE = """
## Receiving Procedure for {firm_name}

### Purpose
Document the receipt of Food Traceability List (FTL) commodities and capture required Key Data Elements (KDEs).

### Scope
Applies to all receiving operations for foods on the FTL at {address}.

### Procedure

1. **Prior to Arrival**
   - Verify incoming shipment is from an approved supplier
   - Ensure receiving area is prepared and clean

2. **Upon Arrival**
   - Inspect transport vehicle for cleanliness and temperature compliance
   - Verify shipping documents match physical shipment

3. **Record Required KDEs**
   For each lot received, record:
   - [ ] Traceability Lot Code (TLC) from supplier
   - [ ] Quantity and Unit of Measure
   - [ ] Product description
   - [ ] Immediate Previous Source (IPS) name and location
   - [ ] Receiving date and time
   - [ ] Reference document number (BOL, Invoice, etc.)

4. **TLC Assignment (if required)**
   If supplier TLC is not present or a new lot is created:
   - Assign new TLC per format: {tlc_format}
   - Link to supplier TLC if available

5. **Documentation**
   - Enter all KDEs into {record_system}
   - Retain records for minimum 2 years
"""

SHIPPING_PROCEDURE_TEMPLATE = """
## Shipping Procedure for {firm_name}

### Purpose
Document the shipment of Food Traceability List (FTL) commodities and maintain traceability chain.

### Scope
Applies to all shipping operations for foods on the FTL from {address}.

### Procedure

1. **Order Preparation**
   - Verify lot is available and meets quality standards
   - Pull correct lots for shipment using FIFO

2. **Record Required KDEs**
   For each lot shipped, record:
   - [ ] Traceability Lot Code (TLC)
   - [ ] Quantity and Unit of Measure
   - [ ] Product description
   - [ ] Ship-to location (name and address)
   - [ ] Ship date and time
   - [ ] Reference document number

3. **Documentation**
   - Generate shipping documents with all KDEs
   - Provide TLC information to receiver
   - Enter shipment record into {record_system}

4. **Verification**
   - Verify shipment matches order
   - Confirm all required KDEs are documented
"""

TRANSFORMATION_PROCEDURE_TEMPLATE = """
## Transformation Procedure for {firm_name}

### Purpose
Document the transformation of FTL commodities while maintaining traceability linkage.

### Scope
Applies to all transformation operations (processing, combining, packing) at {address}.

### Procedure

1. **Input Documentation**
   For all input lots:
   - Record input TLCs
   - Record input quantities
   - Record product descriptions

2. **Transformation Record**
   Document:
   - [ ] All input TLCs used
   - [ ] New TLC assigned to output
   - [ ] Transformation type performed
   - [ ] Date and time of transformation
   - [ ] Location where transformation occurred

3. **Output Documentation**
   - [ ] Assign new TLC using format: {tlc_format}
   - [ ] Record output quantity and unit of measure
   - [ ] Record new product description

4. **Linkage Maintenance**
   - Maintain clear link between input and output TLCs
   - Enable forward and backward tracing
"""

TLC_ASSIGNMENT_TEMPLATE = """
## TLC Assignment Procedure for {firm_name}

### TLC Format
Format: {tlc_format}

Example: {tlc_example}

### Components
- Plant/Location Code: {location_code}
- Date Component: YYYYMMDD or Julian (YYDDD)
- Sequence: Daily sequential number
- Shift (optional): A, B, C for shift identification

### Assignment Rules

1. **New Lot Creation**
   - Assign TLC at point of lot creation
   - Never reuse TLCs

2. **Received Products**
   - Maintain supplier TLC if provided
   - Assign new TLC only if:
     - Supplier TLC not provided
     - Lot is combined with other lots
     - Product undergoes transformation

3. **Record Keeping**
   - Log all TLC assignments in {record_system}
   - Maintain linkage to predecessor TLCs
"""

RECALL_PROCEDURE_TEMPLATE = """
## 24-Hour Recall Response Procedure for {firm_name}

### FDA Requirement
FSMA 204 requires providing traceability information to FDA within 24 hours of request.

### Recall Contact
**Primary Contact:** {recall_contact}
**Backup Contact:** {contact_name}
**Phone:** {contact_phone}
**Email:** {contact_email}

### Procedure

1. **Receipt of FDA Request**
   - Document time of request receipt
   - Identify TLC(s) subject to inquiry
   - Notify Recall Contact immediately

2. **Information Assembly (Target: 4 hours)**
   - Pull all records for affected TLC(s)
   - Generate forward trace (downstream customers)
   - Generate backward trace (upstream suppliers)
   - Compile into sortable spreadsheet format

3. **Verification (Target: 2 hours)**
   - Review completeness of trace data
   - Verify all required KDEs present
   - Document any gaps with explanation

4. **Response Submission (Within 24 hours)**
   - Submit electronic spreadsheet to FDA
   - Include:
     - All affected TLCs
     - Complete chain of custody
     - Contact information for all parties
     - Product quantities at each step

### Mock Recall Schedule
Conduct mock recalls quarterly to verify readiness.
Next scheduled: {next_mock_recall}
"""

TRAINING_PROCEDURE_TEMPLATE = """
## Traceability Training Procedure for {firm_name}

### Purpose
Ensure all personnel understand FSMA 204 requirements and company procedures.

### Training Requirements

1. **Initial Training**
   All employees handling FTL commodities receive training on:
   - FSMA 204 requirements overview
   - Company traceability procedures
   - KDE capture requirements
   - Record keeping systems

2. **Role-Specific Training**
   - Receiving: KDE capture at receipt
   - Production: Transformation documentation
   - Shipping: Outbound KDE requirements
   - Quality: Record review and verification

3. **Refresher Training**
   - Annual refresher for all personnel
   - Update training when procedures change

### Training Records
Maintain training records including:
- Employee name
- Training date
- Topics covered
- Trainer signature
- Employee acknowledgment
"""


# =============================================================================
# PLAN BUILDER
# =============================================================================

class TraceabilityPlanBuilder:
    """Builder for generating FSMA 204 Traceability Plans."""
    
    def __init__(self, firm: FirmInfo):
        self.firm = firm
        self.commodities: List[FTLCommodity] = []
        self.record_locations: List[RecordLocation] = []
        self.tlc_format = ""
        self.record_system = "electronic record system"
        
    def add_commodity(self, commodity: FTLCommodity) -> "TraceabilityPlanBuilder":
        """Add an FTL commodity to the plan."""
        self.commodities.append(commodity)
        return self
    
    def add_record_location(self, location: RecordLocation) -> "TraceabilityPlanBuilder":
        """Add a record storage location."""
        self.record_locations.append(location)
        if location.system_name:
            self.record_system = location.system_name
        return self
    
    def set_tlc_format(self, format_string: str) -> "TraceabilityPlanBuilder":
        """Set the TLC format template."""
        self.tlc_format = format_string
        return self
    
    def _generate_receiving_procedure(self) -> str:
        """Generate receiving procedure from template."""
        return RECEIVING_PROCEDURE_TEMPLATE.format(
            firm_name=self.firm.name,
            address=self.firm.address,
            tlc_format=self.tlc_format or "[PLANT]-[YYYYMMDD]-[SEQ]",
            record_system=self.record_system,
        )
    
    def _generate_shipping_procedure(self) -> str:
        """Generate shipping procedure from template."""
        return SHIPPING_PROCEDURE_TEMPLATE.format(
            firm_name=self.firm.name,
            address=self.firm.address,
            record_system=self.record_system,
        )
    
    def _generate_transformation_procedure(self) -> str:
        """Generate transformation procedure from template."""
        return TRANSFORMATION_PROCEDURE_TEMPLATE.format(
            firm_name=self.firm.name,
            address=self.firm.address,
            tlc_format=self.tlc_format or "[PLANT]-[YYYYMMDD]-[SEQ]",
        )
    
    def _generate_tlc_procedure(self) -> str:
        """Generate TLC assignment procedure from template."""
        # Generate example TLC
        example_tlc = self.tlc_format or "ABC-20240115-001"
        if "{" in example_tlc:
            example_tlc = "ABC-20240115-001"
            
        return TLC_ASSIGNMENT_TEMPLATE.format(
            firm_name=self.firm.name,
            tlc_format=self.tlc_format or "[PLANT]-[YYYYMMDD]-[SEQ]",
            tlc_example=example_tlc,
            location_code=self.firm.gln[:3] if self.firm.gln else "ABC",
            record_system=self.record_system,
        )
    
    def _generate_recall_procedure(self) -> str:
        """Generate recall response procedure from template."""
        return RECALL_PROCEDURE_TEMPLATE.format(
            firm_name=self.firm.name,
            recall_contact=self.firm.contact_name or "Traceability Manager",
            contact_name=self.firm.contact_name,
            contact_phone=self.firm.contact_phone,
            contact_email=self.firm.contact_email,
            next_mock_recall="[Schedule quarterly]",
        )
    
    def _generate_training_procedure(self) -> str:
        """Generate training procedure from template."""
        return TRAINING_PROCEDURE_TEMPLATE.format(
            firm_name=self.firm.name,
        )
    
    def build(self) -> TraceabilityPlan:
        """Build the complete traceability plan."""
        now = datetime.now(timezone.utc).isoformat()
        
        plan = TraceabilityPlan(
            plan_id=str(uuid.uuid4()),
            firm=self.firm,
            version="1.0",
            created_date=now,
            last_updated=now,
            commodities=self.commodities,
            record_locations=self.record_locations,
            receiving_procedure=self._generate_receiving_procedure(),
            shipping_procedure=self._generate_shipping_procedure(),
            transformation_procedure=self._generate_transformation_procedure(),
            tlc_format=self.tlc_format,
            tlc_assignment_procedure=self._generate_tlc_procedure(),
            training_procedure=self._generate_training_procedure(),
            recall_procedure=self._generate_recall_procedure(),
            recall_contact=f"{self.firm.contact_name} - {self.firm.contact_email}",
        )
        
        logger.info(
            "traceability_plan_generated",
            plan_id=plan.plan_id,
            firm_name=self.firm.name,
            commodities=len(self.commodities),
        )
        
        return plan


# =============================================================================
# PLAN EXPORT
# =============================================================================

def export_plan_markdown(plan: TraceabilityPlan) -> str:
    """Export plan as Markdown document."""
    md = f"""# FSMA 204 Traceability Plan

**Company:** {plan.firm.name}  
**Address:** {plan.firm.address}  
**FDA Registration:** {plan.firm.fda_registration or 'N/A'}  
**GLN:** {plan.firm.gln or 'N/A'}  

**Plan Version:** {plan.version}  
**Created:** {plan.created_date}  
**Last Updated:** {plan.last_updated}  

---

## Traceability Contact

**Name:** {plan.firm.contact_name}  
**Email:** {plan.firm.contact_email}  
**Phone:** {plan.firm.contact_phone}  

---

## Food Traceability List (FTL) Commodities

"""
    
    for i, comm in enumerate(plan.commodities, 1):
        md += f"""### {i}. {comm.name}
- **Category:** {comm.category}
- **CTEs Performed:** {', '.join(comm.cte_types) if comm.cte_types else 'N/A'}
- **TLC Method:** {comm.tlc_assignment_method or 'Standard'}

"""
    
    md += f"""---

## Record Storage

"""
    
    for loc in plan.record_locations:
        md += f"""- **Type:** {loc.location_type}
  - System: {loc.system_name or 'N/A'}
  - Location: {loc.physical_address or 'N/A'}
  - Retention: {loc.retention_period.value}

"""
    
    md += f"""---

## TLC Format

**Format:** `{plan.tlc_format}`

---

{plan.receiving_procedure}

---

{plan.shipping_procedure}

---

{plan.transformation_procedure}

---

{plan.tlc_assignment_procedure}

---

{plan.recall_procedure}

---

{plan.training_procedure}

---

## Certification

I certify that this Traceability Plan meets the requirements of FSMA Section 204.

**Signature:** _________________________

**Date:** _________________________

**Title:** _________________________
"""
    
    return md


def export_plan_json(plan: TraceabilityPlan) -> Dict[str, Any]:
    """Export plan as JSON-serializable dictionary."""
    return plan.to_dict()
