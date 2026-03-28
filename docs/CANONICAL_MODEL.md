# RegEngine Canonical Event Model

> Generated from `services/shared/canonical_event.py` (schema version 1.0.0)

## Overview

The canonical event model normalizes traceability events from any ingestion source -- webhooks, EPCIS 2.0 documents, CSV/XLSX uploads, EDI messages, mobile capture, and manual entry -- into a single `TraceabilityEvent` structure. This is RegEngine's **one internal truth model** for all FSMA 204 compliance operations.

Every downstream service (rules engine, FDA export, graph sync, exception queue, request-response workflow) consumes only this model, never format-specific payloads.

**Design principles:**

1. Raw source preserved alongside normalized form (dual payload)
2. Provenance metadata tracks who/when/how/what-version
3. Amendment chains are explicit (`supersedes_event_id`)
4. Schema is versioned for forward compatibility
5. KDEs are structured dicts, not key-value pairs

---

## Core Types

### CTEType (Enum)

Critical Tracking Event types per FSMA 204 Section 1.1310.

| Value | Enum Member | FSMA 204 Meaning |
|---|---|---|
| `harvesting` | `HARVESTING` | Harvesting of a food on the Food Traceability List (FTL) |
| `cooling` | `COOLING` | Cooling of a raw agricultural commodity before initial packing |
| `initial_packing` | `INITIAL_PACKING` | Initial packing of a raw agricultural commodity |
| `first_land_based_receiving` | `FIRST_LAND_BASED_RECEIVING` | First land-based receiving of a food obtained through ocean or inland fishing |
| `shipping` | `SHIPPING` | Shipping of a food on the FTL |
| `receiving` | `RECEIVING` | Receiving of a food on the FTL |
| `transformation` | `TRANSFORMATION` | Transformation of a food on the FTL (e.g., manufacturing, combining, commingling) |

### EventStatus (Enum)

Lifecycle status of a canonical event.

| Value | Enum Member | Description |
|---|---|---|
| `active` | `ACTIVE` | Current, valid event |
| `superseded` | `SUPERSEDED` | Replaced by a newer event via amendment chain |
| `rejected` | `REJECTED` | Failed validation or was rejected during processing |
| `draft` | `DRAFT` | Pending finalization or review |

### IngestionSource (Enum)

Known ingestion source systems.

| Value | Enum Member | Description |
|---|---|---|
| `webhook_api` | `WEBHOOK_API` | Real-time webhook API ingestion |
| `csv_upload` | `CSV_UPLOAD` | CSV file upload |
| `xlsx_upload` | `XLSX_UPLOAD` | Excel file upload |
| `epcis_api` | `EPCIS_API` | EPCIS 2.0 JSON API |
| `epcis_xml` | `EPCIS_XML` | EPCIS 2.0 XML document |
| `edi` | `EDI` | EDI message ingestion |
| `manual` | `MANUAL` | Manual data entry |
| `mobile_capture` | `MOBILE_CAPTURE` | Mobile device capture |
| `supplier_portal` | `SUPPLIER_PORTAL` | Supplier portal submission |
| `legacy_v002` | `LEGACY_V002` | Legacy v0.0.2 format migration |

### IngestionRunStatus (Enum)

Processing state of an ingestion batch.

| Value | Enum Member | Description |
|---|---|---|
| `processing` | `PROCESSING` | Batch is currently being processed |
| `completed` | `COMPLETED` | All records processed successfully |
| `partial` | `PARTIAL` | Some records succeeded, some failed |
| `failed` | `FAILED` | Entire batch failed |

### EvidenceDocumentType (Enum)

Types of evidence documents that can be attached to events.

