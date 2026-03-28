# RegEngine Canonical Model Specification

## Purpose

The Canonical Model Specification defines the single, authoritative representation of food traceability data within RegEngine. All data ingestion pathways—whether from GS1 EPCIS feeds, EDI messages, manual uploads, or API calls—normalize to this canonical form before any rule evaluation, transformation, or persistence occurs.

This specification ensures that:
1. **Consistency**: All downstream rules and queries operate on uniform data regardless of source format
2. **Auditability**: Every ingested CTE can be traced back to its canonical representation and original source
3. **Compliance**: The canonical model directly implements the Key Data Elements (KDEs) required by 21 CFR § 1.1340–1.1350 for FSMA 204
4. **Versioning**: The canonical model itself is versioned, allowing migrations when regulatory requirements or business logic change
5. **Interoperability**: Data exported from RegEngine can be imported into other systems with full fidelity

---

## Critical Traceability Events (CTEs)

FSMA 204 § 1.1340 defines seven types of Critical Traceability Events that must be recorded by all food businesses. RegEngine captures and normalizes all seven:

### 1. Harvesting

A Harvesting event records the initial capture of raw agricultural product.

**Canonical Fields**:
- `event_type`: "HARVESTING"
- `event_timestamp`: UTC timestamp (ISO 8601) when harvesting began
- `product`: Product reference (see Product Entity Model, below)
- `quantity`: Volume or count harvested
- `unit_of_measure`: "KG", "LB", "CASE", "PALLET", or other standardized unit
- `location_harvested`: GLN (Global Location Number) of the farm or field
- `harvest_date_range`: `{start_date, end_date}` if harvesting spanned multiple days
- `crop_identifier`: Optional FSMA-specific identifier for the specific lot or field
- `source_event_id`: The originating system's unique identifier for this event
- `source_format`: "EPCIS", "EDI", "MANUAL", or other format this event came from

**Regulatory Alignment**: 21 CFR § 1.1340(a)

### 2. Cooling

A Cooling event records when a product is temperature-controlled after harvest.

**Canonical Fields**:
- `event_type`: "COOLING"
- `event_timestamp`: UTC timestamp when cooling began
- `product`: Product reference
- `quantity`: Volume or count cooled
- `unit_of_measure`: As above
- `location_cooled`: GLN of the cooling facility
- `equipment_id`: Identifier of the cooling facility or chamber
- `temperature`: Numeric temperature value in Celsius
- `duration_hours`: Number of hours the product was held at that temperature
- `source_event_id`: As above
- `source_format`: As above

**Regulatory Alignment**: 21 CFR § 1.1340(b)

### 3. Packing

A Packing event records when a product is packaged for shipment.

**Canonical Fields**:
- `event_type`: "PACKING"
- `event_timestamp`: UTC timestamp when packing occurred
- `product`: Product reference
- `quantity`: Volume or count packed
- `unit_of_measure`: As above
- `location_packed`: GLN of the packing facility
- `output_shipping_unit`: The SSCC (Serial Shipping Container Code) or other identifier of the shipping unit created by packing
- `input_lot_identifiers`: List of lot identifiers that were combined in this packing event
- `source_event_id`: As above
- `source_format`: As above

**Regulatory Alignment**: 21 CFR § 1.1340(c)

### 4. First Land-Based Receiving

A First Land-Based Receiving event records when an aquaculture or seafood product is received at the first land-based facility after harvest from water.

**Canonical Fields**:
- `event_type`: "FIRST_LAND_BASED_RECEIVING"
- `event_timestamp`: UTC timestamp when product was received
- `product`: Product reference
- `quantity`: Volume or count received
- `unit_of_measure`: As above
- `location_received`: GLN of the receiving facility
- `shipping_unit_identifier`: SSCC or other identifier of the shipping unit received
- `vessel_name`: Optional name of the vessel from which the product came (for seafood traceability)
- `source_event_id`: As above
- `source_format`: As above

**Regulatory Alignment**: 21 CFR § 1.1340(d)

### 5. Shipping

A Shipping event records when a product leaves a facility.

