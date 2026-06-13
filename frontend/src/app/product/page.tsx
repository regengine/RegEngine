import type { Metadata } from "next";
import Link from "next/link";
import { experimentalFeaturesEnabled } from "@/lib/experimental-features";
import {
  ArrowRight,
  ClipboardCheck,
  Database,
  FileOutput,
  GitCommitHorizontal,
  GitPullRequestArrow,
  Lock,
  PackageX,
  ScanLine,
  ShieldCheck,
  Workflow,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Product | RegEngine",
  description:
    "RegEngine preflights supplier traceability feeds, creates fix queues, gates production evidence, and helps assemble FSMA 204 export packages from checked tenant data.",
  openGraph: {
    title: "Product | RegEngine",
    description: "Supplier data readiness plus an FSMA 204 evidence engine with explicit commit gates.",
    url: "https://regengine.co/product",
    type: "website",
  },
};

const inflowEffects = [
  {
    title: "Normalize",
    detail: "Raw rows become CTE/KDE candidates with source, lot, facility, and handoff context.",
    icon: Workflow,
    tone: "var(--re-info)",
  },
  {
    title: "Score",
    detail: "Readiness exposes whether the feed can support traceability, recall, and export workflows.",
    icon: ScanLine,
    tone: "var(--re-signal-green)",
  },
  {
    title: "Route",
    detail: "Missing KDEs and lineage breaks become owner-ready fix queue items before persistence.",
    icon: ClipboardCheck,
    tone: "var(--re-warning)",
  },
  {
    title: "Gate",
    detail: "The commit decision separates sandbox/preflight work from production evidence.",
    icon: GitCommitHorizontal,
    tone: "var(--re-danger)",
  },
];

const engineResults = [
  {
    title: "Blocked or corrected",
    detail: "Bad supplier data is routed back through the fix queue instead of polluting the evidence ledger.",
    icon: PackageX,
  },
  {
    title: "Tenant-scoped evidence",
    detail: "Allowed records persist with tenant context, provenance, run hashes, and audit history.",
    icon: Lock,
  },
  {
    title: "Export-ready package",
    detail: "Compliance score, recall posture, and FDA/retailer exports use checked records only.",
    icon: FileOutput,
  },
];

const controls = [
  ["Tenant isolation", "Records are scoped to the authenticated tenant via row-level policies; cross-tenant hardening is in active rollout."],
  ["Provenance", "Evidence commits require traceable source and run context."],
  ["Mode separation", "Sandbox work cannot silently become production evidence."],
  ["Hash verification", "Committed evidence carries content hashes so downstream consumers can re-check it independently. Strict downstream verification is rolling out."],
];

const outcomes = [
  { icon: ShieldCheck, title: "Readiness is explicit", body: "Scores, fix counts, sources, and export eligibility stay visible." },
  { icon: Lock, title: "Evidence is gated", body: "Production evidence is designed to require identity, provenance, persistence, and clean mode state. Rule enforcement is currently advisory in production and being promoted to blocking." },
  { icon: FileOutput, title: "Exports are explainable", body: "Export packages come from checked records, not a black-box promise. Regulatory acceptance and retention obligations remain with the operator." },
];