| Value | Enum Member | Description |
|---|---|---|
| `bol` | `BOL` | Bill of Lading |
| `invoice` | `INVOICE` | Invoice |
| `lab_report` | `LAB_REPORT` | Laboratory report |
| `photo` | `PHOTO` | Photographic evidence |
| `temperature_log` | `TEMPERATURE_LOG` | Temperature monitoring log |
| `production_record` | `PRODUCTION_RECORD` | Production record |
| `purchase_order` | `PURCHASE_ORDER` | Purchase order |
| `certificate` | `CERTIFICATE` | Certificate (organic, fair trade, etc.) |
| `other` | `OTHER` | Other document type |

---

## TraceabilityEvent

The central canonical model. A Pydantic `BaseModel` subclass representing a single normalized traceability event.

### Identity

| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | `UUID` | Auto-generated | Unique identifier for this event (default: `uuid4()`) |
| `tenant_id` | `UUID` | **Required** | Tenant that owns this event |

### Source Provenance

| Field | Type | Required | Description |
|---|---|---|---|
| `source_system` | `IngestionSource` | **Required** | Which ingestion path produced this event |
| `source_record_id` | `str` | Optional | Identifier from the source system (e.g., EPCIS eventID, CSV row number) |
| `source_file_id` | `UUID` | Optional | Reference to the uploaded source file |
| `ingestion_run_id` | `UUID` | Optional | Links to the `IngestionRun` batch that produced this event |

### Event Classification

| Field | Type | Required | Description |
|---|---|---|---|
| `event_type` | `CTEType` | **Required** | The FSMA 204 Critical Tracking Event type |
| `event_timestamp` | `datetime` | **Required** | When the physical event occurred. Accepts ISO 8601 strings, Z-suffix, or datetime objects. Naive datetimes are assumed UTC. |
| `event_timezone` | `str` | Optional (default: `"UTC"`) | Timezone of the event timestamp |

### Product and Lot

| Field | Type | Required | Description |
|---|---|---|---|
| `product_reference` | `str` | Optional | Product description or GTIN |
| `lot_reference` | `str` | Optional | Lot identifier |
| `traceability_lot_code` | `str` | **Required** (min 3 chars) | The Traceability Lot Code (TLC) per FSMA 204 |
| `quantity` | `float` | **Required** (must be > 0) | Quantity of product |
| `unit_of_measure` | `str` | **Required** | Unit of measure (e.g., `lbs`, `kg`, `cases`, `each`) |

### Facility References

| Field | Type | Required | Description |
|---|---|---|---|
| `from_entity_reference` | `str` | Optional | Business entity shipping/originating the product |
| `to_entity_reference` | `str` | Optional | Business entity receiving the product |
| `from_facility_reference` | `str` | Optional | GLN or name of the originating facility |
| `to_facility_reference` | `str` | Optional | GLN or name of the destination facility |
| `transport_reference` | `str` | Optional | Carrier or transport identifier |

### Key Data Elements (KDEs)

| Field | Type | Required | Description |
|---|---|---|---|
| `kdes` | `Dict[str, Any]` | Optional (default: `{}`) | Structured dictionary of Key Data Elements. Contains CTE-specific fields such as `ship_from_gln`, `harvester_business_name`, `carrier`, temperature readings, etc. |

### Dual Payload

| Field | Type | Required | Description |
|---|---|---|---|
| `raw_payload` | `Dict[str, Any]` | Optional (default: `{}`) | The original source payload preserved verbatim for auditability |
| `normalized_payload` | `Dict[str, Any]` | Optional (default: `{}`) | The canonical normalized form, built by `build_normalized_payload()` |

### Provenance

| Field | Type | Required | Description |
|---|---|---|---|
| `provenance_metadata` | `ProvenanceMetadata` | Auto-generated | Structured provenance: mapper name/version, original format, confidence, rules applied |

### Quality and Status

| Field | Type | Required | Description |
|---|---|---|---|
| `confidence_score` | `float` | Optional (default: `1.0`) | Confidence in normalization accuracy (0.0 to 1.0). Reduced when event types are inferred. |
| `status` | `EventStatus` | Optional (default: `ACTIVE`) | Current lifecycle status |

### Amendment Chain

