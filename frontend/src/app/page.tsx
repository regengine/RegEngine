import Link from "next/link";
import type { Metadata } from "next";
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
import { Container } from "@/components/layout/container";
import { Section } from "@/components/layout/section";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";
import { StatTile } from "@/components/ui/stat-tile";

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

function MetricRail() {
  return (
    <div className="mt-8">
      <p className="mb-3 font-mono text-label uppercase text-re-text-muted">
        Synthetic demo · example numbers · not a customer workspace
      </p>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        {demoMetrics.map((metric) => (
          <StatTile
            key={metric.label}
            label={metric.label}
            value={metric.value}
            status={<ComplianceStateBadge state={metric.state} />}
          >
            <p className="text-small text-re-text-tertiary">{metric.sublabel}</p>
          </StatTile>
        ))}
      </div>
    </div>
  );
}

function ChecklistRadar() {
  return (
    <Card padding="compact">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-label uppercase text-re-text-muted">Demo workspace · synthetic data · 3 open checklist items</p>
          <h2 className="mt-2 text-heading text-re-text-primary">What the export checklist still flags</h2>
        </div>
        <Boxes className="h-5 w-5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
      </div>
      <div className="mt-4 grid gap-3">
        {supplierChecklistExamples.map((item) => (
          <Card key={item.supplier} variant="inset" padding="compact">
            <article className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-subheading text-re-text-primary">{item.supplier}</h3>
                  <ComplianceStateBadge state={item.state} />
                </div>
                <p className="mt-2 text-ui text-re-text-secondary">{item.issue}</p>
              </div>
            </article>
          </Card>
        ))}
      </div>
      <div className="mt-4 border-t border-re-border-subtle pt-3">
        <p className="text-small text-re-text-tertiary">
          Export checklist (advisory) — checks configured in the workspace, not FDA certification, not retailer approval.
        </p>
      </div>
    </Card>
  );
}

