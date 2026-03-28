"""
Canonical TraceabilityEvent Model.

This is the ONE internal truth model for all FSMA 204 compliance operations.
Every ingestion path (webhook API, CSV upload, XLSX import, EPCIS document,
EDI message) normalizes into this model before persistence.

Downstream services — rules engine, FDA export, graph sync, exception queue,
request-response workflow — consume ONLY this model.

Design principles:
    1. Raw source preserved alongside normalized form (dual payload)
    2. Provenance metadata tracks who/when/how/what-version
    3. Amendment chains are explicit (supersedes_event_id)
    4. Schema is versioned for forward compatibility
    5. KDEs are structured dicts, not key-value pairs

Usage:
    from shared.canonical_event import TraceabilityEvent, normalize_webhook_event

    canonical = normalize_webhook_event(webhook_event, tenant_id, source="webhook_api")
    # canonical is now a TraceabilityEvent ready for persistence
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CTEType(str, Enum):
    """Critical Tracking Event types per FSMA 204 §1.1310."""
    HARVESTING = "harvesting"
    COOLING = "cooling"
    INITIAL_PACKING = "initial_packing"
    FIRST_LAND_BASED_RECEIVING = "first_land_based_receiving"
    SHIPPING = "shipping"
    RECEIVING = "receiving"
    TRANSFORMATION = "transformation"


class EventStatus(str, Enum):
    """Lifecycle status of a canonical event."""
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    DRAFT = "draft"


class IngestionSource(str, Enum):
    """Known ingestion source systems."""
    WEBHOOK_API = "webhook_api"
    CSV_UPLOAD = "csv_upload"
    XLSX_UPLOAD = "xlsx_upload"
    EPCIS_API = "epcis_api"
    EPCIS_XML = "epcis_xml"
    EDI = "edi"
    MANUAL = "manual"
    MOBILE_CAPTURE = "mobile_capture"
    SUPPLIER_PORTAL = "supplier_portal"
    LEGACY_V002 = "legacy_v002"


class IngestionRunStatus(str, Enum):
    """Processing state of an ingestion batch."""
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class EvidenceDocumentType(str, Enum):
    """Types of evidence documents."""
    BOL = "bol"
    INVOICE = "invoice"
    LAB_REPORT = "lab_report"
    PHOTO = "photo"
    TEMPERATURE_LOG = "temperature_log"
    PRODUCTION_RECORD = "production_record"
    PURCHASE_ORDER = "purchase_order"
    CERTIFICATE = "certificate"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Provenance Metadata
# ---------------------------------------------------------------------------

class ProvenanceMetadata(BaseModel):
    """
    Structured provenance for a canonical event.

    Answers: Where did this record come from? How was it normalized?
    What confidence do we have in the mapping?
    """
    source_file_hash: Optional[str] = None
    source_file_name: Optional[str] = None
    ingestion_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    mapper_name: str = "unknown"
    mapper_version: str = "1.0.0"
    normalization_rules_applied: List[str] = Field(default_factory=list)
    original_format: str = "unknown"  # json, csv, xlsx, epcis_xml, epcis_json, edi
    extraction_confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)


# ---------------------------------------------------------------------------
# Ingestion Run
# ---------------------------------------------------------------------------

class IngestionRun(BaseModel):
    """Batch provenance — one row per file upload, API call, or EPCIS document."""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID

    source_system: IngestionSource
    source_file_name: Optional[str] = None
    source_file_hash: Optional[str] = None
    source_file_size: Optional[int] = None

    record_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0

    mapper_version: str = "1.0.0"
    schema_version: str = "1.0.0"
    status: IngestionRunStatus = IngestionRunStatus.PROCESSING

    initiated_by: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    errors: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Canonical TraceabilityEvent
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0.0"


class TraceabilityEvent(BaseModel):
    """
    The canonical traceability event — RegEngine's single internal truth model.

    Every ingestion path normalizes into this object. Downstream services
    consume ONLY this model, never format-specific payloads.

    Implements PRD Workstream A requirements:
    - Dual payload preservation (raw_payload + normalized_payload)
    - Structured provenance metadata
    - Amendment chain via supersedes_event_id
    - Schema versioning
    - Confidence scoring
    """

    # Identity
    event_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID

    # Source provenance
    source_system: IngestionSource
    source_record_id: Optional[str] = None
    source_file_id: Optional[UUID] = None
    ingestion_run_id: Optional[UUID] = None

    # Event classification
    event_type: CTEType

    # Temporal
    event_timestamp: datetime
    event_timezone: str = "UTC"

    # Product + Lot
    product_reference: Optional[str] = None
    lot_reference: Optional[str] = None
    traceability_lot_code: str = Field(..., min_length=3)
    quantity: float = Field(..., gt=0)
    unit_of_measure: str

    # Entity + Facility references
    from_entity_reference: Optional[str] = None
    to_entity_reference: Optional[str] = None
    from_facility_reference: Optional[str] = None
    to_facility_reference: Optional[str] = None

    # Transport
    transport_reference: Optional[str] = None

    # Structured KDEs
    kdes: Dict[str, Any] = Field(default_factory=dict)

    # Dual payload preservation
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    normalized_payload: Dict[str, Any] = Field(default_factory=dict)

    # Provenance
    provenance_metadata: ProvenanceMetadata = Field(
        default_factory=lambda: ProvenanceMetadata()
    )

    # Quality
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    status: EventStatus = EventStatus.ACTIVE

    # Amendment chain
    supersedes_event_id: Optional[UUID] = None

    # Schema version
    schema_version: str = SCHEMA_VERSION

    # Integrity (computed during persistence)
    sha256_hash: Optional[str] = None
    chain_hash: Optional[str] = None
    idempotency_key: Optional[str] = None

    # EPCIS interop
    epcis_event_type: Optional[str] = None
    epcis_action: Optional[str] = None
    epcis_biz_step: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    amended_at: Optional[datetime] = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True}

    @field_validator("event_timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> datetime:
        """Parse any reasonable timestamp format to datetime."""
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v
        if isinstance(v, str):
            # Handle Z suffix
            v = v.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(v)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                import dateutil.parser
                dt = dateutil.parser.parse(v, fuzzy=False)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
        raise ValueError(f"Cannot parse timestamp: {v}")

    def compute_sha256_hash(self) -> str:
        """Compute SHA-256 of canonical form for integrity verification."""
        canonical = "|".join([
            str(self.event_id),
            self.event_type.value,
            self.traceability_lot_code,
            self.product_reference or "",
            str(self.quantity),
            self.unit_of_measure,
            self.from_facility_reference or "",
            self.to_facility_reference or "",
            self.event_timestamp.isoformat(),
            json.dumps(self.kdes, sort_keys=True, default=str),
        ])
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def compute_idempotency_key(self) -> str:
        """Compute deduplication key from content-addressable fields."""
        canonical = json.dumps(
            {
                "event_type": self.event_type.value,
                "tlc": self.traceability_lot_code,
                "timestamp": self.event_timestamp.isoformat(),
                "source": self.source_system.value,
                "from_facility": self.from_facility_reference or "",
                "to_facility": self.to_facility_reference or "",
                "kdes": self.kdes,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def build_normalized_payload(self) -> Dict[str, Any]:
        """Build the normalized payload dict for storage."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type.value,
            "traceability_lot_code": self.traceability_lot_code,
            "product_reference": self.product_reference,
            "lot_reference": self.lot_reference,
            "quantity": self.quantity,
            "unit_of_measure": self.unit_of_measure,
            "event_timestamp": self.event_timestamp.isoformat(),
            "event_timezone": self.event_timezone,
            "from_entity_reference": self.from_entity_reference,
            "to_entity_reference": self.to_entity_reference,
            "from_facility_reference": self.from_facility_reference,
            "to_facility_reference": self.to_facility_reference,
            "transport_reference": self.transport_reference,
            "kdes": self.kdes,
            "schema_version": self.schema_version,
        }

    def prepare_for_persistence(self) -> "TraceabilityEvent":
        """
        Finalize the event for storage: compute hashes, build normalized payload.

        Call this after normalization but before writing to the database.
        """
        self.sha256_hash = self.compute_sha256_hash()
        self.idempotency_key = self.compute_idempotency_key()
        self.normalized_payload = self.build_normalized_payload()
        return self


