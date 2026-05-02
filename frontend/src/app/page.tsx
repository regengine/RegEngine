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
  TimerReset,
} from "lucide-react";
import {
  CommitGate,
  ComplianceStateBadge,
  EvidenceCard,
  EvidencePackagePreview,
  HashVerificationStrip,
  ReadinessScore,
  RegulatoryCitationBlock,
} from "@/components/compliance";

export const metadata: Metadata = {
  title: "RegEngine — Compliance OS for Food Traceability",
  description:
    "RegEngine turns messy supplier data into verified FSMA 204 evidence with readiness scoring, supplier gap queues, commit gates, and FDA-ready export packages.",
  openGraph: {
    title: "RegEngine — Compliance OS for Food Traceability",
    description:
      "Preflight supplier data, find KDE gaps, gate evidence commits, and export verified FSMA 204 records.",
    url: "https://regengine.co",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "RegEngine food traceability command center" }],
  },
};

const readinessMetrics = [
  { label: "FTL coverage", value: "91%", state: "ready" as const },
  { label: "KDE completeness", value: "84%", state: "needs-correction" as const },
  { label: "Export eligibility", value: "72%", state: "blocked" as const },
  { label: "Recall clock", value: "18h", state: "recall-ready" as const },
];

const supplierGaps = [
  {
    supplier: "FreshPack Central",
    scope: "Shipping CTE",
    issue: "Ship-to location missing for 3 lots",
    owner: "Supplier portal",
    state: "blocked" as const,
  },
  {
    supplier: "Valley Farms",
    scope: "Harvesting CTE",
    issue: "Harvest date and quantity validated",
    owner: "Evidence commit",
    state: "ready" as const,
  },
  {
    supplier: "Cold Dock 7",
    scope: "Cooling CTE",
    issue: "Temperature note requires review",
    owner: "Ops review",
    state: "needs-correction" as const,
  },
];

const evidenceCards = [
  {
    title: "Supplier Gap Radar",
    description: "Expose the supplier, CTE, lot, and field blocking export readiness before records enter the evidence boundary.",
    state: "blocked" as const,
    meta: "Readiness workbench",
    icon: Gauge,
  },
  {
    title: "Evidence Chain",
    description: "Carry every accepted record forward with provenance, tenant scope, validation history, and hash verification.",
    state: "committed" as const,
    meta: "Evidence ledger",
    icon: GitBranch,
  },
  {
    title: "24-hour Recall Clock",
    description: "Keep recall response posture visible with package readiness, export state, and the work still blocking delivery.",
    state: "recall-ready" as const,
    meta: "Response posture",
    icon: TimerReset,
  },
];

const workflow = [
  { label: "Intake", detail: "CSV, API, EDI, or portal files enter the workbench.", icon: ScanLine },
  { label: "Interrogate", detail: "CTE/KDE coverage, identity, and facility scope are checked.", icon: Database },
  { label: "Correct", detail: "Every gap gets a reason, owner, and recovery path.", icon: ClipboardCheck },
  { label: "Commit", detail: "Only verified records cross the evidence boundary.", icon: ShieldCheck },
  { label: "Export", detail: "Build signed FDA, retailer, or internal evidence packets.", icon: PackageCheck },
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
    <div className="re-home-command-rail mt-8">
      {readinessMetrics.map((metric) => (
        <div key={metric.label} className="border-b border-r border-[var(--re-surface-border)] p-4 last:border-r-0 md:border-b-0">
          <p className="text-2xl font-semibold leading-none text-[var(--re-text-primary)]">{metric.value}</p>
          <div className="mt-3 flex flex-col gap-2">
            <p className="re-label">{metric.label}</p>
            <ComplianceStateBadge state={metric.state} />
          </div>
        </div>
      ))}
    </div>
  );
}

