# Backend security QA supporting report

PR: opened by orchestrator

CI status: pending at time of writing

Scope: local source review and in-process tests at `0927b85a`, branch `qa/2026-10-02-sweep`. This report contributes to the Backend QA group; it is not a fourth QA group. Review began 2026-10-03 00:35:58 UTC after the interrupted session resumed. The existing scripts and artifacts were preserved. No product behavior, migration, deployment, environment file, production service, real database, or credential was changed or contacted.

## Result

Two High findings are confirmed by current source and isolated regression witnesses: BE-010 (streaming request size bypass), BE-011 (supplier bearer capability disclosed in FDA exports). Gate independently reviewed both source paths. No Critical findings were established in this scoped review. This is not a claim that the remaining application is free of vulnerabilities.

The dedicated regressions contribute **3 passing controls and 2 expected failures** to the combined new-test run. The combined Backend run reports `12 passed, 13 xfailed`; `--runxfail` deliberately reports `13 failed, 12 passed`, including both security defects. See [normal regression output](artifacts/backend/20261003T003959.582650Z-added-regressions.txt) and [negative-control output](artifacts/backend/20261003T004024.567761Z-exposed-defect-evidence.txt). The expected failures are strict and restricted to assertion failures, so unrelated import/runtime errors do not silently count as reproduced bugs.

## Exploratory charters and method

| UTC session | Charter | Method and outcome |
|---|---|---|
| 00:36–00:38 | Follow an untrusted request into body parsing, tenant resolution, and public proof verification. | Compared middleware registration order, actual byte reads, and permission dependencies. Found BE-010. Checked idempotency fingerprinting separately: it already bounds actual request bytes, but only when an eligible authenticated request uses the cache. |
| 00:37–00:40 | Follow a supplier link capability from creation through submitted evidence to an external FDA artifact. | Traced token creation, capability-only submission authority, KDE persistence, and formatter redaction. Found BE-011 and added a synthetic-only regression with a passing redaction control. |
| 00:38–00:41 | Review auth/permissions matrix, request replay, SSRF controls, dependency inventory, and safety boundaries. | Source review found explicit API-key/session/workload realms, tenant mismatch rejection, operation-bound replay reservations, and redirect revalidation. Current dependency advisory results remain unavailable within allowed network scope. |

Risk choices: shared monolith availability and evidence integrity have high impact; public body parsing and export sharing are plausible entry points. They received dynamic witnesses before broader static review. The test pyramid favors pure formatter/model tests and in-process ASGI tests here; live external services and real storage are explicitly out of scope. No simulated load attack or memory-exhaustion test was attempted.

## Confirmed findings

| ID | Severity | Group | Title | Exact local repro | Expected versus actual | Evidence | Suggested fix |
|---|---|---|---|---|---|---|---|
| BE-010 | High | Backend QA | Global size limiter accepts oversized bodies without Content-Length | Run `test_request_safety.py::test_streamed_body_is_limited_without_content_length` through the guarded Backend runner with `--runxfail`. It mounts the real limiter at 8 bytes and sends two five-byte chunks to an isolated ASGI route that reads its body. No sockets are used. | Expected: 413 before consuming/retaining bytes beyond the cap. Actual: 200 with `bytes_read: 10`. The declared-nine-byte control returns 413 and the eight-byte boundary control succeeds. | `services/shared/request_safety.py:52`, `server/main.py:343`, `services/ingestion/app/proof_verify_router.py:754`; `tests/qa_sweep_20261002/test_request_safety.py:33`; negative-control output lines 90–95. | Enforce actual received byte counts in an outer ASGI receive wrapper, reject over-limit streams before full buffering, and retain header checks as an early rejection only. Add absent/deceptive-length and chunked-body boundaries. |
| BE-011 | High | Backend QA | Supplier bearer link capability is copied into FDA export evidence | Run `test_portal_export_disclosure.py::test_redacted_fda_export_does_not_disclose_portal_capability` through the guarded runner with `--runxfail`. A fake, invalid capability is passed to the real supplier-event builder, then the resulting KDEs to the real CSV formatter with `include_pii=False`. No link is created and no database is used. | Expected: FDA evidence has a non-authorizing source reference; the bearer capability is absent. Actual: the capability is emitted twice in Additional KDEs, as `portal_id` and in fallback `reference_document`. Any still-valid real capability authorizes public supplier submission. | `services/ingestion/app/supplier_portal.py:513`, `:519`, `:651`, `:896`; `services/ingestion/app/fda_export_service.py:273`; `tests/qa_sweep_20261002/test_portal_export_disclosure.py:50`; negative-control output lines 82–89. | Replace the capability with a separate non-authorizing portal record/reference ID at event creation. Exclude capabilities from every evidence/export/log path even when full PII is requested. Do not solve only the `portal_id` field: the reference-document fallback carries the same value. |

