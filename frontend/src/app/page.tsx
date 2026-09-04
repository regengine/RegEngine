import Link from "next/link";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import {
  ArrowRight,
  Boxes,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileCheck2,
  Gauge,
  GitBranch,
  PackageCheck,
  ScanLine,
  ShieldCheck,
} from "lucide-react";
import {
  CommitGate,
  ComplianceStateBadge,
  EvidenceCard,
  EvidencePackagePreview,
  HashVerificationStrip,
} from "@/components/compliance";
import { sandboxCta } from "@/lib/sandbox-cta";

export const metadata: Metadata = {
  title: "RegEngine — FSMA 204 traceability evidence layer",
  description:
    "Ingest CTE/KDE records, check coverage and completeness, commit append-only after checks you configure, export FDA-oriented and buyer-oriented spreadsheets. Early-stage. Design-partner. Pre-revenue. Not an FDA endorsement.",
  openGraph: {
    title: "RegEngine — FSMA 204 traceability evidence layer",
    description:
      "Ingest CTE/KDE records, check coverage and completeness, commit append-only after checks you configure, export FDA-oriented and buyer-oriented spreadsheets.",
    url: "https://regengine.co",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "RegEngine FSMA 204 traceability evidence layer" }],
  },
};

const demoMetrics = [
  { label: "FTL list overlap", value: "91%", sublabel: "Example", state: "needs-correction" as const },
  { label: "KDE completeness", value: "84%", sublabel: "Gaps flagged", state: "needs-correction" as const },
  { label: "Export checklist", value: "72%", sublabel: "Items open", state: "blocked" as const },
];

const supplierChecklistExamples = [
  {
    supplier: "FreshPack Central",
    issue: "Ship-to location missing for 3 lots",
    state: "blocked" as const,
  },
  {
    supplier: "Valley Farms",
    issue: "Harvest date and quantity validated",
    state: "committed" as const,
  },
  {
    supplier: "Cold Dock 7",
    issue: "Temperature note requires review",
    state: "needs-correction" as const,
  },
];

const evidenceCards = [
  {
    title: "Ingest workspace",
    description: "CTE/KDE records arrive through webhooks, CSV, EPCIS, or EDI and enter the inflow workbench for coverage checking.",
    state: "needs-correction" as const,
    meta: "Inflow workbench",
    icon: Gauge,
  },
  {
    title: "Commit ledger",
    description: "After checks you configure, accepted records enter the append-only evidence ledger with provenance and workspace scope.",
    state: "committed" as const,
    meta: "Evidence ledger",
    icon: GitBranch,
  },
  {
    title: "Export package state",
    description: "Drafted, blocked on checklist, or exported. §1.1455 is the FDA records-request rule. This card does not claim we meet that clock.",
    state: "needs-correction" as const,
    meta: "Package state",
    icon: PackageCheck,
  },
];

const workflow = [
  { label: "Ingest", detail: "Webhooks, CSV, EPCIS, or EDI files enter the workbench.", icon: ScanLine },
  { label: "Check", detail: "CTE/KDE coverage and completeness are flagged in the inflow workbench.", icon: Database },
  { label: "Fix", detail: "Every gap gets a reason, owner, and recovery path.", icon: ClipboardCheck },
  { label: "Commit", detail: "Commit is our append-only step. After the checks you configure, accepted records enter the evidence ledger. Commit is not a certification, not an FDA gate, and not a retailer gate.", icon: ShieldCheck },
  { label: "Export", detail: "FDA-oriented, buyer-oriented, or internal packets with a hash manifest where enabled.", icon: PackageCheck },
];

const destinations = [
  { label: "Product", href: "/product", icon: Database, note: "Command Center workflows" },
  { label: "Tools", href: "/tools", icon: Gauge, note: "Compliance instruments" },
  { label: "Security", href: "/security", icon: FileCheck2, note: "Evidence Ledger controls" },
  { label: "Trust", href: "/trust", icon: CheckCircle2, note: "Verification posture" },
];

function ActionLink({
  href,
  children,
  primary = false,
}: {
  href: string;
  children: ReactNode;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={[
        "inline-flex min-h-11 items-center justify-center gap-2 border px-5 py-3 text-[13px] font-semibold no-underline transition-colors",
        primary
          ? "border-[var(--re-text-primary)] bg-[var(--re-text-primary)] text-[var(--re-surface-base)] hover:bg-[var(--re-success)]"
          : "border-[var(--re-border-strong)] bg-[var(--re-surface-elevated)] text-[var(--re-text-primary)] hover:bg-[var(--re-surface-card)]",
      ].join(" ")}
    >
      {children}
    </Link>
  );
}

