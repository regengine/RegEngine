# RegEngine — Complete Product Feature List

**Prepared:** April 11, 2026
**Version:** Production (regengine.co)
**Audience:** Operations Analyst handover

---

## 1. PLATFORM OVERVIEW

RegEngine is a multi-tenant SaaS platform for FSMA 204 food traceability compliance. It ingests supply chain events (CTEs), validates them against FDA regulations, maintains a cryptographic audit trail, and produces FDA-ready exports. The platform serves manufacturers, distributors, retailers, restaurants, and farms/growers.

**Tech Stack:** Next.js 16 frontend, 6 FastAPI microservices, PostgreSQL (JSONB + RLS), Supabase Auth, Stripe billing, Resend email.

---

## 2. AUTHENTICATION & ACCOUNT MANAGEMENT

| Feature | Description |
|---------|-------------|
| Self-serve signup | Email + password + company name. 14-day free trial, no credit card required. |
| Partner signup link | `/signup?partner=founding` auto-flags account as Founding Design Partner |
| Supabase + custom JWT dual auth | Middleware cross-validates both sessions to prevent redirect loops |
| Password policy | 12-character minimum, validated server-side against policy rules |
| Forgot password / reset | Email-based password reset via `/forgot-password` → `/auth/verify` |
| Login with redirect | `?next=` parameter preserves intended destination post-login |
| Team invitations | Invite users to workspace via email (Resend). Invite tokens with expiry + revocation |
| Accept invite flow | `/accept-invite` for joining an existing workspace |
| Session management | HTTP-only cookies, refresh token rotation, family-based logout-across-devices |
| Rate limiting | 5/min on signup, 5 failed login attempts per email before lockout |
| MFA support | `mfa_secret` column on user model (infrastructure present, UI TBD) |

---

## 3. ONBOARDING FLOW

| Step | Page | Data Collected |
|------|------|----------------|
| 1 — Welcome | `/onboarding/setup/welcome` | User role (5 options), company type (5 options), FSMA 204 compliance status (4 options) |
| 2 — Facility | `/onboarding/setup/facility` | Facility name, full US address (street/city/state/ZIP validated), FDA registration #, supply chain roles |
| 3 — FTL Check | `/onboarding/setup/ftl-check` | Product categories handled → shows FTL coverage ratio, high-risk categories, required CTEs |

**Behaviors:**
- Progress persists in `tenant_settings` JSONB (survives session loss)
- Save failures show retry banner (no silent redirect loops)
- `/onboarding` smart-redirects: authenticated → setup flow, unauthenticated → signup
- Guided walkthrough alternative at `/onboarding/supplier-flow` (8-step interactive tutorial)

---

## 4. DASHBOARD (Authenticated)

| Feature | Route | Description |
|---------|-------|-------------|
| Main dashboard | `/dashboard` | Compliance overview, system health badge, quick actions, getting-started checklist |
| Getting Started card | embedded | 6-item onboarding checklist with progress bar (dismissible, tracks completion) |
| Compliance Score | `/dashboard/compliance` | Compliance grade visualization, trend tracking, gap analysis |
| Supplier Management | `/dashboard/suppliers` | Supplier list, compliance status per supplier, invite suppliers |
| Product Catalog | `/dashboard/products` | Product registry with TLC associations |
| Receiving Dock | `/dashboard/receiving` | Inbound receipt event logging |
| Alerts | `/dashboard/alerts` | Active compliance alerts with countdown timers (24h critical, 48h medium) |
| Issues | `/dashboard/issues` | Compliance exception tracking and resolution |
| Audit Log | `/dashboard/audit-log` | Tamper-evident audit trail viewer (SHA-256 hash chain) |
| Export Jobs | `/dashboard/export-jobs` | Export history with job status tracking |
| Recall Drills | `/dashboard/recall-drills` | Mock recall drill execution with scenario builder and timing metrics |
| Recall Response | `/dashboard/recall-response` | Active recall response workflow |
| Recall Report | `/dashboard/recall-report` | Post-drill report with FDA 24-hour mandate compliance assessment |
| Team | `/dashboard/team` | Workspace member management, invite new members, role assignment |
| Settings | `/dashboard/settings` | Workspace configuration, integration settings |
| Integrations | `/dashboard/integrations` | ERP and third-party integration management |
| Notifications | `/dashboard/notifications` | Notification preferences and alert routing |
| Heartbeat | `/dashboard/heartbeat` | System health monitoring dashboard with service-level status |
| QR Scanner | `/dashboard/scan` | Mobile QR code scanning for traceability verification |
| Founding Partner badge | header | "Founding Partner" badge for design partner accounts |

