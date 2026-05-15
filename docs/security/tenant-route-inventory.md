# Tenant-Scoped Route Inventory

Last updated: 2026-05-14

## Invariant

Tenant-scoped HTTP handlers must derive tenant authority from authenticated
principal state. Client-supplied tenant IDs in path, query, headers, or JSON
body are assertions only; mismatches fail closed with `E_TENANT_MISMATCH`.

## Current Guardrail

Legacy ingestion routers use `webhook_compat.require_tenant_context`, which
authenticates the API key, stores the accepted key on `request.state.api_key`,
resolves the authoritative `TenantContext`, and rejects conflicting tenant
claims before the route handler performs reads or writes.

`webhook_router_v2.py` keeps `_verify_api_key` as a header-presence
compatibility gate, but the ingest handler also calls the shared tenant
resolver after RBAC principal resolution and uses `ctx.tenant_id` for
persistence, rate limiting, and subscription-gated work.

Refresh this inventory with:

```bash
rg -l "require_tenant_context|resolve_tenant_context" services/ingestion/app -g '*.py' | sort
```

## Migrated Tenant-Scoped Ingestion Groups

- `alerts.py`
- `audit_export_log.py`
- `audit_log.py`
- `chain_verification_job.py`
- `compliance_score.py`
- `disaster_recovery.py`
- `epcis/router.py`
- `epcis_export.py`
- `export_monitoring.py`
- `integration_router.py`
- `mock_audit.py`
- `notification_prefs.py`
- `onboarding.py`
- `product_catalog.py`
- `recall_report.py`
- `sensitech_parser.py`
- `settings.py`
- `sla_tracking.py`
- `sop_generator.py`
- `supplier_mgmt.py`
- `supplier_validation.py`
- `team_mgmt.py`
- `webhook_router_v2.py`

## Remaining Compat References

- `webhook_compat.py`: defines `_verify_api_key` and wraps it in
  `require_tenant_context` for legacy routers.
- `webhook_router_v2.py`: keeps `_verify_api_key` as the explicit
  X-RegEngine-API-Key presence check while tenant authority comes from the
  RBAC principal plus shared tenant resolver.
- `stripe_billing/routes.py`: documentation comment describing the old void
  dependency pattern; the billing gate itself derives tenant from authenticated
  principal state.

## Intentionally Non-Tenant Endpoints

Some endpoints in the guarded modules expose static metadata, such as export
formats, integration catalogs, onboarding steps, or available roles. They still
require API-key auth where currently wired, but they do not perform tenant data
access.

## Deprecation Target

The compatibility dependency remains the short-term safety net. New handlers
should prefer `resolve_tenant_context(request)` or `Depends(resolve_tenant_context)`
directly and should use `ctx.tenant_id` for storage keys, RLS context, rate
limits, and response tenant IDs.