function InflowImpactDiagram() {
  return (
    <div className="re-panel overflow-hidden">
      <div className="border-b border-[var(--re-border-subtle)] p-5">
        <p className="re-label">Inflow affects RegEngine before evidence exists</p>
        <h2 className="mt-3 text-2xl font-semibold leading-tight text-[var(--re-text-primary)]">
          It turns supplier noise into a commit decision.
        </h2>
      </div>

      <div className="grid gap-0 lg:grid-cols-[0.86fr_1.14fr]">
        <div className="border-b border-[var(--re-border-subtle)] p-5 lg:border-b-0 lg:border-r">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] text-[var(--re-text-primary)]">
              <Database className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="re-label">Raw supplier feed</p>
              <p className="mt-1 text-sm font-semibold text-[var(--re-text-primary)]">
                CSV, portal, API, EPCIS, or EDI-shaped records
              </p>
            </div>
          </div>

          <div className="mt-5 grid gap-3">
            {["unmapped columns", "missing KDEs", "broken handoffs", "sandbox source mode"].map((label) => (
              <div key={label} className="flex items-center justify-between gap-3 border border-[var(--re-border-subtle)] bg-[var(--re-surface-card)] px-3 py-2">
                <span className="text-sm text-[var(--re-text-secondary)]">{label}</span>
                <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--re-warning)]" aria-hidden="true" />
              </div>
            ))}
          </div>

          <div className="mt-5 border border-[var(--re-border-strong)] bg-[var(--re-text-primary)] p-4 text-[var(--re-surface-base)]">
            <div className="flex items-center gap-2 font-mono text-[11px] uppercase">
              <GitPullRequestArrow className="h-4 w-4" aria-hidden="true" />
              Inflow Workbench output
            </div>
            <p className="mt-3 text-sm leading-6">
              One preflight run containing normalized event candidates, readiness score, fix queue, and commit gate state.
            </p>
          </div>
        </div>

        <div className="grid gap-0">
          <div className="grid gap-0 md:grid-cols-4">
            {inflowEffects.map(({ title, detail, icon: Icon, tone }, index) => (
              <article key={title} className="border-b border-r border-[var(--re-border-subtle)] p-4 last:border-r-0">
                <div className="flex items-center justify-between gap-3">
                  <Icon className="h-5 w-5" style={{ color: tone }} aria-hidden="true" />
                  <span className="font-mono text-[11px] text-[var(--re-text-muted)]">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                </div>
                <h3 className="mt-6 text-base font-semibold text-[var(--re-text-primary)]">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-[var(--re-text-muted)]">{detail}</p>
              </article>
            ))}
          </div>

          <div className="grid items-stretch gap-0 md:grid-cols-[1fr_44px_1fr]">
            <div className="p-5">
              <p className="re-label">Commit gate says no</p>
              <h3 className="mt-3 text-lg font-semibold text-[var(--re-text-primary)]">Fix before evidence</h3>
              <p className="mt-2 text-sm leading-6 text-[var(--re-text-muted)]">
                RegEngine keeps failed preflight work in correction mode until the blockers are cleared.
              </p>
            </div>
            <div className="hidden border-x border-[var(--re-border-subtle)] md:grid md:place-items-center">
              <ArrowRight className="h-5 w-5 text-[var(--re-text-muted)]" aria-hidden="true" />
            </div>
            <div className="border-t border-[var(--re-border-subtle)] p-5 md:border-t-0">
              <p className="re-label">Commit gate says yes</p>
              <h3 className="mt-3 text-lg font-semibold text-[var(--re-text-primary)]">Persist and prove</h3>
              <p className="mt-2 text-sm leading-6 text-[var(--re-text-muted)]">
                RegEngine promotes checked records into tenant-scoped evidence, then uses that evidence for scores and exports.
              </p>
            </div>
          </div>

          <div className="grid gap-0 border-t border-[var(--re-border-subtle)] md:grid-cols-3">
            {engineResults.map(({ title, detail, icon: Icon }) => (
              <article key={title} className="border-b border-r border-[var(--re-border-subtle)] p-4 last:border-r-0 md:border-b-0">
                <Icon className="h-5 w-5 text-[var(--re-text-primary)]" aria-hidden="true" />
                <h3 className="mt-5 text-base font-semibold text-[var(--re-text-primary)]">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-[var(--re-text-muted)]">{detail}</p>
              </article>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ProductPage() {
  return (
    <main className="re-page min-h-screen text-[var(--re-text-secondary)]">
      <section className="re-container pb-12 pt-12 md:pb-16 md:pt-16">
        <div className="max-w-[760px]">
          <p className="re-label mb-5">Product</p>
          <h1 className="re-hero-title">
            A workbench for deciding what can become evidence.
          </h1>
          <p className="re-hero-copy mt-6">
            RegEngine is built around one simple operating rule: supplier data is useful only after it is mapped, checked, fixed, persisted, and explicitly committed.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            {experimentalFeaturesEnabled() && (
              <Link href="/tools/inflow-lab" className="inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] bg-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-surface-base)]">
                Preflight a supplier file <ArrowRight className="h-4 w-4" />
              </Link>
            )}
            <Link href="/security" className="inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-text-primary)]">
              Verify security
            </Link>
          </div>
        </div>

        <div className="mt-10">
          <InflowImpactDiagram />
        </div>
      </section>

      <section className="re-section">
        <div className="re-container grid gap-5 md:grid-cols-2">
          <article className="re-panel p-6">
            <p className="re-label mb-4">Core loop</p>
            <h2 className="text-3xl font-semibold leading-tight">Prepare. Prove. Commit. Export.</h2>
            <p className="mt-4 text-sm leading-6 text-[var(--re-text-muted)]">
              Inflow handles the messy outside world. The Engine handles rules, persistence, and gate decisions. The result is an audit path your operations team can explain under pressure.
            </p>
          </article>
          <article className="re-panel overflow-hidden">
            <table className="re-rule-table">
              <tbody>
                {controls.map(([label, detail]) => (
                  <tr key={label}>
                    <td className="w-1/3">
                      <span className="inline-flex items-center gap-2 font-mono text-[12px] uppercase text-[var(--re-text-muted)]">
                        <span className="re-signal text-[var(--re-success)]" />
                        {label}
                      </span>
                    </td>
                    <td className="text-[var(--re-text-primary)]">{detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </article>
        </div>
      </section>

      <section className="re-section">
        <div className="re-container grid gap-5 md:grid-cols-3">
          {outcomes.map(({ icon: Icon, title, body }) => (
            <article key={title} className="re-panel p-5">
              <Icon className="mb-8 h-5 w-5 text-[var(--re-text-primary)]" />
              <h2 className="text-xl font-semibold">{title}</h2>
              <p className="mt-3 text-sm leading-6 text-[var(--re-text-muted)]">{body}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