**Canonical Fields**:
- `event_type`: "SHIPPING"
- `event_timestamp`: UTC timestamp when shipment left the facility
- `product`: Product reference
- `quantity`: Volume or count shipped
- `unit_of_measure`: As above
- `location_shipped_from`: GLN of the shipping facility
- `shipping_unit_identifier`: SSCC or other identifier of the shipping unit
- `recipient_location`: GLN of the receiving facility
- `transportation_mode`: "TRUCK", "AIR", "RAIL", "SHIP", or other mode
- `expected_delivery_date`: Estimated arrival date (ISO 8601 date)
- `source_event_id`: As above
- `source_format`: As above

**Regulatory Alignment**: 21 CFR § 1.1340(e)

### 6. Receiving

A Receiving event records when a product is received at a facility.

**Canonical Fields**:
- `event_type`: "RECEIVING"
- `event_timestamp`: UTC timestamp when product was received
- `product`: Product reference
- `quantity`: Volume or count received
- `unit_of_measure`: As above
- `location_received`: GLN of the receiving facility
- `shipping_unit_identifier`: SSCC or other identifier of the shipping unit
- `source_event_id`: As above
- `source_format`: As above

**Regulatory Alignment**: 21 CFR § 1.1340(f)

### 7. Transformation

A Transformation event records when a product is converted into a different product (e.g., raw ingredients combined into a finished product).

**Canonical Fields**:
- `event_type`: "TRANSFORMATION"
- `event_timestamp`: UTC timestamp when transformation occurred
- `location_transformed`: GLN of the transformation facility
- `input_products`: List of product references and quantities that were inputs
- `output_product`: Product reference for the output
- `output_quantity`: Volume or count of output
- `output_unit_of_measure`: As above
- `output_lot_identifier`: Lot identifier assigned to the output
- `transformation_process_id`: Identifier of the transformation recipe or process used
- `source_event_id`: As above
- `source_format`: As above

**Regulatory Alignment**: 21 CFR § 1.1340(g)

---

## Key Data Elements (KDEs)

For each CTE type, the following KDEs must be present in the canonical representation. Absence of a required KDE triggers a validation error in RegEngine.

### Universal KDEs (Required for All CTEs)

| KDE | Description | Format | Source Regulation |
|---|---|---|---|
| `event_type` | One of the 7 CTE types | String enum | FSMA 204 § 1.1340 |
| `event_timestamp` | When the event occurred | ISO 8601 UTC | 21 CFR § 1.1340(a)–(g) |
| `product` | The product involved | Product Entity (see below) | 21 CFR § 1.1340 |
| `quantity` | How much was involved | Numeric | 21 CFR § 1.1340 |
| `unit_of_measure` | The unit (KG, LB, CASE, etc.) | String enum | 21 CFR § 1.1340 |
| `source_event_id` | Originating system's ID | String UUID or URN | Audit trail requirement |
| `source_format` | How the event was ingested | String enum | Audit trail requirement |

### CTE-Specific KDEs

**Harvesting, Cooling, Packing, Receiving, Transformation**:
- `location` (field name varies by CTE): GLN of the business location involved
- Must be a valid GS1 GLN registered in the RegEngine directory

**Shipping**:
- `location_shipped_from`, `location_shipped_to`: GLNs
- `transportation_mode`: Required to classify the shipment method

**Transformation**:
- `input_products`: Required list of ingredients with quantities
- `output_lot_identifier`: Required to trace the resulting product

---

## Entity Model

### Product Entity

Every CTE references one or more products. The Product entity is canonical within RegEngine:

**Attributes**:
- `gtin`: Global Trade Item Number (GTIN-8, GTIN-12, GTIN-13, or GTIN-14), if available
- `product_name`: Human-readable name (e.g., "Organic Spinach")
- `product_description`: Optional longer description
- `lot_identifier`: The specific lot or batch of this product (e.g., "LOT-2024-03-28-001")
- `brand_owner_gln`: GLN of the entity that owns the brand
- `manufacturer_gln`: GLN of the manufacturer
- `ndc_code`: National Drug Code, if applicable (for supplements or food additives)
- `parent_product_gtin`: If this product is a variant of another, the parent's GTIN

**Identity Resolution**:
When multiple CTEs reference the same product from different sources, the Product entity must be deduplicated. Deduplication rules:
1. Exact GTIN match → same product
2. Exact lot identifier + product name match → same product
3. Name + manufacturer match → same product
4. Otherwise → distinct products

Aliases are recorded in a `product_aliases` table for audit purposes, so all incoming names are preserved.

### Location (Business) Entity

Every CTE references one or more locations (where an event occurred). The Location entity is canonical:

