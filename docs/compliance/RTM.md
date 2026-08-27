# Requirements Traceability Matrix (RTM) - FSMA 204

| Rule Section | Requirement Description | System Component | Implementation Artifact | Verification |
|--------------|-------------------------|------------------|-------------------------|--------------|
| **§ 1.1300** | **Traceability Plan** | Compliance Service | `services/compliance/fsma_engine.py` — **path does not resolve; unverified** | Unit Tests |
| § 1.1300(a) | Maintain a description of reference records | Ingestion Service | `services/ingestion/app/models.py` | Schema Validation |
| § 1.1300(b) | List of foods on Food Traceability List (FTL) | NLP Service | `services/nlp/app/extractors/fsma_extractor.py` — **path does not resolve; unverified** | Extraction Tests |
| **§ 1.1325–1.1345** | **Records of Critical Tracking Events (CTEs)** | Graph Service | `services/graph/app/models.py` — **path does not resolve; unverified** | Graph Schema |
| § 1.1325 | Harvesting/Cooling (Location, Date, Quantity) | Graph Service | `services/graph/app/routers/trace.py` — **path does not resolve; unverified** | Trace E2E Test |
| § 1.1327 | Initial Packing (Pack date, input lots, harvester) | Ingestion Service | `services/ingestion/app/parsers/` — **path does not resolve; unverified** | Parser Tests |
| § 1.1330 | First Land-Based Receiver (Landing date, vessel, BOL) | Graph Service | `services/graph/app/routers/trace.py` — **path does not resolve; unverified** | Trace E2E Test |
| § 1.1335 | Shipping (TLC Source, Previous Source) | Ingestion Service | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE`) + `services/ingestion/app/webhook_router_v2/validation.py` (`_validate_event_kdes`) | `services/ingestion/tests/test_inflow_lab_contract.py`, `services/ingestion/tests/test_csv_templates.py` |
| § 1.1340 | Receiving (Location, Date, Quantity, TLC) | Ingestion Service | `services/ingestion/app/webhook_models.py` (`REQUIRED_KDES_BY_CTE`) + `services/ingestion/app/webhook_router_v2/validation.py` (`_validate_event_kdes`) | `services/ingestion/tests/test_inflow_lab_contract.py`, `services/ingestion/tests/test_csv_templates.py` |
| § 1.1345 | Transformation (Input/Output Lots) | Compliance Service | `services/compliance/fsma_engine.py` — **path does not resolve; unverified** | Mass Balance Logic |
| **§ 1.1310** | **Validation & Verification** | Operations | `docs/runbooks/fda-audit-checklist.md` | Manual Audit |
| § 1.1455(b) | **Electronic Sortable Spreadsheet** | Compliance Service | `services/compliance/fsma_spreadsheet.py` — **path does not resolve; unverified** | Output Verification |
| **NFR** | **24-Hour Recall Response** | Graph Service | `services/graph/app/routers/recall.py` — **path does not resolve; unverified** | SLA Load Tests |
| **NFR** | **System Availability (99.9%)** | Infrastructure | `docker-compose.yml` (Health Checks) — **path does not resolve; unverified** | Uptime Monitoring |

## Known Defects In This Matrix

This matrix is not currently self-consistent with the code it cites. Two defects are
known and unresolved; do not treat the affected columns as audit evidence until an
owner has signed off on a correction.

1. **The CTE rule-section numbers are shifted relative to 21 CFR part 1 subpart S.**
   The implementing code uses FDA's numbering: `REQUIRED_KDES_BY_CTE` in
   `services/ingestion/app/webhook_models.py` cites § 1.1340 for Shipping, § 1.1345 for
   Receiving and § 1.1350 for Transformation, and treats § 1.1335 as First Land-Based
   Receiving. The "Rule Section" column above pairs those same descriptions with
   § 1.1335, § 1.1340 and § 1.1345. Where the two disagree, the in-code citations are
   authoritative and the **Requirement Description** column — not the Rule Section
   column — identifies which requirement a row is about. Renumbering the table is a
   compliance change requiring owner sign-off and was out of scope for issue #2975.

2. **Most rows cite implementation artifacts that are not present in the tree.**
   Only the § 1.1335 and § 1.1340 rows were reconciled against the code (issue #2975).
   Every other Implementation Artifact path was checked and is marked inline as
   **path does not resolve; unverified** where the file or directory is absent. Those
   rows name no working control today: the requirement is recorded but the evidence
   behind it is not. They need the same treatment the two reconciled rows received —
   find the code that actually implements each requirement and cite it.

## Completion Status
- **Regulatory Coverage**: not verified. The claim of full CTE coverage that previously
  stood here was not supported by the artifact citations in this table; see Known
  Defects above.
- **Validation**: the § 1.1335 and § 1.1340 rows cite passing automated tests. The
  remaining rows' verification claims have not been re-checked.
