# Recall Fixture Audit — 2026-09-16

Scope: which parts of RegEngine already satisfy the seven requirements for a
small recall-reconstruction demonstration (one manufacturer → one DC → one 3PL →
two destinations; two lots; six pallets; run with complete records, with one
3PL pallet-content record withheld, and with the ERP unavailable). Every row
below was verified by reading the cited code, not from documentation claims.

This is a historical audit. The invented recall scenario and its runner were removed under SEL-447; the generic reconstruction engine remains in `services/shared/recall_reconstruction/`.

## Summary

| Requirement | Working | Missing (before this change) | Now covered by the fixture engine |
|---|---|---|---|
| 1. Worksheet with tri-state labels | tri-state precedent (`EvaluationSummary.compliant`) | any `linked / no_link_established / unresolved` vocabulary; pallet column; last-location and destination derivation | yes (DB-free) |
| 2. Controlled scenario + answer key | DB-free runner pattern (`scripts/run_full_fsma_simulation.py`) | answer key; multi-case runs; `sample_data` wired to anything | yes |
| 3. lot → pallet contents → shipment → receipt → movement | lot-keyed events with raw payload + hash chain; transformation links; SSCC/GLN validators | pallet/container entity; shipment line items; receipt↔shipment link; evidence pointer on every link | yes (in-memory) |
| 4. Splits, mixed pallets, repack, identifier change | split expressible as N transformation rows | mixed pallet; identifier succession; quantity reconciliation across a transformation | yes |
| 5. Expose uncertainty | mass balance per TLC; KDE coverage 409 gate; identity ambiguity blocker | missing-handoff detection; conflicting contents; unmatched identifiers; per-shipment quantity delta | yes |
| 6. ERP independence | export path is Postgres-only; raw retention on the remediation path | persisted last-successful-sync per source; sync time in any export; any ERP-unavailable path | yes (sync manifest + retained snapshot) |
| 7. Practitioner package | FDA ZIP + request package manifest (event-centric) | a lot-level scope worksheet a reviewer can read unaided | yes |

## Working (verified)

- Tri-state "no verdict ≠ negative verdict" — `services/shared/rules/types.py:96-114`.
- Package manifest with hash, scope, gap analysis — `services/shared/request_workflow/assembly.py:211-261`.
- DB-free deterministic runner with pass/fail summary — `scripts/run_full_fsma_simulation.py:326-401`; test `tests/scripts/test_run_full_fsma_simulation.py`.
- Canonical event with verbatim `raw_payload`, provenance, hash chain — `services/shared/canonical_event.py:293-389`; `alembic/sql/V043__canonical_traceability_events.sql:110`.
- Lot → lot lineage table — `fsma.transformation_links`; writer `services/shared/canonical_persistence/writer.py:701-762`.
- SSCC-18 / GLN-13 / GTIN-14 validators — `services/shared/fsma_validation.py`.
- Mass balance per TLC that refuses a verdict on mixed UOM — `services/shared/rules/evaluators/relational.py:356-545`.
- KDE coverage gate (409 below 80% unless `allow_incomplete`) — `services/ingestion/app/fda_export/coverage.py:16-58`.
- Trace CSV never borrows values across events — `services/graph/app/exporters/trace_csv.py:24-28`.
- Identity ambiguity queue + submission blocker — `services/shared/identity_resolution/review.py:31-194`; `assembly.py:588-626`.
- FDA export reads Postgres only, no network — `services/ingestion/app/fda_export/queries.py`.
- Raw file bytes + SHA-256 + per-row `raw_row` + `field_provenance` on the remediation manifest path — `fsma.manifest_blobs`, `fsma.manifest_records` (`alembic/versions/20260716_c7a1e5f2b9d4_v095_supplier_remediation_slice.py:88-125`).
- Attested correction primitive (author, role, reason, attestation, evidence_ref) — `services/ingestion/app/remediation/schemas.py:92-99`, `corrections.py`.

## Missing (verified absent)

