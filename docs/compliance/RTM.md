# Requirements Traceability Matrix (RTM) - FSMA 204

| Rule Section | Requirement Description | System Component | Implementation Artifact | Verification |
|--------------|-------------------------|------------------|-------------------------|--------------|
| **§ 1.1300** | **Traceability Plan** | Compliance Service | `services/compliance/fsma_engine.py` | Unit Tests |
| § 1.1300(a) | Maintain a description of reference records | Ingestion Service | `services/ingestion/app/models.py` | Schema Validation |
| § 1.1300(b) | List of foods on Food Traceability List (FTL) | NLP Service | `services/nlp/app/extractors/fsma_extractor.py` | Extraction Tests |
| **§ 1.1305** | **Records of Critical Tracking Events (CTEs)** | Graph Service | `services/graph/app/models.py` | Graph Schema |
| § 1.1305(a) | Harvesting (Location, Date, Quantity) | Graph Service | `services/graph/app/routers/trace.py` | Trace E2E Test |
| § 1.1305(b) | Cooling (Location, Date, Quantity) | Graph Service | `services/graph/app/routers/trace.py` | Trace E2E Test |
| § 1.1305(c) | Initial Packing | Ingestion Service | `services/ingestion/app/parsers/` | Parser Tests |
| § 1.1305(d) | Shipping (TLC Source, Previous Source) | Graph Service | `services/graph/app/consumers/fsma_consumer.py` | Consumer Tests |
| § 1.1305(e) | Receiving (Location, Date, Quantity, TLC) | Graph Service | `services/graph/app/consumers/fsma_consumer.py` | Consumer Tests |
| § 1.1305(f) | Transformation (Input/Output Lots) | Compliance Service | `services/compliance/fsma_engine.py` | Mass Balance Logic |
| **§ 1.1310** | **Validation & Verification** | Operations | `docs/runbooks/fda-audit-checklist.md` | Manual Audit |
| § 1.1455(b) | **Electronic Sortable Spreadsheet** | Compliance Service | `services/compliance/fsma_spreadsheet.py` | Output Verification |
| **NFR** | **24-Hour Recall Response** | Graph Service | `services/graph/app/routers/recall.py` | SLA Load Tests |
| **NFR** | **System Availability (99.9%)** | Infrastructure | `docker-compose.yml` (Health Checks) | Uptime Monitoring |

## Completion Status
- **Regulatory Coverage**: 100% of major CTEs addressed.
- **Validation**: Automated tests cover major flows (Ingestion -> Graph -> Recall).
