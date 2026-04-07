import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  Database,
  FileCheck,
  FileOutput,
  FileSpreadsheet,
  Hash,
  Layers,
  Lock,
  Network,
  ScanLine,
  Shield,
  ShieldCheck,
  Truck,
  Upload,
  Workflow,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Product | RegEngine — FSMA 204 Compliance Infrastructure",
  description:
    "From CSV upload to FDA-ready export: data ingestion, real-time FSMA 204 validation, EPCIS 2.0 normalization, cryptographic audit trails, and compliance mapping against 21 CFR Part 1 Subpart S.",
  openGraph: {
    title: "Product | RegEngine — FSMA 204 Compliance Infrastructure",
    description:
      "From CSV upload to FDA-ready export: data ingestion, real-time FSMA 204 validation, EPCIS 2.0 normalization, and cryptographic audit trails.",
    url: "https://www.regengine.co/product",
    type: "website",
  },
};

/* ── Feature data ── */

const FEATURES = [
  {
    Icon: Upload,
    title: "Data Ingestion",
    subtitle: "Get your data in, however it lives today",
    description:
      "Upload CSV or Excel files with guided column mapping. Connect via REST API for automated pipelines. ERP connectors for SAP, Oracle, and NetSuite map your existing fields to FSMA 204 KDEs automatically.",
    details: [
      "CSV and Excel upload with smart column mapping",
      "REST API with webhook notifications",
      "ERP connectors (SAP, Oracle, NetSuite)",
      "Batch and real-time ingestion modes",
    ],
  },
  {
    Icon: ScanLine,
    title: "Real-Time Validation",
    subtitle: "Every record checked against FSMA 204 rules",
    description:
      "As data enters RegEngine, it is validated against the full FSMA 204 rule set: required Key Data Elements, location identifiers, lot code formats, and date integrity. Invalid records are flagged immediately with specific fix instructions.",
    details: [
      "KDE completeness checks per CTE type",
      "Location identifier validation (GLN, FDA FEI)",
      "Lot code format and uniqueness verification",
      "Date range and sequence integrity",
    ],
  },
  {
    Icon: Layers,
    title: "EPCIS 2.0 Normalization",
    subtitle: "Your data, in the standard the FDA expects",
    description:
      "RegEngine normalizes your traceability data into GS1 EPCIS 2.0 event format — the interoperability standard referenced by FDA guidance. Whether your data comes in as CSV rows or API payloads, it leaves as standards-compliant events.",
    details: [
      "Automatic EPCIS 2.0 event structuring",
      "GS1 identifier normalization (GTIN, SSCC, GLN)",
      "Business context mapping (bizStep, disposition)",
      "JSON-LD and XML export formats",
    ],
  },
  {
    Icon: FileOutput,
    title: "FDA-Ready Export Packages",
    subtitle: "Respond to FDA requests in minutes, not weeks",
    description:
      "Generate complete sortable spreadsheets and structured data packages that match FDA 204 recordkeeping requirements. One click produces the exact output format an FDA investigator expects during an inspection or recall.",
    details: [
      "Sortable spreadsheet export (21 CFR \u00A7 1.1455 format)",
      "Structured electronic records (EPCIS 2.0)",
      "Traceability lot code event history",
      "Facility and supply chain documentation bundles",
    ],
  },
  {
    Icon: Shield,
    title: "Audit Trail & Cryptographic Verification",
    subtitle: "Tamper-evident records you can prove are authentic",
    description:
      "Every compliance record is SHA-256 hashed at creation. Database triggers enforce immutability \u2014 no updates, no deletes. An independent open-source verification script lets auditors confirm data integrity without trusting RegEngine.",
    details: [
      "SHA-256 hash chain on every record",
      "Immutable audit trail (append-only, trigger-enforced)",
      "Open-source verify_chain.py for independent verification",
      "Versioned corrections with full lineage tracking",
    ],
  },
];

/* ── Pipeline stages for architecture diagram ── */

