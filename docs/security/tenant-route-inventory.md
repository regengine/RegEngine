# Tenant-Scoped Route Inventory

Last updated: 2026-05-14

## Invariant

Tenant-scoped HTTP handlers must derive tenant authority from authenticated
principal state. Client-supplied tenant IDs in path, query, headers, or JSON
body are assertions only; mismatches fail closed with `E_TENANT_MISMATCH`.

## Current Guardrail

Legacy ingestion routers that depend on `webhook_compat._verify_api_key` are
protected by the shared tenant resolver. The dependency authenticates the API
key, stores it on `request.state.api_key`, and rejects conflicting tenant
claims before the route handler runs.

Refresh this inventory with:

```bash
rg -l "Depends\\(_verify_api_key\\)" services/ingestion/app -g '*.py' | sort
```

## Guarded Legacy Ingestion Groups

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
- `stripe_billing/routes.py`
- `supplier_mgmt.py`
- `supplier_validation.py`
- `team_mgmt.py`
- `webhook_router_v2.py`

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
