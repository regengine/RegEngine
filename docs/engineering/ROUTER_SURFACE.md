# Router Surface Audit

Source of truth: `server/main.py`

Date: 2026-08-26 (previously 2026-05-03)

Re-audited 2026-08-26 against `VALID_ROUTER_NAMES` in
`server/router_policy.py`, which holds **52** names. `proof_verify` and
`proof_recall` are in the exact production allowlist. `remediation` is a known
router name but remains deliberately release-disabled.

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
- Liveness: `/health` and `/health/live`
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
- `billing`
- `onboarding`
- `recall`
- `proof_verify`
- `proof_recall`
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
- `admin`
- `fsma_compliance`

These are not automatically safe. They are production-relevant only when tests prove tenant isolation, validation behavior, and failure handling.

In development and test, `COMPLIANCE_ROUTERS` protects `remediation`,
`canonical_records`, `rules`, `exceptions`, `fda_export`, and
`chain_verification` from ad hoc `DISABLED_ROUTERS` configuration unless the
explicit degraded-mode override is present. Production does not use that
escape hatch; it enforces the exact approved allowlist above.

## Public Proof Surface (tenantless, unauthenticated)

These are part of the exact release-approved production allowlist:

- `proof_verify` — `POST /api/v1/proof/verify` (`server/main.py:556`).
  Public hash-chain/Merkle-root verifier for an exported FDA bundle. **No
  auth, no tenant context.** Rate-limited to 10 req/min/IP via the shared
  slowapi limiter. The router docstring asserts it touches no database and
  no tenant-scoped store, and operates only on caller-supplied bytes.
- `proof_recall` — `POST /api/v1/proof/recall-drill`
  (`server/main.py:654`). Public deterministic recall drill against a
  frozen synthetic dataset baked into the module. **No auth, no tenant
  context.** Rate-limited to 5 req/min/IP.

Their unauthenticated classification and executable adapters are recorded in
the route-security manifest. A future change that introduces tenant storage or
credentials must change that classification and repeat the promotion gate.

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
Graph promotion additionally requires the tenant matrix against Neo4j and a
database-serialized append API for the FSMA audit chain, with direct runtime
write privileges revoked.

## Explicitly Release-Deferred Surfaces

- `remediation` remains a valid, compliance-critical development router, but
  it is omitted from `PRODUCTION_ENABLED_ROUTERS`. The production UI resolves
  `/remediation` as 404, the ingestion BFF returns an empty 404 for
  `/api/ingestion/api/v1/remediation/**`, and scheduler delivery registration
  and execution remain disabled while the owner is omitted.
- The overlay-backed `/api/controls/**` BFF aliases return an empty 404 for all
  methods and credential states.
- Direct graph routes and the graph-routed FSMA aliases (`compliance`,
  `traceability`, `recall`, `science`, `metrics`, `gaps`, and `export`) return
  an empty 404 before auth or upstream fetch. Scheduler audit-buffer replay is
  gated by the same `graph` owner at both registration and execution time.

These denials are duplicated at the global frontend proxy and the BFF handler
boundary so middleware exclusions or direct handler invocation cannot expose a
release-disabled backend. The retired `x-admin-key` credential is not accepted
or forwarded by these paths.

## Route-Complete Security Manifest

`docs/security/route-security-manifest.json` is generated from effective route
contexts in the consolidated app: the full included path is paired with its
original `APIRoute`. `server/main.py` records ownership at router-inclusion
time; ownership is not inferred from path prefixes. This is compatible with
FastAPI 0.141's included-router wrappers and refuses a vacuous route inventory.

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
