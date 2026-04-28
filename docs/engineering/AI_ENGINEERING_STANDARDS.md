# REGENGINE

## AI Engineering Standards & Direction

How we build. What we ship. What we do not.

Version 1.0  |  March 2026  |  INTERNAL - ENGINEERING TEAM ONLY

## Why This Document Exists

We have been building fast. AI agents have helped us ship six commits in a single session, remove 7,000 lines of dead code, and migrate entire driver stacks. That speed is an asset.

But speed without structure produces slop. And slop in this codebase looks like:

- Fantasy architecture docs: files that describe "multiversal timelines" and "$10T ARR" instead of actual system topology.
- Orphaned code: 5,700 lines of dead imports, unused swarm scripts, and test files for services that do not exist.
- Speculative abstractions: "Omni-Vertical Codex" and "Quantum Reality Patching" in a product that sells to food safety directors.
- Inconsistent contracts: three different API key headers across frontend and backend until last week.

This document sets the engineering standard. Every AI agent, every contractor, and every future hire operates from this playbook. If it is not in here, do not assume it is okay.

## The Cardinal Rule

RegEngine is a food traceability compliance platform for FSMA 204. We sell to food safety directors, supplier ops leads, and compliance officers at mid-market food companies. Every line of code, every doc, every commit message must reflect that reality. Nothing else.

## 1. What We Actually Are

Before writing any code, internalize these facts.

### The Product

- Domain: FDA FSMA 204 food traceability compliance.
- Buyer: VP of Food Safety or Compliance at companies doing $10M-$500M in revenue.
- Wedge: API-first traceability record generation. One API call produces FDA-ready audit records.
- Deadline: FDA enforcement begins July 2028. Retailers (Walmart, Kroger, Costco) are requiring compliance now.

### The Tech Stack

| Layer | Technology | Location |
|---|---|---|
| Frontend | Next.js 16, App Router, Tailwind, TypeScript | `frontend/` |
| Backend Services | Python, FastAPI, psycopg (v3) | `services/` |
| Traceability Storage | PostgreSQL canonical tables; Neo4j is legacy/optional visualization | `services/shared/`, `services/graph/` |
| Relational DB | PostgreSQL on Railway | `Postgres/` |
| Shared Code | Python modules | `services/shared/` |
| Infrastructure | Docker, Railway, GitHub Actions | `infra/`, `.github/` |
| SDK | Python SDK, npm `@regengine/fsma-sdk` | `sdk/`, `sdks/` |

### The Services

| Service | Purpose | Directory |
|---|---|---|
| admin | Tenant management, API keys, user accounts | `services/admin/` |
| compliance | FSMA rule evaluation, FDA spreadsheet generation | `services/compliance/` |
| graph | Legacy/optional traceability graph operations | `services/graph/` |
| ingestion | Document upload, normalization, CTE extraction | `services/ingestion/` |
| nlp | NLP extraction, confidence scoring | `services/nlp/` |
| scheduler | Background jobs, scheduled compliance checks | `services/scheduler/` |

## 2. The Seven Engineering Principles

These are non-negotiable. Every PR gets measured against them.

### Principle 1: Ship What Is Real

Every feature, every abstraction, every line of documentation must describe something that exists or is being built this sprint. Speculative architecture is not architecture. It is fiction.

Test before merge:
"Can I point to the file, endpoint, or test that proves this works?"
If no, it does not ship.

### Principle 2: One Vertical, Done Right

We are an FSMA 204 compliance platform. Not a "multi-industry regulatory operating system." Not an "Omni-Vertical Codex." Food traceability.

- Do: Build FSMA-specific CTE types, KDE validators, and FDA spreadsheet generators.
- Do not: Create abstract "regulatory framework" layers that handle "any jurisdiction."
- Do not: Add nuclear, aerospace, or entertainment compliance modules.

### Principle 3: Delete More Than You Write

Dead code is active technical debt that confuses every agent and engineer who touches the codebase.

- Before adding a file: search for existing implementations. If one exists, extend it.
- Before adding a dependency: check whether an existing module already covers the use case.
- After every sprint: run a dead-code sweep. If a file has zero importers, it is a deletion candidate.

### Principle 4: Docs Are Code

