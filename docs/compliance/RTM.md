# Requirements Traceability Matrix (RTM) - FSMA 204

| Rule Section | Requirement Description | System Component | Implementation Artifact | Verification |
|--------------|-------------------------|------------------|-------------------------|--------------|
| **§ 1.1300** | **Who is subject to this subpart** (persons who manufacture, process, pack, or hold foods on the Food Traceability List) | Compliance / Rules | `services/shared/rules/ftl.py` (`FTL_CATEGORIES`, `is_ftl_food`) + `services/compliance/app/routes.py` (`POST /validate` FTL gate) | `services/compliance/tests/test_validator_ftl_scoping_1105.py` |
| § 1.1315 | Traceability Plan | Shared / Frontend | `services/shared/fsma_plan_builder.py` + `frontend/src/app/compliance/traceability-plan/page.tsx` | `tests/test_fsma_plan_builder.py` |
| § 1.1315(a)(1) | Description of procedures used to maintain required records, including format and location | Shared | `services/shared/fsma_plan_builder.py` (`RecordLocation`, plan builder) | `tests/test_fsma_plan_builder.py` |
| § 1.1315(a)(2) | Procedures used to identify foods on the Food Traceability List | NLP Service | `services/nlp/app/extractors/fsma_extractor/classification.py` (`FTL_CATEGORIES`, `_classify_ftl`) + `services/shared/rules/ftl.py` | `services/nlp/tests/test_fsma_extractor_epic_e.py`, `services/compliance/tests/test_validator_ftl_scoping_1105.py` |
| **§ 1.1325–1.1350** | **Records of Critical Tracking Events (CTEs)** | Ingestion / Graph | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE`) + `services/graph/app/models/fsma_nodes.py` | Graph schema + KDE contract tests |
| § 1.1325 | Harvesting and cooling (same section: (a) harvest, (b) cooling) | Ingestion Service | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE` HARVESTING / COOLING) + `services/ingestion/app/webhook_router_v2/validation.py` (`_validate_event_kdes`) | `services/ingestion/tests/test_inflow_lab_contract.py`, `services/ingestion/tests/test_csv_templates.py` |
| § 1.1330 | Initial packing of a RAC other than a food obtained from a fishing vessel | Ingestion Service | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE` INITIAL_PACKING) + `services/ingestion/app/csv_templates.py` (no parsers package exists under ingestion; CSV templates are the packing ingest control) | `services/ingestion/tests/test_csv_templates.py`, `services/ingestion/tests/test_inflow_lab_contract.py` |
| § 1.1335 | First land-based receiving of food obtained from a fishing vessel | Ingestion Service | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE` FIRST_LAND_BASED_RECEIVING) + `services/ingestion/app/webhook_router_v2/validation.py` (`_validate_event_kdes`) | `services/ingestion/tests/test_inflow_lab_contract.py`, `services/ingestion/tests/test_csv_templates.py` |
| § 1.1340 | Shipping | Ingestion Service | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE`) + `services/ingestion/app/webhook_router_v2/validation.py` (`_validate_event_kdes`) | `services/ingestion/tests/test_inflow_lab_contract.py`, `services/ingestion/tests/test_csv_templates.py` |
| § 1.1345 | Receiving | Ingestion Service | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE`) + `services/ingestion/app/webhook_router_v2/validation.py` (`_validate_event_kdes`) | `services/ingestion/tests/test_inflow_lab_contract.py`, `services/ingestion/tests/test_csv_templates.py` |
| § 1.1350 | Transformation | Ingestion Service | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE` TRANSFORMATION) + `services/ingestion/app/webhook_router_v2/validation.py` (`_validate_event_kdes`) | `services/ingestion/tests/test_inflow_lab_contract.py`, `services/ingestion/tests/test_csv_templates.py` |
| **§ 1.1310** | **Definitions** (including the seven CTE terms) | Ingestion / Graph | `services/ingestion/app/webhook_models.py` (`WebhookCTEType`) + `services/graph/app/models/fsma_nodes.py` (`CTEType`) | Unit Tests |
| § 1.1455(c)(3)(ii) | **Electronic sortable spreadsheet** of CTE records under §§ 1.1325–1.1350 | Ingestion / Compliance | `services/ingestion/app/fda_export/` + `services/compliance/app/fsma_spreadsheet.py` | `services/ingestion/tests/test_fda_export_router.py`, `services/compliance/tests/test_fda_spreadsheet.py` |
| **NFR** | **24-hour recall / records-request response** (§ 1.1455(c)(1)) | Ingestion / Frontend / Operations | `services/ingestion/app/fda_export/router.py` + `frontend/src/app/dashboard/recall-report/page.tsx` + `docs/runbooks/FDA_RECALL_RESPONSE.md` | `docs/runbooks/fda-audit-checklist.md` (manual audit) |
| **NFR** | **System Availability (99.9%)** | Infrastructure | `docker-compose.dev.yml` (Postgres and Redis health checks) | Uptime Monitoring |

## Numbering

Rule-section numbers follow 21 CFR part 1 subpart S as published on Cornell LII / e-CFR (checked 2026-09-02). They match `REQUIRED_KDES_BY_CTE` in `services/ingestion/app/webhook_models.py` for shipping (§ 1.1340), receiving (§ 1.1345), transformation (§ 1.1350), and first land-based receiving (§ 1.1335).

- **§ 1.1300** is “Who is subject to this subpart.” It has no subsections. The traceability plan is **§ 1.1315**; plan contents used here are **(a)(1)** (record procedures) and **(a)(2)** (FTL identification).
- **§ 1.1310** is definitions, not a validation procedure. `WebhookCTEType` / graph `CTEType` implement the CTE terms defined there.
- **§ 1.1325** covers harvesting and cooling in one section: harvest records, then **(b)** cooling before initial packing.
- **§ 1.1330** is initial packing of a RAC other than food from a fishing vessel. **§ 1.1335** is first land-based receiving from a fishing vessel. There is no § 1.1327.
- **§ 1.1455(b)** is records established by another entity, not the spreadsheet. The electronic sortable spreadsheet is **§ 1.1455(c)(3)(ii)**; the 24-hour availability clock is **§ 1.1455(c)(1)**.

Subsection letters above are only those verified on Cornell LII. The previous matrix had CTE numbers shifted one event earlier and labeled § 1.1300 as the traceability plan.

## Completion Status
- **Regulatory Coverage**: CTE KDE rows now cite the same section numbers as `REQUIRED_KDES_BY_CTE`. General-provision rows use official titles (§ 1.1300 who-is-subject, § 1.1315 traceability plan, § 1.1310 definitions).
- **Validation**: CTE ingest rows and the spreadsheet row cite existing automated tests. Traceability-plan and FTL-scoping rows cite existing unit tests. The 24-hour NFR still relies on the FDA audit runbook for operational verification.