| Field | Type | Required | Description |
|---|---|---|---|
| `supersedes_event_id` | `UUID` | Optional | If this event amends a previous event, the ID of the superseded event |

### Schema Version

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | `str` | Auto-set | Schema version string (currently `"1.0.0"`) for forward compatibility |

### Integrity

| Field | Type | Required | Description |
|---|---|---|---|
| `sha256_hash` | `str` | Computed | SHA-256 hash of canonical form for integrity verification |
| `chain_hash` | `str` | Optional | Hash chain value for tamper detection |
| `idempotency_key` | `str` | Computed | Content-addressable deduplication key |

### EPCIS Interop

| Field | Type | Required | Description |
|---|---|---|---|
| `epcis_event_type` | `str` | Optional | EPCIS event type (e.g., `ObjectEvent`, `TransformationEvent`) |
| `epcis_action` | `str` | Optional | EPCIS action (`ADD`, `OBSERVE`, `DELETE`) |
| `epcis_biz_step` | `str` | Optional | EPCIS business step URI or value |

### Timestamps

| Field | Type | Required | Description |
|---|---|---|---|
| `created_at` | `datetime` | Auto-generated | When the canonical event was created |
| `amended_at` | `datetime` | Optional | When this event was last amended |
| `ingested_at` | `datetime` | Auto-generated | When the event was ingested into the system |

---

## Key Methods

### `compute_sha256_hash() -> str`

Computes a SHA-256 hash of the event's canonical form for integrity verification. The hash is computed over a pipe-delimited string of:

```
event_id | event_type | traceability_lot_code | product_reference | quantity |
unit_of_measure | from_facility_reference | to_facility_reference |
event_timestamp (ISO) | kdes (JSON, sorted keys)
```

Empty optional fields are represented as empty strings.

### `compute_idempotency_key() -> str`

Computes a content-addressable deduplication key. Two events with identical business content produce the same key, enabling deduplication across ingestion runs. The key is a SHA-256 hash of a JSON object containing:

```json
{
  "event_type": "...",
  "tlc": "...",
  "timestamp": "...",
  "source": "...",
  "from_facility": "...",
  "to_facility": "...",
  "kdes": { ... }
}
```

The JSON is serialized with sorted keys and compact separators (`(",", ":")`).

### `build_normalized_payload() -> Dict[str, Any]`

Builds the normalized payload dictionary for storage. Includes: `event_id`, `event_type`, `traceability_lot_code`, `product_reference`, `lot_reference`, `quantity`, `unit_of_measure`, `event_timestamp`, `event_timezone`, entity references, facility references, `transport_reference`, `kdes`, and `schema_version`.

### `prepare_for_persistence() -> TraceabilityEvent`

Finalizes the event for database storage by calling all three computation methods in sequence:

1. `self.sha256_hash = self.compute_sha256_hash()`
2. `self.idempotency_key = self.compute_idempotency_key()`
3. `self.normalized_payload = self.build_normalized_payload()`

Returns `self` for method chaining. Call this after normalization but before writing to the database.

---

## ProvenanceMetadata

Structured provenance for a canonical event. Answers: Where did this record come from? How was it normalized? What confidence do we have in the mapping?

| Field | Type | Default | Description |
|---|---|---|---|
| `source_file_hash` | `str` | `None` | SHA hash of the source file |
| `source_file_name` | `str` | `None` | Name of the source file |
| `ingestion_timestamp` | `str` | Current UTC ISO timestamp | When ingestion occurred |
| `mapper_name` | `str` | `"unknown"` | Name of the normalization mapper used |
| `mapper_version` | `str` | `"1.0.0"` | Version of the mapper |
| `normalization_rules_applied` | `List[str]` | `[]` | List of normalization rules that were applied |
| `original_format` | `str` | `"unknown"` | Source format: `json`, `csv`, `xlsx`, `epcis_xml`, `epcis_json`, `edi` |
| `extraction_confidence` | `float` | `1.0` | Confidence in the extraction accuracy |

