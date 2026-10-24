# Production Surface

This file defines the intended production surface for RegEngine. It is a control document, not marketing copy.

## Core FSMA Pipeline

The production contract is:

```text
ingest -> canonicalize -> validate -> persist evidence -> export
```

## Active API Categories

These surfaces are part of the core production spine when their corresponding routers are mounted in `server/main.py`.

- Ingestion and webhook CTE intake
- CSV, EPCIS, and EDI FSMA data intake
- Inflow Workbench preflight and commit gate
- Canonical record and CTE/KDE persistence
- Compliance rules, readiness, exception, and audit review workflows
- Supplier remediation: manifest intake, scoped correction links, and the
  token-scoped supplier correction session (`remediation`; compliance-critical,
  see "Boot-critical routers" below)
- FDA export and export monitoring
- Public proof endpoints: export-bundle verification and the recall-drill endpoint (currently returns no drill data)
  (`proof_verify`, `proof_recall`; tenantless and unauthenticated, see below)
- Tenant, user, API-key, supplier, and audit-log administration
- Billing routes required for customer subscription management
- Health, readiness, metrics, observability, and operational probes

## Required Guarantees

- Tenant isolation is enforced on reads and writes.
- Schema validation occurs before persistence.
- CTE/KDE evidence is persisted through the canonical storage path.
- Hash-chain or audit-chain persistence is required for evidence and administrative audit surfaces.
- FDA export output must be derived from stored tenant-scoped evidence.
- Authentication and authorization must be explicit; development fallbacks must fail closed outside explicitly configured development or test environments.
- Router exposure must be controlled by configuration and reviewed before production promotion.

## Current Router Control

The consolidated FastAPI entrypoint is `server/main.py`. It is the source of
truth; `docs/engineering/ROUTER_SURFACE.md` is the per-router audit.

Router exposure is currently controlled by:

```text
DISABLED_ROUTERS
ENABLE_EXPERIMENTAL_ROUTERS
```

`DISABLED_ROUTERS` is a comma-separated list of router names to suppress at startup.

In production, experimental routers are also suppressed unless:

```text
ENABLE_EXPERIMENTAL_ROUTERS=true
```

Development and test environments retain broad router mounting for local work and CI coverage.

### Boot-critical routers

`server/main.py` defines `_COMPLIANCE_ROUTERS`:

```text
canonical_records, rules, exceptions, remediation, fda_export, chain_verification
```

Naming any of these in `DISABLED_ROUTERS` makes the app raise `RuntimeError`
at import and **refuse to boot**, unless `ALLOW_DISABLE_COMPLIANCE_ROUTERS=true`
is also set — which does not restore the router, it only downgrades the hard
failure to a logged "degraded compliance mode". `remediation` is the entry
most often forgotten, because it is newer than this document's original
router inventory (#2838).

### Public, tenantless, unauthenticated surfaces

Two routers mount unconditionally in production and are **not** experimental,
so `ENABLE_EXPERIMENTAL_ROUTERS` does not gate them:

- `proof_verify` — `POST /api/v1/proof/verify` (`server/main.py:556`).
  Public export-bundle hash-chain/Merkle verifier. No auth, no tenant
  context. Rate limit 10 req/min/IP.
- `proof_recall` — `POST /api/v1/proof/recall-drill` (`server/main.py:654`).
  Public recall-drill endpoint. It reads no customer data and currently returns an honest empty result (`data_available: false`, no steps, no lot, no trace time, no CSV) with an explanatory message. No auth,
  no tenant context. Rate limit 5 req/min/IP.

Both carry an in-module justification docstring arguing they belong to the
FSMA pipeline as the export stage's public attestation surface, and both
assert they read no tenant data. **Neither has a recorded sign-off against
the Promotion Rule below** — that review is outstanding (#2838).

Together with `remediation` (15 routes across its two routers), these three
account for 17 routes that were absent from the router inventory before
2026-08-26.

## Experimental or Non-Core Surfaces

The following categories must not be treated as part of the core production contract unless they are explicitly promoted, tested, and documented:

- Generic NLP and text-analysis modules
- Graph exploration or nonessential graph operations
- Prototype integrations
- Demo-only audit or simulation routes
- Non-FSMA regulatory verticals
- Computer vision or QR decoding paths that bypass the core validation pipeline
- Discovery, scraping, or source-management surfaces that are not required for FSMA evidence intake

## Promotion Rule

A route moves into the production surface only when it has:

- A tenant-isolation test
- A schema-validation or contract test
- A failure-mode test for invalid input
- Clear ownership in documentation
- A reason it belongs to the FSMA pipeline
