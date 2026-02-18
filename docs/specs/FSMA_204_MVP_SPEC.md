# FSMA 204 MVP Specification (Glass Box)

## Scope and Goals
- Deliver demo-ready FSMA 204 traceability with 24-hour FDA spreadsheet, mock recall, and visual E2E trace.
- Phase focus: Shipping CTE first (fastest path to one-up/one-down), then compliance/reporting, then mock recall/visualizer.
- Transparency (“glass box”): deterministic rules + confidence scores + auditable transformations.

## CTEs (Critical Tracking Events)
- Shipping (Phase 1 focus): movement of a traceability lot between facilities.
- Future (not in this MVP but referenced): Receiving, Transformation, Creation, Depletion. Keep schema extensible with `CTEType` enum.

## KDEs (Key Data Elements)
**Shipping mandatory KDEs (7):**
1) Traceability Lot Code (TLC) — GTIN-14 + variable lot code; pattern: `^\d{14}[A-Za-z0-9\-\.]+$`
2) Quantity
3) Product Description
4) Unit of Measure
5) Ship-from Location
6) Ship-to Location
7) Event Date (ship date)

**Additional useful KDEs (optional for enrichment):**
- SKU/GTIN, Batch aliases, PO number, BOL number, Carrier, ASN/Invoice IDs, Document hash, Confidence scores.

## Graph Schema (Neo4j)
- Nodes
  - `Lot { tlc }`
  - `TraceEvent { type, date }` (type = "SHIPPING" for Phase 1)
  - `Facility { gln, name, address }`
  - `Document { source, hash }`
- Relationships (Shipping ingest)
  - `MERGE (l:Lot { tlc: $tlc })`
  - `CREATE (e:TraceEvent { type: "SHIPPING", date: $date })`
  - `MERGE (from:Facility { gln: $ship_from_gln })`
  - `MERGE (to:Facility { gln: $ship_to_gln })`
  - `MERGE (from)-[:SHIPPED]->(e)-[:INCLUDED]->(l)`
  - `MERGE (e)-[:SHIPPED_TO]->(to)`
- Extension hooks: add properties for quantity, unit, product_description on `TraceEvent` or edge metadata if needed; support multi-tenant via existing `Neo4jClient` patterns.

## Kafka Contract (fsma.events.extracted)
- Topic: `fsma.events.extracted`
- Message schema (JSON):
  { 
    "tlc": "string (required)",
    "quantity": "number | null",
    "unit": "string | null",
    "product_description": "string | null",
    "ship_from_gln": "string | null",
    "ship_from_address": "string | null",
    "ship_to_gln": "string | null",
    "ship_to_address": "string | null",
    "date": "ISO 8601 string (required)",
    "document_source": "string | null",  // e.g., s3://... or URL
    "document_hash": "string | null",
    "confidence": "0-1 float",
    "raw_row_index": "int | null"        // line-item index from table extraction
  }
- Emitted by: `FSMAExtractor` (services/nlp) after validation and confidence scoring; high-confidence can also mirror to `graph.update` if reusing existing patterns.

## Extractor Requirements (FSMAExtractor)
- Location: `services/nlp/app/extractors/fsma_extractor.py`
- Base: `BaseExtractor`
- Inputs: text + layout (OCR with line clustering / table detection)
- Outputs: list of FSMA events (one per table row when tabular structure detected) with confidence scores.
- TLC detection: regex for labels ("Lot:", "L/C:", "Batch:") and GTIN-14 + variable lot; allow hyphen/dot. Fallback SKU/GTIN heuristics when TLC not explicitly labeled.
- Table/line-item analysis: detect rows via existing OCR line clustering; each row yields a candidate event; attach row index.
- Confidence: elevate when TLC + product + from/to present in same row; reduce when inferred across rows.
- Mandatory KDE enforcement: TLC and date must be present to emit; log/route low-confidence to review if pipeline supports.