---

## IngestionRun

Batch provenance model -- one record per file upload, API call, or EPCIS document. Tracks the lifecycle and statistics of a batch ingestion operation.

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | `UUID` | `uuid4()` | Unique batch identifier |
| `tenant_id` | `UUID` | **Required** | Owning tenant |
| `source_system` | `IngestionSource` | **Required** | Which ingestion path |
| `source_file_name` | `str` | `None` | Name of uploaded file |
| `source_file_hash` | `str` | `None` | Hash of the source file for integrity |
| `source_file_size` | `int` | `None` | File size in bytes |
| `record_count` | `int` | `0` | Total records in the batch |
| `accepted_count` | `int` | `0` | Records successfully processed |
| `rejected_count` | `int` | `0` | Records that failed validation |
| `mapper_version` | `str` | `"1.0.0"` | Mapper version used |
| `schema_version` | `str` | `"1.0.0"` | Canonical schema version |
| `status` | `IngestionRunStatus` | `PROCESSING` | Current batch status |
| `initiated_by` | `str` | `None` | User or system that initiated the run |
| `started_at` | `datetime` | Current UTC time | When processing started |
| `completed_at` | `datetime` | `None` | When processing finished |
| `errors` | `List[Dict]` | `[]` | Error details for failed records |

---

## EvidenceAttachment

Source document linked to a canonical event for evidentiary chain.

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | `UUID` | `uuid4()` | Unique attachment identifier |
| `tenant_id` | `UUID` | **Required** | Owning tenant |
| `event_id` | `UUID` | **Required** | The canonical event this document is attached to |
| `document_type` | `EvidenceDocumentType` | **Required** | Type of evidence document |
| `file_name` | `str` | `None` | Original file name |
| `file_hash` | `str` | `None` | SHA hash of the file |
| `file_size` | `int` | `None` | File size in bytes |
| `mime_type` | `str` | `None` | MIME type of the document |
| `storage_uri` | `str` | `None` | URI to the stored document |
| `storage_bucket` | `str` | `None` | Storage bucket name |
| `extracted_data` | `Dict[str, Any]` | `{}` | Data extracted from the document (e.g., OCR results) |
| `extraction_status` | `str` | `"pending"` | Status of data extraction |
| `uploaded_by` | `str` | `None` | User who uploaded the document |
| `created_at` | `datetime` | Current UTC time | When the attachment was created |

---

## Normalization Pipeline

Three normalizer functions convert source-specific formats into `TraceabilityEvent` instances. Each calls `prepare_for_persistence()` before returning, so the result is ready for database storage.

### `normalize_webhook_event()`

```python
normalize_webhook_event(
    event: Any,              # Webhook IngestEvent object
    tenant_id: str,
    source: str = "webhook_api",
    raw_payload: Optional[Dict] = None,
    ingestion_run_id: Optional[str] = None,
) -> TraceabilityEvent
```

**Normalization steps:**

1. Builds `raw_payload` from the webhook event if not provided (preserves `cte_type`, `traceability_lot_code`, `product_description`, `quantity`, `unit_of_measure`, `location_gln`, `location_name`, `timestamp`, `kdes`)
2. Extracts facility references from KDEs (`ship_from_gln`, `ship_to_gln`, `ship_to_location`, `receiving_location`)
3. Applies directional mapping for shipping/receiving events
4. Extracts entity references from KDEs (`ship_from_entity`, `harvester_business_name`, `ship_to_entity`, `immediate_previous_source`)
5. Sets provenance: mapper=`webhook_v2_normalizer`, format=`json`, rules=`[webhook_kde_extraction, facility_reference_mapping]`
6. Calls `prepare_for_persistence()`

### `normalize_epcis_event()`

```python
normalize_epcis_event(
    epcis_data: Dict[str, Any],  # EPCIS 2.0 event dict
    tenant_id: str,
    ingestion_run_id: Optional[str] = None,
) -> TraceabilityEvent
```

