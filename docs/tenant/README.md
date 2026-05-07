# Tenant Documentation

> Status: verified 2026-05-06. This directory supports tenant-scoped onboarding and API usage within RegEngine's current FSMA 204 traceability product scope.

## Start Here

1. `ONBOARDING_GUIDE.md` for tenant onboarding and validation flow
2. `API_EXAMPLES.md` for low-level request examples

## What This Directory Covers

- tenant-scoped access patterns
- API-key-based integration examples where that auth model is intentional
- supporting examples for admin and lower-level API usage

## What This Directory Does Not Define

This directory is not the source of truth for:

- overall product positioning
- runtime architecture
- whether a legacy endpoint family is still part of the primary commercial story

For those questions, use:

- `README.md`
- `REPO_PURPOSE.md`
- `ARCHITECTURE.md`
- `docs/product/POSITIONING.md`
- `docs/verticals/README.md`

## Current Product Focus

RegEngine is currently positioned as a pre-production FSMA 204 traceability platform. The strongest documented path is tenant-scoped ingestion, readiness, audit evidence, and export support for food traceability workflows.

Some lower-level or older endpoint families remain in-tree. Treat them as implementation details or secondary surfaces unless the current docs and tests clearly support them as part of the active product path.

## Authentication Notes

- Internal frontend flows should use authenticated sessions and same-origin routes.
- Explicit `X-RegEngine-API-Key` headers are still appropriate for intentional direct API integrations.
- If an example here conflicts with current frontend behavior or developer docs, update the stale example rather than broadening the product story.
