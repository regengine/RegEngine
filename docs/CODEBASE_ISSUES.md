# RegEngine Codebase — Issues to Address

**Audit Date:** February 7, 2026  
**Scope:** Full codebase scan — `services/`, `frontend/src/`, `shared/`, infrastructure files  

---

## 🔴 P0 — Critical (Address Immediately)

### 1. Production Secrets in `.env.production` Are Placeholders
- **File:** `.env.production`
- **Issue:** All critical secrets are still `CHANGE_ME` placeholders — database URLs, Redis, Neo4j, AWS credentials, Supabase.
- **Risk:** Production deployment will fail or connect to wrong resources.
- **Action:** Inject real production secrets via a secrets manager (Vault, AWS Secrets Manager, or Vercel env vars). Remove this file from the repo.

### 2. Hardcoded Credentials in Tracked Files
- **File:** `services/graph/app/verify_migration.py:59-62`
  ```python
  os.environ["NEO4J_URI"] = "bolt://localhost:7687"
  os.environ["NEO4J_USER"] = "neo4j"
  os.environ["NEO4J_PASSWORD"] = "password"
  ```
- **File:** `services/admin/debug_rls.py:9`
  ```python
  os.environ["DATABASE_URL"] = "postgresql+psycopg://app_user:app_password@postgres:5432/regengine_admin"
  ```
- **Risk:** Credential leakage. Even if these are dev-only, they set a dangerous pattern.
- **Action:** Move to environment variables or guard behind `if ENVIRONMENT == "dev"` checks.

### 3. Owner Dashboard Auth Bypassed (SEC-006)
- **Status:** ACTIVE
- **Issue:** The Executive Owner Dashboard (`/owner`) was patched to skip Admin Master Key validation to avoid redirect loops. No auth gate is currently enforced.
- **Risk:** Unauthenticated access to business analytics and tenant data.
- **Action:** Re-implement proper auth gate with session-based flow.

### 4. Auth Stubs in Production Services (DEBT-024)
- **Files:** `services/automotive/app/auth.py:30`, `services/gaming/app/auth.py:30`
  ```python
  # TODO: Validate against database or secrets manager
  ```
- **Risk:** These services accept any API key that matches a hardcoded pattern, bypassing real auth.
- **Action:** Integrate with the shared auth/API key infrastructure.

---

## 🟠 P1 — High Priority (Address This Sprint)

### 5. Bare `except:` Clause (Silent Error Swallowing)
- **File:** `services/ingestion/app/routes.py:381`
- **Issue:** A bare `except:` catches everything including `SystemExit` and `KeyboardInterrupt`, silently swallowing errors.
- **Action:** Change to `except Exception as e:` with proper logging.

### 6. Review Queue Is Fully Stubbed (DEBT-026)
- **File:** `services/admin/app/review_routes.py:48-83`
- **Issue:** All three review endpoints (`list`, `approve`, `reject`) are stub implementations with TODO comments. No actual database queries.
- **Risk:** Curator review workflow is non-functional despite being exposed in the API.
- **Action:** Implement actual database-backed review logic.

### 7. PCOS Components Are Stubbed (DEBT-028)
- **File:** `frontend/src/components/pcos/index.ts:10-27`
- **Issue:** `ComplianceTimeline`, `DocumentTracker`, `RiskHeatMap`, `HowToGuide` are commented out with TODO markers.
- **Risk:** Entertainment/PCOS vertical advertises features it doesn't have.
- **Action:** Implement or remove from feature lists.

### 8. Hardcoded `userId` in Compliance Status (DEBT-029)
- **File:** `frontend/src/app/compliance/status/page.tsx:22`
  ```typescript
  const userId = "current-user"; // TODO: Get from auth context
  ```
- **Risk:** Multi-tenancy violation — all requests appear as the same user.
- **Action:** Integrate with Supabase auth context.