---

## 5. COMPLIANCE ENGINE

| Feature | Description |
|---------|-------------|
| Compliance status machine | COMPLIANT / AT_RISK / NON_COMPLIANT / PENDING / UNKNOWN per tenant |
| Alert system | Source types: FDA_RECALL, FDA_WARNING_LETTER, FDA_IMPORT_ALERT, RETAILER_REQUEST, INTERNAL_AUDIT, MANUAL |
| Countdown timers | 24-hour deadline for CRITICAL/HIGH, 48-hour for MEDIUM severity alerts |
| Product profile matching | Alerts matched to tenants via product categories, supply regions, supplier IDs, FDA product codes, retailer relationships |
| Status transition audit | Every compliance status change logged with trigger type and alert reference |
| Compliance checklists | `/compliance` — FSMA 204 task tracking |
| Compliance snapshots | `/compliance/snapshots` — Point-in-time attestations |
| Compliance status alerts | `/compliance/status` — Active alert management |
| Traceability plan | `/compliance/traceability-plan` — Create and manage FSMA 204 traceability plans |
| Product compliance profile | `/compliance/profile` — Product-level compliance categorization |
| Label generation | `/compliance/labels` — QR codes and serial numbers for traceability labels |
| Exceptions management | `/exceptions` — Track and resolve compliance deviations |

---

## 6. DATA INGESTION (3 Methods)

### 6a. CSV Upload
| Feature | Description |
|---------|-------------|
| Template downloads | Pre-built CSV templates for all 7 CTE types (Harvesting, Cooling, Initial Packing, First Land-Based Receiving, Shipping, Receiving, Transformation) |
| Drag-and-drop upload | .csv and .tsv, max 10 MB |
| Validation pipeline | KDE validation per CTE type, SHA-256 hash per event, hash chained to previous event |
| Sample dataset | One-click synthetic Romaine Lettuce supply chain (TLC1001, 9 events, farm-to-retailer) |
| Bulk upload | `/onboarding/bulk-upload` — Multi-step bulk data ingestion with field mapping |

### 6b. IoT Import
| Feature | Description |
|---------|-------------|
| Sensitech TempTale | CSV export parser (timestamp, temperature °C, alarm status, serial number) → CTE events |
| Excursion detection | Flags readings exceeding cold chain thresholds (default: 5°C) |
| TLC linking | Links temperature data to specific Traceability Lot Codes |
| Additional devices | Tive, Monnit, and custom CSV with timestamp + temperature columns |

### 6c. Webhook API
| Feature | Description |
|---------|-------------|
| REST endpoint | `POST /api/v1/webhooks/ingest` with API key auth |
| Batch ingestion | Multiple events per request |
| KDE validation | Per-CTE-type validation against §1.1325–§1.1350 |
| Integrity | SHA-256 hash computed + chained per event; response includes event_id + chain_hash |

---

## 7. FREE TOOLS (Lead Generation)

All tools at `/tools/*` are gated behind `LeadGate` for anonymous visitors (name/email/company/role capture). Authenticated users bypass the gate automatically.

| Tool | Route | Description |
|------|-------|-------------|
| FTL Coverage Checker | `/tools/ftl-checker` | Check which products are on the FDA Food Traceability List |
| KDE Completeness Checker | `/tools/kde-checker` | Validate Key Data Element completeness per CTE type |
| CTE Coverage Mapper | `/tools/cte-mapper` | Map supply chain operations to required Critical Tracking Events |
| Readiness Assessment | `/tools/readiness-assessment` | Multi-factor FSMA 204 compliance readiness score |
| Retailer Readiness | `/tools/retailer-readiness` | Benchmark against Walmart, Kroger, Costco requirements |
| Recall Readiness Score | `/tools/recall-readiness` | Assess preparedness for FDA recall scenarios |
| ROI Calculator | `/tools/roi-calculator` | Quantify compliance investment vs. risk reduction |
| Data Import Hub | `/tools/data-import` | CSV upload, IoT import, API guide (see Section 6) |
| Export Tool | `/tools/export` | Generate EPCIS 2.0 or FDA spreadsheet exports |
| TLC Validator | `/tools/tlc-validator` | Validate Traceability Lot Code format and uniqueness |
| Obligation Scanner | `/tools/obligation-scanner` | Extract regulatory obligations from FDA/retailer notices |
| Notice Validator | `/tools/notice-validator` | Analyze FDA notices for applicability to your facility |
| SOP Generator | `/tools/sop-generator` | Generate standard operating procedures for compliance processes |
| AI Q&A | `/tools/ask` | NLP-based compliance question answering over documentation |
| Knowledge Graph | `/tools/knowledge-graph` | Visualize supplier relationships and traceability paths |
| Drill Simulator | `/tools/drill-simulator` | Practice recall scenarios with timing metrics |
| Cold Chain Anomaly Simulator | `/tools/anomaly-simulator` | Create synthetic temperature anomalies for testing |
| Barcode / Label Scanner | `/tools/scan`, `/tools/label-scanner` | Mobile product label scanning and data capture |
| Unified FSMA Tool | `/tools/fsma-unified` | Comprehensive single-page FSMA 204 compliance dashboard |

