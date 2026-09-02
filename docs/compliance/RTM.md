# Requirements Traceability Matrix (RTM) - FSMA 204

Every Rule Section below was verified against the live eCFR text of 21 CFR part 1
subpart S (issue #3007; verified 2026-09-02 at
https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S).
Every Implementation Artifact path resolves in this repository and is enforced by
the docs link gate (`scripts/check_docs_links.py`, run in CI), which covers
`docs/compliance/`.

| Rule Section | Requirement Description | System Component | Implementation Artifact | Verification |
|--------------|-------------------------|------------------|-------------------------|--------------|
| **§ 1.1315** | **Traceability Plan** | Shared | `services/shared/fsma_plan_builder.py` (`TraceabilityPlan`, plan builder) | `tests/test_fsma_plan_builder.py` |
| § 1.1315(a)(1) | Description of record-maintenance procedures (format and location of records) | Shared / Ingestion Service | `services/shared/fsma_plan_builder.py` (records-maintenance plan section); record store schema in `services/ingestion/app/models.py` | `tests/test_fsma_plan_builder.py`, Schema Validation |
| § 1.1315(a)(2) | Procedures to identify foods on the Food Traceability List (FTL) | Ingestion Service | `services/ingestion/app/product_catalog.py` (FTL catalog, `FTL_CATEGORIES`) | `services/ingestion/tests/test_product_catalog_1342.py` |
| **§ 1.1325–§ 1.1350** | **Records of Critical Tracking Events (CTEs)** | Ingestion Service | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE`) + `services/ingestion/app/webhook_router_v2/validation.py` (`_validate_event_kdes`) | `services/ingestion/tests/test_inflow_lab_contract.py`, `services/ingestion/tests/test_csv_templates.py` |
| § 1.1325 | Harvesting/Cooling (harvest/cooling date, location, quantity) | Ingestion Service | `services/ingestion/app/webhook_models.py` (`HARVESTING`, `COOLING` KDE lists) | `services/ingestion/tests/test_inflow_lab_contract.py` |
| § 1.1330 | Initial Packing (pack date, harvester business name, TLC assignment) | Ingestion Service | `services/ingestion/app/webhook_models.py` (`INITIAL_PACKING` KDE list) | `services/ingestion/tests/test_inflow_lab_contract.py` |
| § 1.1335 | First Land-Based Receiver (landing date, receiving location, TLC assignment) | Ingestion Service | `services/ingestion/app/webhook_models.py` (`FIRST_LAND_BASED_RECEIVING` KDE list) | `services/ingestion/tests/test_inflow_lab_contract.py` |
| § 1.1340 | Shipping (TLC source, ship-from/ship-to locations, ship date) | Ingestion Service | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE`) + `services/ingestion/app/webhook_router_v2/validation.py` (`_validate_event_kdes`) | `services/ingestion/tests/test_inflow_lab_contract.py`, `services/ingestion/tests/test_csv_templates.py` |
| § 1.1345 | Receiving (location, date, quantity, TLC, immediate previous source) | Ingestion Service | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE`) + `services/ingestion/app/webhook_router_v2/validation.py` (`_validate_event_kdes`) | `services/ingestion/tests/test_inflow_lab_contract.py`, `services/ingestion/tests/test_csv_templates.py` |
| § 1.1350 | Transformation (new TLC, input lot linkage per § 1.1350(a)(1)) | Ingestion Service | `services/ingestion/app/webhook_models.py` (`TRANSFORMATION` KDE list, `input_traceability_lot_codes`) | `services/ingestion/tests/test_inflow_lab_contract.py` |
| **§ 1.1455(c)** | **Record availability to FDA on request (24-hour window)** | Operations | `docs/runbooks/fda-audit-checklist.md` | Manual Audit |
| § 1.1455(c)(3)(ii) | Electronic Sortable Spreadsheet | Ingestion Service | `services/ingestion/app/fda_export/` (`formatters.py`, `router.py`) | `services/ingestion/tests/test_fda_export_formatters_1342.py`, `services/ingestion/tests/test_fda_export_completeness_2698.py` |
| **NFR** | **24-Hour Recall Response** | Ingestion Service | `services/ingestion/app/recall_report.py` (`/api/v1/recall` readiness reporting) | `services/ingestion/tests/test_recall_report_1342.py` |
| **NFR** | **System Availability (99.9%)** | Infrastructure | `railway.toml` (`healthcheckPath = "/readiness"`) + `server/main.py` (`/readiness` deep probe) | Railway health checks / Uptime Monitoring |

## Section Numbering Decision (issue #3007)

An earlier revision of this matrix carried CTE rule sections shifted one CTE
relative to 21 CFR subpart S (e.g. Initial Packing as § 1.1327 — a section that
does not exist — and Shipping as § 1.1335). Per the acceptance criteria of
issue #3007, each section number was verified against the eCFR text of subpart S.
Result: **the implementing code's section-level mapping was correct and the
matrix was wrong.** The authoritative mapping is:

| CTE | Subpart S section |
|---|---|
| Harvesting / Cooling | § 1.1325 |
| Initial Packing | § 1.1330 |
| First Land-Based Receiver | § 1.1335 |
| Shipping | § 1.1340 |
| Receiving | § 1.1345 |
| Transformation | § 1.1350 |

The matrix rows above were renumbered to match. The traceability-plan rows,
previously labeled § 1.1300 (which is "Who is subject to this subpart?"), were
moved to § 1.1315, and the "Validation & Verification" row, previously labeled
§ 1.1310 (definitions), was recast as the § 1.1455(c) record-availability
requirement it actually tracks. The spreadsheet row moved from § 1.1455(b)
(records kept by another entity) to § 1.1455(c)(3)(ii), which is where the
electronic sortable spreadsheet requirement lives.

Paragraph-level citations inside `services/ingestion/app/webhook_models.py`
were corrected in the same change (they had the right sections but paragraph
references transplanted from neighboring sections). Citation strings seeded by
the rules engine (`services/shared/rules/seeds.py`) carry the same historical
shift and are tracked separately as issue #3035 — those are runtime, user-facing
values with pinned tests and seeded tenant data, so they need their own change.

## Completion Status

- **Traceability**: every row cites an implementation artifact path that resolves
  in this repository. This is enforced by `scripts/check_docs_links.py` in CI.
- **Validation**: rows citing automated tests name test files that exist and run
  in the standard suite. The two Manual Audit / Uptime Monitoring rows are
  operational controls without automated verification; they are labeled as such
  rather than counted toward any coverage figure.
- No aggregate coverage percentage is claimed. The previous "Regulatory
  Coverage: 100%" figure was removed in #2975 because it was not derived from
  the table; a percentage will only be reinstated if it is computed from rows
  with resolving artifacts and passing verification.
