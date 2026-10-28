import Link from "next/link";
import { BookCallLink } from "@/components/conversion/BookCallLink";
import type { Metadata } from "next";
import {
  ArrowRight,
  ClipboardCheck,
  Database,
  PackageCheck,
  ScanLine,
} from "lucide-react";
import { Container } from "@/components/layout/container";
import { Section } from "@/components/layout/section";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "FSMA 204 Recordkeeping Software | RegEngine",
  description:
    "Pre-revenue FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. FDA says it will not enforce before July 20, 2028. Not legal advice.",
  openGraph: {
    title: "FSMA 204 Recordkeeping Software | RegEngine",
    description:
      "Pre-revenue FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. FDA says it will not enforce before July 20, 2028. Not legal advice.",
    url: "https://regengine.co",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "RegEngine FSMA 204 recordkeeping software" }],
  },
};

const exampleRows = [
  { lot: "00614141999996-L4471", date: "2026-03-02", from: "Salinas Cooler 2", status: "Complete", tone: "ok" as const },
  { lot: "(blank)", date: "2026-03-02", from: "Salinas Cooler 2", status: "Lot code missing", tone: "bad" as const },
  { lot: "00614141999996-L4472", date: "03/31", from: "Salinas Cooler 2", status: "Date has no year", tone: "warn" as const },
  { lot: "00614141999996-L4473", date: "2026-03-04", from: "Salinas Cooler 2", status: "Complete", tone: "ok" as const },
];

const statusTone = {
  ok: "text-re-success",
  warn: "text-re-warning",
  bad: "text-re-danger",
} as const;

const problems = [
  {
    when: "Today",
    title: "Files arrive broken",
    body: "A missing lot code here, a ship date with no year there. Nobody sees it until someone reads the file line by line.",
  },
  {
    when: "During a recall drill",
    title: "The gaps surface under pressure",
    body: "A buyer or the FDA asks for a lot's history. You spend the response window chasing suppliers instead of answering.",
  },
  {
    when: "Afterward",
    title: "Fixes live in email",
    body: "Who was asked to correct what, and did they? The answer is scattered across inboxes and spreadsheets.",
  },
];

const workflow = [
  { label: "Send", title: "Upload a file or call the API", detail: "CSV uploads and a JSON events API. EPCIS 2.0 is in Preview.", icon: ScanLine },
  { label: "Check", title: "See every gap", detail: "Each record is checked against FSMA 204 key data elements and flagged with a reason.", icon: Database },
  { label: "Fix", title: "Give each gap an owner", detail: "Missing or malformed values become tasks with a person and a recovery path.", icon: ClipboardCheck },
  { label: "Export", title: "Commit and export clean records", detail: "After the checks you configure, accepted records enter the append-only evidence ledger. Export FDA-oriented or buyer-oriented spreadsheets with a hash manifest where enabled.", icon: PackageCheck },
];

