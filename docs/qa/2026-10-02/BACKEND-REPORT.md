# Backend QA pass

PR: opened by orchestrator

CI status: pending at time of writing

## Result and scope

Four Medium input-integrity/error-handling findings were reproduced through the real ingestion routers with authentication and persistence replaced by local fakes. Two High security findings, BE-010 and BE-011, were independently reproduced with the security reviewer; see [SECURITY-REPORT.md](SECURITY-REPORT.md) for their complete impact analysis. Product code was not modified.

The added backend tests comprise 29 cases: **13 passing controls and 16 strict expected failures**, covering six findings. The two Hypothesis properties additionally execute 60 positive finite quantity examples and 80 arbitrary short Unicode input examples, deterministically and without a persistent example database. An unexpected pass fails CI; only `AssertionError` is accepted by the expected-failure markers. Fixture/setup failures remain failures.

These are local unit/ASGI results. Real PostgreSQL RLS, transactions, Redis reservations, Kafka delivery, object storage, billing, external providers, customer data and deployments were not validated. The CSV tests prove what crosses the mocked persistence boundary; they do **not** prove committed database corruption.

## Risk selection and exploratory charters

| Charter | UTC session | Risk / methods | Outcome |
|---|---|---|---|
| BE-C1: ingest/evidence trust boundary | 2026-10-03 00:35–00:38 | High impact × high likelihood: inspect CSV and webhook validators, existing malformed-input/receipt/tenant tests, baseline statement coverage | 65 ingestion tests and 210 shared auth/idempotency/HMAC tests passed; missing local SDK dependency repaired in `/private/tmp` only |
| BE-C2: adversarial input equivalence classes | 00:38–00:46 | High impact × medium likelihood: timestamp timezone classes, finite/nonfinite quantities, duplicate normalized headers, encodings, 0/500/501 event boundaries, deterministic Hypothesis | BE-001 through BE-004 reproduced; source header and numeric ambiguity can reach accepted-event boundary; malformed dates/encodings return 500 |
| BE-C3: auth, retry, resource and export controls | 00:38–00:46 | High impact × medium likelihood: existing permission matrix, HMAC and replay revocation, fake Redis concurrency, tiny chunked body boundary, synthetic portal export | Existing auth/retry tests passed; BE-010 and BE-011 have strict expected-failure witnesses and positive controls |
| BE-C4: breadth and static analysis | 00:40–00:46 | Lower pyramid breadth: guarded existing ingestion/shared suites, admin session/privilege matrix, Ruff bug gate, scoped mypy | Broad results expose test isolation/infrastructure limits; no guard-caused failure is presented as a product vulnerability |

The test pyramid favors inexpensive schema/function tests and in-process ASGI contracts here because real data stores and production connections were explicitly excluded. The highest-impact boundaries received route-level negative cases and positive controls; whole-application/database coverage is not claimed.

## Findings

Run reproductions through `scripts/backend_pytest.py` using the same interpreter and temporary dependency path shown in [BACKEND-SESSION-LOG.md](BACKEND-SESSION-LOG.md). Use `--runxfail --tb=short` to expose the observed failures; omit `--runxfail` for the intended green QA regression run.

