# RegEngine Beta Tester Guide

> Status: verified 2026-05-06. This guide reflects the current FSMA 204 traceability product path and the consolidated deploy shape.

## What RegEngine Is

RegEngine is a mature pre-production FSMA 204 traceability platform. It helps food operators and suppliers turn messy supplier, ERP, CSV, EPCIS, and related traceability inputs into validated, tenant-scoped evidence for readiness reviews, recall drills, and FDA response preparation.

For beta testing, the most important workflow is:

```text
ingest -> preflight -> fix queue -> readiness -> export/response prep
```

## What Beta Testers Should Focus On

- Signing in and selecting the correct tenant
- Uploading or pasting traceability data
- Reviewing readiness and fix-queue feedback
- Verifying export and response-prep workflows
- Reporting where the product is confusing, blocking, or over-promising

## Current Runtime Shape

RegEngine is deployed as one consolidated FastAPI app behind a Next.js frontend.

```text
browser
  -> Next.js app
  -> same-origin proxy routes and authenticated app flows
  -> consolidated FastAPI app (server/main.py)
  -> PostgreSQL-backed traceability, audit, and export paths
```

Legacy service directories still exist in the repository, but the checked-in production path is the consolidated app, not six separate live deploys.

## Key Concepts

### Tenant

Each organization operates inside a tenant-scoped workspace. Readiness views, evidence, exports, and admin actions should stay isolated to that tenant.

### Inflow Workbench

The Inflow Workbench is the main preflight surface for evaluating traceability records before they are treated as production evidence.

### Fix Queue

The fix queue surfaces missing or invalid data that must be resolved before a record set is ready for downstream audit or export workflows.

### Readiness

Readiness summarizes whether the supplied data is complete enough for traceability workflows, not whether every imaginable compliance concern has been solved automatically.

### Export Package

Export and response-prep flows package validated records into FDA-facing or operator-facing outputs.

## Quick Start

### 1. Open the app

Local default:

```text
http://localhost:3000
```

### 2. Sign in and confirm tenant context

If the wrong tenant is selected, stop there and report it. Tenant mix-ups are high-severity issues.

### 3. Run a traceability input through preflight

Recommended starting points:

- `/dashboard/inflow-lab`
- `/dashboard/receiving`
- `/tools/inflow-lab`

### 4. Review the result

Look for:

- readiness score and label
- specific data-quality failures
- fix-queue items
- commit-gate messaging

### 5. Verify downstream flows

Check whether the same dataset can move cleanly into:

- compliance/readiness views
- recall drill preparation
- export or response-prep workflows

## API Access Notes

- External API-key-driven examples belong in the developer docs and developer portal.
- Internal authenticated app flows should generally work through the Next.js app and its same-origin proxy routes.
- If you are testing raw endpoints directly, verify the exact route shape against the live docs instead of assuming legacy service ports are authoritative.

Useful entry points:

- App docs: `http://localhost:3000/docs`
- Developers page: `http://localhost:3000/developers`
- API docs in non-production environments: `/docs` and `/openapi.json` on the consolidated backend

## Expected Beta Behaviors

Beta testers should expect:

- occasional rough edges in workflow polish
- hardening work around auth, tenant scoping, and export flows
- strong emphasis on auditability and deterministic validation over flashy automation claims

Beta testers should not expect:

- a production-ready product surface
- zero-touch "complete compliance"
- universal regulatory intelligence outside the current FSMA 204 product wedge

## Reporting Issues

When filing a beta issue, include:

1. tenant and environment used
2. exact page or endpoint
3. sample input or reproduction steps
4. expected behavior
5. actual behavior
6. whether the issue affected readiness, fix queue, export, or tenant isolation

## Source of Truth

When documentation conflicts, trust these first:

- `README.md`
- `REPO_PURPOSE.md`
- `ARCHITECTURE.md`
- `docs/verticals/README.md`

If the product story in another current doc conflicts with those files, treat it as stale and update it.