Documentation that does not match the codebase is worse than no documentation. Every behavioral change requires a corresponding doc update in the same PR.

Banned patterns in documentation:

- No sci-fi language ("primordial," "multiversal," "quantum," "transcendent").
- No aspirational ARR figures.
- No references to features that do not exist.
- No phase numbers above what is actually shipped.
- No emoji-heavy headers.
- No diagrams of imaginary systems.

### Principle 5: Smallest Viable Change

Every PR should do one thing. If the description requires the word "and," split it.

| Good PR | Bad PR |
|---|---|
| `fix: standardize API key header to X-RegEngine-API-Key` | `feat: new auth system + API keys + migration + tests + docs` |
| `chore: remove 5,678 lines of dead code` | `refactor: restructure entire services layer` |
| `fix: resolve force-dynamic build failure in 7 routes` | `feat: overhaul frontend architecture` |

### Principle 6: Test the Contract, Not the Implementation

Tests should verify that the API returns the right response, not that internal helper functions are called in the right order.

- Required: Every public API endpoint has at least one happy-path and one error-path test.
- Required: Every Pydantic model has a validation test with good and bad inputs.
- Avoid: Mocking internal functions. If you need to mock it, it is probably the wrong test boundary.

### Principle 7: Name Things for the Buyer

Our users are Food Safety Directors, not software engineers. Feature names, error messages, and UI copy must use their vocabulary: "traceability lot," "critical tracking event," "recall drill."

Internal code can use technical terms. Anything user-facing uses FDA/FSMA language.

## 3. Rules for AI Agents

AI agents are treated as junior engineers with unlimited typing speed and zero institutional knowledge.

### 3.1 What Agents Must Do

- Read `AGENTS.md` first.
- Search before creating. Before writing a new file, search for existing implementations.
- Verify before claiming. Never say "tests pass" without running them. Never say "file exists" without checking.
- Use existing patterns. Follow the service bootstrap pattern in `services/shared/paths.py`. Follow App Router patterns in `frontend/src/app/`.
- Stay in scope. If asked to improve architecture, make targeted improvements to what exists.

### 3.2 What Agents Must Not Do

- No speculative docs.
- No new verticals unless explicitly requested by the founder.
- No gratuitous abstraction over a single implementation.
- No creative writing in code.
- No Makefile assumptions. No root `conftest.py` assumptions. No `.gemini/settings.json` assumptions. No absolute `file:///Users/...` paths.

### 3.3 The Agent Output Checklist

Every agent session must end with:

| Check | Requirement |
|---|---|
| Files changed | List every file created, modified, or deleted |
| Commands run | List every test, lint, or build command actually executed |
| CI status | Confirm all GitHub Actions checks pass, or explain what failed |
| Docs updated | If behavior changed, name the doc that was updated |
| Dead code check | If files were deleted, confirm zero remaining imports |

## 4. Code Standards

### 4.1 Python (Backend)

- Formatter: Black (default config).
- Linting: Ruff or flake8.
- Type hints: required on all public function signatures.
- Imports: use `services/shared/paths.py` `ensure_shared_importable()` for cross-service imports.
- Database: psycopg (v3), not psycopg2.
- API keys: `X-RegEngine-API-Key` header exclusively.
- Models: Pydantic v2 for all request/response schemas.

### 4.2 TypeScript (Frontend)

- Framework: Next.js 16 with App Router. No Pages Router.
- Styling: Tailwind CSS. No CSS modules, no styled-components.
- Package manager: npm (`package-lock.json` is committed).
- Static export: `output: export` mode. No `force-dynamic` on routes. Use `force-static` with `generateStaticParams`.
- API calls: use the shared fetch helper in `lib/api-hooks.ts` with `X-RegEngine-API-Key`.
- Mobile: Capacitor for iOS/Android builds.

### 4.3 Commit Messages

Follow Conventional Commits.

`type: short description of what changed`

| Prefix | When to Use | Example |
|---|---|---|
| feat: | New user-facing feature | `feat: add mock recall drill endpoint` |
| fix: | Bug fix | `fix: resolve force-dynamic build failure` |
| chore: | Maintenance, cleanup, deps | `chore: remove 5,678 lines of dead code` |
| SEC: | Security-related change | `SEC: standardize API key header` |
| docs: | Documentation only | `docs: update LOCAL_SETUP_GUIDE` |
| test: | Test additions or fixes | `test: add contract tests for ingestion API` |