| ID | Severity | Group | Title | Exact reproduction | Expected vs actual | Evidence | Suggested fix |
|---|---|---|---|---|---|---|---|
| BE-001 | Medium | Backend | Timezone-naive webhook timestamps produce HTTP 500 | POST `/api/v1/webhooks/ingest` with the valid harvesting payload in `_payload`, `timestamp="2026-04-17T12:00:00"`, and a valid idempotency header. Run `test_webhook_naive_timestamp_is_a_validation_response`. Date-only and fractional naive timestamps also reproduce. | Expected explicit 422 timezone validation; actual 500 `Internal Server Error`. Invalid non-date input correctly returns 422 in the positive control. | `services/ingestion/app/webhook_models.py:201` parses naive datetime; line 209 compares it to aware UTC; `services/ingestion/tests/test_qa_sweep_20261002_contract.py:125`; [observed failure](artifacts/backend/20261003T004024.567761Z-exposed-defect-evidence.txt) | Require a timezone and raise `ValueError` before comparison, or explicitly document/normalize a timezone policy. Preserve a 4xx error for invalid input. |
| BE-002 | Medium | Backend | CSV numeric validation accepts infinity and NaN | POST a one-row harvesting CSV using the fixture header with quantity `inf`, `Infinity`, or `1e309`; separately post transformation CSV with `input_lot_codes=INPUT-QA-001`, `input_quantities=nan/inf/1e309`, `input_units_of_measure=lbs`. Run the two `test_csv_rejects_nonfinite_*` tests. | Expected row rejection before persistence; actual 200 and one invalid event forwarded to fake ingestion. Zero/negative/non-numeric/empty output quantities correctly return 400. Real database outcome is untested. | `csv_templates.py:696`, `:699`, `:827`; `webhook_models.py:179`; [observed failure](artifacts/backend/20261003T004024.567761Z-exposed-defect-evidence.txt) | Enforce finite numbers at both top-level schema and nested input-quantity parser (`allow_inf_nan=False` / `math.isfinite`), then apply positive/nonnegative domain limits. |
| BE-003 | Medium | Backend | Conflicting duplicate CSV headers silently choose the final value | Add a second `quantity` or ` Quantity ` header to the fixture CSV, with original quantity 10 and appended quantity 999. POST `/api/v1/ingest/csv`; run `test_csv_rejects_conflicting_duplicate_headers`. | Expected actionable duplicate-header 400; actual 200 with ingested quantity 999. DictReader/normalization overwrites 10 without reporting a conflict. This is a normalized-event ambiguity, not a claim that retained raw bytes disappear. | `csv_templates.py:732`, `:744`, `:772`; [observed quantity](artifacts/backend/20261003T004024.567761Z-exposed-defect-evidence.txt) | Validate duplicate raw and normalized headers before constructing row dictionaries; reject ambiguous conflicts and identify offending columns. |
| BE-004 | Medium | Backend | Non-UTF8 CSV or photo upload returns HTTP 500 | POST `/api/v1/ingest/csv` with bytes `FF D8 FF E0` (synthetic JPEG prefix), Latin-1 `column\nCaf E9\n`, or UTF-16 prefix. Run `test_csv_non_utf8_upload_returns_client_error`. | Expected encoding/content-type 400/415/422 before persistence; actual 500. UTF-8 BOM control returns 200. No event reaches fake persistence for these invalid encodings. | `csv_templates.py:1371` unguarded `decode("utf-8-sig")`; `test_qa_sweep_20261002_contract.py:187`; [observed HTTP 500](artifacts/backend/20261003T004624.437197Z-invalid-encoding-evidence.txt) | Catch `UnicodeDecodeError` and return a concise client error naming supported encoding; explicitly reject unsupported media types if required by the upload contract. |

BE-010 witness: `tests/qa_sweep_20261002/test_request_safety.py` sends 10 chunked bytes through an 8-byte limiter without Content-Length; actual 200 with `bytes_read=10`, expected 413. Declared oversized and exact-boundary controls pass. No large payload or real network is used.

BE-011 witness: `tests/qa_sweep_20261002/test_portal_export_disclosure.py` constructs a supplier submission with a clearly synthetic capability and generates a redacted FDA CSV. The capability remains in both `portal_id` and `reference_document`. No actual portal token was accessed. Its positive control verifies the lot survives and normal location PII is redacted.

## Verification results