const PIPELINE_STAGES = [
  {
    label: "Your Data",
    sublabel: "CSV, API, ERP",
    Icon: FileSpreadsheet,
  },
  {
    label: "RegEngine API",
    sublabel: "FastAPI",
    Icon: Network,
  },
  {
    label: "Validation Engine",
    sublabel: "FSMA 204 Rules",
    Icon: ShieldCheck,
  },
  {
    label: "PostgreSQL",
    sublabel: "RLS + Audit Trail",
    Icon: Database,
  },
  {
    label: "FDA Export",
    sublabel: "EPCIS 2.0 + CSV",
    Icon: FileCheck,
  },
];

/* ── Security controls ── */

const SECURITY_ITEMS = [
  {
    Icon: Lock,
    title: "Row-Level Security",
    description:
      "Every database query is scoped to the authenticated tenant at the PostgreSQL policy level. Cross-tenant data access is structurally impossible.",
  },
  {
    Icon: Hash,
    title: "AES-256 Encryption at Rest",
    description:
      "All stored data is encrypted with AES-256. Encryption keys are managed by the infrastructure provider with automatic rotation.",
  },
  {
    Icon: ShieldCheck,
    title: "SHA-256 Chain Verification",
    description:
      "Every compliance record is deterministically hashed. Any mutation produces a different hash. Independent verification confirms integrity without database access.",
  },
  {
    Icon: FileCheck,
    title: "SOC 2 Type I",
    description:
      "Currently in progress. RegEngine is implementing the controls framework for SOC 2 Type I certification covering security, availability, and confidentiality.",
    inProgress: true,
  },
];

/* ── CTE types covered ── */

const CTE_TYPES = [
  {
    name: "Harvesting",
    description: "Farm-level harvest events with location, date, and lot code",
  },
  {
    name: "Cooling",
    description: "Post-harvest cooling events with temperature and time data",
  },
  {
    name: "Packing",
    description:
      "Packhouse events linking input lots to packed output with quantities",
  },
  {
    name: "Receiving",
    description:
      "Inbound receipt events with source, lot code, quantity, and date",
  },
  {
    name: "Transforming",
    description:
      "Processing events mapping input lots to new output lots with full traceability",
  },
  {
    name: "Creating",
    description:
      "First point of traceability for products entering the supply chain",
  },
  {
    name: "Shipping",
    description:
      "Outbound shipment events with recipient, carrier, lot code, and date",
  },
];