# ---------------------------------------------------------------------------
# Evidence Attachment
# ---------------------------------------------------------------------------

class EvidenceAttachment(BaseModel):
    """Source document linked to a canonical event for evidentiary chain."""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    event_id: UUID

    document_type: EvidenceDocumentType
    file_name: Optional[str] = None
    file_hash: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None

    storage_uri: Optional[str] = None
    storage_bucket: Optional[str] = None

    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    extraction_status: str = "pending"

    uploaded_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Normalization Functions
# ---------------------------------------------------------------------------

def normalize_webhook_event(
    event: Any,
    tenant_id: str,
    source: str = "webhook_api",
    raw_payload: Optional[Dict[str, Any]] = None,
    ingestion_run_id: Optional[str] = None,
) -> TraceabilityEvent:
    """
    Normalize a webhook IngestEvent into a canonical TraceabilityEvent.

    This is the bridge between the existing webhook ingestion format
    and the canonical model. The raw webhook payload is preserved verbatim.
    """
    # Build raw payload from webhook event if not provided
    if raw_payload is None:
        raw_payload = {
            "cte_type": event.cte_type.value if hasattr(event.cte_type, "value") else event.cte_type,
            "traceability_lot_code": event.traceability_lot_code,
            "product_description": event.product_description,
            "quantity": event.quantity,
            "unit_of_measure": event.unit_of_measure,
            "location_gln": event.location_gln,
            "location_name": event.location_name,
            "timestamp": event.timestamp,
            "kdes": event.kdes,
        }
        if hasattr(event, "input_traceability_lot_codes") and event.input_traceability_lot_codes:
            raw_payload["input_traceability_lot_codes"] = event.input_traceability_lot_codes

    # Extract facility references from KDEs
    kdes = dict(event.kdes) if event.kdes else {}
    from_facility = (
        event.location_gln
        or kdes.get("ship_from_gln")
        or kdes.get("ship_from_location")
        or event.location_name
    )
    to_facility = (
        kdes.get("ship_to_gln")
        or kdes.get("ship_to_location")
        or kdes.get("receiving_location")
    )

    # For shipping/receiving, map directional references
    event_type_val = event.cte_type.value if hasattr(event.cte_type, "value") else event.cte_type
    if event_type_val == "shipping":
        from_facility = from_facility or event.location_name
    elif event_type_val == "receiving":
        to_facility = to_facility or event.location_name or event.location_gln

    # Build provenance
    provenance = ProvenanceMetadata(
        mapper_name="webhook_v2_normalizer",
        mapper_version="1.0.0",
        original_format="json",
        normalization_rules_applied=["webhook_kde_extraction", "facility_reference_mapping"],
    )

    canonical = TraceabilityEvent(
        tenant_id=UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id,
        source_system=IngestionSource.WEBHOOK_API,
        source_record_id=None,
        ingestion_run_id=UUID(ingestion_run_id) if ingestion_run_id else None,

        event_type=CTEType(event_type_val),
        event_timestamp=event.timestamp,
        product_reference=event.product_description,
        lot_reference=event.traceability_lot_code,
        traceability_lot_code=event.traceability_lot_code,
        quantity=event.quantity,
        unit_of_measure=event.unit_of_measure,

        from_facility_reference=from_facility,
        to_facility_reference=to_facility,
        from_entity_reference=kdes.get("ship_from_entity") or kdes.get("harvester_business_name"),
        to_entity_reference=kdes.get("ship_to_entity") or kdes.get("immediate_previous_source"),
        transport_reference=kdes.get("carrier") or kdes.get("transport_reference"),

        kdes=kdes,
        raw_payload=raw_payload,
        provenance_metadata=provenance,
    )

    return canonical.prepare_for_persistence()


