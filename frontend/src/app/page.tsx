import Link from "next/link";
import type { Metadata } from "next";
import {
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileCheck2,
  Gauge,
  ScanLine,
  ShieldCheck,
} from "lucide-react";

export const metadata: Metadata = {
  title: "RegEngine — Traceability Proof for FSMA 204",
  description:
    "RegEngine turns supplier traceability data into verified, tenant-scoped FSMA 204 evidence with preflight checks, fix queues, commit gates, and FDA-ready export packages.",
  openGraph: {
    title: "RegEngine — Traceability Proof for FSMA 204",
    description:
      "Preflight supplier data, create fix queues, gate evidence commits, and export verified FSMA 204 records.",
    url: "https://regengine.co",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "RegEngine traceability proof interface" }],
  },
};

const signalRows = [
  ["FreshPack Central", "Shipping", "TLC-DEMO-001", "Blocked", "Missing ship-to"],
  ["Valley Farms", "Harvesting", "TLC-DEMO-002", "Ready", "Commit eligible"],
  ["Cold Dock 7", "Cooling", "TLC-DEMO-003", "Review", "Temperature note"],
  ["Bay Area DC", "Receiving", "TLC-DEMO-004", "Ready", "Export eligible"],
];

const workflow = [
  {
    title: "Preflight the feed",
    body: "Supplier CSV, spreadsheet, portal, API, and EDI-shaped data is checked before anyone treats it as evidence.",
    icon: ScanLine,
    color: "var(--re-info)",
  },
  {
    title: "Create the fix queue",
    body: "Missing KDEs, malformed values, duplicates, and lineage gaps become work that has an owner and a reason.",
    icon: ClipboardCheck,
    color: "var(--re-warning)",
  },
  {
    title: "Commit clean evidence",
    body: "Clean records are committed only after identity, persistence, provenance, and readiness checks pass.",
    icon: ShieldCheck,
    color: "var(--re-success)",
  },
];

const proof = [
  ["Buyer problem", "Supplier files arrive inconsistent, late, and hard to defend"],
  ["Operator decision", "Ready, review, or blocked before production commit"],
  ["Data boundary", "Tenant-scoped persistence with provenance"],
  ["Response posture", "FDA-ready package path from verified records"],
];

const destinations = [
  { label: "Product", href: "/product", icon: Database },
  { label: "Pricing", href: "/pricing", icon: Gauge },
  { label: "Security", href: "/security", icon: FileCheck2 },
  { label: "Trust", href: "/trust", icon: CheckCircle2 },
];