- Pallet / container / logistic-unit entity with contents. `transport_reference` is one free-text scalar (`V043:104`). EPCIS `childEPCs`/`parentID` are parsed (`epcis/xml_parser.py:256,264`) then dropped (`epcis/normalization.py:108-124`).
- Shipment header with line items; EDI 856 collapses to one event (`edi_ingestion/routes.py:596-606`).
- Receiving ↔ shipping link record. `immediate_previous_source` / `tlc_source_reference` are KDE strings nothing traverses.
- Evidence pointer on every link. `transformation_links.input_event_id` is a "latest event with that TLC" guess (`writer.py:718-727`).
- Mixed pallet (one event = one TLC + one quantity). Identifier succession for lots/units.
- Missing-handoff detection (`sandbox/tracer.py:36` states the intent; not implemented).
- Conflicting pallet contents, unmatched-identifier report, per-shipment shipped-vs-received delta.
- Persisted last-successful-sync per tenant per source (`external_connectors/base.py:146,267` is an instance attribute; `registry.py:23` is a process-global dict). No sync/freshness field in any export manifest (`fda_export_service.py:764-815`). No ERP-unavailable code path or test.
- Any answer-key concept or multi-variant scenario run.

## Broken (confirmed bugs, out of scope for the fixture change)

Status as of 2026-09-18. Line numbers are from the audit date.

