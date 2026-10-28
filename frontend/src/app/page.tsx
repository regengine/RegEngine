import Link from "next/link";
import { BookCallLink } from "@/components/conversion/BookCallLink";
import type { Metadata } from "next";
import {
  ArrowRight,
  Boxes,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileCheck2,
  FileSpreadsheet,
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
import { capabilities } from "@/lib/capabilities";

export const metadata: Metadata = {
  title: "FSMA 204 Recordkeeping Software | RegEngine",
  description:
    "FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. FDA says it will not enforce before July 20, 2028. Not legal advice.",
  openGraph: {
    title: "FSMA 204 Recordkeeping Software | RegEngine",
    description:
      "FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. FDA says it will not enforce before July 20, 2028. Not legal advice.",
    url: "https://regengine.co",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "RegEngine FSMA 204 recordkeeping software" }],
  },
};

const problem = [
  {
    title: "The request",
    detail:
      "Under 21 CFR 1.1455(c)(3)(ii), FDA can ask a covered firm for an electronic sortable spreadsheet of traceability records during an outbreak, a recall, or another threat to public health. It is due within 24 hours unless FDA agrees to more time.",
    icon: FileSpreadsheet,
  },
  {
    title: "The records",
    detail:
      "Lot codes, dates, quantities, and locations for every Critical Tracking Event: harvesting, cooling, initial packing, first land-based receiving, shipping, receiving, and transformation. Most of it comes from suppliers, in whatever shape they keep it.",
    icon: Boxes,
  },
  {
    title: "The date",
    detail:
      "FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive. The requirements did not change. Buyer programs run on their own calendars.",
    icon: CalendarClock,
  },
];

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