export default function HomePage() {
  return (
    <main className="re-page min-h-screen text-[var(--re-text-secondary)]">
      <section className="re-container grid gap-10 pb-14 pt-12 md:grid-cols-[minmax(0,0.9fr)_minmax(440px,1fr)] md:pb-20 md:pt-18">
        <div className="flex flex-col justify-center">
          <p className="re-label mb-5">For FSQA, compliance, and supplier operations</p>
          <h1 className="max-w-[720px] text-[clamp(42px,7vw,78px)] font-semibold leading-[0.96]">
            Know which supplier records are ready to ship.
          </h1>
          <p className="mt-6 max-w-[610px] text-[17px] leading-7 text-[var(--re-text-muted)]">
            RegEngine preflights messy traceability feeds, shows exactly what blocks retailer or FDA readiness, and commits only verified records to tenant-scoped evidence.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/tools/inflow-lab"
              className="inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] bg-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-surface-base)]"
            >
              Preflight a supplier file
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/retailer-readiness"
              className="inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-text-primary)]"
            >
              Check readiness
            </Link>
          </div>
          <div className="mt-8 grid max-w-[620px] gap-0 border-y border-[var(--re-surface-border)] sm:grid-cols-3">
            {["Supplier files", "Retailer requests", "FDA exports"].map((label) => (
              <div key={label} className="border-b border-[var(--re-surface-border)] py-3 text-[12px] font-semibold uppercase text-[var(--re-text-tertiary)] last:border-b-0 sm:border-b-0 sm:border-r sm:px-4 sm:first:pl-0 sm:last:border-r-0">
                {label}
              </div>
            ))}
          </div>
        </div>

        <div className="re-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-[var(--re-surface-border)] px-4 py-3">
            <div>
              <p className="re-label">Operator workbench</p>
              <p className="mt-1 text-sm font-semibold text-[var(--re-text-primary)]">Supplier feed decisions</p>
            </div>
            <div className="flex items-center gap-2 font-mono text-[11px] text-[var(--re-text-muted)]">
              <span className="re-signal text-[var(--re-success)]" />
              Gate verified
            </div>
          </div>
          <div className="grid grid-cols-3 border-b border-[var(--re-surface-border)]">
            {[
              ["Ready", "2"],
              ["Blocked", "1"],
              ["Mode", "Preflight"],
            ].map(([label, value]) => (
              <div key={label} className="border-r border-[var(--re-surface-border)] px-4 py-4 last:border-r-0">
                <p className="re-label">{label}</p>
                <p className="mt-2 text-2xl font-semibold text-[var(--re-text-primary)]">{value}</p>
              </div>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="re-rule-table re-workbench-table">
              <thead>
                <tr>
                  <th>Supplier</th>
                  <th>CTE</th>
                  <th>Lot</th>
                  <th>Decision</th>
                  <th>Next action</th>
                </tr>
              </thead>
              <tbody>
                {signalRows.map((row) => (
                  <tr key={row.join(":")}>
                    <td className="font-medium text-[var(--re-text-primary)]">{row[0]}</td>
                    <td>{row[1]}</td>
                    <td className="font-mono text-[12px]">{row[2]}</td>
                    <td>
                      <span className="inline-flex items-center gap-2">
                        <span
                          className="re-signal"
                          style={{
                            color:
                              row[3] === "Ready"
                                ? "var(--re-success)"
                                : row[3] === "Review"
                                  ? "var(--re-warning)"
                                  : "var(--re-danger)",
                          }}
                        />
                        {row[3]}
                      </span>
                    </td>
                    <td>{row[4]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="re-section">
        <div className="re-container grid gap-5 md:grid-cols-3">
          {workflow.map((item) => (
            <article key={item.title} className="re-panel p-5">
              <div className="mb-8 flex items-center justify-between border-b border-[var(--re-surface-border)] pb-3">
                <item.icon className="h-5 w-5" style={{ color: item.color }} />
                <span className="re-signal" style={{ color: item.color }} />
              </div>
              <h2 className="text-xl font-semibold">{item.title}</h2>
              <p className="mt-3 text-sm leading-6 text-[var(--re-text-muted)]">{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="re-section">
        <div className="re-container grid gap-8 md:grid-cols-[0.8fr_1fr]">
          <div>
            <p className="re-label mb-4">What the system proves</p>
            <h2 className="max-w-[520px] text-[clamp(30px,4vw,48px)] font-semibold leading-tight">
              Less guesswork. More operational proof.
            </h2>
          </div>
          <div className="re-panel overflow-hidden">
            <table className="re-rule-table">
              <tbody>
                {proof.map(([label, value]) => (
                  <tr key={label}>
                    <td className="w-1/3 font-mono text-[12px] uppercase text-[var(--re-text-muted)]">{label}</td>
                    <td className="font-medium text-[var(--re-text-primary)]">{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="re-section">
        <div className="re-container grid gap-5 md:grid-cols-4">
          {destinations.map(({ label, href, icon: Icon }) => (
            <Link key={label} href={href} className="re-panel group flex min-h-[120px] flex-col justify-between p-5 no-underline">
              <Icon className="h-5 w-5 text-[var(--re-text-muted)]" />
              <span className="flex items-center justify-between text-lg font-semibold text-[var(--re-text-primary)]">
                {label}
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </span>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
