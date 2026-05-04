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
- FDA export and export monitoring
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

The consolidated FastAPI entrypoint is `server/main.py`.

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