function IngestPathsCard() {
  return (
    <Card padding="spacious" className="flex flex-col gap-5">
      <h2 className="font-mono text-label uppercase text-re-text-muted">Ingest paths today</h2>
      <div>
        <h3 className="text-heading text-re-text-primary">Live</h3>
        <ul className="mt-3 grid gap-2">
          {capabilities.live.map((name) => (
            <li key={name} className="flex items-center gap-2 text-ui text-re-text-secondary">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              <span>{name}</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="text-heading text-re-text-primary">Preview</h3>
        <ul className="mt-3 grid gap-2">
          {capabilities.preview.map((name) => (
            <li key={name} className="flex items-center justify-between gap-3 text-ui text-re-text-secondary">
              <span>{name}</span>
              <span className="font-mono text-label uppercase text-re-text-muted">Preview</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-small text-re-text-tertiary">Preview paths are in active development.</p>
      </div>
      <Link href="/verify" className="group inline-flex items-center gap-2 text-ui text-re-text-primary no-underline">
        Verify an evidence bundle
        <ArrowRight className="h-4 w-4 transition-transform duration-120 group-hover:translate-x-1 motion-reduce:transition-none" strokeWidth={1.75} aria-hidden="true" />
      </Link>
    </Card>
  );
}

export default function HomePage() {
  return (
    <div className="re-compliance-os min-h-screen">
      <Container as="section" width="marketing" className="grid items-start gap-10 py-12 lg:grid-cols-[1.1fr_0.9fr] lg:py-16">
        <div>
          <p className="mb-4 font-mono text-label uppercase text-re-text-muted">
            FSMA 204 · 21 CFR Part 1 Subpart S
          </p>
          <h1 className="max-w-[760px] font-display text-display text-re-text-primary">
            In an outbreak or recall, the Food Traceability Rule lets the FDA ask for a sortable spreadsheet due within 24 hours. Supplier data does not arrive that way.
          </h1>
          <p className="mt-6 max-w-[68ch] text-body text-re-text-secondary">
            RegEngine checks supplier records for CTE and KDE gaps before they become evidence, routes each gap to an owner, and keeps accepted records in an append-only ledger you can export to support your response to a request.
          </p>
          <p className="mt-3 max-w-[68ch] text-body text-re-text-secondary">
            Send records by CSV upload or the JSON events API. EPCIS 2.0 is in Preview.
          </p>
          <Callout tone="neutral" className="mt-6 max-w-[68ch]">
            <p>
              FDA has said it will not enforce the Food Traceability Rule before <strong className="font-medium text-re-text-primary">July 20, 2028</strong>, following a Congressional directive. Buyer programs are separate and must be confirmed with your buyer.
            </p>
          </Callout>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/tools/kde-checker">
                See the fields your records need
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <BookCallLink href="/contact" placement="home_page">Book a 30-min call</BookCallLink>
            </Button>
          </div>
          <p className="mt-3 text-small text-re-text-tertiary">
            The checklist is free. No account, no API key. An email is only needed to save your result.
          </p>
        </div>

        <IngestPathsCard />
      </Container>

      <Section width="marketing" tone="inset">
        <h2 className="max-w-[24ch] font-display text-heading-lg text-re-text-primary">
          What the rule asks for, and what you actually have.
        </h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {problem.map((item) => (
            <Card key={item.title} padding="compact">
              <item.icon className="h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              <h3 className="mt-4 text-heading text-re-text-primary">{item.title}</h3>
              <p className="mt-2 text-ui text-re-text-secondary">{item.detail}</p>
            </Card>
          ))}
        </div>
      </Section>

      <section className="border-y border-re-border-subtle">
        <Container width="marketing">
          <h2 className="pt-10 font-display text-heading-lg text-re-text-primary">How RegEngine works</h2>
          <ol className="grid md:grid-cols-5">
            {workflow.map((step, index) => (
              <li key={step.label} className="border-b border-re-border-subtle py-5 md:border-b-0 md:border-r md:px-5 md:first:pl-0 md:last:border-r-0 md:last:pr-0">
                <div className="flex items-center justify-between gap-3">
                  <step.icon className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                  <span className="font-mono text-label tabular-nums text-re-text-muted">{String(index + 1).padStart(2, "0")}</span>
                </div>
                <h3 className="mt-5 text-heading text-re-text-primary">{step.label}</h3>
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

      <Section id="next-steps" width="marketing" tone="inset">
        <h2 className="font-display text-heading-lg text-re-text-primary">Next steps</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          <Card padding="compact" className="flex flex-col">
            <ClipboardCheck className="h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            <h3 className="mt-4 text-heading text-re-text-primary">See the fields your records need</h3>
            <p className="mt-2 flex-1 text-ui text-re-text-secondary">
              Pick a food on the Food Traceability List and an event. Get the starting list of Key Data Elements the record needs. Free. No account; an email only saves your result.
            </p>
            <Button asChild className="mt-5 self-start">
              <Link href="/tools/kde-checker">
                See the fields your records need
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </Button>
          </Card>
          <Card padding="compact" className="flex flex-col">
            <ShieldCheck className="h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            <h3 className="mt-4 text-heading text-re-text-primary">Verify an evidence bundle</h3>
            <p className="mt-2 flex-1 text-ui text-re-text-secondary">
              Download the verification script and check the file hashes of a bundle yourself, on your own machine.
            </p>
            <Button asChild variant="secondary" className="mt-5 self-start">
              <Link href="/verify">
                Verify an evidence bundle
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </Button>
          </Card>
          <Card padding="compact" className="flex flex-col">
            <ScanLine className="h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            <h3 className="mt-4 text-heading text-re-text-primary">Talk it through</h3>
            <p className="mt-2 flex-1 text-ui text-re-text-secondary">
              Thirty minutes with the founder on your supplier data and the records you need to hold. Bring one supplier file if you have it.
            </p>
            <Button asChild variant="secondary" className="mt-5 self-start">
              <BookCallLink href="/contact" placement="home_next_steps">
                Book a 30-min call
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </BookCallLink>
            </Button>
          </Card>
        </div>
        <Callout tone="neutral" className="mt-8 max-w-[80ch]">
          <p>
            RegEngine does not imply FDA endorsement or certification, is not a readiness score, does not claim that any workspace meets the 24-hour request, is not a recall clock product, shows no live customer metrics, and is not legal advice.
          </p>
        </Callout>
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
            RegEngine · Pasadena, CA · early-stage
          </p>
          <p className="mt-2 text-small text-re-text-muted">
            FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive. Buyer programs are not FDA. No seals, certifications, or FDA logo.
          </p>
        </Container>
      </footer>
    </div>
  );
}