---

## 8. EXPORT & REPORTING

| Format | Description |
|--------|-------------|
| EPCIS 2.0 JSON-LD | GS1-standard export for retailer compliance (Walmart, Kroger, Costco) |
| FDA 21 CFR 1.1455 | Sortable spreadsheet format for FDA regulatory submissions |
| CSV | General-purpose data export |
| JSON | Programmatic data export |
| SHA-256 manifest | Every export includes a manifest hash for independent integrity verification |
| Export job tracking | Scheduled bundle configuration with status monitoring |
| Recall report | Post-drill report with 24-hour mandate compliance assessment |

---

## 9. SUPPLIER PORTAL

| Feature | Description |
|---------|-------------|
| Supplier portal | `/portal/[portalId]` — External-facing portal for suppliers to submit CTE events |
| Allowed CTE types | Portal scoped to specific CTE types per supplier |
| Submission verification | SHA-256 hash returned on each submission |
| Supplier onboarding funnel | Analytics tracking (SupplierFunnelEventModel) with step/status/metadata |

---

## 10. TRACEABILITY & AUDIT

| Feature | Description |
|---------|-------------|
| Forward/backward trace | `/trace` — Trace products through supply chain in both directions |
| Traceability Lot Codes (TLC) | Per-supplier TLC management with status and product descriptions |
| CTE event log | Immutable event log with KDE data, SHA-256 payload hash, Merkle hash chain |
| Audit trail | Append-only, tamper-evident log: WHO (actor/email/IP/UA), WHAT (event/action/severity), WHERE (resource type/ID) |
| Hash chain verification | `integrity_hash` + `prev_hash` fields implement SHA-256 chain verification (ISO 27001 12.4.1-12.4.3) |
| Open-source verifier | `verify_chain.py` script for independent verification without database access |
| Audit evaluation | `/audit` — Rule evaluation and compliance metrics |

---

## 11. SECURITY & TRUST

| Feature | Route | Description |
|---------|-------|-------------|
| Trust Center | `/trust` | Customer diligence surface: product status, retention, support, deployment posture, security artifacts |
| Architecture overview | `/trust/architecture` | RLS testing, hash verification, audit trail enforcement details |
| Data retention | `/trust/retention` | Retention policies and export integrity verification |
| Support posture | `/trust/support` | Support channels and SLA documentation |
| Security page | `/security` | RLS, SHA-256 hashing, immutable audit trails, open-source verification |
| DPA | `/dpa` | Data Processing Agreement (countersigned DPA available for enterprise/design partners) |
| Hash chain verification | `/verify` | Public-facing hash chain verification tool |
| Row-Level Security | infrastructure | Tenant data isolation enforced at database level |
| Encryption | infrastructure | AES-256 at rest, TLS 1.3 in transit |

---

## 12. DEVELOPER PLATFORM

| Feature | Route/Endpoint | Description |
|---------|----------------|-------------|
| Developer portal | `/developers` | API capabilities overview, authentication guide, SDK roadmap |
| OpenAPI docs | `/docs` | Interactive API reference |
| API Console | `/admin/api-console` | Interactive endpoint testing (admin) |
| Webhook ingestion API | `POST /api/v1/webhooks/ingest` | Push CTE events from any system |
| Ingest file API | `POST /api/v1/ingest/file` | Upload CSV files programmatically |
| IoT ingest API | `POST /api/v1/ingest/iot/sensitech` | Sensitech TempTale import |
| Features endpoint | `GET /api/v1/features` | Discover enabled/disabled API capabilities |
| API key management | `/api-keys` | Self-serve API key generation and rotation |

---

## 13. ADMIN CAPABILITIES

| Feature | Description |
|---------|-------------|
| System admin role | `is_sysadmin` flag on user model |
| Admin master key | Brute-force protected (5 attempts/60s/IP) |
| Partner provisioning | `PATCH /tenants/{id}/partner-status` — Set founding/standard tier (sysadmin only) |
| Tenant creation | `POST /admin/tenants` — Create new workspaces |
| Review queue | Flagged extraction review with approve/reject workflow |
| Funnel metrics | Signup → onboarding → activation conversion tracking |
| System alerts | `/admin/alerts` — System-wide alert monitoring |
| Health checks | `/health` — Deep dependency probes (PostgreSQL, Neo4j, Redis) |
| Metrics endpoint | `/metrics` — Prometheus-compatible metrics (requires X-Metrics-Key) |

