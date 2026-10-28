# ============================================================
# UNSAFE ZONE: This file (1025 lines) mixes compliance scoring,
# graph-based traceability queries, CSV/export generation, and
# route handling in one module. Duplicates Neo4jClient import.
# Depends on Neo4j — will need rewrite during Neo4j→PostgreSQL
# consolidation.
# Refactoring target — see PHASE 3.5 in REGENGINE_CODEBASE_REMEDIATION_PRD.md
# ============================================================
from __future__ import annotations

import csv
import io
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from shared.auth import reconcile_tenant_scope, require_api_key
from shared.fsma_plan_builder import (
    FirmInfo,
    FirmType,
    FTLCommodity,
    RecordLocation,
    RecordRetentionPeriod,
    TraceabilityPlanBuilder,
    export_plan_json,
    export_plan_markdown,
)

# Add shared utilities (portable path resolution)
from shared.middleware import get_current_tenant_id
from shared.rate_limit import limiter

from ...exporters import (
    RECALL_CONTACTS_HEADER,
    TRACE_CSV_HEADER,
    build_recall_contacts_rows,
    build_trace_csv_rows,
    csv_safe,
    header_filename,
    xml_escape,
)
from ...fsma_utils import find_gaps, find_orphaned_lots, trace_backward, trace_forward
from ...neo4j_utils import Neo4jClient

# Validate the API key before any endpoint parameter. The handlers below declare
# ``Depends(get_current_tenant_id)`` ahead of ``Depends(require_api_key)``, and FastAPI
# resolves endpoint dependencies in declaration order, so the tenant lookup ran first,
# found no principal on ``request.state`` (#2524 fallback) and returned 401 before the
# key was checked. Router-level dependencies resolve before endpoint parameters, and
# the per-request dependency cache means the key is still validated exactly once.
router = APIRouter(tags=["Compliance"], dependencies=[Depends(require_api_key)])
logger = structlog.get_logger("fsma-compliance")


# ============================================================================
# COVERAGE CARD ENDPOINT
# ============================================================================


