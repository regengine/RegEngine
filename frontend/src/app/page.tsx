import Link from "next/link";
import type { Metadata } from "next";
import {
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileCheck2,
  Gauge,
  PackageCheck,
  ScanLine,
  ShieldCheck,
  TimerReset,
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

const feedRows = [
  { supplier: "FreshPack Central", cte: "Shipping", lot: "TLC-DEMO-001", status: "Blocked", issue: "Ship-to missing" },
  { supplier: "Valley Farms", cte: "Harvesting", lot: "TLC-DEMO-002", status: "Ready", issue: "Commit eligible" },
  { supplier: "Cold Dock 7", cte: "Cooling", lot: "TLC-DEMO-003", status: "Review", issue: "Temp note" },
  { supplier: "Bay Area DC", cte: "Receiving", lot: "TLC-DEMO-004", status: "Ready", issue: "Export eligible" },
];

const workflow = [
  { label: "Intake", detail: "CSV, API, EDI, portal", icon: ScanLine, color: "var(--re-info)" },
  { label: "Normalize", detail: "CTE/KDE shape check", icon: Database, color: "var(--re-signal-blue)" },
  { label: "Block / fix", detail: "Owner and reason", icon: ClipboardCheck, color: "var(--re-warning)" },
  { label: "Commit", detail: "Tenant evidence gate", icon: ShieldCheck, color: "var(--re-success)" },
  { label: "Export", detail: "FDA-ready package", icon: PackageCheck, color: "var(--re-danger)" },
];

const proof = [
  ["Supplier reality", "Different file shapes, late responses, duplicate lots, missing KDEs."],
  ["Operator decision", "Ready, review, or blocked before records become evidence."],
  ["Evidence boundary", "Tenant-scoped persistence with provenance and verification history."],
  ["Response posture", "Recall and retailer request packages generated from clean records."],
];

const outcomes = [
  {
    title: "Find the failure point",
    body: "See which CTE, supplier, lot, or field blocks readiness before the problem lands in production.",
    icon: ScanLine,
  },
  {
    title: "Give the queue an owner",
    body: "Turn missing KDEs and malformed values into accountable remediation work instead of spreadsheet archaeology.",
    icon: ClipboardCheck,
  },
  {
    title: "Ship defensible evidence",
    body: "Commit only records that pass identity, provenance, persistence, and export checks.",
    icon: ShieldCheck,
  },
];

const destinations = [
  { label: "Product", href: "/product", icon: Database, note: "Platform view" },
  { label: "Pricing", href: "/pricing", icon: Gauge, note: "Plans and limits" },
  { label: "Security", href: "/security", icon: FileCheck2, note: "Controls and posture" },
  { label: "Trust", href: "/trust", icon: CheckCircle2, note: "Architecture and proof" },
];

function statusColor(status: string) {
  if (status === "Ready") {
    return "var(--re-success)";
  }
  if (status === "Review") {
    return "var(--re-warning)";
  }
  return "var(--re-danger)";
}

function StatusDot({ status }: { status: string }) {
  return <span className="re-signal" style={{ color: statusColor(status) }} />;
}

function ActionLink({
  href,
  children,
  primary = false,
}: {
  href: string;
  children: React.ReactNode;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={[
        "inline-flex h-11 items-center justify-center gap-2 border px-5 text-[13px] font-semibold no-underline transition-colors",
        primary
          ? "border-[var(--re-text-primary)] bg-[var(--re-text-primary)] text-[var(--re-surface-base)] hover:bg-[var(--re-signal-green)]"
          : "border-[var(--re-border-strong)] text-[var(--re-text-primary)] hover:bg-[var(--re-surface-elevated)]",
      ].join(" ")}
    >
      {children}
    </Link>
  );
}

function WorkbenchPreview() {
  return (
    <div className="re-panel overflow-hidden bg-[var(--re-surface-elevated)]">
      <div className="grid border-b border-[var(--re-surface-border)] md:grid-cols-[1fr_180px]">
        <div className="p-5">
          <p className="re-label">Live preflight</p>
          <h2 className="mt-2 text-2xl font-semibold leading-tight text-[var(--re-text-primary)]">Supplier feed decisions</h2>
          <p className="mt-2 max-w-[460px] text-sm leading-6 text-[var(--re-text-muted)]">
            Records are scored before commit, with every blocker tied to an owner and evidence boundary.
          </p>
        </div>
        <div className="grid grid-cols-3 border-t border-[var(--re-surface-border)] md:grid-cols-1 md:border-l md:border-t-0">
          {[
            ["Ready", "2", "var(--re-success)"],
            ["Blocked", "1", "var(--re-danger)"],
            ["ETA", "04:12", "var(--re-warning)"],
          ].map(([label, value, color]) => (
            <div key={label} className="border-r border-[var(--re-surface-border)] px-4 py-3 last:border-r-0 md:border-b md:border-r-0 md:last:border-b-0">
              <p className="re-label">{label}</p>
              <p className="mt-1 flex items-center gap-2 text-xl font-semibold text-[var(--re-text-primary)]">
                <span className="re-signal" style={{ color }} />
                {value}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] border-collapse text-[13px]">
            <thead>
              <tr>
                {["Supplier", "CTE", "Lot", "Status", "Issue"].map((label) => (
                  <th key={label} className="border-b border-[var(--re-surface-border)] px-4 py-3 text-left font-mono text-[11px] font-medium uppercase text-[var(--re-text-muted)]">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {feedRows.map((row) => (
                <tr key={row.lot}>
                  <td className="border-b border-[var(--re-surface-border)] px-4 py-3 font-medium text-[var(--re-text-primary)]">{row.supplier}</td>
                  <td className="border-b border-[var(--re-surface-border)] px-4 py-3">{row.cte}</td>
                  <td className="border-b border-[var(--re-surface-border)] px-4 py-3 font-mono text-[12px]">{row.lot}</td>
                  <td className="border-b border-[var(--re-surface-border)] px-4 py-3">
                    <span className="inline-flex items-center gap-2">
                      <StatusDot status={row.status} />
                      {row.status}
                    </span>
                  </td>
                  <td className="border-b border-[var(--re-surface-border)] px-4 py-3">{row.issue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid border-t border-[var(--re-surface-border)] sm:grid-cols-3">
          {["Identity resolved", "KDE completeness", "Hash chain ready"].map((item, index) => (
            <div key={item} className="border-b border-[var(--re-surface-border)] px-4 py-3 sm:border-b-0 sm:border-r sm:last:border-r-0">
              <p className="flex items-center gap-2 text-sm font-semibold text-[var(--re-text-primary)]">
                <span className="flex h-5 w-5 items-center justify-center border border-[var(--re-border-default)] text-[10px]">
                  {index + 1}
                </span>
                {item}
              </p>
              <p className="mt-1 font-mono text-[11px] text-[var(--re-text-muted)]">pass:{index === 1 ? "review" : "true"}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <main className="re-page min-h-screen text-[var(--re-text-secondary)]">
      <section className="re-container grid min-h-[calc(100vh-56px)] items-center gap-10 py-10 lg:grid-cols-[0.86fr_1.14fr] lg:py-12">
        <div>
          <h1 className="max-w-[680px] text-[clamp(44px,6.6vw,76px)] font-semibold leading-[0.95] text-[var(--re-text-primary)]">
            Traceability proof before records ship.
          </h1>
          <p className="mt-6 max-w-[590px] text-[18px] leading-8 text-[var(--re-text-muted)]">
            RegEngine turns messy supplier files into clear readiness decisions, fix queues, and verified FSMA 204 evidence packages.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ActionLink href="/tools/inflow-lab" primary>
              Preflight a supplier file
              <ArrowRight className="h-4 w-4" />
            </ActionLink>
            <ActionLink href="/retailer-readiness">Check readiness</ActionLink>
          </div>
          <div className="mt-10 grid max-w-[620px] border-y border-[var(--re-surface-border)] sm:grid-cols-3">
            {[
              ["24h", "Recall response path"],
              ["CTE/KDE", "Field-level blockers"],
              ["Tenant", "Scoped evidence"],
            ].map(([value, label]) => (
              <div key={label} className="border-b border-[var(--re-surface-border)] py-4 sm:border-b-0 sm:border-r sm:px-4 sm:first:pl-0 sm:last:border-r-0">
                <p className="text-2xl font-semibold text-[var(--re-text-primary)]">{value}</p>
                <p className="mt-1 re-label">{label}</p>
              </div>
            ))}
          </div>
        </div>

        <WorkbenchPreview />
      </section>

      <section className="border-y border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
        <div className="re-container grid gap-0 py-0 md:grid-cols-5">
          {workflow.map((step, index) => (
            <div key={step.label} className="border-b border-[var(--re-surface-border)] px-0 py-5 md:border-b-0 md:border-r md:px-5 md:first:pl-0 md:last:border-r-0">
              <div className="flex items-center justify-between gap-3">
                <step.icon className="h-5 w-5" style={{ color: step.color }} />
                <span className="font-mono text-[11px] text-[var(--re-text-muted)]">{String(index + 1).padStart(2, "0")}</span>
              </div>
              <h2 className="mt-5 text-xl font-semibold text-[var(--re-text-primary)]">{step.label}</h2>
              <p className="mt-2 text-sm text-[var(--re-text-muted)]">{step.detail}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="re-section">
        <div className="re-container grid gap-10 lg:grid-cols-[0.82fr_1fr]">
          <div>
            <h2 className="max-w-[540px] text-[clamp(32px,4.5vw,56px)] font-semibold leading-tight">
              Make the readiness decision visible.
            </h2>
            <p className="mt-5 max-w-[480px] text-base leading-7 text-[var(--re-text-muted)]">
              The interface is built around the daily question: which supplier records can move, which need review, and what proof will survive an audit.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            {outcomes.map(({ title, body, icon: Icon }) => (
              <article key={title} className="border-t border-[var(--re-border-strong)] pt-4">
                <Icon className="h-5 w-5 text-[var(--re-text-primary)]" />
                <h3 className="mt-7 text-xl font-semibold text-[var(--re-text-primary)]">{title}</h3>
                <p className="mt-3 text-sm leading-6 text-[var(--re-text-muted)]">{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="re-section">
        <div className="re-container grid gap-8 lg:grid-cols-[0.74fr_1fr]">
          <div>
            <TimerReset className="h-7 w-7 text-[var(--re-signal-red)]" />
            <h2 className="mt-6 max-w-[520px] text-[clamp(30px,4vw,48px)] font-semibold leading-tight">
              Operational proof without the spreadsheet chase.
            </h2>
          </div>
          <div className="re-panel overflow-hidden">
            <table className="re-rule-table">
              <tbody>
                {proof.map(([label, value]) => (
                  <tr key={label}>
                    <td className="w-[34%] font-mono text-[12px] uppercase text-[var(--re-text-muted)]">{label}</td>
                    <td className="font-medium text-[var(--re-text-primary)]">{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="re-section pb-24">
        <div className="re-container grid gap-5 md:grid-cols-4">
          {destinations.map(({ label, href, icon: Icon, note }) => (
            <Link key={label} href={href} className="group border-t border-[var(--re-border-strong)] pt-4 no-underline">
              <div className="flex items-center justify-between">
                <Icon className="h-5 w-5 text-[var(--re-text-muted)]" />
                <ArrowRight className="h-4 w-4 text-[var(--re-text-primary)] transition-transform group-hover:translate-x-1" />
              </div>
              <span className="mt-10 block text-2xl font-semibold text-[var(--re-text-primary)]">{label}</span>
              <span className="mt-2 block text-sm text-[var(--re-text-muted)]">{note}</span>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