| Selection | Result | Evidence |
|---|---|---|
| Added tests with locked FastAPI/Starlette/Pydantic runtime overlay | 13 passed,16 strict xfailed; all six findings persist | [compatibility run](artifacts/backend/20261003T004902.545619Z-locked-runtime-added-tests.txt) |
| Focused ingestion baseline, 7 existing files | 65 passed | [baseline](artifacts/backend/20261003T003755.090249Z-baseline-ingest-final.txt) |
| Focused ingestion baseline + QA contract tests | 75 passed, 14 strict xfailed | [after](artifacts/backend/20261003T004540.374674Z-ingest-after-final.txt) |
| Focused shared auth/permission/tenant/idempotency/HMAC/canonical baseline | 210 passed, 1 real-Redis case deselected | [baseline](artifacts/backend/20261003T003827.342544Z-baseline-shared.txt) |
| Same shared baseline + export/body-size QA tests | 213 passed, 2 strict xfailed, 1 deselected | [after](artifacts/backend/20261003T004559.647569Z-shared-after.txt) |
| Initial broad existing ingestion | 463 passed, 6 failed, 14 errors, 50 skipped, 15 deselected; stopped at 20 failures | [full attempt](artifacts/backend/20261003T004038.332020Z-broad-ingestion-existing.txt) |
| Initial broad existing shared | 746 passed, 15 subprocess-guard failures, 1 skipped; stopped at 15 | [full attempt](artifacts/backend/20261003T004202.181410Z-broad-shared-existing.txt) |
| Broad shared, omitting live/subprocess-only files | 886 passed, 3 DNS-guard failures, 16 skipped | [in-process scope](artifacts/backend/20261003T004222.708785Z-broad-shared-inprocess.txt) |
| Admin session/privilege + route-manifest checks | 55 passed, 3 failed: two manifest drift assertions and one subprocess guard | [matrix](artifacts/backend/20261003T004257.713724Z-admin-auth-matrix.txt) |
| Admin privilege/session modules alone, final guard | 34 passed; 286/370 statements (77.2973%) | [isolated matrix](artifacts/backend/20261003T004754.305855Z-admin-auth-final.txt) |
| Narrow Ruff bug rules (`E9,F63,F7,F82`) across ingestion/shared/admin/server | Passed | [Ruff](artifacts/backend/20261003T004114.745845Z-static-bug-gate.txt) |
| Focused mypy on csv_templates/webhook_models/request_safety | One existing error: Optional header passed to `len` at csv_templates.py:784 | [mypy](artifacts/backend/20261003T004115.045419Z-typecheck-focus.txt) |

Counts above overlap; they must not be summed into a unique test count. Coverage belongs to the named scopes, not the whole repository. The route-manifest runtime differs only on disabled `graph:GET:/api/v1/provisions/by-request` (179 runtime vs 180 committed omitted operations); enabled classifications remain 250. See the security review for independent source validation and disposition.

The ingestion broad run's 14 collection/setup errors come from `test_boundaries.py:45–58` inserting partial OpenTelemetry modules globally, leaving `opentelemetry.sdk.trace.sampling` unavailable. Six failures involve the intentional DNS/network guard. The shared broad scope's three remaining failures are alternate-loopback URL tests that call real DNS resolution. Fifteen task-queue cases require Docker/testcontainers/Postgres and one database-URL case requires PostgreSQL. None establishes a product defect independently of those limits.

## Coverage

| Product-code scope | Before | After | Delta |
|---|---|---|---|
| Ingestion csv_templates + webhook_models + authz | 531/816 statements = 65.0735% | 540/816 = 66.1765% | +9 statements / +1.103 percentage points |
| Shared auth + idempotency + webhook_security + permissions + canonical_event | 607/1013 = 59.9210% | 607/1013 = 59.9210% | No statement increase; new witnesses exercise previously uncovered input classes |
| Broad shared module inventory, partial existing run | 4400/14143 = 31.1108% | No comparable after measurement | Includes unexecuted shared modules in denominator |