function MetricRail() {
  return (
    <div className="mt-8">
      <p className="mb-3 inline-flex border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] px-3 py-1 font-mono text-[11px] uppercase text-[var(--re-text-muted)]">
        Synthetic demo · example numbers · not a customer workspace
      </p>
      <div className="re-home-command-rail">
        {demoMetrics.map((metric) => (
          <div key={metric.label} className="border-b border-r border-[var(--re-surface-border)] p-4 last:border-r-0 md:border-b-0">
            <p className="text-2xl font-semibold leading-none text-[var(--re-text-primary)]">{metric.value}</p>
            <div className="mt-3 flex flex-col gap-2">
              <p className="re-label">{metric.label}</p>
              <p className="text-xs text-[var(--re-text-muted)]">{metric.sublabel}</p>
              <ComplianceStateBadge state={metric.state} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChecklistRadar() {
  return (
    <section className="border bg-[var(--re-surface-elevated)] p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="re-label">Demo workspace · synthetic data · 3 open checklist items</p>
          <h2 className="mt-2 text-xl font-semibold leading-tight text-[var(--re-text-primary)]">What the export checklist still flags</h2>
        </div>
        <Boxes className="h-5 w-5 text-[var(--re-text-muted)]" aria-hidden="true" />
      </div>
      <div className="mt-4 grid gap-3">
        {supplierChecklistExamples.map((item) => (
          <article key={item.supplier} className="grid gap-3 border border-[var(--re-border-subtle)] bg-[var(--re-surface-card)] p-3 sm:grid-cols-[1fr_auto] sm:items-center">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-[var(--re-text-primary)]">{item.supplier}</h3>
                <ComplianceStateBadge state={item.state} />
              </div>
              <p className="mt-2 text-sm leading-5 text-[var(--re-text-muted)]">{item.issue}</p>
            </div>
          </article>
        ))}
      </div>
      <div className="mt-4 border-t border-[var(--re-border-subtle)] pt-3">
        <p className="text-xs leading-5 text-[var(--re-text-muted)]">
          Export checklist (advisory) — checks configured in the workspace, not FDA certification, not retailer approval.
        </p>
      </div>
    </section>
  );
}

function CommandCenterPreview() {
  return (
    <div className="re-home-grid-panel border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-3 shadow-[var(--re-shadow-md)]">
      <div className="mb-3 flex justify-end">
        <span className="border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] px-2.5 py-1 font-mono text-[11px] uppercase text-[var(--re-text-muted)]">
          Demo workspace
        </span>
      </div>
      <ChecklistRadar />
      <div className="mt-3 grid gap-3">
        <CommitGate
          status="blocked"
          title="Export checklist (advisory)"
          description="The export package can build after missing ship-to locations are corrected and revalidated. Checklist is advisory; passing it is not FDA certification or retailer approval."
          criteria={[
            { label: "Workspace identity resolved", passed: true },
            { label: "CTE/KDE coverage above threshold", passed: true },
            { label: "Supplier gaps cleared", passed: false, detail: "FreshPack Central has 3 unresolved shipping lots." },
          ]}
        />
        <HashVerificationStrip
          hash="sample-demo-chain-hash-example"
          verifiedAt="example/synthetic"
          state="committed"
        />
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <main className="re-compliance-os min-h-screen">
      <section className="re-container grid min-h-[calc(100vh-56px)] items-start gap-8 py-10 lg:grid-cols-[0.9fr_1.1fr] lg:py-12">
        <div>
          <p className="mb-4 inline-flex border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] px-3 py-1 font-mono text-[11px] uppercase text-[var(--re-text-muted)]">
            FSMA 204 evidence layer · design-partner · pre-revenue
          </p>
          <h1 className="max-w-[720px] text-[clamp(40px,5.2vw,64px)] font-semibold leading-[0.98] text-[var(--re-text-primary)]">
            FSMA 204 traceability evidence layer.
          </h1>
          <p className="mt-6 max-w-[620px] text-[18px] leading-8 text-[var(--re-text-muted)]">
            Ingest supply-chain data through webhooks, CSV, EPCIS, or EDI. Check CTE/KDE coverage and completeness in the Inflow Workbench. Persist append-only after checks you configure. Export FDA-oriented and buyer-oriented spreadsheets.
          </p>
          <div className="mt-6 rounded border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4">
            <p className="text-sm leading-6 text-[var(--re-text-muted)]">
              The federal compliance date for the Food Traceability Rule is <strong className="text-[var(--re-text-primary)]">July 20, 2028</strong>. That is the FDA date. Buyer programs are separate and must be confirmed with your buyer.
            </p>
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <ActionLink href="/verify" primary>
              Verify a sample export
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </ActionLink>
            <ActionLink href="/contact">Book a 30-min call</ActionLink>
          </div>
          <MetricRail />
        </div>

        <CommandCenterPreview />
      </section>

      <section className="border-y border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
        <div className="re-container grid gap-0 py-0 md:grid-cols-5">
          {workflow.map((step, index) => (
            <div key={step.label} className="border-b border-[var(--re-surface-border)] py-5 md:border-b-0 md:border-r md:px-5 md:first:pl-0 md:last:border-r-0">
              <div className="flex items-center justify-between gap-3">
                <step.icon className="h-5 w-5 text-[var(--re-text-primary)]" aria-hidden="true" />
                <span className="font-mono text-[11px] text-[var(--re-text-muted)]">{String(index + 1).padStart(2, "0")}</span>
              </div>
              <h2 className="mt-5 text-xl font-semibold text-[var(--re-text-primary)]">{step.label}</h2>
              <p className="mt-2 text-sm leading-6 text-[var(--re-text-muted)]">{step.detail}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="re-section">
        <div className="re-container grid gap-10 lg:grid-cols-[0.72fr_1fr]">
          <div>
            <h2 className="max-w-[560px] text-[clamp(32px,4.5vw,56px)] font-semibold leading-tight text-[var(--re-text-primary)]">
              Make every compliance object show its state.
            </h2>
            <p className="mt-5 max-w-[500px] text-base leading-7 text-[var(--re-text-muted)]">
              Teams can see blocked, needs correction, corrected, committed, or exported. We do not mark anyone recall-ready, retailer-ready, or FDA-ready.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {evidenceCards.map((card) => (
              <EvidenceCard key={card.title} {...card}>
                <p className="text-xs leading-5 text-[var(--re-text-muted)]">Object state drives badge, border, copy, and next action.</p>
              </EvidenceCard>
            ))}
          </div>
        </div>
      </section>

      <section className="re-section bg-[var(--re-surface-card)]">
        <div className="re-container grid gap-8 lg:grid-cols-[1fr_0.9fr]">
          <div className="grid gap-4">
            <EvidencePackagePreview
              packageId="RE-DEMO-PKG-0427"
              status="building"
              records={1284}
              kdeCoverage={94}
              generatedAt="example/synthetic"
              items={["Facility scope manifest", "Committed CTE/KDE records", "Supplier correction log", "Hash verification strip"]}
            />
            <HashVerificationStrip
              hash="demo-example-chain-hash-synthetic"
              verifiedAt="example/synthetic"
              state="signed"
            />
          </div>
          <div>
            <div className="rounded border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-5">
              <p className="mb-3 font-mono text-[11px] uppercase tracking-widest text-[var(--re-text-disabled)]">
                What this is not
              </p>
              <ul className="space-y-2 text-sm leading-6 text-[var(--re-text-muted)]">
                <li>• Not FDA endorsement</li>
                <li>• Not a claim we meet §1.1455 24-hour request</li>
                <li>• Not retailer-readiness score</li>
                <li>• Not a commit-gate that certifies</li>
                <li>• Not a 24-hour Recall Clock product</li>
                <li>• Not live customer metrics</li>
                <li>• Not legal advice</li>
              </ul>
            </div>
            <div className="mt-5">
              <p className="mb-3 inline-flex border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] px-3 py-1 font-mono text-[11px] uppercase text-[var(--re-text-muted)]">
                Sample data · illustrative · synthetic
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  ["Records with full provenance", "1,184"],
                  ["Open supplier blockers", "3"],
                  ["Facilities scoped", "12/14"],
                ].map(([label, value]) => (
                  <div key={label} className="border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-4">
                    <p className="text-2xl font-semibold text-[var(--re-text-primary)]">{value}</p>
                    <p className="mt-2 re-label">{label}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="sandbox" className="re-section border-y border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
        <div className="re-container">
          <h2 className="text-2xl font-semibold text-[var(--re-text-primary)]">
            Walk the synthetic workspace
          </h2>
          <p className="mt-3 max-w-[620px] text-sm leading-7 text-[var(--re-text-muted)]">
            {sandboxCta().blurb}
          </p>
          <div className="mt-6">
            <ActionLink href={sandboxCta().href} primary>
              {sandboxCta().label}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </ActionLink>
          </div>
        </div>
      </section>

      <section className="re-section pb-24">
        <div className="re-container grid gap-5 md:grid-cols-4">
          {destinations.map(({ label, href, icon: Icon, note }) => (
            <Link key={label} href={href} className="group border-t border-[var(--re-border-strong)] pt-4 no-underline">
              <div className="flex items-center justify-between">
                <Icon className="h-5 w-5 text-[var(--re-text-muted)]" aria-hidden="true" />
                <ArrowRight className="h-4 w-4 text-[var(--re-text-primary)] transition-transform group-hover:translate-x-1" aria-hidden="true" />
              </div>
              <span className="mt-10 block text-2xl font-semibold text-[var(--re-text-primary)]">{label}</span>
              <span className="mt-2 block text-sm text-[var(--re-text-muted)]">{note}</span>
            </Link>
          ))}
        </div>
      </section>

      <footer className="border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] py-8">
        <div className="re-container">
          <p className="text-sm text-[var(--re-text-muted)]">
            RegEngine · Pasadena, CA · early-stage · design-partner · pre-revenue
          </p>
          <p className="mt-2 text-xs text-[var(--re-text-disabled)]">
            FDA date July 20, 2028. Buyer programs are not FDA. No seals, certifications, or FDA logo.
          </p>
        </div>
      </footer>
    </main>
  );
}
