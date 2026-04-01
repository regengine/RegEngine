"""
SOP Generator Router.

Auto-generates FSMA 204 Standard Operating Procedures (SOPs) and
Traceability Plans based on a tenant's data profile. Outputs a
markdown document ready for download, print, or PDF export.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.webhook_compat import _verify_api_key

logger = logging.getLogger("sop-generator")

router = APIRouter(prefix="/api/v1/sop", tags=["SOP Generator"])


class SOPRequest(BaseModel):
    """Request to generate an SOP / Traceability Plan."""
    company_name: str = Field(..., description="Company name")
    company_type: str = Field(
        "manufacturer",
        description="Type: grower, manufacturer, distributor, retailer, importer"
    )
    products: list[str] = Field(..., description="List of FTL-covered products", min_length=1)
    facilities: list[str] = Field(..., description="Facility names/locations", min_length=1)
    primary_contact: str = Field(..., description="FSMA compliance contact name")
    contact_title: Optional[str] = Field(None, description="Contact's title")
    contact_email: Optional[str] = Field(None, description="Contact email")
    has_iot_monitoring: bool = Field(False, description="Uses IoT temperature monitoring")
    has_erp_integration: bool = Field(False, description="Has ERP/WMS integration")
    target_retailers: list[str] = Field(default_factory=list, description="Target retailers (Walmart, Kroger, etc.)")


class SOPResponse(BaseModel):
    """Generated SOP document."""
    company_name: str
    generated_at: str
    document_title: str
    markdown_content: str
    sections: list[str]
    page_estimate: int
    compliance_citations: list[str]


def _generate_cte_procedures(company_type: str, products: list[str], has_iot: bool) -> str:
    """Generate CTE-specific SOPs based on company type."""
    product_list = ", ".join(products[:5])
    sections = []

    if company_type in ("grower", "manufacturer"):
        sections.append(f"""### 4.1 Harvesting CTE (§1.1325(a))

**Scope**: All harvesting operations for FTL products ({product_list})

**Procedure**:
1. At point of harvest, assign Traceability Lot Code (TLC) using format: `[PRODUCT]-[DATE]-[FIELD]-[SEQUENCE]`
2. Record required KDEs:
   - TLC assigned
   - Product description (commodity, variety, pack size)
   - Quantity and unit of measure
   - Location of harvest (field ID, farm name, GPS coordinates if available)
   - Date and time of harvest
   - Name of harvester (business entity)
3. Apply TLC label to each container/pallet at point of harvest
4. Enter data into RegEngine within 4 hours of harvest completion

**Responsible**: Field Supervisor / Harvest Lead""")

    if company_type in ("grower", "manufacturer"):
        temp_line = "7. Verify IoT temperature logger is recording (Sensitech TempTale or equivalent)" if has_iot else "7. Record manual temperature check at start and end of cooling"
        sections.append(f"""### 4.2 Cooling CTE (§1.1325(b))

**Scope**: All cooling operations for temperature-sensitive FTL products

**Procedure**:
1. Upon receipt at cooling facility, scan TLC barcode or enter TLC manually
2. Record cooling start date and time
3. Record cooling facility location (GLN or facility name)
4. Record product description and quantity
5. Set target temperature per product specification
6. Monitor temperature throughout cooling period
{temp_line}
8. Enter cooling CTE data into RegEngine upon cooling completion

**Responsible**: Cold Storage Supervisor""")

    sections.append(f"""### 4.3 Shipping CTE (§1.1340)

**Scope**: All outbound shipments of FTL products

**Procedure**:
1. Generate Bill of Lading (BOL) with TLC prominently displayed
2. Record required KDEs:
   - TLC for each lot being shipped
   - Product description and quantity
   - Ship-from location (GLN or name + address)
   - Ship-to location (GLN or name + address)
   - Ship date and time
   - Carrier name and transport vehicle ID
3. {"Attach IoT temperature logger to shipment" if has_iot else "Record temperature at loading dock"}
4. Enter shipping CTE into RegEngine before truck departs
5. Retain copy of BOL for 2 years minimum

**Responsible**: Shipping/Logistics Manager""")

    sections.append(f"""### 4.4 Receiving CTE (§1.1345)

**Scope**: All inbound receipts of FTL products

**Procedure**:
1. Upon arrival, verify TLC on product matches BOL/ASN
2. Record required KDEs:
   - TLC received
   - Product description and quantity received
   - Receiving location (GLN or name + address)
   - Date and time of receipt
   - Immediate previous source (who shipped it to you)
   - TLC assigned by the shipper
3. {"Download IoT temperature log and upload to RegEngine" if has_iot else "Record temperature at receiving dock"}
4. Inspect product condition — note any damage or temperature concerns
5. Enter receiving CTE into RegEngine within 2 hours of receipt

**Responsible**: Receiving/Warehouse Manager""")

    if company_type in ("importer", "distributor"):
        sections.append(f"""### 4.5 First Land-Based Receiving CTE (§1.1325(c))

**Scope**: All first land-based receiving of FTL products imported or landed from vessels