Raw JSON: [ingestion before](artifacts/backend/coverage-ingest-before.json), [ingestion after](artifacts/backend/coverage-ingest-after.json), [shared before](artifacts/backend/coverage-shared-before.json), [shared after](artifacts/backend/coverage-shared-after.json), [shared broad partial](artifacts/backend/coverage-shared-broad.json). These measure statements, not branch coverage. `webhook_models.py` already had 100% statement coverage before the naive-timestamp defect was found: line coverage does not establish input-class correctness.

## Environment, interruptions, and safety limitations

- Resumed the interrupted sweep in the named worktree at 2026-10-03 00:35 UTC. Existing logs/artifacts/scripts were retained. Branch `qa/2026-10-02-sweep`, origin RegEngine, HEAD `0927b85a` were checked before edits. No commits, pushes, PR creation, deploys or product fixes occurred.
- The main checkout's existing Python 3.11.15 environment was used read-only. Observed versions: pytest 9.0.3, coverage 7.13.5, Hypothesis 6.152.4, FastAPI 0.136.0, Pydantic 2.13.2, httpx 0.28.1. This is not a clean install of `requirements.lock`, whose Hypothesis/Pydantic versions are newer; dependency-exact CI remains pending.
- `typesafe-sdk==0.7.2`, `httpx2==2.12.0`, `httpcore2==2.12.0`, and `truststore==0.10.4` were missing and installed from public packages into `/private/tmp/regengine-qa-backend-deps`. A default uv-cache permission error was resolved by using `/private/tmp/regengine-qa-uv-cache`. Neither the application dependency files nor the existing environment were changed.
- `run_logged.py` scrubs inherited credentials and redacts output. `backend_pytest.py` disables dotenv and plugin autoload, permits only pytest-cov/asyncio/Hypothesis plugins, denies socket connections/DNS/subprocesses/credential-file reads, and now denies SQLAlchemy/native-driver connections. Only local `.coverage*` SQLite artifact files are allowed. Initial over-broad SQLite denial caused two coverage-finalization errors, recorded in the log, then was narrowed to permit those QA artifacts.
- The first broad ingestion collection loaded a remediation fixture that attempted its hardcoded localhost scratch-Postgres availability probe. It reported unavailable and skipped 50 cases; no successful database read/write is evidenced. Native drivers can bypass Python socket audit events, so native/SQLAlchemy connection guards were then added before subsequent collection. This limitation and the corrective guard are preserved in [the guard note](artifacts/backend/20261003T004358.677870Z-guard-hardening-note.txt).
- `.env` files, real credentials and known leaked keys were not read or re-investigated. Tests use only synthetic identifiers and local stubs. Direct production service, database, billing, secret rotation and provider validation remain out of scope.

## Next fix order within this pass

1. Remove the bearer portal capability from exportable evidence (BE-011).
2. Enforce streamed body byte limits independently of Content-Length (BE-010).
3. Reject nonfinite quantities and conflicting CSV headers before accepted-event construction (BE-002, BE-003).
4. Return actionable 4xx validation errors for naive timestamps and unsupported encodings (BE-001, BE-004).
5. Resolve manifest drift/test collection isolation and run the resulting fixes in dependency-exact CI and disposable PostgreSQL/Redis integration environments.

## Locked runtime compatibility check

To rule out the principal framework-version differences, the added tests were rerun with FastAPI 0.141.1, Starlette 1.6.0, Pydantic 2.13.5, pydantic-core 2.46.5, typing-extensions 4.16.0, typing-inspection 0.4.4, annotated-types 0.8.0, annotated-doc 0.0.5 and anyio 4.14.2 installed into a separate `/private/tmp/regengine-qa-locked-deps` overlay. All pins come from the committed requirements.lock. [Import readback](artifacts/backend/20261003T004926.712769Z-locked-runtime-readback.txt) confirms the four core runtime packages loaded from that overlay. Result:13 passed and16 strict xfailed; all six reproduced findings persist. This is a targeted compatibility check, not a clean installation of the entire dependency lock, and it does not replace the original before/after coverage measurements.
