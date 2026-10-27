import Link from "next/link";
import { BookCallLink } from "@/components/conversion/BookCallLink";
import type { Metadata } from "next";
import {
  ArrowRight,
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
import { EvidenceCard } from "@/components/compliance";
import { Container } from "@/components/layout/container";
import { Section } from "@/components/layout/section";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "FSMA 204 Recordkeeping Software | RegEngine",
  description:
    "Pre-revenue FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive. Not legal advice.",
  openGraph: {
    title: "FSMA 204 Recordkeeping Software | RegEngine",
    description:
      "Pre-revenue FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive. Not legal advice.",
    url: "https://regengine.co",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "RegEngine FSMA 204 recordkeeping software" }],
  },
};

const evidenceCards = [
  {
    title: "Ingest workspace",
    description: "CTE/KDE records arrive through CSV upload or the JSON events API and enter the inflow workbench for coverage checking.",
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
  { label: "Ingest", detail: "CSV uploads and JSON events API submissions enter the workbench.", icon: ScanLine },
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

export default function HomePage() {
  return (
    <div className="re-compliance-os min-h-screen">
      <Container as="section" width="marketing" className="grid items-start gap-10 py-12 lg:grid-cols-[0.9fr_1.1fr] lg:py-16">
        <div>
          <p className="mb-4 font-mono text-label uppercase text-re-text-muted">
            FSMA 204 evidence layer · design-partner · pre-revenue
          </p>
          <h1 className="max-w-[720px] font-display text-display text-re-text-primary">
            FSMA 204 recordkeeping for the Food Traceability Rule.
          </h1>
          <p className="mt-6 max-w-[68ch] text-body text-re-text-secondary">
            Send records by CSV upload or the JSON events API. EPCIS 2.0 is in Preview. Check CTE/KDE coverage and completeness in the Inflow Workbench. Persist append-only after checks you configure. Export FDA-oriented and buyer-oriented spreadsheets.
          </p>
          <Callout tone="neutral" className="mt-6 max-w-[68ch]">
            <p>
              The federal compliance date for the Food Traceability Rule is <strong className="font-medium text-re-text-primary">July 20, 2028</strong>. That is the FDA date. Buyer programs are separate and must be confirmed with your buyer.
            </p>
          </Callout>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/verify">
                Verify an evidence bundle
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <BookCallLink href="/contact" placement="home_page">Book a 30-min call</BookCallLink>
            </Button>
          </div>
        </div>

        <Card padding="spacious" className="flex flex-col items-start gap-3">
          <p className="font-mono text-label uppercase text-re-text-muted">Workspace preview</p>
          <h2 className="text-heading text-re-text-primary">No data yet</h2>
          <p className="text-ui text-re-text-secondary">
            There is no public workspace to show. Connect your own supplier data and the
            ingest, checklist, and export views populate from your records.
          </p>
          <Button asChild variant="secondary" size="lg" className="mt-2">
            <Link href="/ingest">
              Start setup
              <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </Link>
          </Button>
        </Card>
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
        <Card padding="compact" className="max-w-[68ch]">
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
            FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive. Buyer programs are not FDA. No seals, certifications, or FDA logo.
          </p>
        </Container>
      </footer>
    </div>
  );
}