export default function HomePage() {
  return (
    <div className="re-compliance-os min-h-screen">
      <Container as="section" width="marketing" className="grid items-center gap-10 py-12 lg:grid-cols-[1.05fr_1fr] lg:py-16">
        <div>
          <p className="mb-4 font-mono text-label uppercase text-re-text-muted">
            FSMA 204 traceability records
          </p>
          <h1 className="max-w-[22ch] font-display text-display text-re-text-primary">
            {"Find the gaps in your suppliers' traceability data before a buyer or the FDA does."}
          </h1>
          <p className="mt-6 max-w-[60ch] text-body text-re-text-secondary">
            Suppliers send lot codes, dates, and locations as spreadsheets, PDFs, and emails. RegEngine checks every file against the FSMA 204 requirements, assigns each gap to someone, and exports only the records that are complete.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <BookCallLink href="/contact" placement="home_page_send_file">
                Send us one supplier file
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </BookCallLink>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/tools/ftl-checker">Check the Food Traceability List</Link>
            </Button>
          </div>
          <p className="mt-4 max-w-[60ch] text-small text-re-text-muted">
            Free. You get a gap report on that file within one business day. No contract, no integration.
          </p>
        </div>

        <Card padding="compact" className="overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-re-border-subtle pb-3">
            <p className="font-mono text-small text-re-text-primary">supplier_ship_log_march.csv</p>
            <p className="font-mono text-label uppercase text-re-text-muted">Example data</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[460px] text-left font-mono text-small">
              <caption className="sr-only">Example gap report: two of four rows complete, two need correction</caption>
              <thead className="text-re-text-muted">
                <tr>
                  <th scope="col" className="py-2 pr-3 font-normal">Lot code</th>
                  <th scope="col" className="py-2 pr-3 font-normal">Ship date</th>
                  <th scope="col" className="py-2 pr-3 font-normal">Ship-from</th>
                  <th scope="col" className="py-2 font-normal">Status</th>
                </tr>
              </thead>
              <tbody>
                {exampleRows.map((row) => (
                  <tr key={row.lot + row.date + row.status} className="border-t border-re-border-subtle align-top">
                    <td className="py-2.5 pr-3 text-re-text-primary">{row.lot}</td>
                    <td className="py-2.5 pr-3 text-re-text-primary">{row.date}</td>
                    <td className="py-2.5 pr-3 text-re-text-secondary">{row.from}</td>
                    <td className={`py-2.5 ${statusTone[row.tone]}`}>{row.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-1 flex flex-wrap justify-between gap-2 border-t border-re-border-subtle pt-3 text-ui">
            <p className="text-re-text-primary"><strong className="font-medium">2 of 4</strong> rows ready to export</p>
            <p className="text-re-text-secondary">2 fixes assigned</p>
          </div>
        </Card>
      </Container>

      <Section width="marketing" tone="inset">
        <p className="font-mono text-label uppercase text-re-text-muted">The problem</p>
        <h2 className="mt-3 max-w-[24ch] font-display text-heading-lg text-re-text-primary">
          You find out a record is incomplete at the worst possible moment.
        </h2>
        <p className="mt-4 max-w-[60ch] text-body text-re-text-secondary">
          The Food Traceability Rule requires lot codes and key data elements at each shipping, receiving, and transformation step. Most of that data lives with your suppliers, in formats you do not control.
        </p>
        <div className="mt-10 grid gap-8 md:grid-cols-3">
          {problems.map((item) => (
            <div key={item.title}>
              <p className="font-mono text-label uppercase text-re-danger">{item.when}</p>
              <h3 className="mt-2 text-heading text-re-text-primary">{item.title}</h3>
              <p className="mt-2 text-ui text-re-text-secondary">{item.body}</p>
            </div>
          ))}
        </div>
      </Section>

      <section className="border-y border-re-border-subtle">
        <Container width="marketing" className="py-12">
          <p className="font-mono text-label uppercase text-re-text-muted">How it works</p>
          <h2 className="mt-3 max-w-[26ch] font-display text-heading-lg text-re-text-primary">
            Check first. Fix what is wrong. Export what is complete.
          </h2>
          <ol className="mt-8 grid md:grid-cols-4">
            {workflow.map((step) => (
              <li key={step.label} className="border-b border-re-border-subtle py-5 md:border-b-0 md:border-r md:px-5 md:first:pl-0 md:last:border-r-0 md:last:pr-0">
                <div className="flex items-center gap-2">
                  <step.icon className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                  <span className="font-mono text-label uppercase text-re-text-muted">{step.label}</span>
                </div>
                <h3 className="mt-4 text-heading text-re-text-primary">{step.title}</h3>
                <p className="mt-2 text-ui text-re-text-secondary">{step.detail}</p>
              </li>
            ))}
          </ol>
        </Container>
      </section>

      <Section width="marketing">
        <div className="grid gap-10 lg:grid-cols-2">
          <div>
            <p className="font-mono text-label uppercase text-re-text-muted">Do not take our word for it</p>
            <h2 className="mt-3 font-display text-heading-lg text-re-text-primary">Verify our records yourself.</h2>
            <p className="mt-4 max-w-[52ch] text-body text-re-text-secondary">
              We are early, so we do not ask for blind trust. Every export carries a hash manifest you can check without logging in to RegEngine.
            </p>
            <div className="mt-6">
              <Button asChild variant="secondary" size="lg">
                <Link href="/verify">
                  Verify an evidence bundle
                  <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                </Link>
              </Button>
            </div>
          </div>
          <ul className="space-y-4 text-ui text-re-text-secondary">
            <li><strong className="font-medium text-re-text-primary">Public verifier.</strong> Check a bundle in your browser or with the downloadable Python script.</li>
            <li><strong className="font-medium text-re-text-primary">Free tools, no sales call.</strong> Food Traceability List, CTE, KDE, and lot code checkers.</li>
            <li><strong className="font-medium text-re-text-primary">Plain limits.</strong> A passing check proves the file was not altered. It does not prove the source data is accurate, and it is not FDA approval.</li>
          </ul>
        </div>
      </Section>

      <Section width="marketing" tone="inset">
        <p className="font-mono text-label uppercase text-re-text-muted">Built for</p>
        <h2 className="mt-3 max-w-[26ch] font-display text-heading-lg text-re-text-primary">
          Teams that collect traceability data from other companies.
        </h2>
        <ul className="mt-6 max-w-[60ch] space-y-3 text-ui text-re-text-secondary">
          <li><strong className="font-medium text-re-text-primary">Food manufacturers and processors</strong> receiving lots from growers and co-packers.</li>
          <li><strong className="font-medium text-re-text-primary">Distributors and importers</strong> moving product between facilities.</li>
          <li><strong className="font-medium text-re-text-primary">Suppliers to retailers</strong> preparing records for a buyer program.</li>
        </ul>
      </Section>

      <Section width="marketing">
        <Card padding="spacious" className="flex flex-col items-start gap-3">
          <h2 className="font-display text-heading-lg text-re-text-primary">Start with one file.</h2>
          <p className="max-w-[56ch] text-body text-re-text-secondary">
            Send one anonymized supplier file. We return a gap report within one business day, free. If the report is useful, we talk about the next step. If not, you keep the report.
          </p>
          <div className="mt-2 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <BookCallLink href="/contact" placement="home_page_final_cta">
                Send us one supplier file
                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </BookCallLink>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/pricing">See pricing</Link>
            </Button>
          </div>
        </Card>
      </Section>

      <Section width="marketing" tone="inset">
        <Callout tone="neutral" className="max-w-[68ch]">
          <p>
            FDA has said it will not enforce the Food Traceability Rule before <strong className="font-medium text-re-text-primary">July 20, 2028</strong>, following a Congressional directive. Buyer programs are separate and may ask sooner; confirm with your buyer.
          </p>
        </Callout>
        <Card padding="compact" className="mt-6 max-w-[68ch]">
          <p className="mb-3 font-mono text-label uppercase text-re-text-muted">What this is not</p>
          <ul className="list-disc space-y-2 pl-5 text-ui text-re-text-secondary marker:text-re-text-tertiary">
            <li>Not FDA endorsement</li>
            <li>Not a claim we meet the §1.1455 24-hour request</li>
            <li>Not a retailer-readiness score</li>
            <li>Not a commit gate that certifies</li>
            <li>Not a 24-hour Recall Clock product</li>
            <li>Not live customer metrics</li>
            <li>Not legal advice</li>
          </ul>
        </Card>
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
