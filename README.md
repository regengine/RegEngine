# RegEngine

**API-first FSMA 204 compliance infrastructure for recall-ready traceability.**

RegEngine converts supply-chain traceability events into structured, exportable, and independently verifiable compliance records.

## Current Focus

- **Primary wedge:** Food and Beverage (FSMA 204)
- **Core outcome:** Generate FDA-sortable traceability records inside the 24-hour response window
- **Product posture:** FSMA-first execution before broader vertical expansion

## Recently Shipped (March 2026)

- Production auth/login chain stabilized end-to-end:
  - Same-origin Next.js admin proxy at `frontend/src/app/api/admin/[...path]/route.ts`
  - Public upstream targeting for Vercel (no private DNS dependency)
  - Working `/api/auth/login` -> `/api/admin/auth/login` routing
- Railway Redis service added and wired for persistent sessions:
  - Refresh token flow restored
  - Rate limiting and auth session persistence run on Redis
  - Graceful fallback paths remain in code for degraded scenarios
- FSMA-first narrative cleanup across marketing surfaces:
  - Removed broad "Soon" industry signaling from primary marketing footer/nav
  - Tightened homepage CTA and proof language to food-traceability outcomes
- New interactive supplier onboarding wireframe route:
  - `frontend/src/app/onboarding/supplier-flow/page.jsx`
  - Available in app at `/onboarding/supplier-flow`
  - Linked from onboarding and gated by authenticated session state

## Production Topology

- **Frontend + edge:** Vercel (`regengine.co`)
- **App/API service:** Railway `RegEngine` service (admin/auth API)
- **Stateful services:** Railway `Postgres`, `neo4j`, `Redis`

This 4-service runtime is the current P0/P1 topology and is intentionally minimal.

## Core Capabilities

- FSMA obligation mapping and traceability workflows
- Neo4j knowledge graph (`obligation -> control -> evidence`)
- Tamper-evident evidence model (SHA-256 + hash-chain primitives)
- Compliance score model (coverage x effectiveness x freshness)
- Multi-tenant enforcement and audit logging
- Free FSMA utility tools (FTL checker, readiness flows, simulation tools)

## Supplier Onboarding V1 (In-App Wireframe)

The current onboarding flow design follows this sequence:

1. Buyer invite
2. Supplier signup
3. Facility registration
4. FTL category scoping
5. CTE/KDE capture
6. TLC management
7. Supplier compliance dashboard
8. FDA export

Route: `/onboarding/supplier-flow`

## Local Development

Start core services:

```bash
docker-compose up -d
```

Start frontend:

```bash
cd frontend
pnpm dev
```

## Deployment Notes

- Vercel-hosted frontend should use a **public** admin API base URL.
- Recommended env on Vercel:
  - `NEXT_PUBLIC_ADMIN_URL=https://<railway-public-domain>`
- Avoid relying on private/internal hostnames from Vercel runtime routes.

## Validation Commands

Frontend login tests:

```bash
cd frontend
pnpm vitest src/__tests__/auth/login.test.tsx
```

Frontend production build:

```bash
cd frontend
pnpm build
```

## Reference Docs

- FSMA deployment runbook: `docs/FSMA_RAILWAY_DEPLOYMENT.md`
- Env setup checklist (beginner-friendly): `docs/ENV_SETUP_CHECKLIST.md`
- FSMA MVP spec: `docs/specs/FSMA_204_MVP_SPEC.md`
- Fair lending module spec: `docs/specs/FAIR_LENDING_COMPLIANCE_OS_MVP_SPEC.md`
- SOC2 control mapping (fair lending): `docs/security/SOC2_FAIR_LENDING_CONTROL_MAPPING.md`
- Investor wedge narrative (fair lending): `docs/whitepapers/FAIR_LENDING_WEDGE_INVESTOR_NARRATIVE.md`

---

Status: Active FSMA wedge execution with production auth stabilized and supplier onboarding V1 flow live in-app.
