# Router Surface Audit

Source of truth: `server/main.py`

Date: 2026-08-03

## Current Mount Model

RegEngine runs as a consolidated FastAPI app.

Production router exposure is controlled by:

```text
ENABLED_ROUTERS
```

The current behavior is fail closed:

- Always mount a small system/ingestion base.
- In production, require the exact release-approved allowlist below; a missing,
  extra, or unknown router aborts startup.
- Reject production `DISABLED_ROUTERS` and
  `ENABLE_EXPERIMENTAL_ROUTERS=true` configuration.
- Development/test retain broad mounting and the historical
  `DISABLED_ROUTERS` behavior for focused local work.

That means the production default is narrower for explicitly experimental routers, while product/ops-adjacent routers still require deployment review.

## Always Mounted

These are mounted unconditionally:

- Root endpoint: `/`
- Liveness: `/health`
- Readiness: `/readiness`
- Feature listing: `/api/v1/features`
- Ingestion core router from `services.ingestion.app.routes`
- Core URL/file/direct/regulation ingest router from
  `services.ingestion.app.routes_ingest`
- Health/metrics router from `services.ingestion.app.routes_health_metrics`
- Ingestion status router from `services.ingestion.app.routes_status`
- Webhook ingest router from `services.ingestion.app.webhook_router_v2`
- Metrics-protected scheduler status router from
  `server.routes_scheduler_status`

The FSMA readiness compatibility routes are owned by `readiness` and are
mounted only when that approved router group is enabled. They are not part of
the unconditional base.

## FSMA Production Spine

These routers belong closest to the FSMA production story:

- `inflow_workbench`
- `fda_export`
- `csv`
- `edi`
- `epcis_ingestion`
- `score`
- `portal`
- `inbound_email` (Postmark inbound-parse webhook ingestion; disable-by-default — pending an explicit production-allowlist security review, not in the recommended `ENABLED_ROUTERS` string)
- `billing`
- `onboarding`
- `recall`
- `proof_verify`
- `proof_recall`
- `canonical_records`
- `rules`
- `exceptions`
- `remediation` (compliance repair workflow; disable-by-default — not in the recommended `ENABLED_ROUTERS` string)
- `request_workflow`
- `auditor`
- `compliance_metrics`
- `readiness`
- `chain_verification`
- `audit_export_log`
- `sla_tracking`
- `export_monitoring`
- `admin`
- `fsma_compliance`

These are not automatically safe. They are production-relevant only when tests prove tenant isolation, validation behavior, and failure handling.

## Product/Ops Adjacent

These may be useful for onboarding, customer operations, or commercial workflow, but they are not the narrow ingest/validate/export spine:

- `alerts`
- `supplier_mgmt`
- `audit_log`
- `product_catalog`
- `notification_prefs`
- `team_mgmt`
- `settings`
- `integration`
- `identity`
- `supplier_validation` — release-disabled until supplier dashboard records
  have a stable, tenant-scoped identity link to canonical portal/CTE events;
  the historical query targeted a table that was never migrated
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

## Required Production Configuration

```text
ENABLED_ROUTERS=inflow_workbench,fda_export,csv,edi,epcis_ingestion,score,portal,billing,onboarding,recall,proof_verify,proof_recall,canonical_records,rules,exceptions,request_workflow,auditor,compliance_metrics,readiness,chain_verification,audit_export_log,sla_tracking,export_monitoring,admin,fsma_compliance
```

This value is intentionally exact, not a customizable production subset. A
router change is a release-gate change: update `server/router_policy.py`, add
the operation-level auth/tenant manifest and executable test adapters, and
repeat staging isolation checks before changing the environment.

Graph, NLP, scraping, discovery, sandbox, recall simulations, legacy export,
and every other omitted optional router are release-disabled and return 404.
Graph promotion additionally requires the tenant matrix against Neo4j.

## Route-Complete Security Manifest

`docs/security/route-security-manifest.json` is generated from the copied
`APIRoute` objects in the consolidated app. `server/main.py` records ownership
at router-inclusion time; ownership is not inferred from path prefixes.

Run the blocking gate locally with:

```bash
python scripts/generate_route_security_manifest.py --check
```

The gate executes a security adapter for every enabled operation, rejects
unowned/unclassified/duplicate operations, compares the generated table with
the checked-in manifest, imports the production allowlist in a clean process,
and issues one safe exact-404 probe for every unique omitted route path. A
route promotion requires an explicit operation policy and adapter before the
manifest can be regenerated.

## Acceptance Rule

No route should be considered production unless it has:

- Tenant-isolation coverage
- Authentication/authorization coverage
- Invalid-input coverage
- Failure-mode coverage
- A direct connection to the FSMA pipeline or a documented operator requirement
