# Router Surface Audit

Source of truth: `server/main.py`

Date: 2026-08-26 (previously 2026-05-03)

Re-audited 2026-08-26 against `_VALID_ROUTER_NAMES` in `server/main.py`,
which holds **52** names. The 2026-05-03 revision of this file enumerated
only 49 and omitted `remediation`, `proof_verify`, and `proof_recall`
(#2838). All three are now listed below and in the allowlist.

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
- `remediation` — **boot-critical.** Listed in `_COMPLIANCE_ROUTERS`
  (`server/main.py`). Putting it in `DISABLED_ROUTERS` makes the app raise
  `RuntimeError` at import and **refuse to boot** unless
  `ALLOW_DISABLE_COMPLIANCE_ROUTERS=true` is also set (which only downgrades
  the hard failure to a `logger.critical` "degraded compliance mode"). Mounts
  two routers — `/api/v1/remediation` (10 routes) and
  `/api/v1/remediation/supplier` (5 routes, token-scoped supplier access).
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

The other compliance-critical names in `_COMPLIANCE_ROUTERS` are
`canonical_records`, `rules`, `exceptions`, `fda_export`, and
`chain_verification`. Disabling any of them has the same boot-refusal
effect described for `remediation`.

## Public Proof Surface (tenantless, unauthenticated)

These mount unconditionally in production — they are **not** in
`_EXPERIMENTAL_ROUTERS`, so `ENABLE_EXPERIMENTAL_ROUTERS` does not gate
them and nothing suppresses them unless they are named in
`DISABLED_ROUTERS`:

- `proof_verify` — `POST /api/v1/proof/verify` (`server/main.py:556`).
  Public hash-chain/Merkle-root verifier for an exported FDA bundle. **No
  auth, no tenant context.** Rate-limited to 10 req/min/IP via the shared
  slowapi limiter. The router docstring asserts it touches no database and
  no tenant-scoped store, and operates only on caller-supplied bytes.
- `proof_recall` — `POST /api/v1/proof/recall-drill`
  (`server/main.py:654`). Public deterministic recall drill against a
  frozen synthetic dataset baked into the module. **No auth, no tenant
  context.** Rate-limited to 5 req/min/IP.

**Open promotion gap (#2838):** these are live public production surfaces
that were never recorded against the Acceptance Rule at the bottom of this
file, and `PRODUCTION_SURFACE.md`'s Promotion Rule was never applied to
them in writing. Each router carries an in-module justification docstring,
but that is the author's argument, not a completed review. Treat closing
that review as outstanding work; the "no tenant data" claim in particular
deserves an enforced test (static assertion of zero `shared.database` /
`CTEPersistence` imports) rather than a docstring.

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
ENABLED_ROUTERS=inflow_workbench,fda_export,csv,edi,epcis_ingestion,score,portal,canonical_records,rules,exceptions,remediation,request_workflow,auditor,compliance_metrics,readiness,chain_verification,audit_export_log,sla_tracking,export_monitoring,supplier_validation,admin,fsma_compliance,proof_verify,proof_recall
```

> **Corrected 2026-08-26 (#2838).** The previous allowlist was **not**
> safe to copy-paste:
>
> - It omitted `remediation`. `ENABLED_ROUTERS` is allow-by-configuration,
>   so once it is implemented, omission means "disabled" — and
>   `remediation` is compliance-critical, so a deploy using the old string
>   would have **failed to boot**.
> - It omitted `proof_verify` and `proof_recall`, silently removing two
>   live public endpoints.
> - It omitted `portal`, which the FSMA Production Spine list above does
>   include.
>
> If you would rather not expose the public proof endpoints in a given
> environment, drop `proof_verify,proof_recall` from the string
> deliberately — but never drop `remediation`.

**Implementation status:** `ENABLED_ROUTERS` is still a proposal. As of
2026-08-26 `server/main.py` reads only `DISABLED_ROUTERS` and
`ENABLE_EXPERIMENTAL_ROUTERS`; setting `ENABLED_ROUTERS` today has no
effect. Keep this string correct anyway — it is the spec the follow-up
will be built against.

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
