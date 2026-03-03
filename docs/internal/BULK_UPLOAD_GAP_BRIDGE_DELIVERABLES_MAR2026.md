# RegEngine
# Bulk Upload Tool + Gap Bridge Deliverables
## Complete File Inventory, Integration Guide, and Alignment Map

March 2026

18 files changed | 5 new bulk-upload endpoints | 6 new backend tests | 4 onboarding gaps bridged

## 1. Executive Summary

This document captures what actually shipped for the supplier bulk-upload workstream and how it aligns to onboarding friction and audit-integrity goals.

The implementation is live in `main` and passed CI on commit `d46459f05b0f147a55b96be9f76a9b0d3923d512`.

What shipped:
- File-based supplier onboarding (CSV/XLSX/JSON/PDF) with parse -> validate -> commit session flow.
- Idempotent upsert behavior for facilities, FTL scope, and TLCs.
- Cryptographic parity with manual CTE creation by reusing the same tenant-wide hash/Merkle service path.
- Frontend onboarding entry point and standalone bulk upload page.

Not in this sprint:
- Exemption triage tool flow (`/tools/exemption-triage`).
- FDA drill grading endpoint (`/fda-drill`).

## 2. Alignment Map

| Objective | Pre-existing State | Gap | Shipped Bridge |
|---|---|---|---|
| High-volume onboarding without manual form entry | Supplier flow existed but required step-by-step data entry | Friction for large supplier datasets | Added bulk upload parse/validate/commit endpoints + onboarding page |
| Cryptographic trust parity | Manual CTE endpoint already produced hash + tenant-wide Merkle chain | Bulk path could diverge from verification model | Extracted shared CTE service and reused in bulk transaction manager |
| Safe ingestion before commit | No supplier parse/preview stage | Risk of bad writes and unclear row errors | Added validation preview with dependency order and row errors |
| Retry safety and repeatability | No supplier upload session state | Duplicate writes/retry ambiguity | Session-based workflow with statuses and idempotent commit behavior |

## 3. Complete File Inventory

### Backend (Admin Service)

New files:
- `services/admin/app/supplier_cte_service.py`
- `services/admin/app/bulk_upload/__init__.py`
- `services/admin/app/bulk_upload/parsers.py`
- `services/admin/app/bulk_upload/validators.py`
- `services/admin/app/bulk_upload/session_store.py`
- `services/admin/app/bulk_upload/transaction_manager.py`
- `services/admin/app/bulk_upload/templates.py`
- `services/admin/app/bulk_upload/routes.py`

Updated files:
- `services/admin/app/supplier_onboarding_routes.py` (shared CTE service reuse)
- `services/admin/main.py` (bulk router mount)
- `services/admin/requirements.txt` (bulk parser deps)

### Frontend

New files:
- `frontend/src/app/onboarding/bulk-upload/page.tsx`

Updated files:
- `frontend/src/lib/api-client.ts`
- `frontend/src/types/api.ts`
- `frontend/src/app/onboarding/supplier-flow/page.jsx`

### Tests

New files:
- `services/admin/tests/test_bulk_upload_parsers.py`
- `services/admin/tests/test_bulk_upload_validators.py`
- `services/admin/tests/test_bulk_upload_e2e.py`

## 4. API Endpoints in Scope

### New bulk-upload endpoints

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/v1/supplier/bulk-upload/parse` | Upload file and create parse session | Supplier auth |
| POST | `/v1/supplier/bulk-upload/validate` | Validate session payload and return preview | Supplier auth |
| POST | `/v1/supplier/bulk-upload/commit` | Execute idempotent transaction + chain events | Supplier auth |
| GET | `/v1/supplier/bulk-upload/status/{session_id}` | Read session status/summary | Supplier auth |
| GET | `/v1/supplier/bulk-upload/template` | Download CSV/XLSX template | Supplier auth |

### Existing endpoints used by the same onboarding loop

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/supplier/facilities/{id}/cte-events` | Manual event path that bulk now matches cryptographically |
| GET | `/v1/supplier/export/fda-records/preview` | Preview export rows |
| GET | `/v1/supplier/export/fda-records` | Download FDA-ready CSV/XLSX |

## 5. Integration Steps

Required:
1. Ensure admin service includes bulk router mount in `services/admin/main.py`.
2. Ensure dependencies in `services/admin/requirements.txt` are installed (`pdfplumber`, `openpyxl`, `python-multipart`, `redis`).
3. Set `REDIS_URL` for persistent upload sessions (module includes in-memory fallback if Redis unavailable).

Already wired in this branch:
4. Frontend typed API client methods in `frontend/src/lib/api-client.ts`.
5. Bulk upload route page at `/onboarding/bulk-upload`.
6. Supplier flow entry link and endpoint spec updates in `frontend/src/app/onboarding/supplier-flow/page.jsx`.

Validation commands:
7. Backend syntax check (already used in this sprint):
   - `python3 -m py_compile services/admin/app/bulk_upload/*.py services/admin/app/supplier_cte_service.py`
8. Frontend lint on changed files:
   - `npm run lint -- --file src/app/onboarding/bulk-upload/page.tsx --file src/app/onboarding/supplier-flow/page.jsx --file src/lib/api-client.ts --file src/types/api.ts`

## 6. Data Flow

1. User enters supplier onboarding and follows bulk-upload link.
2. File is uploaded to `/v1/supplier/bulk-upload/parse`.
3. Parser normalizes detected rows into facilities, FTL scope, TLCs, and CTE events.
4. Validation endpoint enforces dependency order and returns create/update/error preview.
5. Commit endpoint runs one transaction:
   - facilities upsert
   - FTL scope upsert
   - TLC upsert
   - CTE append through shared `_persist_supplier_cte_event` (tenant-wide chain parity)
6. Neo4j sync hooks run for scoped facilities and emitted CTE events.
7. Data is immediately available to compliance/gap scoring and FDA export endpoints.

## 7. Test Suite Status

New test coverage added in this sprint:
- `test_bulk_upload_parsers.py` (2 tests)
- `test_bulk_upload_validators.py` (3 tests)
- `test_bulk_upload_e2e.py` (1 test)

CI status for fix commit `d46459f05b0f147a55b96be9f76a9b0d3923d512`:
- Backend Services CI/CD: success
- Frontend CI/CD: success
- security: success
- Test Suite Health Check: success
- Deploy to Railway: success

Admin pytest summary from CI:
- `221 passed, 27 skipped`

## 8. Key Design Decisions

- Hash parity is strict: bulk CTE events use the same canonical JSON hash and Merkle progression as manual events.
- Chain model is tenant-wide parity (no separate per-TLC chain model).
- Validation is dependency-ordered so downstream references can resolve entities created in the same batch.
- Commit is idempotent at session level (`completed` session returns prior summary instead of rewriting).
- Session lifecycle is explicit (`parsed`, `validated`, `processing`, `completed`, `failed`) with TTL-based cleanup.

## 9. Remaining Work

1. Add large-batch async processing mode for very large uploads (current commit path is synchronous).
2. Expand parser robustness for low-structure PDFs and add confidence/error UX in frontend table form.
3. Add optional import audit tables if long-term row-level provenance beyond existing supplier tables is required.
4. Add deeper E2E cases for XLSX/PDF commit paths and duplicate-row conflict policies.