### 9. Kafka Poison Pill Fragility (DEBT-006)
- **Status:** ACTIVE
- **Issue:** Consumers crash on malformed/non-UTF8 Kafka messages. No Dead Letter Queue (DLQ) strategy.
- **Risk:** A single bad message can take down the entire processing pipeline.
- **Action:** Add try/except in deserializer, implement DLQ topic.

### 10. PCOS ROI Calculator Uses Static Multipliers (LOGIC-001)
- **Status:** ACTIVE
- **Issue:** Entertainment budget calculator uses hardcoded static multipliers. Users report inaccurate ROI projections.
- **Action:** Implement dynamic calculation based on actual production data.

### 11. NPM Security Vulnerabilities (4 High Severity)
- **Dependencies:** `xlsx` (Prototype Pollution, ReDoS), `tar` via `@capacitor/cli`
- **Issue:** `xlsx` has no fix available — it's an abandoned package.
- **Action:** Migrate from `xlsx` to `sheetjs-ce` (community edition) or `exceljs`. Evaluate if `@capacitor/assets` is needed.

### 12. Sentry Integration Broken (BLD-002)
- **File:** `frontend/sentry.client.config.ts`
- **Issue:** `@sentry/nextjs` is imported but not in `package.json`. Currently stubbed with a comment saying "DISABLED."
- **Risk:** No error tracking in production.
- **Action:** Either install and configure Sentry properly, or remove the dead config files entirely.

### 13. Scheduler Service Instability (OPS-004)
- **Status:** ACTIVE
- **Issue:** Scheduler consistently fails health checks during stack startup due to Redis/Kafka dependency timing.
- **Action:** Add readiness probes and dependency wait logic.

### 14. NLP Resource Path Fragility (DEBT-027)
- **File:** `services/nlp/app/consumer.py:242`
  ```python
  # Last ditch: try to use the hardcoded relative path that works locally
  ```
- **Risk:** Resource loading breaks in Docker containers.
- **Action:** Use `importlib.resources` or ENV-based path configuration.

---

## 🟡 P2 — Medium Priority (Address This Quarter)

### 15. Pervasive `: any` Type Holes in Frontend (40+ instances)
- **Locations:** `budget_parser.ts` (14 instances), `sysadmin/page.tsx`, `trace/page.tsx`, `SnapshotDetailModal.tsx`, API routes, `ExportButton.tsx`, `CodePlayground.tsx`, and more.
- **Risk:** Type safety erosion — defeats the purpose of TypeScript.
- **Action:** Systematic replacement with proper types. Priority: API routes and data-handling code.

### 16. `console.log` Statements in Production Code
- **Count:** 40+ instances across frontend
- **Notable offenders:**
  - `frontend/src/app/compliance/snapshots/page.tsx:107` — "Using mock snapshots"
  - `frontend/src/app/api/v1/compliance/status/[tenantId]/route.ts:32` — "using demo mode"
  - `frontend/src/app/api/snapshots/[id]/route.ts:118` — "Database query failed, using mock data"
  - `frontend/src/app/pcos/page.tsx:346`
- **Note:** Many in `/playground`, `/developers`, `/api-reference` are code _examples_ shown to users (SAFE). But the ones in API routes and dashboard logic are real debug leaks.
- **Action:** Remove from API routes and dashboard logic. Leave code-example ones.

### 17. Mock Data Hard-Wired Into Production Pages
- **Locations:**
  - `frontend/src/app/owner/page.tsx:28` — "Mock data for demo"
  - `frontend/src/app/snapshots/page.tsx:15` — "Mock data for now"
  - `frontend/src/app/energy/dashboard/page.tsx:5` — "Mock data"
  - `frontend/src/app/pcos/page.tsx:32` — "Mock data for demonstration"
  - `frontend/src/app/api/snapshots/[id]/route.ts` — Full `MOCK_SNAPSHOTS` object with fallback
  - `frontend/src/app/verticals/gaming/dashboard/api.ts` — "Mock data for Gaming"
  - `frontend/src/app/verticals/technology/dashboard/api.ts` — "Mock data implementation"
  - `frontend/src/app/verticals/nuclear/dashboard/api.ts` — "Mock data implementation"
  - `frontend/src/app/verticals/healthcare/dashboard/api.ts` — "Mock data implementation"
  - `frontend/src/app/verticals/entertainment/dashboard/api.ts` — "Mock data"