**Attributes**:
- `gln`: Global Location Number (required, unique)
- `business_name`: Legal business name
- `business_dba`: Doing Business As name(s)
- `street_address`: Physical address
- `city`, `state_province`, `postal_code`, `country`: Address components
- `business_type`: "FARM", "DISTRIBUTOR", "PROCESSOR", "RETAIL", etc.
- `is_active`: Boolean (locations may be decommissioned)
- `regulatory_status`: "REGISTERED", "EXEMPT", "SUSPENDED", etc. (per FDA FSMA registration)

**Identity Resolution**:
GLN is the authoritative identifier. If a CTE arrives with multiple location identifiers (e.g., GLN and DUNS), RegEngine attempts to reconcile them to a single Location entity.

### Party (Business Partner) Entity

Every CTE implicitly involves one or more business partners (e.g., the shipper, receiver, processor). The Party entity tracks these relationships:

**Attributes**:
- `gln`: Global Location Number or Global Service Relation Number (GSRN), if available
- `partner_type`: "SUPPLIER", "CUSTOMER", "LOGISTICS_PROVIDER", "TRANSFORMATION_PARTNER", etc.
- `partner_name`: Name of the business
- `legal_entity_identifier`: LEI code, if available
- `contact_person`: Optional contact name
- `contact_email`, `contact_phone`: Contact information

---

## Event Lifecycle

Every CTE follows a standardized lifecycle within RegEngine:

### 1. Ingestion

A CTE arrives in RegEngine via one of several pathways:
- **EPCIS**: Parsed from GS1 EPCIS XML or JSON
- **EDI**: Parsed from EDI 856 or other EDI messages
- **API**: Submitted via the REST API in the canonical JSON format
- **MANUAL**: Entered via a web form or uploaded spreadsheet

The `IngestorService` (or pathway-specific ingestor) receives the CTE in its native format.

### 2. Normalization