export default function ProductPage() {
  return (
    <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      {/* ── Hero ── */}
      <section className="max-w-[800px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-12 sm:pb-16 text-center">
        <p className="text-xs font-mono uppercase tracking-[0.15em] text-[var(--re-brand)] mb-4">
          Product
        </p>
        <h1 className="font-display text-3xl sm:text-4xl md:text-5xl font-bold text-[var(--re-text-primary)] leading-tight mb-5">
          From your data to{" "}
          <span className="text-[var(--re-brand)]">FDA-ready</span>{" "}
          in one pipeline
        </h1>
        <p className="text-lg text-[var(--re-text-muted)] max-w-xl mx-auto leading-relaxed">
          RegEngine ingests your traceability data, validates it against FSMA 204
          rules in real time, normalizes it to EPCIS 2.0, and produces the exact
          export packages the FDA expects.
        </p>
      </section>

      {/* ── Architecture Diagram ── */}
      <section className="max-w-[900px] mx-auto px-4 sm:px-6 pb-14 sm:pb-20">
        <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-3 text-center">
          How it works
        </h2>
        <p className="text-sm text-[var(--re-text-muted)] text-center mb-10 max-w-lg mx-auto">
          A single pipeline from ingestion to FDA export. No manual steps, no
          data re-entry.
        </p>

        <div
          className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 sm:p-8"
          style={{
            boxShadow:
              "0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)",
          }}
        >
          {/* Desktop: horizontal pipeline */}
          <div className="hidden md:flex items-center justify-between gap-2">
            {PIPELINE_STAGES.map((stage, i) => (
              <div key={stage.label} className="flex items-center gap-2 flex-1">
                <div className="flex flex-col items-center text-center flex-1">
                  <div
                    className="w-14 h-14 rounded-xl flex items-center justify-center mb-3"
                    style={{
                      background:
                        i === 0 || i === PIPELINE_STAGES.length - 1
                          ? "var(--re-brand)"
                          : "var(--re-surface-elevated)",
                      border:
                        i === 0 || i === PIPELINE_STAGES.length - 1
                          ? "none"
                          : "1px solid var(--re-surface-border)",
                    }}
                  >
                    <stage.Icon
                      className="w-6 h-6"
                      style={{
                        color:
                          i === 0 || i === PIPELINE_STAGES.length - 1
                            ? "white"
                            : "var(--re-brand)",
                      }}
                    />
                  </div>
                  <p className="text-sm font-semibold text-[var(--re-text-primary)]">
                    {stage.label}
                  </p>
                  <p className="text-xs font-mono text-[var(--re-text-muted)] mt-0.5">
                    {stage.sublabel}
                  </p>
                </div>
                {i < PIPELINE_STAGES.length - 1 && (
                  <ArrowRight className="w-5 h-5 text-[var(--re-brand)] flex-shrink-0 opacity-60" />
                )}
              </div>
            ))}
          </div>

          {/* Mobile: vertical pipeline */}
          <div className="md:hidden flex flex-col gap-4">
            {PIPELINE_STAGES.map((stage, i) => (
              <div key={stage.label}>
                <div className="flex items-center gap-4">
                  <div
                    className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{
                      background:
                        i === 0 || i === PIPELINE_STAGES.length - 1
                          ? "var(--re-brand)"
                          : "var(--re-surface-elevated)",
                      border:
                        i === 0 || i === PIPELINE_STAGES.length - 1
                          ? "none"
                          : "1px solid var(--re-surface-border)",
                    }}
                  >
                    <stage.Icon
                      className="w-5 h-5"
                      style={{
                        color:
                          i === 0 || i === PIPELINE_STAGES.length - 1
                            ? "white"
                            : "var(--re-brand)",
                      }}
                    />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-[var(--re-text-primary)]">
                      {stage.label}
                    </p>
                    <p className="text-xs font-mono text-[var(--re-text-muted)]">
                      {stage.sublabel}
                    </p>
                  </div>
                </div>
                {i < PIPELINE_STAGES.length - 1 && (
                  <div className="ml-6 mt-2 mb-1 h-4 border-l-2 border-dashed border-[var(--re-brand)]/30" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Feature Walkthrough ── */}
      <section className="max-w-[900px] mx-auto px-4 sm:px-6 pb-14 sm:pb-20">
        <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-3 text-center">
          What RegEngine does
        </h2>
        <p className="text-sm text-[var(--re-text-muted)] text-center mb-10 max-w-lg mx-auto">
          Five capabilities that take you from raw traceability data to
          FDA-ready compliance.
        </p>

        <div className="flex flex-col gap-6">
          {FEATURES.map((feature) => (
            <article
              key={feature.title}
              className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 sm:p-8"
              style={{
                borderLeft: "3px solid var(--re-brand)",
                boxShadow:
                  "0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)",
              }}
            >
              <div className="flex items-start gap-4">
                <div className="p-2.5 rounded-lg bg-[var(--re-brand)]/10 border border-[var(--re-brand)]/20 flex-shrink-0">
                  <feature.Icon className="w-5 h-5 text-[var(--re-brand)]" />
                </div>
                <div className="flex-1">
                  <h3 className="font-display text-lg font-bold text-[var(--re-text-primary)]">
                    {feature.title}
                  </h3>
                  <p className="text-sm font-serif italic text-[var(--re-brand)] mt-0.5">
                    {feature.subtitle}
                  </p>
                  <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mt-3">
                    {feature.description}
                  </p>
                  <ul className="mt-4 grid sm:grid-cols-2 gap-2">
                    {feature.details.map((detail) => (
                      <li
                        key={detail}
                        className="flex items-start gap-2 text-sm text-[var(--re-text-secondary)]"
                      >
                        <CheckCircle2 className="w-4 h-4 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                        {detail}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ── Security Posture ── */}
      <section className="max-w-[900px] mx-auto px-4 sm:px-6 pb-14 sm:pb-20">
        <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-3 text-center">
          Security posture
        </h2>
        <p className="text-sm text-[var(--re-text-muted)] text-center mb-10 max-w-lg mx-auto">
          Compliance data demands enterprise-grade security. Here is what
          protects your records.
        </p>

        <div className="grid sm:grid-cols-2 gap-5">
          {SECURITY_ITEMS.map((item) => (
            <div
              key={item.title}
              className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5"
            >
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 rounded-lg bg-[var(--re-brand)]/10 border border-[var(--re-brand)]/20">
                  <item.Icon className="w-5 h-5 text-[var(--re-brand)]" />
                </div>
                <h3 className="text-sm font-semibold text-[var(--re-text-primary)] flex-1">
                  {item.title}
                </h3>
                {item.inProgress && (
                  <span className="text-[10px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 flex-shrink-0">
                    In Progress
                  </span>
                )}
              </div>
              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                {item.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── FSMA 204 Compliance Mapping ── */}
      <section className="max-w-[900px] mx-auto px-4 sm:px-6 pb-14 sm:pb-20">
        <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-3 text-center">
          FSMA 204 compliance mapping
        </h2>
        <p className="text-sm text-[var(--re-text-muted)] text-center mb-10 max-w-lg mx-auto">
          RegEngine covers all Critical Tracking Event types defined in{" "}
          <span className="font-mono text-[var(--re-text-secondary)]">
            21 CFR &sect; 1.1310
          </span>{" "}
          with recordkeeping requirements per{" "}
          <span className="font-mono text-[var(--re-text-secondary)]">
            21 CFR &sect; 1.1455
          </span>
          .
        </p>

        <div
          className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 sm:p-8"
          style={{
            boxShadow:
              "0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)",
          }}
        >
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-lg bg-[var(--re-brand)]/10 border border-[var(--re-brand)]/20">
              <Workflow className="w-5 h-5 text-[var(--re-brand)]" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-[var(--re-text-primary)]">
                All 7 Critical Tracking Event types
              </h3>
              <p className="text-xs font-mono text-[var(--re-text-muted)]">
                21 CFR Part 1, Subpart S
              </p>
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-3">
            {CTE_TYPES.map((cte) => (
              <div
                key={cte.name}
                className="flex items-start gap-3 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] p-3.5"
              >
                <CheckCircle2 className="w-4 h-4 text-[var(--re-brand)] flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-[var(--re-text-primary)]">
                    {cte.name}
                  </p>
                  <p className="text-xs text-[var(--re-text-muted)] leading-relaxed mt-0.5">
                    {cte.description}
                  </p>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] p-4">
            <p className="text-xs font-mono text-[var(--re-text-muted)] leading-relaxed">
              <span className="text-[var(--re-brand)] font-semibold">
                Regulatory reference:
              </span>{" "}
              Critical Tracking Events defined in 21 CFR &sect; 1.1310.
              Recordkeeping requirements for maintaining and providing records
              per 21 CFR &sect; 1.1455. Key Data Elements (KDEs) validated per
              CTE type as specified in Subpart S of Part 1.
            </p>
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="max-w-[800px] mx-auto px-4 sm:px-6 pb-20 sm:pb-28 text-center">
        <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-3">
          See it in action
        </h2>
        <p className="text-sm text-[var(--re-text-muted)] max-w-md mx-auto mb-8 leading-relaxed">
          Start with the retailer readiness assessment to see where you stand,
          or jump straight to pricing.
        </p>
        <div className="flex gap-3 justify-center flex-wrap">
          <Link
            href="/retailer-readiness"
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--re-brand)] px-6 py-3 text-sm font-semibold text-white hover:bg-[var(--re-brand-dark)] transition-all hover:-translate-y-0.5"
            style={{ boxShadow: "0 4px 16px var(--re-brand-muted)" }}
          >
            <Truck className="w-4 h-4" />
            Retailer readiness assessment
          </Link>
          <Link
            href="/pricing"
            className="inline-flex items-center gap-2 rounded-lg border border-[var(--re-surface-border)] px-6 py-3 text-sm font-semibold text-[var(--re-text-secondary)] hover:border-[var(--re-brand)]/30 transition-colors"
          >
            View pricing
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </main>
  );
}