---

## 14. BILLING & PRICING

| Tier | GA Price | Partner Price (50% off) | Limits |
|------|----------|------------------------|--------|
| Growth | $999/mo ($832/yr) | $500/mo ($416/yr) | 1 facility, 50K events/mo |
| Scale | $1,999/mo ($1,666/yr) | $1,000/mo ($833/yr) | 5 facilities, 250K events/mo |
| Enterprise | Custom | Custom | Unlimited facilities and events |

| Feature | Description |
|---------|-------------|
| Stripe integration | Checkout flow via `PricingCheckoutButton` |
| 14-day free trial | No credit card required |
| Annual billing | ~15% discount vs. monthly |
| Founding Design Partner | 50% off GA pricing for life, locked at signup or via admin endpoint |
| Plan upgrade/downgrade | Upgrade anytime (prorated), downgrade at end of billing cycle |

---

## 15. BACKEND SERVICES (6 Microservices)

| Service | Port | Endpoints | Description |
|---------|------|-----------|-------------|
| Admin API | 8400 | ~85 | Auth, tenant management, RBAC, invites, supplier onboarding, audit, review queue, billing |
| Ingestion Service | 8002 | ~198 | Webhook ingestion, CSV/IoT import, KDE validation, hash chain, export, rules engine, portal |
| Compliance Service | 8500 | ~6 | FSMA 204 compliance scoring and status management |
| Graph Service | 8200 | ~64 | Supply chain graph queries, forward/backward trace, FSMA trace endpoints |
| NLP Service | 8100 | ~3 | AI-powered document analysis and compliance Q&A |
| Scheduler | 8600 | health only | APScheduler-based background job execution |

**Shared infrastructure per service:** Request size limit (10 MB), request timeout (120s), tenant context middleware, request ID tracing, CORS, rate limiting (100-200 rpm/tenant), Sentry error tracking, structured logging.

---

## 16. INFRASTRUCTURE

| Component | Purpose |
|-----------|---------|
| PostgreSQL | Primary data store with JSONB columns and Row-Level Security |
| Supabase | Auth provider, real-time subscriptions, vector embeddings |
| Redis | Session store, caching, rate limiting |
| Neo4j | Supply chain graph database for trace queries |
| Redpanda (Kafka) | Event streaming between services |
| Nginx | API gateway / reverse proxy |
| Alembic | Database migration management (7 migrations, v002–v052) |
| Docker Compose | Local development orchestration |

---

## 17. CLI TOOL

| Command | Description |
|---------|-------------|
| `regengine compile vertical <name>` | Compile a vertical from YAML schemas → FastAPI routes, Pydantic models, graph nodes, tests |
| `regengine validate vertical <name>` | Validate vertical.yaml and obligations.yaml without compilation |
| `regengine list-verticals` | List all available verticals |

---

## 18. PUBLIC MARKETING PAGES

| Page | Route | Purpose |
|------|-------|---------|
| Landing page | `/` | Hero, features, CTA |
| Product | `/product` | Detailed feature breakdown |
| Pricing | `/pricing` | Plans, partner FAQ, competitor comparison |
| FSMA 204 Guide | `/fsma-204` | Regulatory overview |
| About | `/about` | Company info |
| Case Studies | `/case-studies` | Customer success stories |
| Supplier Compliance | `/supplier-compliance` | Supplier-focused value prop |
| 24-Hour Walkthrough | `/walkthrough` | Step-by-step FDA response demo |
| Blog (9 articles) | `/blog/*` | SEO content on FSMA 204, TLCs, CTEs, compliance checklists, software comparison |

---

## 19. KEY REGULATORY CONSTANTS

| Constant | Value |
|----------|-------|
| FSMA 204 enforcement date | July 20, 2028 |
| Authority | FY 2025 Consolidated Appropriations Act, Division A §775, Pub. L. 118-158 |
| CTE types supported | Harvesting, Cooling, Initial Packing, First Land-Based Receiving, Shipping, Receiving, Transformation |
| Supply chain roles | Grower, Packer, Processor, Distributor, Importer |
| Alert severity levels | CRITICAL (24h), HIGH (24h), MEDIUM (48h), LOW (informational) |

---

*Total: 356 API endpoints, 53 frontend routes, 20 free tools, 17 dashboard pages, 14 database models, 6 microservices.*
