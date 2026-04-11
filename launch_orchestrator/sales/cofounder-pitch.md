# RegEngine — Technical Co-Founder Opportunity

## The One-Liner

Join as co-founder of an API-first FSMA 204 compliance platform with a shipped production product, $400K pre-seed raise in progress, and a 200,000-facility regulatory mandate with a hard federal deadline.

## Why This Exists

The FDA's FSMA 204 rule requires 200,000+ US food facilities to implement end-to-end traceability by **July 20, 2028**. Every company on the FDA's Food Traceability List — from leafy greens growers to seafood distributors — must capture, store, and produce standardized compliance records within 24 hours of an FDA request.

The incumbents (ReposiTrak, FoodLogiQ, TraceGains) are UI-heavy, implementation-heavy, and priced for Fortune 500 food companies. The mid-market — 50,000+ companies doing $10M–$150M in revenue — has no affordable, API-first option.

**RegEngine is that option.**

## What's Already Built (Not a Slide Deck — Shipped Code)

- **Full-stack production deployment**: Next.js 15 on Vercel, FastAPI on Railway, PostgreSQL on Supabase
- **All 7 FSMA 204 CTE types** with complete KDE capture and validation
- **24-hour recall response system** with 5-phase gates, live countdown timer, FDA-ready export
- **Cryptographic audit trail** — SHA-256 hash chain that lets any party independently verify record integrity without trusting the platform
- **Multi-source ingestion**: API, CSV, XLSX, EPCIS 2.0, EDI, QR/barcode scan, supplier portal
- **6-dimensional compliance scoring** with 78+ tracked regulatory obligations
- **Developer API portal** with interactive playground and partner gateway OpenAPI spec
- **11 CI/CD workflows**, 54 automated checks, 52+ database migrations
- **WCAG 2.1 AA accessibility** — unusual at pre-seed, signals product maturity

Simulated recall performance: **42 minutes** (vs. 18+ hour industry baseline), **98% KDE completeness**.

## Tech Stack

| Layer | Stack |
|-------|-------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| Frontend | Next.js 15, React 18, TypeScript 5.9, Tailwind, shadcn/ui |
| Database | PostgreSQL 17 (Supabase), migrating off Neo4j/Redis to consolidated Postgres |
| Infra | Vercel Pro, Railway Pro, Docker Compose (15+ services local dev) |
| Observability | OpenTelemetry, Jaeger, Prometheus, Grafana, Sentry |
| CI/CD | GitHub Actions (11 workflows), Playwright E2E, Vitest |
| Auth | Supabase Auth (SSR) + JWT fallback, RLS multi-tenancy |

## The Role

**Title**: Co-Founder / CTO
**Equity**: Negotiable (meaningful co-founder stake, not employee options)
**Cash**: Modest salary from pre-seed raise, scaling with revenue
**Location**: Remote-first

### What You'd Own

1. **Customer engineering** — Work directly with design partners to deploy, debug, and iterate. The first 5 customers will define the product.
2. **Backend architecture** — Lead the consolidation from 6 microservices to a monolith (already planned), replace Kafka/Neo4j/Redis with PostgreSQL-native solutions.
3. **Data pipeline reliability** — EPCIS 2.0 ingestion, supplier data quality, format normalization across CSV/EDI/XML.
4. **Compliance engine** — The core regulatory logic that maps raw supply chain events to FDA-auditable records.
5. **Production operations** — Monitoring, incident response, scaling. Runbooks exist. Culture of operational discipline is established.

### What You'd Need

- Strong Python (FastAPI preferred) or willingness to ramp fast
- Database depth — PostgreSQL performance, migrations, query optimization
- Comfort with ambiguity — pre-seed means wearing every hat
- Ability to talk to customers (food safety managers, IT directors at distributors)
- Not required but valuable: food industry, supply chain, or regulatory compliance experience

### What You Wouldn't Need to Do

- Fundraise (founder handles investor relations)
- Design UI (design system and component library are established)
- Build from scratch (688K lines of production code already exist)
- Set up CI/CD (54 automated checks already running)

## Market Timing

| Signal | Detail |
|--------|--------|
| Federal deadline | July 20, 2028 — hard, non-negotiable |
| Retailer pressure | Walmart, Kroger, Costco pushing suppliers to prove readiness NOW |
| Competitor gaps | No API-first player in mid-market. iFoodDS and ReposiTrak landing accounts but are UI/enterprise-first |
| TAM | 200,000+ facilities, $999–$1,999/mo price point |
| Exit comps | TraceGains acquired for $350M. FoodLogiQ acquired by Trustwell |

## What's Next

- **Raising**: $400K pre-seed
- **Pipeline**: 5 named design partner targets ($15M–$116M revenue each)
- **Goal**: First paying customer within 60 days of co-founder joining
- **12-month target**: $60K ARR from 5 mid-market accounts

## About the Founder

Christopher Sellers — solo technical founder. Built the entire platform in ~2 months (993 commits, 8 versioned releases). Background in compliance systems. Ships fast, documents obsessively (7 self-audits, 6 runbooks, production environment checklist with 167 categorized env vars). Looking for a co-founder who complements with customer-facing engineering and production ops depth.

## How to Evaluate This

1. **Visit the product**: It's deployed. Real pages, real APIs, real data flows.
2. **Read the codebase**: Public repo. The code quality speaks for itself.
3. **Run the demo script**: `sales/design_partner_demo_script.md` — 15-minute walkthrough of the full product.
4. **Check the audit trail**: `scripts/verify_fsma_only.py` — the same verification an FDA inspector would run.

This isn't a pitch deck looking for an engineer. It's a shipped product looking for a co-founder.
