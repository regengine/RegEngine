# RegEngine Tenant Onboarding Guide

> Status: verified 2026-05-06. This guide reflects the current FSMA 204 traceability product path and tenant-scoped operational model.

## Who This Guide Is For

Use this guide if you are:

- onboarding a food operator, supplier, or internal pilot tenant
- testing tenant-scoped dashboard and API workflows
- validating that traceability data stays isolated and export-ready

## What RegEngine Does For A Tenant

RegEngine helps a tenant:

- ingest traceability data from supplier, ERP, CSV, EPCIS, and related sources
- preflight records before they become evidence
- surface readiness and fix-queue issues
- manage tenant-scoped users, API keys, and audit activity
- prepare validated records for recall drills and FDA response workflows

## Tenant Essentials

Each tenant should have:

- a tenant identifier
- appropriate user access
- API keys only for the surfaces that intentionally use API-key auth
- a clear owner for onboarding, readiness review, and export validation

## Recommended First Session

### 1. Confirm access

- Sign in to the frontend
- Verify you are in the correct tenant
- Confirm the expected dashboard pages and admin capabilities are visible

### 2. Exercise the preflight path

Recommended entry points:

- `/dashboard/inflow-lab`
- `/dashboard/receiving`
- `/tools/inflow-lab`

Use real or representative sample records and confirm:

- inputs are accepted
- failures are explained clearly
- readiness and fix-queue results make sense

### 3. Review tenant-scoped outputs

Inspect:

- compliance/readiness views
- export-related views
- audit/admin activity where relevant

### 4. Validate API access if needed

If the tenant uses direct API access, validate those flows through the current developer docs. Do not assume legacy service-port examples are the active contract.

## Authentication Guidance

- Internal app usage should rely on the authenticated frontend session and same-origin proxy routes.
- Explicit `X-RegEngine-API-Key` usage remains valid for intentional API-key surfaces such as direct developer/operator integrations.
- Browser-based dashboard flows should not require a copied API key just to function.

## What Good Looks Like

- tenant stays isolated from other tenants
- data-quality failures are specific and actionable
- readiness signals match the supplied records
- export/response-prep workflows reflect validated evidence, not raw unchecked data

## Common Problems To Catch Early

- wrong tenant selected in the UI
- data accepted without enough validation context
- fix queue missing or misleading items
- export-ready messaging that overstates actual record completeness
- dashboard behavior that depends on manual browser API-key handling

## Current Product Boundaries

RegEngine is currently positioned as an FSMA 204 traceability platform in a mature pre-production phase.

Do not position tenant onboarding as:

- a universal regulatory intelligence rollout
- a full replacement for every food safety or GRC workflow on day one
- proof of zero-touch compliance

## Source Of Truth

Use these files when onboarding language or promises drift:

- `README.md`
- `REPO_PURPOSE.md`
- `ARCHITECTURE.md`
- `docs/product/POSITIONING.md`