def normalize_epcis_event(
    epcis_data: Dict[str, Any],
    tenant_id: str,
    ingestion_run_id: Optional[str] = None,
) -> TraceabilityEvent:
    """
    Normalize an EPCIS 2.0 event dict into a canonical TraceabilityEvent.

    Maps EPCIS vocabulary (bizStep, readPoint, bizLocation) to canonical fields.
    """
    # Map EPCIS bizStep to CTE type
    biz_step = epcis_data.get("bizStep", "")
    event_type_map = {
        "shipping": CTEType.SHIPPING,
        "receiving": CTEType.RECEIVING,
        "commissioning": CTEType.INITIAL_PACKING,
        "transforming": CTEType.TRANSFORMATION,
        "harvesting": CTEType.HARVESTING,
        "cooling": CTEType.COOLING,
    }
    # Extract CTE type from bizStep URI or direct value
    cte_type = CTEType.RECEIVING  # default
    for key, val in event_type_map.items():
        if key in biz_step.lower():
            cte_type = val
            break

    # Extract identifiers
    epc_list = epcis_data.get("epcList", [])
    tlc = ""
    gtin = None
    for epc in epc_list:
        if "sgtin" in epc.lower() or "lgtin" in epc.lower():
            # Extract GTIN and serial/lot from EPC URI
            parts = epc.rsplit(".", 1)
            if len(parts) == 2:
                tlc = parts[-1]
                gtin_part = parts[0].rsplit(":", 1)
                if gtin_part:
                    gtin = gtin_part[-1]
    if not tlc:
        tlc = epcis_data.get("traceability_lot_code", epcis_data.get("lotNumber", "UNKNOWN"))

    # Build KDEs from EPCIS extensions
    kdes: Dict[str, Any] = {}
    if gtin:
        kdes["gtin"] = gtin
    extensions = epcis_data.get("ilmd", {})
    extensions.update(epcis_data.get("extension", {}))
    for k, v in extensions.items():
        kdes[k] = v

    provenance = ProvenanceMetadata(
        mapper_name="epcis_normalizer",
        mapper_version="1.0.0",
        original_format="epcis_json" if not epcis_data.get("_xml_source") else "epcis_xml",
        normalization_rules_applied=["epcis_bizstep_mapping", "epc_uri_parsing"],
    )

    canonical = TraceabilityEvent(
        tenant_id=UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id,
        source_system=IngestionSource.EPCIS_API,
        source_record_id=epcis_data.get("eventID"),
        ingestion_run_id=UUID(ingestion_run_id) if ingestion_run_id else None,

        event_type=cte_type,
        event_timestamp=epcis_data.get("eventTime", datetime.now(timezone.utc).isoformat()),
        event_timezone=epcis_data.get("eventTimeZoneOffset", "UTC"),

        product_reference=epcis_data.get("productDescription", kdes.get("gtin", "")),
        lot_reference=tlc,
        traceability_lot_code=tlc if len(tlc) >= 3 else f"EPCIS-{tlc or 'UNKNOWN'}",
        quantity=float(epcis_data.get("quantity", {}).get("value", 1)),
        unit_of_measure=epcis_data.get("quantity", {}).get("uom", "each"),

        from_facility_reference=epcis_data.get("readPoint", {}).get("id") if isinstance(epcis_data.get("readPoint"), dict) else epcis_data.get("readPoint"),
        to_facility_reference=epcis_data.get("bizLocation", {}).get("id") if isinstance(epcis_data.get("bizLocation"), dict) else epcis_data.get("bizLocation"),

        kdes=kdes,
        raw_payload=epcis_data,
        provenance_metadata=provenance,

        epcis_event_type=epcis_data.get("type", epcis_data.get("eventType")),
        epcis_action=epcis_data.get("action"),
        epcis_biz_step=biz_step,
    )

    return canonical.prepare_for_persistence()


