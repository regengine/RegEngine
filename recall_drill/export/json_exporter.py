"""JSON export for drill reports and traceability data.

Supports two output modes:
  1. Standard RegEngine JSON — the default drill-report format.
  2. EPCIS 2.0 compatible JSON-LD — for FDA interoperability.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# EPCIS 2.0 mapping helpers
# ---------------------------------------------------------------------------

_CTE_TO_EPCIS_TYPE: dict[str, str] = {
    "harvesting": "ObjectEvent",
    "cooling": "ObjectEvent",
    "packing": "AggregationEvent",
    "shipping": "ObjectEvent",
    "receiving": "ObjectEvent",
    "transformation": "TransformationEvent",
    "creating": "ObjectEvent",
}

_CTE_TO_BIZ_STEP: dict[str, str] = {
    "harvesting": "urn:epcglobal:cbv:bizstep:harvesting",
    "cooling": "urn:epcglobal:cbv:bizstep:storing",
    "packing": "urn:epcglobal:cbv:bizstep:packing",
    "shipping": "urn:epcglobal:cbv:bizstep:shipping",
    "receiving": "urn:epcglobal:cbv:bizstep:receiving",
    "transformation": "urn:epcglobal:cbv:bizstep:transforming",
    "creating": "urn:epcglobal:cbv:bizstep:commissioning",
}


def _gln_to_sgln(gln: str) -> str:
    """Convert a raw GLN to an SGLN URN."""
    if gln and not gln.startswith("urn:"):
        return f"urn:epc:id:sgln:{gln}.0"
    return gln or ""


def _record_to_epcis_event(record: dict) -> dict:
    """Map a single CTE record to an EPCIS 2.0 event structure."""
    cte_type = record.get("event_type", "")
    event_type = _CTE_TO_EPCIS_TYPE.get(cte_type, "ObjectEvent")
    biz_step = _CTE_TO_BIZ_STEP.get(cte_type, "")

    event_date = record.get("event_date", "")
    event_time = record.get("event_time", "00:00:00")
    if event_date:
        event_time_str = f"{event_date}T{event_time}Z"
    else:
        event_time_str = ""

    tlc = record.get("traceability_lot_code", "")

    event: dict[str, Any] = {
        "type": event_type,
        "eventID": f"urn:uuid:{uuid.uuid4()}",
        "eventTime": event_time_str,
        "eventTimeZoneOffset": "+00:00",
        "bizStep": biz_step,
        "readPoint": {"id": _gln_to_sgln(record.get("origin_gln", ""))},
        "bizLocation": {"id": _gln_to_sgln(record.get("destination_gln", ""))},
    }

    # EPC list
    epc_urn = f"urn:epc:id:sgtin:{tlc}" if tlc else ""
    if event_type == "TransformationEvent":
        event["inputEPCList"] = [epc_urn] if epc_urn else []
        event["outputEPCList"] = []
    elif event_type == "AggregationEvent":
        event["childEPCs"] = [epc_urn] if epc_urn else []
        event["action"] = "ADD"
    else:
        event["epcList"] = [epc_urn] if epc_urn else []
        event["action"] = "OBSERVE"

    # Quantity list
    event["quantityList"] = [
        {
            "epcClass": epc_urn,
            "quantity": record.get("quantity", 0),
            "uom": record.get("unit_of_measure", ""),
        }
    ]

    # FSMA 204 extension KDEs
    event["fsma204"] = {
        "productDescription": record.get("product_description", ""),
        "traceabilityLotCode": tlc,
        "immeditatePreviousSource": record.get("immediate_previous_source", ""),
        "tlcSourceGLN": record.get("tlc_source_gln", ""),
        "tlcSourceFDARegistration": record.get("tlc_source_fda_reg", ""),
        "referenceDocumentType": record.get("reference_document_type", ""),
        "referenceDocumentNumber": record.get("reference_document_number", ""),
    }

    # Optional fields
    for optional_key in ("temperature", "carrier"):
        val = record.get(optional_key)
        if val:
            event["fsma204"][optional_key] = val

    return event


def records_to_epcis_document(records: list[dict]) -> dict:
    """Convert a list of CTE records to an EPCIS 2.0 JSON-LD document."""
    events = [_record_to_epcis_event(r) for r in records]

    return {
        "@context": [
            "https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld",
        ],
        "type": "EPCISDocument",
        "schemaVersion": "2.0",
        "creationDate": datetime.now(timezone.utc).isoformat(),
        "epcisBody": {
            "eventList": events,
        },
        "fsma204Extension": {
            "generatedBy": "RegEngine Recall Drill System",
            "totalEvents": len(events),
            "traceabilityLotCodes": sorted(
                {r.get("traceability_lot_code", "") for r in records} - {""}
            ),
        },
    }


class JSONExporter:
    """Export drill reports and traceability data as structured JSON.

    Supports both standard RegEngine format and EPCIS 2.0 JSON-LD.
    """

    def export_string(self, data: Any) -> str:
        """Serialize *data* to a formatted JSON string."""
        return json.dumps(data, indent=2, default=str, ensure_ascii=False)

    def export_file(self, data: Any, path: str | Path) -> str:
        """Write *data* as JSON to *path*, creating directories as needed."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.export_string(data)
        path.write_text(content, encoding="utf-8")
        return str(path)

    def export_epcis(self, records: list[dict]) -> str:
        """Export CTE records as an EPCIS 2.0 JSON-LD string."""
        doc = records_to_epcis_document(records)
        return self.export_string(doc)

    def export_epcis_file(self, records: list[dict], path: str | Path) -> str:
        """Export CTE records as an EPCIS 2.0 JSON-LD file."""
        doc = records_to_epcis_document(records)
        return self.export_file(doc, path)