**Normalization steps:**

1. Maps EPCIS `bizStep` to `CTEType` via keyword matching (default: `RECEIVING`)
2. Extracts TLC and GTIN from EPC URIs in `epcList` (supports SGTIN and LGTIN formats)
3. Builds KDEs from EPCIS `ilmd` and `extension` fields
4. Maps `readPoint` to `from_facility_reference`, `bizLocation` to `to_facility_reference`
5. Preserves EPCIS interop fields (`epcis_event_type`, `epcis_action`, `epcis_biz_step`)
6. Sets provenance: mapper=`epcis_normalizer`, rules=`[epcis_bizstep_mapping, epc_uri_parsing]`
7. Calls `prepare_for_persistence()`

**bizStep to CTEType mapping:**

| bizStep keyword | CTEType |
|---|---|
| `shipping` | `SHIPPING` |
| `receiving` | `RECEIVING` |
| `commissioning` | `INITIAL_PACKING` |
| `transforming` | `TRANSFORMATION` |
| `harvesting` | `HARVESTING` |
| `cooling` | `COOLING` |

### `normalize_csv_row()`

```python
normalize_csv_row(
    row: Dict[str, Any],              # Single CSV/XLSX row as dict
    tenant_id: str,
    column_mapping: Dict[str, str],   # source_column -> canonical_field
    ingestion_run_id: Optional[str] = None,
    source_file_name: Optional[str] = None,
    row_number: Optional[int] = None,
) -> TraceabilityEvent
```

**Normalization steps:**

1. Applies `column_mapping` to translate source columns to canonical fields
2. Unmapped columns with non-empty values are stored as KDEs
3. Maps event type strings to `CTEType` using a flexible alias map (e.g., `"harvest"` -> `HARVESTING`, `"ship"` -> `SHIPPING`)
4. Reduces `confidence_score` to 0.7 if event type required inference
5. Sets provenance: mapper=`csv_normalizer`, format=`csv`, rules=`[csv_column_mapping]` (plus `event_type_inference` if applicable)
6. Calls `prepare_for_persistence()`

**Event type alias map:**

| Input alias(es) | Canonical CTEType |
|---|---|
| `harvest`, `harvesting` | `HARVESTING` |
| `cool`, `cooling` | `COOLING` |
| `pack`, `initial_packing`, `initial packing` | `INITIAL_PACKING` |
| `first_land_based_receiving` | `FIRST_LAND_BASED_RECEIVING` |
| `ship`, `shipping` | `SHIPPING` |
| `receive`, `receiving` | `RECEIVING` |
| `transform`, `transformation` | `TRANSFORMATION` |

---

## Example Payloads

### Webhook-normalized shipping event