def normalize_csv_row(
    row: Dict[str, Any],
    tenant_id: str,
    column_mapping: Dict[str, str],
    ingestion_run_id: Optional[str] = None,
    source_file_name: Optional[str] = None,
    row_number: Optional[int] = None,
) -> TraceabilityEvent:
    """
    Normalize a CSV/XLSX row dict into a canonical TraceabilityEvent.

    column_mapping maps source column names to canonical field names.
    Unmapped columns are stored in kdes.
    """
    # Apply column mapping
    mapped: Dict[str, Any] = {}
    kdes: Dict[str, Any] = {}
    for src_col, value in row.items():
        if src_col in column_mapping:
            mapped[column_mapping[src_col]] = value
        else:
            # Unmapped columns become KDEs
            if value is not None and str(value).strip():
                kdes[src_col] = value

    # Required fields with fallbacks
    event_type_raw = str(mapped.get("event_type", "receiving")).lower().strip()
    cte_type_map = {
        "harvest": "harvesting", "harvesting": "harvesting",
        "cool": "cooling", "cooling": "cooling",
        "pack": "initial_packing", "initial_packing": "initial_packing",
        "initial packing": "initial_packing",
        "first_land_based_receiving": "first_land_based_receiving",
        "ship": "shipping", "shipping": "shipping",
        "receive": "receiving", "receiving": "receiving",
        "transform": "transformation", "transformation": "transformation",
    }
    event_type = cte_type_map.get(event_type_raw, "receiving")

    rules_applied = ["csv_column_mapping"]
    confidence = 1.0

    # Detect if event type was inferred
    if event_type_raw not in cte_type_map:
        rules_applied.append("event_type_inference")
        confidence = 0.7

    provenance = ProvenanceMetadata(
        source_file_name=source_file_name,
        mapper_name="csv_normalizer",
        mapper_version="1.0.0",
        original_format="csv",
        normalization_rules_applied=rules_applied,
        extraction_confidence=confidence,
    )

    canonical = TraceabilityEvent(
        tenant_id=UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id,
        source_system=IngestionSource.CSV_UPLOAD,
        source_record_id=str(row_number) if row_number is not None else None,
        ingestion_run_id=UUID(ingestion_run_id) if ingestion_run_id else None,

        event_type=CTEType(event_type),
        event_timestamp=mapped.get("event_timestamp", mapped.get("timestamp", datetime.now(timezone.utc).isoformat())),

        product_reference=mapped.get("product_description", mapped.get("product_reference", "")),
        lot_reference=mapped.get("lot_reference", mapped.get("traceability_lot_code", "")),
        traceability_lot_code=mapped.get("traceability_lot_code", mapped.get("tlc", "UNKNOWN")),
        quantity=float(mapped.get("quantity", 1)),
        unit_of_measure=str(mapped.get("unit_of_measure", "each")).lower(),

        from_facility_reference=mapped.get("from_facility_reference", mapped.get("ship_from_location", mapped.get("location_gln"))),
        to_facility_reference=mapped.get("to_facility_reference", mapped.get("ship_to_location")),
        from_entity_reference=mapped.get("from_entity_reference"),
        to_entity_reference=mapped.get("to_entity_reference"),
        transport_reference=mapped.get("transport_reference", mapped.get("carrier")),

        kdes=kdes,
        raw_payload=row,
        provenance_metadata=provenance,
        confidence_score=confidence,
    )

    return canonical.prepare_for_persistence()