Bad commit messages: "update stuff," "fix things," "wip," "miscellaneous improvements."

## 5. Pull Request Process

Every change goes through a PR. No direct pushes to `main` except by the founder in emergencies.

### 5.1 PR Requirements

- Title matches commit message format (`type: description`).
- Description includes what changed, why it changed, and how to test it.
- Size under 400 lines of diff. If bigger, split it.
- CI checks pass before merge.
- No secrets committed (`.env`, API keys, database credentials, tokens).

### 5.2 CI Pipeline

Frontend CI runs five jobs: Build and Bundle Analysis, Lint and Format, Unit Tests, Security Audit, and CI Status Gate. All five must pass. Backend runs pytest across service test directories.

Quick reference: CI failures

- Build failure with "force-dynamic" error -> change to `force-static` and add `generateStaticParams`.
- Import error on psycopg2 -> replace with psycopg (v3).
- API key header mismatch -> use `X-RegEngine-API-Key` everywhere.

## 6. What Good Looks Like vs. What Slop Looks Like

Concrete examples so there is no ambiguity.

### Architecture Documentation

| Good | Slop |
|---|---|
| "RegEngine uses 6 Python FastAPI services behind a Next.js frontend. Traceability data flows from ingestion -> canonical PostgreSQL events -> compliance evaluation -> FDA export." | "RegEngine is a Singular Primordial Source governing every conceivable jurisdiction across 1,024 multiversal timelines via a Sovereign Intelligence Moat." |
| "The compliance service evaluates FSMA 204 rules against ingested CTE records and generates FDA-format spreadsheets." | "The Eternal Return module enables self-sustaining recursive compliance loops that rewrite findings as laws of physics." |

### Feature Naming

| Good | Slop |
|---|---|
| FTL Coverage Checker | Omni-Vertical Compliance Codex |
| Mock Recall Drill | Quantum Reality Patching Engine |
| CTE Record Validator | Primordial Unity Validation Core |
| Supplier Readiness Score | Sovereign Intelligence Moat Score |

### Roadmap Items

| Good | Slop |
|---|---|
| "Add Receiving CTE type to ingestion pipeline" | "Phase 15: Transcend temporal compliance boundaries" |
| "Build email capture on FTL Checker results page" | "Activate Omni-Lead Genesis across all vertical codices" |
| "Integrate Walmart EPCIS 2.0 export format" | "Deploy autonomous cross-retailer reality weaving" |

## 7. Immediate Engineering Priorities

### Priority 1: Email Capture on Free Tools

The FTL Checker and Retailer Readiness Assessment generate free tool usage but capture zero leads. After a user checks coverage, show a results page with a soft gate: "Enter your email to save your results."

- Backend: new endpoint in admin service: `POST /api/leads` with `email`, `tool_used`, and results payload.
- Frontend: results page component with email input, stored to Supabase or PostgreSQL.
- Scope: 2-3 day task. No over-engineering.

### Priority 2: Fix Existing Docs

`ARCHITECTURE.md` and `PRODUCT_ROADMAP.md` contained AI-generated fantasy and must reflect reality.

- `ARCHITECTURE.md`: actual service topology, data flow, and infrastructure diagram.
- `PRODUCT_ROADMAP.md`: concrete 90-day plan tied to customer acquisition.
- Scope: 1 day task.

### Priority 3: API Response Examples in Developer Docs

The `/developers` page shows request code but not response shapes. Add JSON response examples to every code tab on the developers page.

### Priority 4: Free Tier on Pricing Page

There is no bridge between free-tool users and paid customers. Add a Free/Starter tier with limited API calls (100 events/mo, 1 user, community support).

## 8. The Standard

RegEngine is a real product solving a real compliance deadline for real food companies. The engineering team's job is to make that product reliable, fast, and trustworthy.

Not to build science fiction. Not to impress other engineers. Not to create abstractions for problems we do not have.

Ship what is real. Delete what is not. Keep it boring. Boring ships.

Christopher Sellers  
Founder, RegEngine  
March 2026