```json
{
  "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "tenant_id": "11111111-2222-3333-4444-555555555555",
  "source_system": "webhook_api",
  "source_record_id": null,
  "ingestion_run_id": null,
  "event_type": "shipping",
  "event_timestamp": "2026-03-15T14:30:00+00:00",
  "event_timezone": "UTC",
  "product_reference": "Organic Romaine Lettuce",
  "lot_reference": "LOT-2026-0315-A",
  "traceability_lot_code": "LOT-2026-0315-A",
  "quantity": 500.0,
  "unit_of_measure": "cases",
  "from_entity_reference": "Fresh Farms Inc.",
  "to_entity_reference": "Metro Distribution LLC",
  "from_facility_reference": "urn:epc:id:sgln:0614141.00001.0",
  "to_facility_reference": "urn:epc:id:sgln:0614141.00002.0",
  "transport_reference": "CARRIER-XYZ-98765",
  "kdes": {
    "ship_from_gln": "urn:epc:id:sgln:0614141.00001.0",
    "ship_to_gln": "urn:epc:id:sgln:0614141.00002.0",
    "ship_from_entity": "Fresh Farms Inc.",
    "ship_to_entity": "Metro Distribution LLC",
    "carrier": "CARRIER-XYZ-98765",
    "temperature_min": 34,
    "temperature_max": 38,
    "temperature_uom": "fahrenheit"
  },
  "raw_payload": {
    "cte_type": "shipping",
    "traceability_lot_code": "LOT-2026-0315-A",
    "product_description": "Organic Romaine Lettuce",
    "quantity": 500.0,
    "unit_of_measure": "cases",
    "location_gln": "urn:epc:id:sgln:0614141.00001.0",
    "location_name": "Fresh Farms Salinas",
    "timestamp": "2026-03-15T14:30:00Z",
    "kdes": { "...": "..." }
  },
  "normalized_payload": {
    "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "event_type": "shipping",
    "traceability_lot_code": "LOT-2026-0315-A",
    "product_reference": "Organic Romaine Lettuce",
    "lot_reference": "LOT-2026-0315-A",
    "quantity": 500.0,
    "unit_of_measure": "cases",
    "event_timestamp": "2026-03-15T14:30:00+00:00",
    "event_timezone": "UTC",
    "from_facility_reference": "urn:epc:id:sgln:0614141.00001.0",
    "to_facility_reference": "urn:epc:id:sgln:0614141.00002.0",
    "kdes": { "...": "..." },
    "schema_version": "1.0.0"
  },
  "provenance_metadata": {
    "ingestion_timestamp": "2026-03-15T14:30:05.123456+00:00",
    "mapper_name": "webhook_v2_normalizer",
    "mapper_version": "1.0.0",
    "original_format": "json",
    "normalization_rules_applied": [
      "webhook_kde_extraction",
      "facility_reference_mapping"
    ],
    "extraction_confidence": 1.0
  },
  "confidence_score": 1.0,
  "status": "active",
  "schema_version": "1.0.0",
  "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "idempotency_key": "a9f3c2d1b8e74f5690abcdef12345678abcdef1234567890abcdef1234567890"
}
```

### CSV-normalized receiving event

```json
{
  "event_id": "f9e8d7c6-b5a4-3210-fedc-ba9876543210",
  "tenant_id": "11111111-2222-3333-4444-555555555555",
  "source_system": "csv_upload",
  "source_record_id": "42",
  "ingestion_run_id": "aaaabbbb-cccc-dddd-eeee-ffffffffffff",
  "event_type": "receiving",
  "event_timestamp": "2026-03-16T08:00:00+00:00",
  "event_timezone": "UTC",
  "product_reference": "Atlantic Salmon Fillets",
  "lot_reference": "SAL-2026-0316",
  "traceability_lot_code": "SAL-2026-0316",
  "quantity": 200.0,
  "unit_of_measure": "lbs",
  "from_facility_reference": "0857674001001",
  "to_facility_reference": "0857674001002",
  "kdes": {
    "purchase_order": "PO-2026-4521",
    "temperature_at_receiving": "33F"
  },
  "raw_payload": {
    "TLC": "SAL-2026-0316",
    "Product": "Atlantic Salmon Fillets",
    "Qty": "200",
    "UOM": "lbs",
    "Event Type": "receiving",
    "Date": "2026-03-16T08:00:00Z",
    "Ship From GLN": "0857674001001",
    "Ship To GLN": "0857674001002",
    "PO Number": "PO-2026-4521",
    "Temp": "33F"
  },
  "provenance_metadata": {
    "source_file_name": "march_receiving_log.csv",
    "ingestion_timestamp": "2026-03-16T09:15:00.000000+00:00",
    "mapper_name": "csv_normalizer",
    "mapper_version": "1.0.0",
    "original_format": "csv",
    "normalization_rules_applied": ["csv_column_mapping"],
    "extraction_confidence": 1.0
  },
  "confidence_score": 1.0,
  "status": "active",
  "schema_version": "1.0.0",
  "sha256_hash": "...",
  "idempotency_key": "..."
}
```