- **Risk:** Users see fake data in what appears to be production dashboards. API routes serve mock data with `X-Data-Source: MOCK` headers.
- **Action:** Connect dashboards to real backend APIs or clearly label as "Demo Preview."

### 18. Unpinned Dependencies in Two Services
- **Files:** `services/internal/requirements.txt`, `services/scheduler/requirements.txt`
- **Issue:** No version pinning (`==`) — uses `>=` ranges only. All other services properly pin.
- **Risk:** Non-reproducible builds; dependency updates may break services silently.
- **Action:** Pin all dependencies with exact versions.

### 19. Missing Test Suites for Multiple Verticals
- **Services with placeholder tests only:**
  - `services/scheduler/tests/test_placeholder.py` — `assert True`
  - `services/compliance/tests/test_placeholder.py` — `assert True`
- **Services missing from CI matrix:**
  - `aerospace`, `automotive`, `compliance` (real tests), `construction`, `gaming`, `manufacturing`, `nlp`
  - CI only tests: `admin, energy, ingestion, opportunity, graph, internal, scheduler`
- **Action:** Add real tests and include all services in CI pipeline.

### 20. Automotive PPAP Vault Has No Storage (DEBT-025)
- **File:** `services/automotive/app/ppap_vault.py:202`
  ```python
  # TODO: Actually store file to S3 or local storage
  ```
- **Issue:** File upload endpoint accepts files but doesn't persist them.
- **Action:** Implement S3 or local filesystem storage.

### 21. NLP Resolution Service Uses Hardcoded Stub Data
- **File:** `services/nlp/app/resolution.py:8-17`
  ```python
  # Stubbed Master Data (Simulating a MDM System / DUNS Database)
  # Common Suppliers (Stubbed)
  ```
- **Risk:** Entity resolution returns fake supplier data.
- **Action:** Integrate with actual master data source.

### 22. Telemetry Noise in Local Dev (OPS-005)
- **Issue:** `ingestion-service` spams `otel-collector:4317` connection errors in local dev.
- **Action:** Add conditional OTel initialization — only connect when collector is present.

### 23. Path Resolution Fragility (DEBT-004)
- **Issue:** Multiple services rely on `Path(__file__).parents[n]` for resource loading, which breaks when run from different working directories or inside Docker.
- **Action:** Standardize on `importlib.resources` or config-based resource discovery.

### 24. Local Dev Productivity (DEBT-003)
- **Issue:** NLP and Ingestion services lack volume mounts in `docker-compose.yml`, forcing full `docker compose up --build` for every code change.
- **Action:** Add development volume mounts for hot-reload.

### 25. Monolithic Files Need Decomposition
- **Critical offenders:**
  - `services/admin/app/pcos_routes.py` — **3,269 lines** (!)
  - `services/admin/app/pcos_models.py` — **2,185 lines**
  - `services/graph/app/fsma_utils.py` — **1,321 lines**
  - `services/nlp/app/extractors/fsma_extractor.py` — **1,259 lines**
  - `services/ingestion/app/routes.py` — **1,069 lines**
- **Action:** Break into focused modules. `pcos_routes.py` should be split into at least 5-6 domain-specific route files.

### 26. Database Context Split Confusion (DEBT-011)
- **Issue:** `regengine` vs `regengine_admin` logical split causes manual script failures. Cross-DB dependencies aren't documented.
- **Action:** Document the database topology and add health checks that validate cross-DB connectivity.

---

## 🔵 P3 — Low Priority (Backlog)

