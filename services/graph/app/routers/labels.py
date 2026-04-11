"""
Label Inception Service - Traceability Label Generation API.
Merged v1.3 Security Fixes with v1.0 Operational Features.
"""

from __future__ import annotations

import os
import urllib.parse
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Literal, Optional
from urllib.parse import quote
import uuid
import sys
from pathlib import Path

# Add shared utilities (portable path resolution)
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.middleware import get_current_tenant_id
from shared.auth import require_api_key

import structlog
from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel, Field, validator

from ..models.fsma_nodes import CTEType
from ..neo4j_utils import Neo4jClient

# ✅ KEEP: Versioning & Logging
router = APIRouter(tags=["Traceability Labels"])
logger = structlog.get_logger("label-inception")
TRACEABILITY_DOMAIN = os.getenv("TRACEABILITY_DOMAIN", "https://trace.regengine.ai")

# ============================================================================
# MODELS (Preserved + Enhanced)
# ============================================================================


class UnitOfMeasure(str, Enum):
    EA = "EA"
    LBS = "LBS"
    CASE = "CASE"


class PackagingLevel(str, Enum):
    ITEM = "item"
    CASE = "case"
    PALLET = "pallet"


class ProductInfo(BaseModel):
    gtin: str = Field(..., min_length=14, max_length=14, description="GS1 GTIN-14")
    description: str
    plu: Optional[str] = None
    expected_units: int = Field(..., gt=0)

    @validator("gtin")
    def validate_gtin(cls, v):
        if not v.isdigit() or len(v) != 14:
            raise ValueError("GTIN must be exactly 14 digits")
        return v


class TraceabilityInfo(BaseModel):
    lot_number: str
    pack_date: str  # YYYY-MM-DD
    grower_gln: Optional[str] = None


class LabelBatchInitRequest(BaseModel):
    packer_gln: str
    product: ProductInfo
    traceability: TraceabilityInfo
    quantity: int = Field(..., gt=0, le=10000)
    unit_of_measure: UnitOfMeasure = UnitOfMeasure.EA
    packaging_level: PackagingLevel = PackagingLevel.ITEM


class LabelData(BaseModel):
    serial: str
    qr_payload: str
    zpl_code: str
    packaging_level: str


class LabelBatchInitResponse(BaseModel):
    batch_id: str
    tlc: str
    reserved_range: Dict[str, int]
    labels: List[LabelData]


# ============================================================================
# HELPERS (Preserved + Fixed)
# ============================================================================


def generate_sscc(gln: str, serial: int) -> str:
    """Preserved: Generates SSCC with GS1 check digit."""
    extension = "0"
    gln_part = gln.zfill(12)[:12]
    serial_part = str(serial).zfill(5)[-5:]
    base = extension + gln_part + serial_part

    # GS1 Check Digit Algorithm
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(base)))
    check_digit = str((10 - (total % 10)) % 10)

    return base + check_digit

def generate_qr_payload(gtin: str, lot: str, serial: str, domain: Optional[str] = None) -> str:
    """Security Fix: Use GS1 Digital Link Path Syntax (No Query Params)."""
    base_domain = domain or TRACEABILITY_DOMAIN
    safe_lot = urllib.parse.quote(lot, safe='')
    return f"{base_domain}/01/{gtin}/10/{safe_lot}/21/{serial}"


def generate_zpl_code(
    desc: str, plu: Optional[str], qr: str, serial: str, gtin: str
) -> str:
    """Reliability Fix: Use ^FDMM for Medium Error Correction."""
    plu_text = f"^FO50,80^A0N,60,60^FD{plu}^FS" if plu else ""
    return f"""^XA
^FO10,10^A0N,25,25^FD{desc[:30]}^FS
{plu_text}
^FO250,60^BQN,2,4^FDMM,{qr}^FS
^FO10,150^A0N,20,20^FDSerial: {serial}^FS
^FO10,175^A0N,15,15^FDGTIN: {gtin}^FS
^XZ"""


# ============================================================================
# ENDPOINTS (Secured)
# ============================================================================