**Procedure**:
1. Upon first receipt at a land-based facility, assign or verify Traceability Lot Code (TLC)
2. Record required KDEs:
   - TLC for product received
   - Product description (species, variety, pack size)
   - Quantity and unit of measure
   - Landing date and time
   - Receiving location (GLN or facility name + address)
   - Immediate previous source (vessel name, exporter, or transshipment entity)
   - Reference document number (Bill of Lading, import entry, or catch certificate)
   - Temperature at receipt (recommended)
3. Verify product documentation matches physical shipment
4. Enter FLBR CTE into RegEngine within 2 hours of landing receipt
5. Retain all import documentation for 2 years minimum

**Responsible**: Import/Receiving Manager""")

    if company_type in ("manufacturer",):
        sections.append(f"""### 4.5 Transformation CTE (§1.1350)

**Scope**: All processing, mixing, or repackaging of FTL products

**Procedure**:
1. Before transformation begins, record ALL input TLCs (source lots)
2. Assign NEW TLC to output product using format: `[OUTPUT]-[DATE]-[SEQUENCE]`
3. Record required KDEs:
   - New TLC for output product
   - All input TLCs (complete list)
   - Output product description and quantity
   - Transformation location (GLN or name + address)
   - Date and time of transformation
4. Maintain input-to-output lot mapping in RegEngine
5. This is the MOST CRITICAL CTE for recall tracing — ensure 100% accuracy

**Responsible**: Production / Quality Manager""")

    return "\n\n".join(sections)


@router.post(
    "/generate",
    response_model=SOPResponse,
    summary="Generate FSMA 204 SOP / Traceability Plan",
    description="Auto-generates a complete Standard Operating Procedure document based on company profile.",
)
async def generate_sop(
    request: SOPRequest,
    _: None = Depends(_verify_api_key),
) -> SOPResponse:
    """Generate a complete FSMA 204 SOP document."""

    now = datetime.now(timezone.utc)
    product_list = ", ".join(request.products[:10])
    facility_list = "\n".join([f"   - {f}" for f in request.facilities])
    retailer_section = ""

    if request.target_retailers:
        retailer_list = ", ".join(request.target_retailers)
        retailer_section = f"""
### 8.1 Retailer-Specific Requirements

**Target Retailers**: {retailer_list}

{"- **Walmart**: Requires GS1 EPCIS 2.0 format via Walmart GDSN portal. TLC must follow GS1-128 barcode standard." if "Walmart" in request.target_retailers or "walmart" in [r.lower() for r in request.target_retailers] else ""}
{"- **Kroger**: Accepts RegEngine FDA export format. Requires GLN for all facilities." if "Kroger" in request.target_retailers or "kroger" in [r.lower() for r in request.target_retailers] else ""}
{"- **Costco**: Requires full lot genealogy for all FTL products. Prefers EPCIS JSON-LD." if "Costco" in request.target_retailers or "costco" in [r.lower() for r in request.target_retailers] else ""}
"""

    cte_procedures = _generate_cte_procedures(
        request.company_type, request.products, request.has_iot_monitoring
    )

    integration_section = ""
    if request.has_erp_integration or request.has_iot_monitoring:
        integration_section = """
## 7. Technology Integration

"""
        if request.has_erp_integration:
            integration_section += """### 7.1 ERP/WMS Integration
- Traceability events are automatically pushed from ERP/WMS to RegEngine via webhook API
- Endpoint: `POST /api/v1/webhooks/ingest`
- Events are validated, SHA-256 hashed, and chained in real-time
- Monitor integration health via RegEngine dashboard

"""
        if request.has_iot_monitoring:
            integration_section += """### 7.2 IoT Temperature Monitoring
- Sensitech TempTale CSV exports are uploaded via `POST /api/v1/ingest/iot/sensitech`
- Temperature excursions are automatically flagged (threshold: 5°C for cold chain)
- Temperature data is linked to specific TLCs in the audit trail
- Excursion alerts trigger immediate review per Section 6 (Corrective Actions)

"""

    markdown = f"""# FSMA 204 Traceability Plan & Standard Operating Procedures

**Company**: {request.company_name}
**Company Type**: {request.company_type.title()}
**Document Version**: 1.0
**Generated**: {now.strftime("%B %d, %Y")}
**Compliance Contact**: {request.primary_contact}{f" — {request.contact_title}" if request.contact_title else ""}
{f"**Contact Email**: {request.contact_email}" if request.contact_email else ""}

---

## 1. Purpose & Scope

This Traceability Plan establishes the procedures and controls that {request.company_name} uses to maintain records required under the Food Safety Modernization Act (FSMA), Section 204 — Requirements for Additional Traceability Records for Certain Foods (21 CFR Part 1, Subpart S).

**Products Covered**: {product_list}

**Facilities**:
{facility_list}

## 2. Regulatory Background

FSMA Section 204 requires persons who manufacture, process, pack, or hold foods on the Food Traceability List (FTL) to maintain additional traceability records beyond existing requirements. Key requirements:

- **Critical Tracking Events (CTEs)**: Record key events in the supply chain
- **Key Data Elements (KDEs)**: Capture specific data points at each CTE
- **24-Hour Response**: Provide records to FDA within 24 hours of request (21 CFR 1.1455)
- **Electronic Format**: Records must be in electronic, sortable format
- **2-Year Retention**: Maintain records for at least 2 years

## 3. Traceability Lot Code (TLC) Assignment

### 3.1 TLC Format
{request.company_name} uses the following TLC format:

```
[PRODUCT CODE]-[MMDD]-[FACILITY]-[SEQUENCE]
```

Example: `ROM-0226-F3-001` (Romaine Lettuce, Feb 26, Facility 3, Lot 001)

### 3.2 TLC Assignment Rules
- A new TLC is assigned at each originating CTE (harvest, initial packing, transformation)
- TLCs must be unique within the organization
- TLC must be physically applied to product packaging (label, sticker, or case mark)
- TLC format must be communicated to all supply chain partners

## 4. Critical Tracking Event Procedures

{cte_procedures}

## 5. Record Keeping & Data Management

### 5.1 System of Record
{request.company_name} uses **RegEngine** as the primary traceability records system.

- All CTE events are entered into RegEngine via {"API integration" if request.has_erp_integration else "manual entry or CSV upload"}
- Each event is cryptographically hashed (SHA-256) and chained to an immutable audit trail
- Records are retained for a minimum of 2 years per 21 CFR 1.1455(c)

### 5.2 Data Entry Timelines
| CTE Type | Maximum Entry Delay |
|---|---|
| Harvesting | 4 hours after completion |
| Cooling | Upon cooling completion |
| Initial Packing | 2 hours after completion |
| Shipping | Before truck departure |
| Receiving | 2 hours after receipt |
| First Land-Based Receiving | 2 hours after landing receipt |
| Transformation | Immediately upon completion |

### 5.3 Supplier Data Collection
- Suppliers submit shipping data via **RegEngine Supplier Portal** (link-based, no account required)
- Supplier portal link: `https://regengine.co/portal`
- Suppliers must include TLC, product description, quantity, ship-from, and ship-to

## 6. Corrective Actions

### 6.1 Missing or Incomplete Records
1. Notify compliance contact immediately
2. Contact upstream/downstream partner to obtain missing data
3. Enter corrected data into RegEngine with notation
4. Document root cause and preventive action

### 6.2 Temperature Excursion
1. Quarantine affected product immediately
2. Assess product safety per company food safety plan
3. Document excursion in RegEngine with temperature data
4. Determine disposition (release, rework, destroy)
5. Notify affected supply chain partners if product was distributed

### 6.3 FDA Records Request (21 CFR 1.1455)
1. **Receipt**: Acknowledge request immediately, note 24-hour deadline
2. **Retrieval**: Export records from RegEngine using FDA Export function
3. **Review**: Verify completeness — all CTEs, KDEs, and lot genealogy present
4. **Submit**: Provide records in electronic, sortable spreadsheet format
5. **Document**: Log the request, response time, and any issues in RegEngine

{integration_section}
{retailer_section}

## 8. Training

### 8.1 Required Training
All personnel involved in traceability operations must complete:
- FSMA 204 overview training (within 30 days of hire)
- RegEngine system training (within 30 days of hire)
- Annual refresher training on FSMA 204 requirements
- CTE/KDE recording procedures specific to their role

### 8.2 Training Records
- Training completion records maintained in company HR system
- Training materials available on RegEngine platform
- Compliance contact responsible for tracking training compliance

## 9. Document Control

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | {now.strftime("%Y-%m-%d")} | {request.primary_contact} | Initial plan generated via RegEngine |

---

*This Traceability Plan was generated by RegEngine. It should be reviewed, customized, and approved by {request.company_name}'s food safety team before implementation. Contact support@regengine.co for assistance.*
"""

    sections = [
        "Purpose & Scope",
        "Regulatory Background",
        "TLC Assignment",
        "CTE Procedures",
        "Record Keeping & Data Management",
        "Corrective Actions",
        "Training",
        "Document Control",
    ]
    if request.has_erp_integration or request.has_iot_monitoring:
        sections.insert(6, "Technology Integration")
    if request.target_retailers:
        sections.append("Retailer-Specific Requirements")

    return SOPResponse(
        company_name=request.company_name,
        generated_at=now.isoformat(),
        document_title=f"FSMA 204 Traceability Plan — {request.company_name}",
        markdown_content=markdown,
        sections=sections,
        page_estimate=max(8, len(markdown) // 3000 + 1),
        compliance_citations=[
            "21 CFR Part 1, Subpart S",
            "21 CFR 1.1325 — Harvesting/Cooling CTEs",
            "21 CFR 1.1340 — Shipping CTE",
            "21 CFR 1.1345 — Receiving CTE",
            "21 CFR 1.1350 — Transformation CTE",
            "21 CFR 1.1455 — FDA Records Request (24-hour mandate)",
        ],
    )