BE-010 confidence: high for the in-process bypass. The public proof route calls `request.body()` before its own 5 MB check; FastAPI JSON routes also parse request bodies. Remote ingress buffering/limits and an actual out-of-memory failure were not tested, so the report does not claim a demonstrated production outage.

BE-011 confidence: high for the source-to-formatter disclosure. `supplier_portal.py:962` passes the KDE map to ingestion; `webhook_compat.py:307` and `shared/canonical_event.py:775,820` preserve those fields. Portal tokens are generated with `secrets.token_urlsafe(16)` and default to 90-day validity (`supplier_portal.py:451,651`). The helper/formatter witness is not live database, export-download, or successful unauthorized-submission proof. Export readers with the capability could submit as that supplier while the link remains valid. Existing production exposure is unknown. No real capability was read, logged, or reproduced; all runtime evidence uses an explicitly invalid synthetic fixture. Previously known leaked credentials were not re-investigated.

## Auth and permissions matrix

This is a source-derived expectation matrix, not a claim that each combination was exercised against a full running monolith. Backend suite results are reported separately.

| Actor/context | Intended outcome and reviewed source | Evidence/remaining validation |
|---|---|---|
| Missing/invalid API key in restricted runtime | 401, no fallback from a presented rejected credential to development-open authority. | `services/shared/auth.py:300`, `services/ingestion/app/authz.py:243`. Existing shared-auth suite exercised by Backend. |
| Tenant A key plus tenant B query/header, including wildcard scopes | 403; scope breadth does not grant cross-tenant authority. | `services/ingestion/app/authz.py:346`; FDA routes additionally call tenant resolver (`fda_export/router.py:257`). Real PostgreSQL RLS untested. |
| Tenant key presented on workload provisioning route | Denied: tenantless credential with exact `internal.tenants.create` scope is required. | `services/admin/app/privileged_auth.py:672,691`; no real workload credential used. |
| Workload credential presented on tenant routes | 403 when tenant is absent or `internal.*` scope is present. | `services/shared/auth.py:375`; no production credential used. |
| Browser cookie: revoked/expired session or inactive user | 401; session query requires unrevoked, unexpired session and active user status. | `services/admin/app/auth/session_auth.py:73`; actual cookie-store/RLS behavior untested here. |
| Browser identity with no active tenant membership | 401; multi-membership selection must be trusted and membership must remain active. | `services/admin/app/dependencies.py:438,503,513`. |
| Ordinary user or low-assurance session on global administration | Denied; sysadmin plus WebAuthn/SSO-backed session required. | `services/admin/app/privileged_auth.py:420,453`. |
| Cookie-authenticated mutation through browser proxy | CSRF control belongs to the frontend proxy and is checked by the route adapter. | `server/route_security_policy.py:668`; direct production origin/cookie topology untested. Do not infer CORS alone proves CSRF safety. |
| FDA export scope without PII scope | Redacted fields by default; explicit PII export additionally authorized/audited. | `services/ingestion/app/fda_export/router.py:104,249`; BE-011 shows an authorization capability is outside that redaction. |
| Anonymous request with a valid supplier portal link | Allowed to inspect/submit only to that link’s tenant, with expiry, per-link throttles and subscription check. | `supplier_portal.py:356,896,920`; BE-011 compromises the intended possession boundary if the bearer is exported. |

The committed manifest inventories **250 enabled operations**: 199 tenant-scoped, 29 public, 15 global-sysadmin and 7 workload-only; 180 omitted operations are also recorded. These are committed inventory counts, not a fresh imported-route certification. [Inventory evidence](artifacts/security/20261003T004005.376534Z-manifest-count-and-coverage-map.txt).

## OWASP API Top 10 coverage

