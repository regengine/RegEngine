# Router Surface Audit

Source of truth: `server/main.py`

Date: 2026-05-03

## Current Mount Model

RegEngine runs as a consolidated FastAPI app.

Router exposure is controlled by:

```text
DISABLED_ROUTERS
```

The current behavior is:

- Always mount a small system/ingestion base.
- Mount every feature router unless its name is listed in `DISABLED_ROUTERS`.
- In production, auto-disable experimental routers unless `ENABLE_EXPERIMENTAL_ROUTERS=true`.

That means the production default is narrower for explicitly experimental routers, while product/ops-adjacent routers still require deployment review.

## Always Mounted

These are mounted unconditionally:

- Root endpoint: `/`
- Liveness: `/health`
- Readiness: `/readiness`
- Feature listing: `/api/v1/features`
- Ingestion core router from `services.ingestion.app.routes`
- Health/metrics router from `services.ingestion.app.routes_health_metrics`
- Ingestion status router from `services.ingestion.app.routes_status`
- Webhook ingest router from `services.ingestion.app.webhook_router_v2`

## FSMA Production Spine

These routers belong closest to the FSMA production story:

- `inflow_workbench`
- `fda_export`
- `csv`
- `edi`
- `epcis_ingestion`
- `score`
- `portal`
- `canonical_records`
- `rules`
- `exceptions`
- `request_workflow`
- `auditor`
- `compliance_metrics`
- `readiness`
- `chain_verification`
- `audit_export_log`
- `sla_tracking`
- `export_monitoring`
- `supplier_validation`
- `admin`
- `fsma_compliance`

These are not automatically safe. They are production-relevant only when tests prove tenant isolation, validation behavior, and failure handling.

## Product/Ops Adjacent

These may be useful for onboarding, customer operations, or commercial workflow, but they are not the narrow ingest/validate/export spine:

- `billing`
- `alerts`
- `onboarding`
- `recall`
- `supplier_mgmt`
- `audit_log`
- `product_catalog`
- `notification_prefs`
- `team_mgmt`
- `settings`
- `integration`
- `identity`
- `incidents`
- `disaster_recovery`

Recommendation: keep only the minimum required subset enabled in production until each route has explicit owner documentation and tenant-boundary tests.

## Experimental / Disable By Default Candidates

These should be disabled in production unless explicitly promoted:

- `scraping`
- `discovery`
- `sources`
- `sandbox`
- `sensitech`
- `audit` (mock audit)
- `sop`
- `export` (legacy EPCIS/data export path)
- `qr_decoder`
- `label_vision`
- `exchange`
- `recall_simulations`
- `graph`
- `nlp`

Rationale: these surfaces either expand the product beyond FSMA evidence flow, are demo/prototype oriented, or can create a confusing public API surface for an investor/CTO review.

## Recommended Production Configuration

Short-term production discipline can be achieved without deleting code by setting `DISABLED_ROUTERS` to disable non-core surfaces.

Suggested starting point:

```text
DISABLED_ROUTERS=scraping,discovery,sources,sandbox,sensitech,audit,sop,export,qr_decoder,label_vision,exchange,recall_simulations,graph,nlp
```

Then review the Product/Ops Adjacent group and disable anything not required for the current design-partner workflow.

## Stronger Follow-Up

The first production guard is implemented: experimental routers require `ENABLE_EXPERIMENTAL_ROUTERS=true` in production.

The stronger follow-up is to replace deny-by-configuration with allow-by-configuration for all optional production routers:

```text
ENABLE_EXPERIMENTAL_ROUTERS=false
ENABLED_ROUTERS=inflow_workbench,fda_export,csv,edi,epcis_ingestion,score,canonical_records,rules,exceptions,request_workflow,auditor,compliance_metrics,readiness,chain_verification,audit_export_log,sla_tracking,export_monitoring,supplier_validation,admin,fsma_compliance
```

Recommended behavior for that follow-up:

- Development/test may keep broad router mounting.
- Production should mount only explicitly enabled routers.
- Experimental routers should require both `ENABLE_EXPERIMENTAL_ROUTERS=true` and explicit listing.

## Acceptance Rule

No route should be considered production unless it has:

- Tenant-isolation coverage
- Authentication/authorization coverage
- Invalid-input coverage
- Failure-mode coverage
- A direct connection to the FSMA pipeline or a documented operator requirement
