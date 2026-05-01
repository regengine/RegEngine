import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  ClipboardCheck,
  Database,
  FileOutput,
  GitCommitHorizontal,
  Lock,
  ScanLine,
  ShieldCheck,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Product | RegEngine",
  description:
    "RegEngine preflights supplier traceability feeds, creates fix queues, gates production evidence, and exports verified FSMA 204 records.",
  openGraph: {
    title: "Product | RegEngine",
    description: "Supplier data readiness plus a gated FSMA 204 evidence engine.",
    url: "https://regengine.co/product",
    type: "website",
  },
};

const stages = [
  { num: "01", title: "Supplier input", detail: "CSV, spreadsheet, portal, API, or EDI-shaped feed", icon: Database },
  { num: "02", title: "Preflight", detail: "KDE/CTE completeness and lineage checks", icon: ScanLine },
  { num: "03", title: "Fix queue", detail: "Owner-ready defects with severity and evidence impact", icon: ClipboardCheck },
  { num: "04", title: "Commit gate", detail: "Simulation, preflight, staging, production evidence", icon: GitCommitHorizontal },
  { num: "05", title: "Export", detail: "FDA-ready records from verified tenant data", icon: FileOutput },
];

const controls = [
  ["Tenant isolation", "Every record remains scoped to the authenticated tenant."],
  ["Provenance", "Evidence commits require traceable source and run context."],
  ["Mode separation", "Sandbox work cannot silently become production evidence."],
  ["Hash verification", "Committed evidence can be checked without trusting a dashboard."],
];

const outcomes = [
  { icon: ShieldCheck, title: "Readiness is explicit", body: "Scores, fix counts, sources, and export eligibility stay visible." },
  { icon: Lock, title: "Evidence is gated", body: "Production evidence requires identity, provenance, persistence, and clean mode state." },
  { icon: FileOutput, title: "Exports are explainable", body: "FDA packages come from checked records, not a black-box promise." },
];

export default function ProductPage() {
  return (
    <main className="re-page min-h-screen text-[var(--re-text-secondary)]">
      <section className="re-container pb-12 pt-12 md:pb-16 md:pt-16">
        <div className="grid items-start gap-10 md:grid-cols-[0.85fr_1fr]">
          <div>
            <p className="re-label mb-5">Product</p>
            <h1 className="re-hero-title">
              A workbench for deciding what can become evidence.
            </h1>
            <p className="re-hero-copy mt-6">
              RegEngine is built around one simple operating rule: supplier data is useful only after it is mapped, checked, fixed, persisted, and explicitly committed.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/tools/inflow-lab" className="inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] bg-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-surface-base)]">
                Preflight a supplier file <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href="/security" className="inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-text-primary)]">
                Verify security
              </Link>
            </div>
          </div>

          <div className="re-panel self-start overflow-hidden">
            {stages.map(({ num, title, detail, icon: Icon }, index) => (
              <div key={title} className="grid grid-cols-[56px_44px_1fr] items-start gap-4 border-b border-[var(--re-surface-border)] p-4 last:border-b-0">
                <span className="font-mono text-[12px] text-[var(--re-text-muted)]">{num}</span>
                <Icon className="h-5 w-5" style={{ color: index === 3 ? "var(--re-signal-red)" : "var(--re-text-primary)" }} />
                <div>
                  <h2 className="text-base font-semibold">{title}</h2>
                  <p className="mt-1 text-sm leading-6 text-[var(--re-text-muted)]">{detail}</p>
                </div>
              </div>
            ))}
          </div>
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