function CommandCenterPreview() {
  return (
    <div className="rounded-lg border border-re-border bg-re-surface-inset p-3">
      <div className="mb-3 flex justify-end">
        <span className="font-mono text-label uppercase text-re-text-muted">
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
      <Container as="section" width="marketing" className="grid items-start gap-10 py-12 lg:grid-cols-[0.9fr_1.1fr] lg:py-16">
        <div>
          <p className="mb-4 font-mono text-label uppercase text-re-text-muted">
            FSMA 204 evidence layer · design-partner · pre-revenue
          </p>
          <h1 className="max-w-[720px] font-display text-display text-re-text-primary">
            FSMA 204 traceability evidence layer.
          </h1>
          <p className="mt-6 max-w-[68ch] text-body text-re-text-secondary">
            Ingest supply-chain data through webhooks, CSV, EPCIS, or EDI. Check CTE/KDE coverage and completeness in the Inflow Workbench. Persist append-only after checks you configure. Export FDA-oriented and buyer-oriented spreadsheets.
          </p>
          <Callout tone="neutral" className="mt-6 max-w-[68ch]">
            <p>
              The federal compliance date for the Food Traceability Rule is <strong className="font-medium text-re-text-primary">July 20, 2028</strong>. That is the FDA date. Buyer programs are separate and must be confirmed with your buyer.
            </p>
          </Callout>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/verify">
                Verify a sample export
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/contact">Book a 30-min call</Link>
            </Button>
          </div>
          <MetricRail />
        </div>

        <CommandCenterPreview />
      </Container>

      <section className="border-y border-re-border-subtle">
        <Container width="marketing">
          <ol className="grid md:grid-cols-5">
            {workflow.map((step, index) => (
              <li key={step.label} className="border-b border-re-border-subtle py-5 md:border-b-0 md:border-r md:px-5 md:first:pl-0 md:last:border-r-0 md:last:pr-0">
                <div className="flex items-center justify-between gap-3">
                  <step.icon className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                  <span className="font-mono text-label tabular-nums text-re-text-muted">{String(index + 1).padStart(2, "0")}</span>
                </div>
                <h2 className="mt-5 text-heading text-re-text-primary">{step.label}</h2>
                <p className="mt-2 text-ui text-re-text-secondary">{step.detail}</p>
              </li>
            ))}
          </ol>
        </Container>
      </section>

      <Section width="marketing" flush>
        <div className="grid gap-10 lg:grid-cols-[0.72fr_1fr]">
          <div>
            <h2 className="max-w-[20ch] font-display text-heading-lg text-re-text-primary">
              Make every compliance object show its state.
            </h2>
            <p className="mt-5 max-w-[68ch] text-body text-re-text-secondary">
              Teams can see blocked, needs correction, corrected, committed, or exported. These statuses do not establish readiness for a recall, a retailer, or an FDA request.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {evidenceCards.map((card) => (
              <EvidenceCard key={card.title} {...card}>
                <p className="text-small text-re-text-tertiary">Object state drives badge, border, copy, and next action.</p>
              </EvidenceCard>
            ))}
          </div>
        </div>
      </Section>

      <Section width="marketing" tone="inset">
        <div className="grid gap-8 lg:grid-cols-[1fr_0.9fr]">
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
            <Card padding="compact">
              <p className="mb-3 font-mono text-label uppercase text-re-text-muted">
                What this is not
              </p>
              <ul className="list-disc space-y-2 pl-5 text-ui text-re-text-secondary marker:text-re-text-tertiary">
                <li>Not FDA endorsement</li>
                <li>Not a claim we meet §1.1455 24-hour request</li>
                <li>Not retailer-readiness score</li>
                <li>Not a commit-gate that certifies</li>
                <li>Not a 24-hour Recall Clock product</li>
                <li>Not live customer metrics</li>
                <li>Not legal advice</li>
              </ul>
            </Card>
            <div className="mt-5">
              <p className="mb-3 font-mono text-label uppercase text-re-text-muted">
                Sample data · illustrative · synthetic
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  ["Records with full provenance", "1,184"],
                  ["Open supplier blockers", "3"],
                  ["Facilities scoped", "12/14"],
                ].map(([label, value]) => (
                  <StatTile key={label} label={label} value={value} />
                ))}
              </div>
            </div>
          </div>
        </div>
      </Section>

      <Section id="sandbox" width="marketing">
        <h2 className="font-display text-heading-lg text-re-text-primary">
          Walk the synthetic workspace
        </h2>
        <p className="mt-3 max-w-[68ch] text-body text-re-text-secondary">
          {sandboxCta().blurb}
        </p>
        <div className="mt-6">
          <Button asChild size="lg">
            <Link href={sandboxCta().href}>
              {sandboxCta().label}
              <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </Link>
          </Button>
        </div>
      </Section>

      <Section width="marketing" className="pb-20 sm:pb-24">
        <div className="grid gap-5 md:grid-cols-4">
          {destinations.map(({ label, href, icon: Icon, note }) => (
            <Link key={label} href={href} className="group border-t border-re-border-strong pt-4 no-underline">
              <div className="flex items-center justify-between">
                <Icon className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                <ArrowRight className="h-4 w-4 text-re-text-tertiary transition-transform duration-120 group-hover:translate-x-1 motion-reduce:transition-none" strokeWidth={1.75} aria-hidden="true" />
              </div>
              <span className="mt-10 block text-heading text-re-text-primary">{label}</span>
              <span className="mt-2 block text-ui text-re-text-secondary">{note}</span>
            </Link>
          ))}
        </div>
      </Section>

      <footer className="border-t border-re-border-subtle py-8">
        <Container width="marketing">
          <p className="text-ui text-re-text-secondary">
            RegEngine · Pasadena, CA · early-stage · design-partner · pre-revenue
          </p>
          <p className="mt-2 text-small text-re-text-muted">
            FDA date July 20, 2028. Buyer programs are not FDA. No seals, certifications, or FDA logo.
          </p>
        </Container>
      </footer>
    </main>
  );
}
