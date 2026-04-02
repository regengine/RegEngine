/**
 * marketing-claims.ts
 *
 * Single source of truth for every verifiable claim on the public website.
 * Before adding a claim here, confirm it with code, tests, or a cited source.
 *
 * ── Update checklist ──
 * 1. Verify the claim is true (code, test output, or external source).
 * 2. Add/update the entry below with a `source` annotation.
 * 3. Every public page imports from this file — changes propagate automatically.
 */

// ─── Verified Capabilities ─────────────────────────────────────────
// These are backed by implemented, tested code in the repository.

export const VERIFIED_CAPABILITIES = {
  epcis: "EPCIS 2.0 native",
  hashChain: "SHA-256 hash-chained audit trail",
  merkleVerification: "Merkle proof verification",
  fdaExport: "FDA-sortable CSV export per 21 CFR 1.1455(b)(3)",
  ftlCategories: "All 23 FDA Food Traceability List categories",
  rls: "Row-Level Security (PostgreSQL RLS)",
  immutableAudit: "Immutable append-only audit trail",
  gs1Validation: "GS1 identifier validation (GTIN, GLN, SSCC, TLC)",
  kdeValidation: "KDE validation on every inbound CTE",
  complianceStateMachine: "Compliance state tracking",
  identityResolution: "Fuzzy matching with confidence scoring",
  supabase: "Built on Supabase",
} as const;

// ─── Homepage "Built on" credibility strip ─────────────────────────
// Only claims backed by shipped code. No traction metrics.
export const CREDIBILITY_CLAIMS = [
  "EPCIS 2.0 native",
  "SHA-256 verified chains",
  "Built on Supabase",
] as const;

// ─── Security page: verified evidence statements ───────────────────
// Each `evidence` field must describe what the code does, not fabricated output.
export const SECURITY_EVIDENCE = {
  rls: "Tested: Tenant A cannot query Tenant B data (0 rows returned). Public access correctly blocked.",
  hashing:
    "Verified: Re-running ingestion produces identical hashes. Independent verification script (verify_chain.py) confirms integrity.",
  immutableAudit:
    "Enforced via prevent_mutation trigger (V20). Append-only audit_logs enforced via prevent_audit_modification (V30). Version chain verified from V1 through V16.",
  independentVerification:
    "verify_chain.py lets anyone independently verify data integrity without database access. Merkle proof validation confirms chain integrity.",
} as const;

// ─── Regulatory facts (externally verifiable) ──────────────────────
export const REGULATORY = {
  fsma204Deadline: "July 20, 2028",
  fdaResponseWindow: "24 hours",
  // Source: FDA FSMA 204 final rule, 21 CFR Part 1 Subpart S
  fdaReInspectionFeePerHour: "$225",
  // Source: Grocery Manufacturers Association / industry estimates
  averageRecallCost: "$10 million",
} as const;

// Retailer enforcement claims — include source so they can be re-verified
export const RETAILER_ENFORCEMENT = [
  {
    retailer: "Walmart",
    claim: "Supplier compliance clauses active since August 2025",
    source: "Walmart supplier portal — ASN and packaging requirements",
  },
  {
    retailer: "Kroger",
    claim: "Enhanced traceability requirements for fresh categories",
    source: "Kroger EDI 856 compliance requirement",
  },
  {
    retailer: "Albertsons",
    claim: "FSMA 204 requirements in new supplier contracts",
    source: "Albertsons supplier onboarding materials",
  },
  {
    retailer: "Costco",
    claim: "Supplier quality programs incorporating traceability",
    source: "Costco supplier quality program",
  },
] as const;

// ─── Pricing ───────────────────────────────────────────────────────
// Business decisions, not traction claims. Update when pricing changes.
export const PRICING = {
  partnerDiscount: "50% off GA pricing for the life of their account",
  starterMonthly: "$425",
  growthMonthly: "$549",
  scaleMonthly: "$639",
  // Numeric values for calculations (keep in sync with strings above)
  starterMonthlyNum: 425,
  growthMonthlyNum: 549,
  scaleMonthlyNum: 639,
  freeTrialDays: 14,
} as const;

// ─── Roadmap items (clearly future) ───────────────────────────────
// These are labeled as targets, not achievements.
export const ROADMAP = {
  soc2Type1: "SOC 2 Type I — target Q3 2026",
  soc2Type2: "SOC 2 Type II — target Q1 2027",
  penTesting: "Annual penetration testing — starting Q4 2026",
  gdprDpa: "GDPR Data Processing Agreement template — Q2 2026",
} as const;

// ─── Developer page capability descriptions ────────────────────────
// Feature descriptions backed by implemented code.
export const API_CAPABILITIES = {
  webhookIngestion:
    "POST events with KDE validation. Every inbound CTE is validated against FSMA 204 Key Data Elements before chain-hashing.",
  rulesEngine:
    "FSMA 204 validation rules run automatically on every event. Catch missing fields, invalid TLCs, and schema violations in real time.",
  identityResolution:
    "Fuzzy matching across trading partners with confidence scoring. Deduplicate facilities, carriers, and contacts automatically.",
  fdaExport:
    "21 CFR 1.1455 sortable spreadsheet and EPCIS 2.0 event export. One API call to generate an FDA-ready compliance package.",
  complianceScoring:
    "Multi-dimension score with letter grade. Coverage, completeness, timeliness, accuracy, chain integrity, and identity resolution.",
  requestWorkflow:
    "State machine for FDA response management. Track requests from intake through investigation, response, and closure.",
} as const;