@router.get("/health")
def health_check():
    """Preserved: Monitoring endpoint."""
    return {"status": "healthy", "service": "label-inception", "version": "1.3.0"}


@router.post("/batch/init", response_model=LabelBatchInitResponse)
async def initialize_label_batch(
    request: LabelBatchInitRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key: str = Depends(require_api_key)
):
    # Get tenant specific database
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
    neo4j = Neo4jClient(database=db_name)
    
    tlc = f"{request.product.gtin}-{request.traceability.lot_number}"
    
    # Store tenant_id as string for Cypher
    tenant_id_str = str(tenant_id)

    logger.info("batch_init_start", tenant_id=tenant_id_str, tlc=tlc)


    # ✅ ATOMICITY FIX: Single Transaction for Create + Reserve
    cypher = """
    MERGE (tenant:Tenant {id: $tenant_id})
    MERGE (packer:Facility {gln: $packer_gln, tenant_id: $tenant_id})

    MERGE (l:Lot {tlc: $tlc, tenant_id: $tenant_id})
    ON CREATE SET
        l.gtin = $gtin,
        l.product_description = $desc,
        l.created_at = datetime(),
        l.next_serial = 1,
        l.tlc_source_gln = $packer_gln

    MERGE (l)-[:BELONGS_TO]->(tenant)
    MERGE (l)-[:ASSIGNED_BY]->(packer)

    // Atomic Reservation: Lock node, read current, add quantity, write back
    WITH l
    CALL apoc.atomic.add(l, 'next_serial', $quantity) YIELD oldValue AS start, newValue AS next
    RETURN start, (start + $quantity - 1) as end
    """

    # Fallback Cypher if APOC is not available
    fallback_cypher = """
    MERGE (tenant:Tenant {id: $tenant_id})
    MERGE (packer:Facility {gln: $packer_gln, tenant_id: $tenant_id})
    MERGE (l:Lot {tlc: $tlc, tenant_id: $tenant_id})
    ON CREATE SET
        l.gtin = $gtin,
        l.product_description = $desc,
        l.created_at = datetime(),
        l.next_serial = 1,
        l.tlc_source_gln = $packer_gln

    MERGE (l)-[:BELONGS_TO]->(tenant)
    MERGE (l)-[:ASSIGNED_BY]->(packer)

    WITH l, coalesce(l.next_serial, 1) AS start
    SET l.next_serial = start + $quantity
    RETURN start, (start + $quantity - 1) as end
    """

    try:
        async with neo4j.session() as session:
            # Note: We prioritize the fallback_cypher here for broader compatibility
            # unless APOC is explicitly confirmed.
            result = await session.run(
                fallback_cypher,
                tenant_id=tenant_id_str,
                packer_gln=request.packer_gln,
                tlc=tlc,
                gtin=request.product.gtin,
                desc=request.product.description,
                quantity=request.quantity,
            )
            record = await result.single()

            if not record:
                raise RuntimeError("Transaction returned no result")

            start_serial = record["start"]
            end_serial = record["end"]

    except Exception as e:
        logger.error("batch_init_failed", error=str(e))
        raise HTTPException(500, "Database transaction failed")
    finally:
        await neo4j.close()

    # Generate Labels (In Memory)
    labels = []
    for sn in range(start_serial, end_serial + 1):
        sscc = generate_sscc(request.packer_gln, sn)
        qr = generate_qr_payload(
            request.product.gtin, request.traceability.lot_number, sscc
        )
        zpl = generate_zpl_code(
            request.product.description,
            request.product.plu,
            qr,
            sscc,
            request.product.gtin,
        )

        labels.append(
            LabelData(
                serial=sscc,
                qr_payload=qr,
                zpl_code=zpl,
                packaging_level=request.packaging_level.value,
            )
        )

    logger.info("batch_init_success", batch_id=tlc, count=len(labels))

    return LabelBatchInitResponse(
        batch_id=tlc,
        tlc=tlc,
        reserved_range={"start": start_serial, "end": end_serial},
        labels=labels,
    )
