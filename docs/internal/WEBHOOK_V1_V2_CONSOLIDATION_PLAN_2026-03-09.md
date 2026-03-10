# Webhook Router v1/v2 Consolidation Plan

**Date:** March 9, 2026  
**Status:** Phase 2 complete (v1 shim landed)

## Goal

Consolidate ingestion webhook logic onto `webhook_router_v2.py` without breaking modules that historically imported helpers from `webhook_router.py`.

## Current State

- `services/ingestion/main.py` mounts **v2** router: `app.webhook_router_v2.router`.
- Legacy `webhook_router.py` is **not mounted** but was still used as a helper import source (`_verify_api_key`, `ingest_events`).
- Internal modules now use a stable compat surface:
  - `services/ingestion/app/webhook_compat.py`

## Phase 1 (Completed in this PR)

### What changed

1. Added compat module:
   - `app.webhook_compat._verify_api_key` (re-export from v2)
   - `app.webhook_compat.ingest_events(...)` (delegates to v2)
2. Repointed helper imports from v1/v2 modules to `app.webhook_compat` across ingestion modules and tests.
3. Updated internal ingest callers that rely on API-key tenant resolution:
   - `csv_templates.py` now forwards `X-RegEngine-API-Key` to compat ingest helper.
   - `sensitech_parser.py` now forwards `X-RegEngine-API-Key` to compat ingest helper.

### Why this is safe

- Mounted HTTP ingest path remains unchanged (`/api/v1/webhooks/ingest` from v2).
- No endpoint paths were renamed.
- Dependency override tests now target stable compat helper rather than legacy v1 module.

## Phase 2 (Completed)

### What changed

1. Replaced legacy v1 business logic in `services/ingestion/app/webhook_router.py` with a thin compatibility shim.
2. Kept backward-compatible exports for legacy external imports:
   - `_verify_api_key` (re-export via `app.webhook_compat`)
   - `ingest_events(...)` (delegates to v2-backed compat helper)
3. Added one-time deprecation logging in the v1 shim to make remaining usage visible without log spam.
4. Added targeted shim tests in `services/ingestion/tests/test_webhook_router_shim.py`.

## Phase 3 (Final cleanup)

1. Remove any remaining references to `webhook_router.py`.
2. Keep `webhook_compat.py` as the only helper import surface for non-router modules.
3. Delete `webhook_router.py` after one full release cycle with no v1 shim usage telemetry.
4. Document deprecation completion in release notes.

## Verification Checklist

- [x] `services/ingestion/tests/test_epcis_ingestion_api.py`
- [x] `services/ingestion/tests/test_recall_simulations_api.py`
- [x] `services/ingestion/tests/test_webhook_router_shim.py`
- [ ] targeted API smoke tests for CSV and Sensitech ingest paths