@router.get("/coverage")
@limiter.limit("10/minute")
async def get_coverage_card(
    request: Request,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Get the FSMA 204 Regulatory Coverage Card.

    Provides real-time status of the regulatory authority, monitoring sources,
    and enforcement timelines.
    """
    return {
        "authority": "FDA FSMA 204 (21 CFR Part 1 Subpart S)",
        "sources_monitored": [
            "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods",
            "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S",
        ],
        "check_interval": "24 hours",
        "enforcement_status": "FDA not enforcing before July 20, 2028 (Congressional directive)",
        # No durable verification run backs this coverage card.
        "last_request_at": None,
        "verification_status": "not_verified",
        "compliance_deadline": "2028-07-20",
    }


# ============================================================================
# FDA SPREADSHEET EXPORT ENDPOINTS
# ============================================================================


@router.get("/export/fda-request")
@limiter.limit("10/minute")
async def export_fda_request_sheet(
    request: Request,
    # RE-SEC-003: constrain shape of strings that flow into Content-Disposition.
    start_date: str = Query(..., pattern=r"^[0-9T:.\-]{1,32}$", description="Start Date (YYYY-MM-DD or ISO)"),
    end_date: str = Query(..., pattern=r"^[0-9T:.\-]{1,32}$", description="End Date (YYYY-MM-DD or ISO)"),
    tlc: Optional[str] = Query(
        None,
        min_length=1,
        max_length=256,
        description="Traceability Lot Code. When set, only events for this exact lot are exported.",
    ),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Generate the official FDA Electronic Sortable Spreadsheet (24-hour request mode).

    This exports ALL CTEs (Critical Tracking Events) within the requested time range
    formatted exactly according to the FDA's Excel template columns:
    [Traceability Lot Code, Product, Quantity, Unit, Location, Date, Time, ...]

    Required by FSMA 204: 21 CFR 1.1455(c)(3) sets the 24 hour deadline after an
    FDA request, and 1.1455(c)(3)(ii) requires the electronic sortable spreadsheet.
    """
    logger.info("fda_request_export_initiated", start=start_date, end=end_date, has_tlc_filter=tlc is not None)

    # #2511: reconcile the two tenant sources (middleware vs authenticated
    # API key) and scope Neo4j to the authenticated principal — fail closed
    # (409 E_TENANT_MISMATCH) on divergence before any read.
    scoped_tenant_id = reconcile_tenant_scope(api_key, tenant_id, request_path=request.url.path)
    db_name = Neo4jClient.get_tenant_database_name(uuid.UUID(scoped_tenant_id))

    try:
        from ...fsma_utils import query_events_by_range

        # #2833: `async with` closes the driver — and its connection
        # pool — on every exit path. The explicit close that used to
        # sit inside the try was skipped whenever the query or the
        # serialization below it raised, leaking a driver (and pool)
        # per failed request behind the generic 500 handler.
        async with Neo4jClient(database=db_name) as client:
            events = await query_events_by_range(client, start_date, end_date, scoped_tenant_id, tlc=tlc)

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)

        # FDA Sortable Spreadsheet Columns (Simplified for CSV)
        writer.writerow(
            [
                "Traceability Lot Code",
                "Event Type (CTE)",
                "Product Description",
                "Quantity",
                "Unit of Measure",
                "Location Description",
                "Location Identifier (GLN)",
                "Date",
                "Time",
                "Reference Document Type",
                "Reference Document Number",
            ]
        )

        for event in events:
            # RE-SEC-002: every cell goes through csv_safe() to neutralize
            # Excel formula prefixes from tenant-stored values.
            # nosemgrep: python.django.security.injection.csv-writer-injection.csv-writer-injection -- cells are Neo4j-sourced and csv_safe()-wrapped; the only `request` reference (request.url.path at #2511 reconcile) feeds logging, never a CSV cell.
            writer.writerow(
                [
                    csv_safe(event.get("tlc", "")),
                    csv_safe(event.get("type", "")),
                    csv_safe(event.get("product_description", "")),
                    csv_safe(event.get("quantity", "")),
                    csv_safe(event.get("unit_of_measure", "")),
                    csv_safe(event.get("location_description", "")),
                    csv_safe(event.get("location_gln", "")),
                    csv_safe(event.get("event_date", "")),
                    csv_safe(event.get("event_time", "")),
                    csv_safe(event.get("reference_doc_type", "")),
                    csv_safe(event.get("reference_doc_num", "")),
                ]
            )

        csv_content = csv_buffer.getvalue()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = header_filename(f"fda_sortable_spreadsheet_{start_date}_{end_date}_{timestamp}.csv")

        logger.info("fda_request_export_completed", count=len(events))

        return StreamingResponse(
            io.BytesIO(b"\xef\xbb\xbf" + csv_content.encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.exception("fda_request_export_error", error=str(e))
        logger.exception("endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# GS1 EPCIS 2.0 EXPORT (Walmart/Kroger Automation)
# ============================================================================


@router.get("/export/epcis")
@limiter.limit("10/minute")
async def export_epcis(
    request: Request,
    # RE-SEC-003: constrain shape of strings that flow into Content-Disposition.
    start_date: str = Query(..., pattern=r"^[0-9T:.\-]{1,32}$", description="Start Date (YYYY-MM-DD)"),
    end_date: str = Query(..., pattern=r"^[0-9T:.\-]{1,32}$", description="End Date (YYYY-MM-DD)"),
    format: str = Query("json-ld", pattern="^(json-ld|xml)$", description="EPCIS format"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Export traceability data in GS1 EPCIS 2.0 format.

    This enables automated data exchange with major retailers (Walmart, Kroger)
    who mandate GS1 standards for supply chain visibility.

    Formats:
    - json-ld: EPCIS 2.0 JSON-LD (recommended)
    - xml: EPCIS 2.0 XML

    Event Types Mapped:
    - CREATION → epcis:ObjectEvent (bizStep: commissioning)
    - RECEIVING → epcis:ObjectEvent (bizStep: receiving)
    - SHIPPING → epcis:ObjectEvent (bizStep: shipping)
    - TRANSFORMATION → epcis:TransformationEvent
    """
    logger.info("epcis_export_initiated", start=start_date, end=end_date, format=format)

    # #2511: reconcile the two tenant sources (middleware vs authenticated
    # API key) and scope Neo4j to the authenticated principal — fail closed
    # (409 E_TENANT_MISMATCH) on divergence before any read.
    scoped_tenant_id = reconcile_tenant_scope(api_key, tenant_id, request_path=request.url.path)
    db_name = Neo4jClient.get_tenant_database_name(uuid.UUID(scoped_tenant_id))

    try:
        from ...fsma_utils import query_events_by_range

        # #2833: `async with` closes the driver — and its connection
        # pool — on every exit path. The explicit close that used to
        # sit inside the try was skipped whenever the query or the
        # serialization below it raised, leaking a driver (and pool)
        # per failed request behind the generic 500 handler.
        async with Neo4jClient(database=db_name) as client:
            events = await query_events_by_range(client, start_date, end_date, scoped_tenant_id)

        # Map CTE types to EPCIS bizStep
        BIZ_STEP_MAP = {
            "CREATION": "urn:epcglobal:cbv:bizstep:commissioning",
            "RECEIVING": "urn:epcglobal:cbv:bizstep:receiving",
            "SHIPPING": "urn:epcglobal:cbv:bizstep:shipping",
            "TRANSFORMATION": "urn:epcglobal:cbv:bizstep:transforming",
        }

        # Build EPCIS document
        epcis_events = []

        for event in events:
            event_type = event.get("type", "").upper()

            # Build EPC URN from TLC
            tlc = event.get("tlc", "")
            # Convert TLC to EPC URN format (simplified)
            epc_urn = f"urn:epc:id:sgtin:{tlc}" if tlc else None

            # Build location URN from GLN
            gln = event.get("location_gln", event.get("facility_gln", ""))
            read_point = f"urn:epc:id:sgln:{gln}" if gln else None

            if event_type == "TRANSFORMATION":
                # TransformationEvent for TRANSFORMATION CTEs
                epcis_event = {
                    "type": "TransformationEvent",
                    "eventTime": f"{event.get('event_date', '')}T{event.get('event_time', '00:00:00')}Z",
                    "eventTimeZoneOffset": "-08:00",
                    "inputEPCList": [f"urn:epc:id:sgtin:{event.get('input_tlc', '')}"]
                    if event.get("input_tlc")
                    else [],
                    "outputEPCList": [epc_urn] if epc_urn else [],
                    "transformationID": f"urn:epc:id:gdti:{event.get('event_id', '')}",
                    "bizStep": BIZ_STEP_MAP.get(event_type, ""),
                    "readPoint": {"id": read_point} if read_point else None,
                    "extension": {
                        "quantityList": [
                            {
                                "epcClass": epc_urn,
                                "quantity": event.get("quantity", 0),
                                "uom": event.get("unit_of_measure", event.get("unit", "EA")),
                            }
                        ]
                    },
                }
            else:
                # ObjectEvent for CREATION, RECEIVING, SHIPPING
                epcis_event = {
                    "type": "ObjectEvent",
                    "eventTime": f"{event.get('event_date', '')}T{event.get('event_time', '00:00:00')}Z",
                    "eventTimeZoneOffset": "-08:00",
                    "epcList": [epc_urn] if epc_urn else [],
                    "action": "ADD" if event_type in ["CREATION", "RECEIVING"] else "OBSERVE",
                    "bizStep": BIZ_STEP_MAP.get(event_type, ""),
                    "disposition": "urn:epcglobal:cbv:disp:in_transit"
                    if event_type == "SHIPPING"
                    else "urn:epcglobal:cbv:disp:in_progress",
                    "readPoint": {"id": read_point} if read_point else None,
                    "bizLocation": {"id": read_point} if read_point else None,
                    "extension": {
                        "quantityList": [
                            {
                                "epcClass": epc_urn,
                                "quantity": event.get("quantity", 0),
                                "uom": event.get("unit_of_measure", event.get("unit", "EA")),
                            }
                        ],
                        "sourceList": [
                            {
                                "type": "urn:epcglobal:cbv:sdt:possessing_party",
                                "source": f"urn:epc:id:sgln:{event.get('ship_from_gln', '')}",
                            }
                        ]
                        if event.get("ship_from_gln")
                        else [],
                        "destinationList": [
                            {
                                "type": "urn:epcglobal:cbv:sdt:possessing_party",
                                "destination": f"urn:epc:id:sgln:{event.get('ship_to_gln', '')}",
                            }
                        ]
                        if event.get("ship_to_gln")
                        else [],
                    },
                }

            epcis_events.append(epcis_event)

        # Build full EPCIS document
        epcis_document = {
            "@context": ["https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"],
            "type": "EPCISDocument",
            "schemaVersion": "2.0",
            "creationDate": datetime.now(timezone.utc).isoformat(),
            "epcisBody": {"eventList": epcis_events},
            "sender": {"type": "Organization", "name": "RegEngine FSMA 204 Platform"},
            "receiver": {"type": "Organization", "name": "FDA / Retailer"},
        }

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        if format == "xml":
            # Convert to XML format
            xml_content = _epcis_to_xml(epcis_document)
            filename = header_filename(f"epcis_export_{start_date}_{end_date}_{timestamp}.xml")

            logger.info("epcis_xml_export_completed", count=len(epcis_events))

            return StreamingResponse(
                io.BytesIO(xml_content.encode("utf-8")),
                media_type="application/xml",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        else:
            # JSON-LD format (default)
            import json

            json_content = json.dumps(epcis_document, indent=2)
            filename = header_filename(f"epcis_export_{start_date}_{end_date}_{timestamp}.jsonld")

            logger.info("epcis_jsonld_export_completed", count=len(epcis_events))

            return StreamingResponse(
                io.BytesIO(json_content.encode("utf-8")),
                media_type="application/ld+json",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )

    except Exception as e:
        logger.exception("epcis_export_error", error=str(e))
        logger.exception("endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


def _epcis_to_xml(epcis_doc: dict) -> str:
    """Convert EPCIS JSON-LD to XML format.

    RE-SEC-001: every interpolated value is wrapped in :func:`xml_escape` so
    tenant-controlled strings (TLC, GLN, free-text fields) cannot break out
    of element/attribute context and inject sibling elements into the
    EPCIS document FDA / Walmart / Kroger consume.

    TODO(RE-SEC-001): migrate this builder to ``xml.etree.ElementTree``
    elements + ``ElementTree.tostring`` so escaping is structural rather
    than per-call. Tracked as a follow-up; the wrapping below is the
    minimum viable fix that ships in the same PR as the helper module.
    """
    events_xml = []
    for event in epcis_doc.get("epcisBody", {}).get("eventList", []):
        event_type = event.get("type", "ObjectEvent")
        if event_type == "ObjectEvent":
            events_xml.append(f"""
    <ObjectEvent>
      <eventTime>{xml_escape(event.get("eventTime", ""))}</eventTime>
      <eventTimeZoneOffset>{xml_escape(event.get("eventTimeZoneOffset", "-08:00"))}</eventTimeZoneOffset>
      <epcList>
        {"".join(f"<epc>{xml_escape(epc)}</epc>" for epc in event.get("epcList", []))}
      </epcList>
      <action>{xml_escape(event.get("action", "OBSERVE"))}</action>
      <bizStep>{xml_escape(event.get("bizStep", ""))}</bizStep>
      <disposition>{xml_escape(event.get("disposition", ""))}</disposition>
      <readPoint><id>{xml_escape((event.get("readPoint") or {}).get("id", ""))}</id></readPoint>
    </ObjectEvent>""")
        elif event_type == "TransformationEvent":
            events_xml.append(f"""
    <TransformationEvent>
      <eventTime>{xml_escape(event.get("eventTime", ""))}</eventTime>
      <eventTimeZoneOffset>{xml_escape(event.get("eventTimeZoneOffset", "-08:00"))}</eventTimeZoneOffset>
      <inputEPCList>
        {"".join(f"<epc>{xml_escape(epc)}</epc>" for epc in event.get("inputEPCList", []))}
      </inputEPCList>
      <outputEPCList>
        {"".join(f"<epc>{xml_escape(epc)}</epc>" for epc in event.get("outputEPCList", []))}
      </outputEPCList>
      <bizStep>{xml_escape(event.get("bizStep", ""))}</bizStep>
    </TransformationEvent>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<epcis:EPCISDocument
  xmlns:epcis="urn:epcglobal:epcis:xsd:2"
  xmlns:cbv="urn:epcglobal:cbv:xsd"
  schemaVersion="2.0"
  creationDate="{xml_escape(epcis_doc.get("creationDate", ""))}">
  <EPCISBody>
    <EventList>
      {"".join(events_xml)}
    </EventList>
  </EPCISBody>
</epcis:EPCISDocument>"""


@router.get("/export/trace/{tlc}")
@limiter.limit("10/minute")
async def export_trace_csv(
    request: Request,
    # RE-SEC-003: constrain TLC charset to GS1-safe alnum/dot/dash/underscore.
    tlc: str = PathParam(..., pattern=r"^[A-Za-z0-9._\-]{1,64}$"),
    direction: str = Query("forward", pattern="^(forward|backward)$"),
    max_depth: int = Query(10, ge=1, le=20),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Export traceability data as an FDA-oriented CSV spreadsheet.

    The CSV format is designed for submission to FDA during recall events
    and follows the sortable spreadsheet format described in FSMA 204.

    Columns:
    - TLC (Traceability Lot Code)
    - Product Description
    - Quantity
    - Unit of Measure
    - Event Type (CTE)
    - Event Date
    - Event Time
    - Facility Name
    - Facility GLN
    - Facility Address
    """
    # #2511: reconcile the two tenant sources (middleware vs authenticated
    # API key) and scope Neo4j to the authenticated principal — fail closed
    # (409 E_TENANT_MISMATCH) on divergence before any read.
    scoped_tenant_id = reconcile_tenant_scope(api_key, tenant_id, request_path=request.url.path)
    db_name = Neo4jClient.get_tenant_database_name(uuid.UUID(scoped_tenant_id))

    try:
        # #2833: `async with` closes the driver — and its connection
        # pool — on every exit path. The explicit close that used to
        # sit inside the try was skipped whenever the query or the
        # serialization below it raised, leaking a driver (and pool)
        # per failed request behind the generic 500 handler.
        async with Neo4jClient(database=db_name) as client:
            if direction == "forward":
                result = await trace_forward(client, tlc, max_depth, scoped_tenant_id)
            else:
                result = await trace_backward(client, tlc, max_depth, scoped_tenant_id)

        # Generate CSV content. #2945: rows come from the shared builder,
        # which emits one row per observed lot<->event<->facility association
        # (``result.trace_rows``) and leaves unknown cells blank — the old
        # inline loop here paired every lot with every event and stamped the
        # first GLN-bearing facility on all of them, fabricating associations
        # on an FDA submission artifact. Cells are csv_safe()d (RE-SEC-002)
        # inside the builder.
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(TRACE_CSV_HEADER)
        data_rows = build_trace_csv_rows(result, tlc)
        # nosemgrep: python.django.security.injection.csv-writer-injection.csv-writer-injection -- every cell is csv_safe()-wrapped in build_trace_csv_rows; the only `request` reference (request.url.path at #2511 reconcile) feeds logging, never a CSV cell.
        writer.writerows(data_rows)

        csv_content = csv_buffer.getvalue()

        # Generate filename — RE-SEC-003: encode for Content-Disposition.
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = header_filename(f"fsma_trace_{direction}_{tlc}_{timestamp}.csv")

        # #2945: report the number of rows actually written, not an estimate.
        logger.info(
            "csv_export_generated",
            tlc=tlc,
            direction=direction,
            rows=len(data_rows),
        )

        return StreamingResponse(
            io.BytesIO(b"\xef\xbb\xbf" + csv_content.encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.exception("csv_export_error", tlc=tlc, error=str(e))
        logger.exception("endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/export/recall-contacts/{tlc}")
@limiter.limit("10/minute")
async def export_recall_contacts(
    request: Request,
    # RE-SEC-003: constrain TLC charset.
    tlc: str = PathParam(..., pattern=r"^[A-Za-z0-9._\-]{1,64}$"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Generate Recall Contact List CSV for FDA notification.

    Lists all downstream facilities that took custody of the lot, suitable
    for direct notification during a recall event. One row per receiving
    event the graph records (facility, lot, date received, quantity and
    unit); a facility reached without a receiving event on record is listed
    with those cells blank. Contact Status is blank on every row: the
    system records no notification outcomes, so the column is the recall
    coordinator's to fill in. See ``exporters.recall_contacts_csv``.
    """
    # #2511: reconcile the two tenant sources (middleware vs authenticated
    # API key) and scope Neo4j to the authenticated principal — fail closed
    # (409 E_TENANT_MISMATCH) on divergence before any read.
    scoped_tenant_id = reconcile_tenant_scope(api_key, tenant_id, request_path=request.url.path)
    db_name = Neo4jClient.get_tenant_database_name(uuid.UUID(scoped_tenant_id))

    try:
        # #2833: `async with` closes the driver — and its connection
        # pool — on every exit path. The explicit close that used to
        # sit inside the try was skipped whenever the query or the
        # serialization below it raised, leaking a driver (and pool)
        # per failed request behind the generic 500 handler.
        async with Neo4jClient(database=db_name) as client:
            result = await trace_forward(client, tlc, 10, scoped_tenant_id)

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(RECALL_CONTACTS_HEADER)
        # RE-SEC-002: every cell is csv_safe()-wrapped inside the builder.
        data_rows = build_recall_contacts_rows(result)
        # nosemgrep: python.django.security.injection.csv-writer-injection.csv-writer-injection -- every cell is csv_safe()-wrapped in build_recall_contacts_rows; the only `request` reference (request.url.path at #2511 reconcile) feeds logging, never a CSV cell.
        writer.writerows(data_rows)

        csv_content = csv_buffer.getvalue()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = header_filename(f"recall_contacts_{tlc}_{timestamp}.csv")

        logger.info(
            "recall_contacts_export",
            tlc=tlc,
            facility_count=len(result.facilities),
            rows=len(data_rows),
        )

        return StreamingResponse(
            io.BytesIO(b"\xef\xbb\xbf" + csv_content.encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.exception("recall_contacts_error", tlc=tlc, error=str(e))
        logger.exception("endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# GAP ANALYSIS ENDPOINTS
# ============================================================================


@router.get("/gaps")
@limiter.limit("10/minute")
async def get_compliance_gaps(
    request: Request,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Find TraceEvents with missing required Key Data Elements (KDEs).

    Returns events that are missing critical FSMA 204 required fields,
    enabling compliance officers to prioritize data collection.
    """
    # #2511: scope Neo4j to the authenticated API-key tenant; fail closed
    # on any divergence from the middleware-resolved tenant.
    scoped_tenant_id = reconcile_tenant_scope(api_key, tenant_id, request_path=request.url.path)
    db_name = Neo4jClient.get_tenant_database_name(uuid.UUID(scoped_tenant_id))

    try:
        # #2833: `async with` closes the driver — and its connection
        # pool — on every exit path. The explicit close that used to
        # sit inside the try was skipped whenever the query or the
        # serialization below it raised, leaking a driver (and pool)
        # per failed request behind the generic 500 handler.
        async with Neo4jClient(database=db_name) as client:
            gaps = await find_gaps(client, scoped_tenant_id)

        return {
            "total_gaps": len(gaps),
            "events_with_gaps": gaps,
            "summary": {
                "missing_date": len([g for g in gaps if "missing_date" in g.get("gaps", [])]),
                "missing_lot": len([g for g in gaps if "missing_lot" in g.get("gaps", [])]),
            },
        }
    except Exception as e:
        logger.exception("gap_analysis_error", error=str(e))
        logger.exception("endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/gaps/orphans")
@limiter.limit("10/minute")
async def get_orphaned_lots(
    request: Request,
    days_stagnant: int = Query(30, ge=1, le=365, description="Days without outbound activity"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Find 'orphan' lots that have been created/received but never shipped or consumed.

    These represent potential inventory issues or broken traceability chains:
    - Product received but never used or distributed
    - Transformation outputs that were never shipped
    - Data entry errors where outbound events were not recorded

    FSMA 204 requires complete chain of custody - orphan lots may indicate
    compliance gaps requiring remediation.
    """
    # #2511: scope Neo4j to the authenticated API-key tenant; fail closed
    # on any divergence from the middleware-resolved tenant.
    scoped_tenant_id = reconcile_tenant_scope(api_key, tenant_id, request_path=request.url.path)
    db_name = Neo4jClient.get_tenant_database_name(uuid.UUID(scoped_tenant_id))

    try:
        # #2833: `async with` closes the driver — and its connection
        # pool — on every exit path. The explicit close that used to
        # sit inside the try was skipped whenever the query or the
        # serialization below it raised, leaking a driver (and pool)
        # per failed request behind the generic 500 handler.
        async with Neo4jClient(database=db_name) as client:
            orphans = await find_orphaned_lots(client, scoped_tenant_id, days_stagnant)

        return {
            "total_orphans": len(orphans),
            "threshold_days": days_stagnant,
            "orphans": [
                {
                    "tlc": o.tlc,
                    "product_description": o.product_description,
                    "quantity": o.quantity,
                    "unit_of_measure": o.unit_of_measure,
                    "created_at": o.created_at,
                    "stagnant_days": o.stagnant_days,
                    "last_event_type": o.last_event_type,
                    "last_event_date": o.last_event_date,
                }
                for o in orphans
            ],
            "summary": {
                "avg_stagnant_days": (round(sum(o.stagnant_days for o in orphans) / len(orphans), 1) if orphans else 0),
                "total_quantity_at_risk": sum(o.quantity or 0 for o in orphans),
            },
        }
    except Exception as e:
        logger.exception("orphan_detection_error", error=str(e))
        logger.exception("endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/export/gaps")
@limiter.limit("10/minute")
async def export_gaps_csv(
    request: Request,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Export compliance gaps as CSV for review and remediation tracking.
    """
    # #2511: scope Neo4j to the authenticated API-key tenant; fail closed
    # on any divergence from the middleware-resolved tenant.
    scoped_tenant_id = reconcile_tenant_scope(api_key, tenant_id, request_path=request.url.path)
    db_name = Neo4jClient.get_tenant_database_name(uuid.UUID(scoped_tenant_id))

    try:
        # #2833: `async with` closes the driver — and its connection
        # pool — on every exit path. The explicit close that used to
        # sit inside the try was skipped whenever the query or the
        # serialization below it raised, leaking a driver (and pool)
        # per failed request behind the generic 500 handler.
        async with Neo4jClient(database=db_name) as client:
            gaps = await find_gaps(client, scoped_tenant_id)

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)

        writer.writerow(
            [
                "Event ID",
                "Event Type",
                "Event Date",
                "Document ID",
                "Missing Fields",
                "Remediation Status",
            ]
        )

        for gap in gaps:
            # RE-SEC-002: csv_safe() on tenant-stored cells.
            # nosemgrep: python.django.security.injection.csv-writer-injection.csv-writer-injection -- cells are Neo4j-sourced and csv_safe()-wrapped; the only `request` reference (request.url.path at #2511 reconcile) feeds logging, never a CSV cell.
            writer.writerow(
                [
                    csv_safe(gap.get("event_id", "")),
                    csv_safe(gap.get("type", "")),
                    csv_safe(gap.get("event_date", "")),
                    csv_safe(gap.get("document_id", "")),
                    csv_safe(", ".join(gap.get("gaps", []))),
                    "OPEN",  # Default status
                ]
            )

        csv_content = csv_buffer.getvalue()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = header_filename(f"fsma_compliance_gaps_{timestamp}.csv")

        return StreamingResponse(
            io.BytesIO(b"\xef\xbb\xbf" + csv_content.encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.exception("gaps_export_error", error=str(e))
        logger.exception("endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# TRACEABILITY PLAN BUILDER ENDPOINTS
# ============================================================================


class CommodityRequest(BaseModel):
    name: str
    category: str
    cte_types: List[str] = []
    tlc_assignment_method: str = ""


class RecordLocationRequest(BaseModel):
    location_type: str  # "electronic", "paper", "hybrid"
    system_name: Optional[str] = None
    physical_address: Optional[str] = None
    backup_procedure: str = ""
    retention_period: str = "2_years"


class TraceabilityPlanRequest(BaseModel):
    firm_name: str
    firm_address: str
    firm_type: str  # grower, manufacturer, processor, etc.
    gln: Optional[str] = None
    fda_registration: Optional[str] = None
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    commodities: List[CommodityRequest] = []
    record_locations: List[RecordLocationRequest] = []
    tlc_format: str = ""


@router.post("/plan/generate")
@limiter.limit("10/minute")
def generate_traceability_plan(
    request: Request,
    payload: TraceabilityPlanRequest,
    format: str = Query("json", pattern="^(json|markdown)$"),
    api_key=Depends(require_api_key),
):
    """
    Generate an FSMA 204 Traceability Plan.

    Creates a complete traceability plan document with:
    - Receiving procedures
    - Shipping procedures
    - Transformation procedures
    - TLC assignment procedures
    - 24-hour recall response procedures
    - Training requirements

    Returns plan in JSON or Markdown format.
    """
    try:
        firm_type = FirmType(payload.firm_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid firm_type: {payload.firm_type}. "
            f"Valid types: grower, manufacturer, processor, packer, "
            f"holder, distributor, retailer, restaurant",
        )

    # Build firm info
    firm = FirmInfo(
        name=payload.firm_name,
        address=payload.firm_address,
        firm_type=firm_type,
        gln=payload.gln,
        fda_registration=payload.fda_registration,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
    )

    # Build plan
    builder = TraceabilityPlanBuilder(firm)

    # Add commodities
    for comm in payload.commodities:
        builder.add_commodity(
            FTLCommodity(
                name=comm.name,
                category=comm.category,
                cte_types=comm.cte_types,
                tlc_assignment_method=comm.tlc_assignment_method,
            )
        )

    # Add record locations
    for loc in payload.record_locations:
        try:
            retention = RecordRetentionPeriod(loc.retention_period)
        except ValueError:
            retention = RecordRetentionPeriod.TWO_YEARS

        builder.add_record_location(
            RecordLocation(
                location_type=loc.location_type,
                system_name=loc.system_name,
                physical_address=loc.physical_address,
                backup_procedure=loc.backup_procedure,
                retention_period=retention,
            )
        )

    # Set TLC format
    if payload.tlc_format:
        builder.set_tlc_format(payload.tlc_format)

    plan = builder.build()

    logger.info(
        "traceability_plan_generated",
        plan_id=plan.plan_id,
        firm=payload.firm_name,
        format=format,
    )

    if format == "markdown":
        content = export_plan_markdown(plan)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/markdown",
            headers={
                # RE-SEC-003: plan_id is server-generated (uuid), but route
                # filename through header_filename anyway — defense in depth.
                "Content-Disposition": (
                    "attachment; filename=" + header_filename(f"traceability_plan_{plan.plan_id[:8]}.md")
                )
            },
        )
    else:
        return export_plan_json(plan)


@router.get("/plan/template")
def get_plan_template(
    firm_type: str = Query("manufacturer", description="Type of firm"),
    api_key=Depends(require_api_key),
):
    """
    Get a sample Traceability Plan request body.
    """
    return {
        "firm_name": "Example Corp",
        "firm_address": "123 Food Safety Way",
        "firm_type": firm_type,
        "contact_name": "Jane Doe",
        "commodities": [
            {
                "name": "Fresh Spinach",
                "category": "Leafy Greens",
                "cte_types": ["growing", "harvesting", "packing"],
            }
        ],
        "record_locations": [{"location_type": "electronic", "system_name": "NetSuite"}],
    }


# ============================================================================
# Phase 29 — Compliance Score Endpoint
# ============================================================================


class ComplianceScoreResponse(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "overall_score": 87.5,
                "obligation_coverage": 92.0,
                "control_effectiveness": 85.0,
                "evidence_freshness": 88.0,
                "total_obligations": 28,
                "controls_mapped": 24,
                "evidence_items": 156,
                "is_demo": False,
                "generated_at": "2026-04-12T14:30:00Z",
            }
        }
    }

    tenant_id: str
    overall_score: Optional[float]
    obligation_coverage: Optional[float]
    control_effectiveness: Optional[float]
    evidence_freshness: Optional[float]
    total_obligations: int
    controls_mapped: int
    evidence_items: int
    is_demo: bool = False
    generated_at: str


@router.get("/score", response_model=ComplianceScoreResponse)
@limiter.limit("10/minute")
async def get_compliance_score(
    request: Request,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """Return a tenant-scoped compliance score for the FSMA pilot dashboard.

    Queries the Neo4j graph for Obligation → Control → Evidence chains and
    computes four dimensions:

    - **obligation_coverage**: % of obligations that have ≥1 mapped control
    - **control_effectiveness**: average effectiveness_score of mapped controls
    - **evidence_freshness**: % of evidence items created within the last 90 days
    - **overall_score**: geometric mean of the three above

    Returns unmeasured dimensions for an empty graph; database failures return 503.
    """
    generated_at = datetime.now(timezone.utc).isoformat()
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)

    # Scope to the tenant database like every other endpoint in this module.
    # On Community Neo4j the client pins to the global database either way,
    # so this is a no-op there; on Enterprise it keeps the score query on
    # the same per-tenant database as the rest of the FSMA surface.
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)

    try:
        async with Neo4jClient(database=db_name) as client:
            async with client.session() as session:
                # #1273 — every OPTIONAL MATCH must repeat the tenant filter.
                # The Obligation anchor was scoped, but Control and Evidence
                # were not, so a Control belonging to tenant B reached via a
                # cross-tenant REQUIRES edge (ingestion bug, mistakenly
                # shared global control, etc.) was being counted into
                # tenant A's score AND its `controls_mapped`/`evidence_items`
                # response fields. That's both a numeric correctness bug
                # (dashboard reflects another tenant's controls) and an
                # info-disclosure leak.
                result = await session.run(
                    """
                    MATCH (o:Obligation {tenant_id: $tenant_id})
                    OPTIONAL MATCH (o)-[:REQUIRES]->(c:Control)
                        WHERE c.tenant_id = $tenant_id
                    OPTIONAL MATCH (c)-[:PROVEN_BY]->(e:Evidence)
                        WHERE e.tenant_id = $tenant_id
                    WITH
                        count(DISTINCT o)  AS total_obligations,
                        count(DISTINCT c)  AS controls_mapped,
                        count(DISTINCT e)  AS evidence_items,
                        avg(c.effectiveness_score) AS avg_effectiveness,
                        // Obligations with at least one mapped control.
                        // count(DISTINCT c) would score 200% when each
                        // obligation has two controls; coverage is about
                        // obligations, so count those distinctly.
                        count(DISTINCT CASE WHEN c IS NOT NULL THEN o END)
                            AS covered_obligations,
                        // Distinct fresh evidence NODES, not join rows: one
                        // evidence proving two controls is one row in
                        // evidence_items but two rows here under SUM.
                        count(DISTINCT CASE
                            WHEN e.timestamp > datetime() - duration('P90D') THEN e
                        END)
                            AS fresh_evidence
                    RETURN
                        total_obligations,
                        controls_mapped,
                        evidence_items,
                        avg_effectiveness,
                        covered_obligations,
                        fresh_evidence
                    """,
                    tenant_id=str(tenant_id),
                )
                row = await result.single()

        total_obligations = row["total_obligations"] if row else 0
        controls_mapped = row["controls_mapped"] if row else 0
        evidence_items = row["evidence_items"] if row else 0
        avg_eff = row["avg_effectiveness"] if row and row["avg_effectiveness"] else 0.0
        covered_obligations = row["covered_obligations"] if row else 0
        fresh_evidence = row["fresh_evidence"] if row else 0

        if total_obligations == 0:
            return ComplianceScoreResponse(
                tenant_id=str(tenant_id),
                overall_score=None,
                obligation_coverage=None,
                control_effectiveness=None,
                evidence_freshness=None,
                total_obligations=0,
                controls_mapped=0,
                evidence_items=0,
                is_demo=False,
                generated_at=generated_at,
            )

        obligation_coverage = (covered_obligations / total_obligations * 100) if total_obligations else 0.0
        control_effectiveness = avg_eff * 100
        evidence_freshness = (fresh_evidence / evidence_items * 100) if evidence_items else 0.0

        # Geometric mean of the three dimensions (each 0-100)
        import math

        dims = [max(0.01, obligation_coverage), max(0.01, control_effectiveness), max(0.01, evidence_freshness)]
        overall = round(math.pow(dims[0] * dims[1] * dims[2], 1 / 3), 1)

        return ComplianceScoreResponse(
            tenant_id=str(tenant_id),
            overall_score=overall,
            obligation_coverage=round(obligation_coverage, 1),
            control_effectiveness=round(control_effectiveness, 1),
            evidence_freshness=round(evidence_freshness, 1),
            total_obligations=total_obligations,
            controls_mapped=controls_mapped,
            evidence_items=evidence_items,
            is_demo=False,
            generated_at=generated_at,
        )

    except Exception as exc:
        logger.error("compliance_score_failed", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Compliance measurements are unavailable") from None