## Pydantic Models (shared/schemas.py additions)
- `class CTEType(str, Enum): SHIPPING = "SHIPPING"` (extensible)
- `class Location(BaseModel): gln: Optional[str]; name: Optional[str]; address: Optional[str]`
- `class ProductDescription(BaseModel): text: str; sku: Optional[str] = None; gtin: Optional[str] = None`
- `class KDE(BaseModel): name: str; value: Any; confidence: Optional[float] = None`
- `class FSMAEvent(BaseModel): tlc: str; cte_type: CTEType = CTEType.SHIPPING; date: datetime; quantity: Optional[float]; unit: Optional[str]; product: Optional[ProductDescription]; ship_from: Optional[Location]; ship_to: Optional[Location]; document_source: Optional[str]; document_hash: Optional[str]; raw_row_index: Optional[int]; kdes: List[KDE] = []`
- Ensure JSON-serializable; use canonical shared import pattern.

## FDA 24-Hour Spreadsheet Mapping (CSV)
- Generator: `services/compliance/fsma_spreadsheet.py` → `generate_fda_spreadsheet(tlc, start_date, end_date)` using Pandas.
- Columns (flattened rows ordered by event date):
  - Traceability Lot Code
  - Event Type (SHIPPING)
  - Event Date (ISO8601)
  - Quantity
  - Unit
  - Product Description
  - Ship From GLN
  - Ship From Name
  - Ship From Address
  - Ship To GLN
  - Ship To Name
  - Ship To Address
  - Source Document
  - Document Hash
  - Confidence
- REST: `GET /fsma/audit/spreadsheet?tlc={id}&start_date={...}&end_date={...}` returns downloadable `.csv` (auth via `X-RegEngine-API-Key`).

## Validation Rules
- TLC format regex: `^\d{14}[A-Za-z0-9\-\.]+$` (use in `services/compliance/fsma_engine.py` and plugin rule `invalid_tlc_format` in `industry_plugins/food_beverage/fsma_204.yaml`).
- Required KDEs for Shipping: TLC and Date; warn if missing ship_from/ship_to/product/quantity.

## Trace Forward (One-Up/One-Down)
- Function: `trace_forward(tlc_id)` in `services/graph/app/fsma_utils.py` returns ordered hops (facility chain) following `SHIPPED`/`SHIPPED_TO` relationships from the lot’s shipping events.

## Demo/Testing Artifacts
- Golden sample test: `services/nlp/tests/test_fsma_extractor.py` using provided BOL PDF; assert TLC extraction `GTIN-14 + Lot-123` and presence of 7 KDEs.
- Demo data seeder: `scripts/demo/seed_fsma_data.py` to create Farm → Packer → Distributor → Retailer chain with ~50 events.

## Global Harmonization & Impact Analysis (Phase 29-30)
- **Semantic Mapping** – Using `MappingEngine` (shared/graph/mapping_engine.py) to link FSMA 204 obligations to equivalent requirements in other jurisdictions (e.g., EMA, PMDA).
- **Supply Chain Linking** – Using `TraceabilityLinker` (shared/graph/traceability_linker.py) to establish `GOVERNS` relationships between obligations and `TraceEvent`/`Lot` nodes.
- **Impact Querying** – Sub-second identification of shipments impacted by specific regulatory updates.

**New Linkage Metadata:**
- Relationship: `(Obligation)-[:GOVERNS {link_type: 'keyword_match', confidence: float}]->(TraceEvent)`
- Relationship: `(Obligation)-[:MAPPED_TO {justification: string}]->(Obligation)`

## Security & Logging
- All service endpoints: require `X-RegEngine-API-Key` (use `require_api_key`).
- Structured logging via `structlog` with `request_id`/`correlation_id`; avoid logging raw PII.
- Tenant isolation: follow existing `Neo4jClient` tenant routing; scope queries appropriately.

## Non-blocking Known Gaps (from repo instructions)
- Scrapers: `nydfs.py` returns empty bytes (not used for FSMA MVP).
- Scheduler: missing auto-ingestion trigger; can be deferred for demo.
- Compliance service absent from docker-compose; ensure it’s started (e.g., `uvicorn services.compliance.main:app --port 8500`) for spreadsheet and validation endpoints.