- **Fixed (#3122, #3125).** `/api/v1/ingest/csv` creates no `ingestion_runs` receipt and retains neither the file nor the verbatim row (`services/ingestion/app/csv_templates.py:663`; the only caller of `create_ingestion_run` is `remediation/service.py:101`). Every upload, and every emailed attachment on the inbound-email route, now opens a run and stores the verbatim file before the first row is processed.
- **Fixed (#3119).** CSV normalizer silently defaults a missing quantity to 1, a missing TLC to `UNKNOWN`, and an unknown event type to `receiving` (`services/shared/canonical_event.py:1180,1208-1209`). `normalize_csv_row` raises `CSVRowNormalizationError` per row instead.
- **Fixed (#3120).** Three conflicting input-lot key conventions: rule reads `kdes.input_traceability_lot_codes` (`rules/seeds.py:460`), CSV parser writes `kdes.input_lot_codes` (`csv_templates.py:620`), sandbox writes `input_traceability_lot_codes` (`sandbox/csv_parser.py:222-227`). CSV-ingested transformations fail "Input TLCs Required" even when inputs are present. The rule now reads `kdes.input_lot_codes` first and `kdes.input_traceability_lot_codes` second (migration v124); the sandbox still writes the second key.
- **Fixed (#3121).** `transformation_links.input_quantity` / `input_unit` are never written (`writer.py:738-760`) but `trace_backward` selects them (`writer.py:905`), so backward-trace quantity is always `None`. CSV and EPCIS transformations now carry per-input quantity and unit in `kdes.inputs`, and the writer stores them.
- **Fixed (#3119).** `initial_packing` rows with `input_lot_codes` create no links (`writer.py:703`).
- **Fixed (leftovers PR).** `RecallResult.orphans_found` is never populated; `gaps` = facilities with no lots (`services/graph/app/fsma_recall/engine.py:277-278`). Orphans and per-facility lots and quantities now come from the trace's lot-event associations; `orphans_found` is `None` until a forward trace with associations is measured. The same change removed the `"unknown"` / `"Unknown Facility"` / `"cases"` / trace-direction placeholders `_extract_facilities` wrote, and the `lots` / `quantity` keys it read that the tracer never emits (every production drill had recorded 0% completeness).
- **Fixed (this PR).** Recall-contacts CSV hardcodes `Date Received` / `Quantity Received` empty and `Contact Status="PENDING"` (`services/graph/app/routers/fsma/compliance.py:558-561`). Rows now come from the trace's recorded receiving events (`exporters/recall_contacts_csv.py`); a facility with no receiving event keeps those cells blank, and Contact Status is blank because nothing records a notification outcome.
- **Fixed (#3119).** Default settings fabricate `sensitech last_sync=now()` when no tenant row exists (`services/ingestion/app/settings.py:70-84`).

Found while confirming the above, fixed in the same PR as the recall-contacts CSV:

- `evaluate_field_presence` / `evaluate_multi_field_presence` counted an empty list as present, so `kdes.input_lot_codes == []` passed "Input TLCs Required" while the link writer wrote no links (`services/shared/rules/evaluators/stateless.py`).
- `parse_csv_rows` stamped an unreadable date with `1970-01-01T00:00:00Z`, a missing unit with `"units"`, a missing quantity with `0`, and a missing ship-to with `"See receiver"` (`services/ingestion/app/csv_templates.py`). Each now rejects the row with the reason.
- `normalize_epcis_event` stored a lot identifier under 3 characters as `EPCIS-<id>` and a flat-shape quantity with no unit as `each`; `_validate_as_fsma_event` validated unmapped event types as RECEIVING and stamped `"UNKNOWN"` / `now()` on a missing lot code or event time (`services/shared/canonical_event.py`, `services/ingestion/app/epcis/validation.py`).
- The supplier-portal and mobile-capture canonical bridges wrote `quantity=1.0` / `"each"` when the source had neither (`services/admin/app/supplier_cte_service.py`, `services/graph/app/routers/fsma/traceability.py`).

Leftovers of the same kind, fixed in the follow-up PR after #3125:

- EPCIS `product_description` was synthesized as `EPCIS Product <id>` / `EPCIS Traceability Event` and stored (`services/ingestion/app/epcis/validation.py:96`, `epcis/persistence.py:848`); the legacy EPCIS row stored `"units"` for a missing unit (`epcis/persistence.py:850`) while the canonical row stored `each`. The row now stores the payload's `productDescription` (top-level or ILMD) or an empty cell, and `each` for a CBV count element; a missing `eventTime` is a 422 instead of `now()`.
- Connector mappers defaulted a missing unit to `"units"` and a missing quantity to `1.0` (`services/shared/external_connectors/csv_sftp.py`, `food_safety.py` FoodReady/FoodDocs, `safetyculture.py`). `NormalizedCTEEvent.quantity` / `.unit_of_measure` are now Optional and the ingest schema rejects the event.
- The sandbox parser wrote `input_traceability_lot_codes` (`services/ingestion/app/sandbox/csv_parser.py:222`), a bare string for a single lot, and renamed the writer-compatible `input_lot_codes` column away. It now writes `kdes.input_lot_codes` as a list; tracer, evaluators and the frontend diagnosis alias list read it.

Still open, found while fixing the above:

- Tive (`food_safety.py` `_shipment_to_ctes`, `"cases"` at `:402`), `retailers.py` (`"cases"`, `quantity` / `qty` default `1`) and `inflow_lab.py:74-75` (`"each"`, quantity `0`) keep unit and quantity defaults; connector timestamps fall back to `now()` (`csv_sftp.py`, `food_safety.py`, `safetyculture.py`).
- Connector lot codes are synthesized from the source record id (`FR-<id>`, `FD-<id>`, `SC-<audit_id>`) when the record names none.
- EDI: `_safe_float(value, fallback=1.0)` and `_normalize_unit` → `"units"` (`services/ingestion/app/edi_ingestion/utils.py:80-105`); `edi_ingestion/validation.py:72-75` synthesizes `EDI <set> Item` as the product description.
- NLP tabular extraction stores `Unknown Product` for a missing description (`services/nlp/app/extractors/fsma_extractor/tabular.py:99`).
- `fsma.cte_events` still carries `CHECK (quantity > 0)` (`alembic/sql/V002__fsma_cte_persistence.sql`), contradicting the #1249 comment that zero quantities persist.
- Recall-drill orphan counting cannot see the relationship direction in `trace_rows`, so a lot a transformation produced and nothing shipped is not counted; the count can be low, never high. Returning `type(r)` from the tracer's association query (and teaching `services/graph/tests/_fsma_graph_double.py` to project it) would close that.
- `fsma_recall/__init__.py:62-67` builds a `MockRecallEngine()` with no trace functions wired, so `create_mock_recall` / `get_recall_readiness` always produce `simulated` drills.

## Unverified (needs Postgres or live services; not runnable in the audit environment)

- `CanonicalEventStore.trace_forward/backward` on real data (`writer.py:794,876`).
- Whether `fsma.evidence_attachments` is ever populated in production (no writer found).
- Neo4j tracer paths (`services/graph/app/fsma/tracer.py`); sync is off by default with no deployed consumer (`webhook_router_v2/graph_sync.py:113-130`).

## What the fixture engine does not do

It is in-memory and reads CSVs from a directory. It does not persist to Postgres, does not expose an API route, and does not touch tenant isolation. Those are the next step after practitioner review of the worksheet format.
