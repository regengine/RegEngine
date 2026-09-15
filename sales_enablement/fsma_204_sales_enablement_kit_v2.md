# RegEngine FSMA 204 Sales Enablement Kit v2

Status: **Pre-production / Founding Design Partners only.** Not production-marketed. Replaces v1.1 (archived); see `_archive/`.

---

## 1. Honest Product Description

**One line:** RegEngine ingests CTE/KDE traceability events, runs preflight against FDA 21 CFR 1.1455, and produces a tamper-evident, publicly verifiable export within the FSMA 204 24-hour window.

**Two paragraphs.** RegEngine is a single-container Python service backed by Postgres. It accepts FSMA 204 traceability data via EPCIS 2.0 XML/JSON, GS1 EDI, and CSV, persists it under a tenant-scoped audit chain, and runs the data through the Inflow Workbench — a preflight + commit gate that surfaces missing KDEs, malformed Lot/SSCC identifiers, and CTE coverage gaps before commit. Operators commit only what passes; nothing else mutates the trace graph.

When FDA requests a record, the operator generates a sortable spreadsheet export aligned to 21 CFR 1.1455 along with a SHA-256 hash manifest. Anyone — auditor, customer, regulator — can re-check the export off-platform using the public verifier at `frontend/public/sdk/verify_chain.py`. That check confirms the export's files match the manifest packaged with them; the manifest is not signed, so it does not authenticate the issuer or prove RegEngine origin. There is no message bus, no microservice fan-out, and no partner gateway in the production path: ingest, validate, persist, export, verify.

---

## 2. Verified Capabilities Matrix

| Capability | Status | File evidence |
|---|---|---|
| EPCIS 2.0 ingest (XML + JSON) | Shipping | `services/ingestion/parsers/epcis_*.py` |
| FDA 21 CFR 1.1455 sortable spreadsheet export | Shipping | `services/admin/exports/fda_export.py` |
| Inflow Workbench preflight + commit gate | Shipping | `frontend/app/inflow-lab/`, `services/ingestion/preflight/` |
| Tamper-evident audit chain + public verifier | Shipping | `services/shared/canonical_persistence/`, `frontend/public/sdk/verify_chain.py` |
| Recall drill (mock recall → traceback in <24h) | Shipping | `services/admin/recall/`, demo script in `docs/demos/recall_drill.md` |

Every other capability — partner gateway, white-label provisioning, revenue share, evidence envelope v3 — is **not in the production path** and must not be sold.

---

## 3. 3-Touch Cold Outbound

Target: mid-market fresh-cut QA leads and FLBR/importer compliance owners. Cadence shape preserved from v1.1; specific receiver-program claims removed unless the prospect first confirms the program applies to them.

**Touch 1 — Call (Day 0).** "Hi [Name], I'm [X] from RegEngine. We help FSMA 204 covered operators turn CTE/KDE data into an FDA-oriented sortable export workflow without a six-month integration project. Are you the person who'd own the response if FDA called tomorrow?" If yes: 30-second demo offer. If no: ask for the right name and exit.

**Touch 2 — LinkedIn voice note (Day 2).** 25 seconds. "Saw you own QA / compliance at [Company]. Quick question — when you run a mock recall today, can you produce the FDA sortable spreadsheet in under 24 hours? Most operators we talk to can't yet. Happy to show you what ours looks like — no slides, just the export."

**Touch 3 — Email (Day 5).**
> Subject: 24-hour FDA export for [Company]
>
> [Name] — following the call/voice note. RegEngine produces the 21 CFR 1.1455 sortable spreadsheet from your existing CTE/KDE data, with a tamper-evident manifest your auditor can verify off-platform. Conditional on your buyer's program, we can also produce the ASN/SSCC-18/GS1-128 fields they require.
>
> 15 minutes this week to walk through the export and the verifier?
>
> [Sig]

---

## 4. Objection Handlers

**"Are you focused enough? FSMA 204 is narrow."** Yes — and that's the bet. We do CTE/KDE ingest, preflight, export, and verify. We are not a TMS, a QMS, or an ERP. Narrow scope is why we ship a working 24-hour export instead of a roadmap.

**"You're AI-forward — I don't want a hallucinating compliance tool."** Nothing AI-generated mutates regulated data. Preflight rules are deterministic and code-reviewed; the audit chain is hash-linked; the verifier runs offline. AI is used for operator UX (suggestions, error explanations) and never for ingest, validation, or export.

**"You're pre-revenue — what happens if you go away?"** Your data is yours: standard EPCIS export at any time, plus the public verifier script in our open repo. If RegEngine disappears, your audit chain still verifies and your export still validates against FDA's spec.

---

## 5. Pricing Quick Reference

| Tier | Price | Notes |
|---|---|---|
| Free trial | $0 | 14 days, full feature parity with Growth |
| Growth | $999 / mo | Single tenant, single facility, EPCIS + FDA export, public verifier |
| Scale | Custom | Multi-facility, multi-tenant operator, SSO |
| Enterprise | Custom | Procurement-grade contracts, named CSM, on-prem verifier mirror |

Founding Design Partners: contact sales for pre-production pricing and roadmap input.

---

## 6. What We Are Not

1. **Not a Partner Gateway / white-label provisioning platform.** Routes are stubbed in production (`services/admin/main.py:350`). Partner outreach paused — see §7.
2. **Not a multi-microservice mesh.** One container, one Postgres. No legacy event-broker stack or Redis-as-bus.
3. **Not a TMS, QMS, or ERP.** We sit downstream of those systems and consume their outputs.
4. **Not an "EvidenceEnvelopeV3" platform.** That construct does not exist in the codebase.
5. **Not generally available or production-marketed.** Pre-production. Founding Design Partners only. No public service-level commitments offered.

---

## 7. Partner Outreach

PARTNER OUTREACH PAUSED pending Partner Gateway production decision. See `docs/PRODUCT_DESCRIPTION.md`.