function SupplierGapRadar() {
  return (
    <section className="border bg-[var(--re-surface-elevated)] p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="re-label">Supplier Gap Radar</p>
          <h2 className="mt-2 text-xl font-semibold leading-tight text-[var(--re-text-primary)]">What blocks export readiness</h2>
        </div>
        <Boxes className="h-5 w-5 text-[var(--re-text-muted)]" aria-hidden="true" />
      </div>
      <div className="mt-4 grid gap-3">
        {supplierGaps.map((gap) => (
          <article key={gap.supplier} className="grid gap-3 border border-[var(--re-border-subtle)] bg-[var(--re-surface-card)] p-3 sm:grid-cols-[1fr_auto] sm:items-center">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-[var(--re-text-primary)]">{gap.supplier}</h3>
                <ComplianceStateBadge state={gap.state} />
              </div>
              <p className="mt-2 text-sm leading-5 text-[var(--re-text-muted)]">{gap.issue}</p>
            </div>
            <div className="grid gap-1 text-left sm:text-right">
              <span className="font-mono text-[11px] uppercase text-[var(--re-text-muted)]">{gap.scope}</span>
              <span className="text-xs font-semibold text-[var(--re-text-secondary)]">{gap.owner}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function CommandCenterPreview() {
  return (
    <div className="re-home-grid-panel border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-3 shadow-[var(--re-shadow-md)]">
      <div className="grid gap-3 xl:grid-cols-[250px_minmax(0,1fr)]">
        <ReadinessScore
          score={86}
          label="Traceability readiness"
          description="Facility scope, KDE coverage, supplier response, and export blockers scored before commit."
          blockers={3}
          size="sm"
        />
        <SupplierGapRadar />
      </div>
      <div className="mt-3 grid gap-3">
        <CommitGate
          status="blocked"
          title="Export eligibility gate"
          description="The FDA package can build after missing ship-to locations are corrected and revalidated."
          criteria={[
            { label: "Tenant identity resolved", passed: true },
            { label: "CTE/KDE coverage above threshold", passed: true },
            { label: "Supplier gaps cleared", passed: false, detail: "FreshPack Central has 3 unresolved shipping lots." },
          ]}
        />
        <HashVerificationStrip
          hash="sample-package-chain-hash"
          verifiedAt="verified 04:12 UTC"
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
          <h1 className="max-w-[720px] text-[clamp(40px,5.2vw,64px)] font-semibold leading-[0.98] text-[var(--re-text-primary)]">
            Compliance operating system for food traceability.
          </h1>
          <p className="mt-6 max-w-[620px] text-[18px] leading-8 text-[var(--re-text-muted)]">
            RegEngine is where messy supplier data enters, gets interrogated, corrected, verified, committed, and exported as defensible FSMA 204 evidence.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ActionLink href="/tools/inflow-lab" primary>
              Preflight a supplier file
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </ActionLink>
            <ActionLink href="/retailer-readiness">Check readiness</ActionLink>
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
              Suppliers, records, exports, and facilities use the same state model everywhere, so teams know what is ready, blocked, corrected, committed, and recall-ready.
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
              packageId="FDA-204-PKG-0427"
              status="building"
              records={1284}
              kdeCoverage={94}
              generatedAt="04:12"
              items={["Facility scope manifest", "Committed CTE/KDE records", "Supplier correction log", "Hash verification strip"]}
            />
            <HashVerificationStrip
              hash="demo-signed-chain-hash"
              verifiedAt="chain checked today"
              state="signed"
            />
          </div>
          <div>
            <RegulatoryCitationBlock citation="21 CFR 1.1455" title="Records must be sortable and provided within 24 hours.">
              RegEngine treats recall response as an operating state, not a static report. The interface keeps the evidence package, blockers, owners, and verification trail visible before the clock starts.
            </RegulatoryCitationBlock>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {[
                ["Records with full provenance", "1,184"],
                ["Open supplier blockers", "3"],
                ["Facilities scoped", "12/14"],
                ["Days since recall drill", "18"],
              ].map(([label, value]) => (
                <div key={label} className="border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-4">
                  <p className="text-2xl font-semibold text-[var(--re-text-primary)]">{value}</p>
                  <p className="mt-2 re-label">{label}</p>
                </div>
              ))}
            </div>
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
    </main>
  );
}