| Area | Checks performed | Result/limit |
|---|---|---|
| API1 Broken Object Level Authorization | Credential-bound tenant resolver, query/header mismatch checks, supplier ownership filters, export tenant binding. | Guards identified; no additional BOLA defect established. Real RLS/role grants and full route-by-route two-tenant matrix were not run. |
| API2 Broken Authentication | Session expiry/revocation/active-user checks; API key versus workload separation; bearer capability handling. | BE-011 confirmed. Login/credential lifecycle with real identities intentionally untested. |
| API3 Broken Object Property Level Authorization | FDA default PII redaction versus arbitrary KDE fields. | BE-011 confirmed. Freeform evidence can contain authority-bearing data beyond PII. |
| API4 Unrestricted Resource Consumption | Global byte limiter, public proof buffering, per-link throttles, idempotency stream bounds. | BE-010 confirmed. No stress or OOM experiment; infrastructure caps unverified. |
| API5 Broken Function Level Authorization | Per-operation scopes, sysadmin high assurance, workload exact-scope guard, route allowlist. | No new confirmed gap from sampled routes; exhaustive dynamic authorization matrix remains untested. |
| API6 Unrestricted Access to Sensitive Business Flows | Portal submission, per-link rate limits, retry reservation semantics. | Capability-disclosure impact captured in BE-011; subscription provider and distributed throttles not exercised. |
| API7 Server Side Request Forgery | URL scheme/port/embedded-credential/private-network checks; per-redirect revalidation and pinned HTTP client call. | Source controls at `routes_ingest.py:983,1036,1061`; no real outbound requests or DNS testing. |
| API8 Security Misconfiguration | Production router allowlist, trusted-host/CORS middleware, dangerous local fallback gates. | Sampled source controls identified; deployment/provider configuration deliberately unverified. |
| API9 Improper Inventory Management | Route manifest and explicit omitted-router policy. | Committed inventory counts above; runtime inventory drift is a separate test target. |
| API10 Unsafe Consumption of APIs | URL-fetch status handling, redirect limit, 50 MB response ceiling; exported artifact consistency boundaries. | Source reviewed at `routes_ingest.py:978–1029`; third-party calls were not made. |

## Retry, idempotency and concurrency assessment

`services/shared/idempotency.py:242` fingerprints method, URL, content type, credential, current scopes/jurisdictions and exact bytes. Redis `SET NX` creates a reservation before dispatch (`:333`); conflicting payloads and in-flight replays receive 409, and compare-and-set avoids an expired worker overwriting another reservation (`:393`). Session/cookie operations deliberately bypass this cache (`:299`) so revocation and single-use dependencies still run. These controls were read and existing idempotency tests were included by Backend. This is cache-level duplicate suppression, not exactly-once database execution. Real Redis concurrent workers, process crashes, PostgreSQL transaction races and distributed throttles remain untested under this sweep’s isolation rules.

## Dependency vulnerability audit limitation

A version/lockfile inventory was completed, but **a current vulnerability advisory audit was not completed**. No pip-audit, Safety, or OSV scanner is installed and no advisory database is supplied in the checkout. The orchestrator allows network only for public dependency/browser packages; npm audit/PyPI/OSV advisory API requests fall outside that scope and were not sent. No dependency was labelled safe or vulnerable merely from a remembered advisory.

Observed locks: frontend lockfile v3 with 931 package entries; Next 16.3.5, React 18.3.1, axios 1.20.0, Sentry Next 10.75.1. Backend lock: FastAPI 0.141.1, Starlette 1.6.0, Pydantic 2.13.5, python-multipart 0.0.32, SQLAlchemy 2.0.54, cryptography 50.0.1, httpx 0.28.1, Redis client 8.1.0. Six frontend package entries omit integrity; this alone is not treated as a vulnerability without provenance context. [Dependency evidence](artifacts/security/20261003T003927.913030Z-dependency-inventory.txt).

## Handoff and limitations

Owned test addition: `tests/qa_sweep_20261002/test_portal_export_disclosure.py`. Backend owns `test_request_safety.py` and all pytest scheduling. Every shell command in this lane is timestamped in [SECURITY-SESSION-LOG.md](SECURITY-SESSION-LOG.md); failures from stale guessed source paths are retained in the artifacts.

No product fixes were applied. Recommended security order: prevent capability persistence/export (BE-011), then enforce streaming body limits (BE-010), then obtain an authorized current advisory database/audit and run isolated PostgreSQL/Redis authorization/concurrency suites. No push, commit, draft-PR command, production probe, external authenticated API, credential-file read or key rotation was performed.