The ingestor converts the native format into the canonical form:
- Field names are mapped to canonical field names
- Values are validated (dates are parsed, locations are looked up in the directory, quantities are checked for valid units)
- Missing KDEs trigger validation errors (logged but do not stop processing if the error is non-critical)
- The canonical CTE is assigned a `source_event_id` (the original system's ID) and a `normalized_at` timestamp

**Mapping Examples**:
- EPCIS `epcisDateTime` → canonical `event_timestamp`
- EDI 857 `DTM01` → canonical `event_timestamp`
- API request `timestamp_iso8601` → canonical `event_timestamp`

### 3. Validation

The `ValidationService` checks the canonical CTE against a set of business rules:
- Required KDEs are present
- Data types are correct (numeric, date, enum)
- Values are within acceptable ranges (quantity > 0, temperature within expected range)
- References are valid (product GTIN is real, location GLN is registered, party exists)
- Sequence rules are satisfied (e.g., a Receiving event should follow a Shipping event for the same lot)

Invalid CTEs are logged with the validation error and may be quarantined for manual review.

### 4. Persistence

Valid CTEs are persisted to the PostgreSQL database by the `CTEPersistence` module:
- The canonical CTE is inserted into the `critical_events` table
- The source format, source event ID, and tenant ID are recorded
- A SHA-256 hash is computed over the canonical form and stored (for audit trail purposes)
- A `created_at` timestamp is recorded

### 5. Export

When a user requests a CTE export (via API or bulk export), the `ExportService` retrieves the persisted CTE and produces a response package:
- The CTE is serialized back to the canonical JSON form
- All associated audit records (rule evaluations, validations) are included
- The response package is sealed with a package-level hash and signature
- The user can download the sealed package or send it to another system

---

## EPCIS 2.0 Alignment

RegEngine's canonical model is compatible with GS1 EPCIS 2.0 and maps bidirectionally:

### Canonical-to-EPCIS Mapping

Each CTE in RegEngine maps to one or more EPCIS event types:

| Canonical CTE Type | EPCIS Event Type | EPCIS Mapping Details |
|---|---|---|
| HARVESTING | `ObjectEvent` | `action: OBSERVE`, contextual data includes harvest location |
| COOLING | `ObjectEvent` | `action: OBSERVE`, contextual data includes temperature, facility ID |
| PACKING | `AggregationEvent` or `ObjectEvent` | If multiple inputs combined, `AggregationEvent`; output is the new shipping unit |
| FIRST_LAND_BASED_RECEIVING | `ObjectEvent` | `action: OBSERVE`, includes vessel identifier if available |
| SHIPPING | `ObjectEvent` | `action: SHIP`, destination GLN, transportation mode |
| RECEIVING | `ObjectEvent` | `action: RECEIVE`, source GLN, receiving location |
| TRANSFORMATION | `TransformationEvent` | Input products, output product, transformation facility, process ID |

### EPCIS-to-Canonical Mapping

When EPCIS events are ingested, they are normalized to canonical CTEs:
- EPCIS `ObjectEvent` with type=OBSERVE and context=harvest location → HARVESTING CTE
- EPCIS `ObjectEvent` with action=SHIP → SHIPPING CTE
- EPCIS `TransformationEvent` → TRANSFORMATION CTE

### Bidirectional Export

A CTE can be exported as valid EPCIS 2.0 XML or JSON. When re-imported, it normalizes back to an identical canonical CTE.

---

## Versioning

The canonical model itself is versioned. When regulatory requirements change or new CTE types are added, the canonical model version is incremented.

### Version Scheme

Canonical model versions follow semantic versioning: `MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking changes (e.g., removal of a required KDE, new CTE type added)
- **MINOR**: Non-breaking additions (e.g., new optional field, new product attribute)
- **PATCH**: Bug fixes or clarifications

### Version Tracking

Every persisted CTE records the canonical model version in effect when it was ingested:
- `canonical_model_version`: "1.2.3"

When rule evaluations or exports occur, the system uses the version recorded in the CTE to ensure backward compatibility.

### Migration Process

When the canonical model is updated:
1. A new version is defined and documented (this file is updated)
2. Both the old and new versions are supported simultaneously for a transition period (typically 30 days)
3. Ingestion pathways are updated to normalize to the new version
4. A bulk migration tool is provided to allow existing CTEs to be migrated
5. After the transition period, the old version is deprecated (but old CTEs remain queryable)

**Example Migration**: If FSMA 204 is amended to require a new CTE type, the canonical model is updated to version 2.0.0. All new CTEs use version 2.0.0, but existing version 1.x CTEs remain valid for audit purposes.

---

## Canonical JSON Schema

Below is the canonical JSON schema that all CTEs conform to:

```json
{
  "event_type": "string (one of HARVESTING, COOLING, PACKING, FIRST_LAND_BASED_RECEIVING, SHIPPING, RECEIVING, TRANSFORMATION)",
  "event_timestamp": "string (ISO 8601 UTC)",
  "product": {
    "gtin": "string (optional, GTIN-8/12/13/14)",
    "product_name": "string",
    "product_description": "string (optional)",
    "lot_identifier": "string",
    "brand_owner_gln": "string (GLN)",
    "manufacturer_gln": "string (GLN, optional)",
    "ndc_code": "string (optional)",
    "parent_product_gtin": "string (optional)"
  },
  "quantity": "number (> 0)",
  "unit_of_measure": "string (one of KG, LB, CASE, PALLET, ...)",
  "location_involved": "string (GLN, varies by event type)",
  "source_event_id": "string (UUID or URN from source system)",
  "source_format": "string (EPCIS, EDI, API, MANUAL)",
  "canonical_model_version": "string (e.g., 1.2.3)",
  "ingest_timestamp": "string (ISO 8601 UTC, when RegEngine received the event)",
  "event_hash_sha256": "string (SHA-256 hex digest of canonical event)"
}
```

CTE-specific fields are added as needed (e.g., `temperature` for Cooling, `input_products` for Transformation).

---

## Quality and Completeness

The canonical model is validated continuously:

- **CI Integration**: Every commit runs `pytest -m canonical_model` which:
  - Generates synthetic CTEs of all 7 types
  - Normalizes them through all ingestion pathways
  - Verifies they match the expected canonical form
  - Exports them back to EPCIS and re-imports to verify round-trip fidelity

- **Production Monitoring**: The system logs all validation errors and normalizations. If a new pattern emerges (e.g., a product name that cannot be parsed), the security and compliance teams are alerted.

---

## References

- GS1 EPCIS 2.0 Specification: https://www.gs1.org/standards/epcis
- FDA FSMA 204: 21 CFR § 1.1340–1.1350
- GS1 GLN: https://www.gs1.org/standards/gln
- GS1 GTIN: https://www.gs1.org/standards/gtin
- GS1 SSCC: https://www.gs1.org/standards/sscc
