#!/usr/bin/env python3
"""
RegEngine Second-Pass Audit — GitHub Issue Creator
Findings from Security, Legal/Compliance, SRE, and API/DX sweeps.
Run: GITHUB_TOKEN=ghp_xxx python audit-issues-pass2.py
"""
import os
import sys
import time

try:
    from github import Github, Auth
except ImportError:
    print("pip install PyGithub")
    sys.exit(1)

REPO = "regengine/RegEngine"
TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    print("Set GITHUB_TOKEN env var first.")
    sys.exit(1)

g = Github(auth=Auth.Token(TOKEN))
repo = g.get_repo(REPO)

# Ensure new labels exist
NEW_LABELS = {"pii": "d93f0b", "resilience": "0e8a16", "api-dx": "1d76db", "gdpr": "fef2c0"}
existing = {l.name for l in repo.get_labels()}
for name, color in NEW_LABELS.items():
    if name not in existing:
        try:
            repo.create_label(name, color)
            print(f"  Created label: {name}")
        except Exception:
            print(f"  Skipped label: {name}")

ISSUES = [
    # ==================== P0 — SECURITY / PII ====================
    {
        "title": "[P0][security] PII (email addresses) logged in plaintext in auth and invite routes",
        "labels": ["P0", "security", "backend", "pii"],
        "body": """## Problem
Email addresses are logged in plaintext in structured log fields across auth and invite flows. If logs are shipped to an external aggregator (Datadog, CloudWatch, etc.), this violates data-minimization principles and creates breach surface.

## Files
- `services/admin/app/auth_routes.py` — lines 135, 267, 687 (`email=normalized_email` in logger calls)
- `services/admin/app/invite_routes.py` — lines 45, 51, 87, 89 (`email=recipient_email` in logger calls)

## Action
1. Create a `services/shared/pii_utils.py` with `mask_email(email)` → `c***@regengine.co`
2. Replace all raw email log fields with masked versions
3. Add a grep-based pre-commit hook or CI check: `grep -rn 'email=' services/ | grep 'logger'` should return zero matches
4. Audit other PII fields (names, phone numbers) in log statements
""",
    },
    {
        "title": "[P0][security] JWT signing uses HS256 (symmetric) — migrate to RS256",
        "labels": ["P0", "security", "auth"],
        "body": """## Problem
JWT verification in middleware uses HS256 (symmetric signing). The same secret that signs tokens also verifies them, meaning any service with the verification key can forge tokens. RS256 (asymmetric) separates signing (private key) from verification (public key).

## Files
- `frontend/src/middleware.ts` — line 208: `algorithms: ['HS256']`
- `services/admin/app/auth_routes.py` — JWT signing logic

## Action
1. Generate RS256 key pair (RSA 2048-bit minimum)
2. Update token signing in admin service to use private key
3. Update middleware and all verification points to use public key with `algorithms: ['RS256']`
4. Support a transition period: accept both HS256 and RS256 during rollout, then remove HS256
5. Rotate the current HS256 secret after migration completes
""",
    },
    # ==================== P1 — SRE / RESILIENCE ====================
    {
        "title": "[P1][infra] MemoryJobStore loses scheduled jobs on restart — use persistent store",
        "labels": ["P1", "infra", "backend", "resilience"],
        "body": """## Problem
APScheduler in the scheduler service uses `MemoryJobStore`, which loses all scheduled jobs when the process restarts. Regulatory monitoring jobs (FSMA deadline checks, compliance alerts) silently disappear on deploy or crash.

## Files
- `services/scheduler/main.py` — line 25: `from apscheduler.jobstores.memory import MemoryJobStore`
- `services/scheduler/main.py` — line 87-88: `jobstores = {'default': MemoryJobStore()}`

## Action
1. Replace `MemoryJobStore` with `SQLAlchemyJobStore` backed by Postgres (reuse existing DB connection)
2. Add a startup health check that verifies expected jobs exist and re-registers any missing ones
3. Add monitoring: alert if the scheduler process restarts and job count drops
4. Document the expected job list in a config file for drift detection
""",
    },
    {
        "title": "[P1][compliance] FSMA immutability triggers — verify existence and add integration tests",
        "labels": ["P1", "compliance", "backend"],
        "body": """## Problem
FSMA 204 requires that Critical Tracking Events (CTEs) be immutable once recorded. The codebase references "immutability triggers active" in logging, but there are no integration tests that verify the database triggers actually prevent UPDATE/DELETE on `fsma.cte_events` and `fsma.cte_kdes`.

## Files
- `services/ingestion/app/recall_report.py` — references immutability triggers
- `services/admin/app/compliance_invariants.py` — defines immutability constraints
- `migrations/V002__fsma_cte_persistence.sql` — CTE schema (check for trigger definitions)

## Action
1. Audit migrations to confirm triggers exist that RAISE EXCEPTION on UPDATE/DELETE of cte_events and cte_kdes
2. If triggers don't exist, create a migration to add them
3. Add integration tests that attempt UPDATE and DELETE on cte_events and assert they fail
4. Add a compliance health check endpoint that verifies triggers are active
""",
    },
    {
        "title": "[P1][backend] Graceful shutdown missing in admin, ingestion, nlp, compliance, scheduler services",
        "labels": ["P1", "backend", "resilience"],
        "body": """## Problem
Only the graph service implements graceful shutdown (threading.Event + signal handlers). The other 5 services (admin, ingestion, nlp, compliance, scheduler) have no shutdown handling — in-flight requests and background tasks are killed on deploy.

## Files
- `services/graph/app/consumer.py` — lines 38, 147, 205 (working pattern)
- `services/graph/scripts/fsma_sync_worker.py` — lines 12, 350-351 (signal handler pattern)
- All other services: no signal handlers or shutdown events

## Action
1. Create `services/shared/shutdown.py` with a reusable GracefulShutdown class (signal handler + event)
2. Add shutdown handling to FastAPI lifespan in each service's main.py
3. Ensure APScheduler in scheduler service calls `scheduler.shutdown(wait=True)` on SIGTERM
4. Add health check endpoint that returns 503 during shutdown drain period
""",
    },
    {
        "title": "[P1][backend] Admin POST endpoints lack idempotency keys",
        "labels": ["P1", "backend", "api-dx"],
        "body": """## Problem
Admin service POST endpoints (tenant creation, key creation, invites) don't accept idempotency keys. Network retries or client bugs can create duplicate tenants, keys, or invitations.

## Files
- `services/admin/app/routes.py` — line 451-461 (POST /admin/tenants)
- `services/admin/app/routes.py` — line 316 (POST /admin/keys)
- `services/admin/app/invite_routes.py` — invite creation endpoints

## Action
1. Add optional `Idempotency-Key` header support to all POST endpoints
2. Store idempotency keys in Redis with 24-hour TTL
3. Return cached response for duplicate keys within the TTL window
4. Add `Idempotency-Key` to API documentation
""",
    },
    {
        "title": "[P1][infra] Test coverage thresholds not enforced in CI",
        "labels": ["P1", "infra", "tech-debt"],
        "body": """## Problem
`pyproject.toml` defines test paths but no coverage thresholds. `backend-ci.yml` has per-service thresholds in the workflow file, but there's no enforcement for frontend coverage or for new services added later. Coverage can silently regress.

## Files
- `pyproject.toml` — lines 110-131 (no coverage config)
- `.github/workflows/backend-ci.yml` — line 170+ (per-service thresholds)

## Action
1. Add `[tool.coverage.report]` section to `pyproject.toml` with `fail_under = 50` baseline
2. Add per-service overrides where appropriate (ingestion=42% is below baseline — raise it)
3. Add frontend coverage reporting to `frontend-ci.yml` with `--coverage` flag
4. Add a coverage trend check: fail CI if coverage drops more than 2% from the previous run
""",
    },
    # ==================== P2 — API/DX + COMPLIANCE GAPS ====================
    {
        "title": "[P2][backend] Response envelope inconsistent across API endpoints",
        "labels": ["P2", "backend", "api-dx"],
        "body": """## Problem
Some endpoints return bare JSON objects, others return `{data: ..., meta: ...}` envelopes, and the graph pagination endpoint (after #564 fix) will return `{items, total_count, limit, offset}`. Inconsistency makes client integration harder.

## Action
1. Define a standard response envelope in `services/shared/response.py`: `{data, meta: {request_id, timestamp}, pagination?: {total, limit, offset}}`
2. Apply to all new endpoints immediately
3. Create a migration plan for existing endpoints (add envelope in next major version)
4. Document the envelope standard in API docs
""",
    },
    {
        "title": "[P2][compliance] PII may appear in compliance audit exports and FDA reports",
        "labels": ["P2", "compliance", "pii", "legal"],
        "body": """## Problem
FDA export and compliance audit reports may include user email addresses or names from the audit trail. FSMA 204 requires traceability data but not PII in exported datasets.

## Files
- `services/ingestion/app/recall_report.py` — check what user data is included in exports
- `migrations/V002__fsma_cte_persistence.sql` — `fda_export_log` table schema

## Action
1. Audit all export endpoints and report generators for PII fields
2. Replace user identifiers with anonymized tenant-level references in exports
3. Add a PII scrubbing pass before any data leaves the system boundary
4. Document which fields are included in FDA exports for compliance review
""",
    },
    {
        "title": "[P2][legal] GDPR right-to-erasure not implemented",
        "labels": ["P2", "legal", "compliance", "gdpr"],
        "body": """## Problem
No mechanism exists for a user to request deletion of their personal data (GDPR Article 17). With FSMA immutability requirements on CTE data, the system needs a clear policy on what can be deleted (user account, PII) vs. what must be retained (regulatory records with PII redacted).

## Action
1. Define a data retention policy: user PII is deletable, CTE records are retained with PII redacted
2. Create an admin endpoint: POST /admin/gdpr/erasure-request that queues PII deletion
3. Implement PII redaction in CTE records (replace names/emails with "REDACTED-{hash}")
4. Add audit log entry for erasure requests (required by GDPR)
5. Document the erasure process and expected timeline
""",
    },
    {
        "title": "[P2][compliance] Pre-deletion audit snapshots not captured",
        "labels": ["P2", "compliance", "backend"],
        "body": """## Problem
When records are soft-deleted or modified (tenant deactivation, key revocation, user removal), no audit snapshot is captured of the pre-change state. This makes forensic investigation and compliance audits difficult.

## Action
1. Add a `change_log` table: `id, entity_type, entity_id, action, before_state (JSONB), after_state (JSONB), actor_id, timestamp`
2. Create a shared `audit_change()` function that captures before/after state
3. Call it from tenant deactivation, key revocation, user deletion, and role changes
4. Add retention policy: keep change_log entries for 7 years (regulatory minimum)
""",
    },
    {
        "title": "[P2][backend] Webhook retry and dead-letter queue missing",
        "labels": ["P2", "backend", "resilience"],
        "body": """## Problem
Webhook delivery (`WebhookNotifier` in scheduler) has no retry logic or dead-letter queue. Failed webhook deliveries are lost. For a compliance platform, missed notifications could mean missed regulatory deadlines.

## Files
- `services/scheduler/main.py` — line 82: `self.notifier = WebhookNotifier()`
- `services/scheduler/main.py` — lines 331-341: webhook notification error handling

## Action
1. Add exponential backoff retry (3 attempts: 1s, 5s, 25s)
2. After final retry failure, write to a `webhook_dlq` table with payload, error, and timestamp
3. Add an admin endpoint to list and replay failed webhooks
4. Add monitoring: alert if DLQ depth exceeds threshold
""",
    },
    {
        "title": "[P2][api-dx] API breaking-change policy not documented",
        "labels": ["P2", "api-dx", "tech-debt"],
        "body": """## Problem
No documented policy for API versioning or breaking changes. As RegEngine onboards customers, breaking changes to the CTE ingestion API or admin API could disrupt integrations.

## Action
1. Create `docs/API_VERSIONING.md` with policy: URL prefix versioning (`/v1/`, `/v2/`)
2. Define what constitutes a breaking change (field removal, type change, behavior change)
3. Commit to deprecation timeline: 90-day notice before removing any v1 endpoint
4. Add `API-Version` response header to all endpoints
5. Add `Sunset` header to deprecated endpoints per RFC 8594
""",
    },
    {
        "title": "[P2][security] CreateKeyRequest model lacks input validation",
        "labels": ["P2", "security", "backend"],
        "body": """## Problem
The `CreateKeyRequest` Pydantic model for API key creation may not enforce field-level validation (key name length, allowed characters, scope restrictions). Missing validation allows junk data and potential injection.

## Files
- `services/admin/app/routes.py` — line 316 (POST /admin/keys)

## Action
1. Add Pydantic validators: key name max 128 chars, alphanumeric + hyphens only
2. Add scope validation: only allow predefined scope values (read, write, admin)
3. Add rate limiting on key creation (max 10 keys per tenant)
4. Return 422 with field-level error details on validation failure
""",
    },
    {
        "title": "[P2][infra] CORS allowed origins may drift from actual deployment domains",
        "labels": ["P2", "infra", "security"],
        "body": """## Problem
CORS configuration in `services/shared/cors.py` has hardcoded defaults (localhost:3000, regengine.co, app.regengine.co). As new subdomains or staging environments are added, the CORS list may not be updated, causing silent failures or overly permissive access.

## Files
- `services/shared/cors.py` — lines 10-32

## Action
1. Move CORS allowed origins entirely to environment variable (no hardcoded defaults in production)
2. Add a CI check that validates CORS_ALLOWED_ORIGINS is set in all deployment configs
3. Add monitoring: log and alert on CORS rejections to catch misconfigurations early
4. Document the process for adding new allowed origins
""",
    },
]

# --- Create issues ---
created = 0
for issue_data in ISSUES:
    title = issue_data["title"]
    try:
        issue = repo.create_issue(
            title=title,
            body=issue_data["body"],
            labels=issue_data["labels"],
        )
        print(f"  ✅ #{issue.number}: {title}")
        created += 1
        time.sleep(1)  # rate-limit courtesy
    except Exception as exc:
        print(f"  ❌ FAILED: {title} — {exc}")

print(f"\nDone. Created {created}/{len(ISSUES)} issues.")