### 27. Immutable Sandbox Deficiency (DEBT-017)
- **Issue:** Immutability triggers block test data cleanup. CI must use URL-based Run IDs as workarounds.
- **Action:** Implement dedicated test tenants with bypassed immutability or sandbox mode.

### 28. Worker Transaction Patterns Need Standardization (ARCH-001)
- **Issue:** Async workers (NLP, Ingestion) lack a standard boilerplate for Kafka consumer lifecycle.
- **Action:** Create a shared `BaseKafkaWorker` class with proper lifespan management.

### 29. Legacy TODO Comments (DEBT-001)
- **Count:** 13+ identified stubs across the codebase
- **Notable:**
  - `services/energy/app/queries.py:169` — "Migrate to Redis for horizontal scaling"
  - `services/energy/app/models.py:69` — "In production, enforce user_id requirement"
  - `frontend/src/app/pcos/page.tsx:347` — "Integrate with backend API when available"
- **Action:** Convert to tracked issues/tickets.

### 30. Venvs Committed or Lingering in Repo
- **Files:** `services/graph/venv/` (40MB), `services/admin/.venv/` (119MB), `.venv/` (123MB), `.venv-test/` (26MB)
- **Issue:** `.gitignore` ignores `.venv*/` and `venv*/` patterns, but some appear to be tracked or at least present locally, bloating the working tree.
- **Action:** Verify none are tracked via `git ls-files`. Clean up local artifacts.

### 31. Stale Debug/Artifact Files in Root
- **Files:** `login_resp.json`, `ingest_logs.txt`, `ingest_logs_2.txt`, `frontend_logs.txt`, `lifeboat.zip`, `lifeboat_8400.zip`, `lifeboat_final.zip`, `lifeboat_success.zip`, `admin.db`, `.tenants.db`
- **Action:** Delete or add to `.gitignore` (most should already be ignored; verify and clean).

### 32. `print()` Statements in Production Services
- **Files:** `services/graph/app/verify_migration.py`, `services/admin/app/password_policy.py`, `services/admin/app/union_rate_checker.py`, `services/admin/app/verticals/healthcare/service.py`
- **Action:** Replace with `structlog` or `logging` calls.

### 33. Ingestion Scraper Has Stub S3/Kafka Clients
- **File:** `services/ingestion/app/scrapers/state_generic.py:10`
  ```python
  # Stubs for S3 and Kafka integrations; replace with actual clients
  ```
- **Action:** Wire up actual S3 and Kafka clients, or remove if unused.

### 34. Graph Service `.env` File Tracked
- **File:** `services/graph/.env` — present in the filesystem but the root `.gitignore` should exclude it.
- **Action:** Verify it's not tracked, and if it contains secrets, rotate them.

---

## 📊 Summary

| Priority | Count | Category Breakdown |
|----------|-------|--------------------|
| 🔴 **P0** | 4 | Security (3), Config (1) |
| 🟠 **P1** | 10 | Security (2), Reliability (3), Integrity (3), DevOps (2) |
| 🟡 **P2** | 12 | Code Quality (4), Testing (1), Architecture (3), DevOps (2), Integrity (2) |
| 🔵 **P3** | 8 | Maintainability (5), Testing (1), Architecture (2) |
| **Total** | **34** | |

---

## Strategic Recommendations

1. **Security Sprint (1-2 days):** Tackle all P0s — rotate hardcoded creds, fix auth bypasses, inject real production secrets.
2. **Code Quality Week:** Systematic sweep of `: any` types, `console.log` cleanup, and mock data labeling.
3. **Testing Initiative:** Add real tests for placeholder services. Expand CI matrix to cover all 14 services.
4. **Architecture:** Plan the "Modular Monolith" consolidation (DEBT-041) to reduce the 14-microservice overhead for a solo founder.
5. **Dependency Hygiene:** Replace `xlsx`, pin `internal` and `scheduler` deps, install or remove Sentry.
