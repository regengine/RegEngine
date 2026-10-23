import type { Metadata } from "next";
import Link from "next/link";
import { BookCallLink } from "@/components/conversion/BookCallLink";
import { ArrowRight, CheckCircle2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";
import { Container } from "@/components/layout/container";

export const metadata: Metadata = {
  title: "Buyer traceability programs | RegEngine",
  description:
    "Some buyers have published their own traceability programs. Those programs are the buyer's. They are not federal enforcement and they are not a RegEngine badge. We help you structure CTE/KDE records and export a sortable package.",
  openGraph: {
    title: "Buyer traceability programs | RegEngine",
    description:
      "Buyer programs are not the FDA clock. We help you structure CTE/KDE records and export a sortable package. You confirm format, scope, and dates with your buyer.",
    url: "https://regengine.co/buyer-programs",
    type: "website",
  },
};

/** Every list on this page is a plain hairline-free bullet list of short facts. */
const factList = "space-y-2 text-ui leading-relaxed text-re-text-secondary";

export default function BuyerProgramsPage() {
  return (
    <div className="bg-re-surface-base text-re-text-secondary">
      <Container as="section" width="tool" className="pb-10 pt-14 sm:pb-14 sm:pt-20">
        <span className="mb-4 block font-mono text-label uppercase text-re-text-muted">
          Buyer Traceability Programs
        </span>
        <h1 className="mb-4 max-w-[20ch] font-display text-display text-re-text-primary">
          Buyer programs are not the FDA clock.
        </h1>
        <p className="max-w-[68ch] text-body leading-relaxed text-re-text-secondary">
          Some buyers have published their own traceability programs. Those programs are the buyer's. They are not federal enforcement and they are not a RegEngine badge. We help you structure CTE/KDE records and export a sortable package. You confirm format, scope, and dates with your buyer.
        </p>

        <Callout tone="warning" title="FDA date" className="mt-6">
          <p className="leading-relaxed">
            The FDA Food Traceability Rule compliance date is <strong className="font-medium text-re-text-primary">July 20, 2028</strong>. We will not imply that clock is now.
          </p>
        </Callout>

        <Callout tone="info" title="FTL vs covered person" className="mt-4">
          <p className="leading-relaxed">
            The Food Traceability List is the list of foods. Who must keep Subpart S records is a separate question. Being on the list is not the same as being a covered person. We do not decide either one for you.
          </p>
        </Callout>

        <div className="mt-8 flex flex-wrap gap-3">
          <Button asChild size="lg">
            <BookCallLink href="/contact" placement="buyer_programs" className="no-underline">
              Book a 30-min call
              <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </BookCallLink>
          </Button>
          <Button asChild variant="secondary" size="lg">
            <Link href="/verify" className="no-underline">
              Verify a sample export
            </Link>
          </Button>
        </div>
      </Container>

      <section className="border-t border-re-border-subtle">
        <Container width="tool" className="py-10 sm:py-14">
          <h2 className="mb-6 font-display text-heading-lg text-re-text-primary">
            Named buyer programs (first-party facts only)
          </h2>

          <div className="space-y-6">
            <Card padding="spacious">
              <h3 className="mb-3 text-subheading text-re-text-primary">
                Walmart Food Traceability / ASN
              </h3>
              <p className="mb-3 text-ui leading-relaxed text-re-text-secondary">
                Source: <a href="https://enablement.walmart.com" target="_blank" rel="noopener noreferrer" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">enablement.walmart.com</a>
              </p>
              <ul className={factList}>
                <li>• ASN containing KDEs</li>
                <li>• SSCC-18 on food pallets</li>
                <li>• GS1-128 on food cases</li>
                <li>• As of August 1, 2025 Walmart and Sam's Club require all food and beverage ASN+packaging</li>
                <li>• FTL by that date; other products ASAP</li>
              </ul>
              <p className="mt-4 text-small leading-relaxed text-re-text-tertiary">
                We do not make you Walmart-ready, transmit ASN on Retail Link, certify labels, or assess chargebacks.
              </p>
            </Card>

            <Card padding="spacious">
              <h3 className="mb-3 text-subheading text-re-text-primary">
                Albertsons Companies
              </h3>
              <p className="mb-3 text-ui leading-relaxed text-re-text-secondary">
                Source: Letter dated 17 September 2025 (PDF at suppliers.safeway.com)
              </p>
              <ul className={factList}>
                <li>• All food and non-alcoholic beverages</li>
                <li>• Albertsons deadline January 1, 2027</li>
                <li>• Federal date remains July 20, 2028</li>
              </ul>
            </Card>

            <Card padding="spacious">
              <h3 className="mb-3 text-subheading text-re-text-primary">
                Kroger Food Traceability Policy
              </h3>
              <p className="mb-3 text-ui leading-relaxed text-re-text-secondary">
                Source: December 2023 first-party letter
              </p>
              <Callout tone="warning">
                <p className="font-medium leading-relaxed text-re-text-primary">
                  A December 2023 first-party Kroger letter stated a June 30, 2025 supplier transition. We have not found a later first-party update. The letter's FDA date of January 20, 2026 is stale. The federal compliance date is July 20, 2028. This is not a claim that anyone is Kroger-ready.
                </p>
              </Callout>
            </Card>
          </div>
        </Container>
      </section>

      <section className="border-t border-re-border-subtle">
        <Container width="tool" className="py-10 sm:py-14">
          <h2 className="mb-6 font-display text-heading-lg text-re-text-primary">
            What we export
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            <Card padding="default" className="p-5">
              <div className="mb-3 flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                <h3 className="text-subheading text-re-text-primary">RegEngine provides</h3>
              </div>
              <ul className={factList}>
                <li>• CTE/KDE workspace</li>
                <li>• Advisory coverage/completeness checklist</li>
                <li>• Append-only commit</li>
                <li>• FDA-oriented sortable spreadsheet</li>
                <li>• CSV upload, JSON events API (EPCIS export)</li>
                <li>• Hash manifest re-checkable at /verify</li>
              </ul>
            </Card>

            <Card padding="default" className="p-5">
              <div className="mb-3 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                <h3 className="text-subheading text-re-text-primary">Operator still owns</h3>
              </div>
              <ul className={factList}>
                <li>• Covered-person status</li>
                <li>• FTL membership</li>
                <li>• Buyer acceptance</li>
                <li>• Physical labels/SSCC-18/GS1-128</li>
                <li>• Answering FDA under §1.1455</li>
              </ul>
            </Card>
          </div>
        </Container>
      </section>

      <section className="border-t border-re-border-subtle">
        <Container width="tool" className="py-10 sm:py-14">
          <h2 className="mb-4 font-display text-heading-lg text-re-text-primary">
            Pricing
          </h2>
          <Card padding="spacious">
            <div className="mb-4 flex flex-wrap items-baseline gap-3">
              <span className="text-title tabular-nums text-re-text-primary">$425</span>
              <span className="text-ui text-re-text-tertiary">per month, billed annually</span>
            </div>
            <p className="text-ui leading-relaxed text-re-text-secondary">
              No facility/CTE cap. No SLA. No retailer-specific benchmark. No quarterly compliance review. No audit. No readiness score. No FDA/buyer approval. No three-tier ladder or strikethrough list prices.
            </p>
          </Card>
        </Container>
      </section>

      <section className="border-t border-re-border-subtle">
        <Container width="tool" className="py-10 sm:py-14">
          <Card padding="spacious">
            <p className="mb-4 text-ui leading-relaxed text-re-text-secondary">
              <strong className="font-medium text-re-text-primary">Founder-led.</strong> Book a call. No score.
            </p>
            <p className="text-small text-re-text-tertiary">
              Pasadena, CA
            </p>
          </Card>
        </Container>
      </section>

      <section className="border-t border-re-border-subtle bg-re-surface-inset">
        <Container width="tool" className="py-10 text-center sm:py-14">
          <div className="flex flex-wrap justify-center gap-x-6 gap-y-3">
            <BookCallLink
              href="/contact"
              placement="buyer_programs"
              className="inline-flex items-center gap-1.5 text-ui text-re-brand underline underline-offset-[3px] decoration-re-border-strong transition-colors duration-120 hover:decoration-re-brand motion-reduce:transition-none"
            >
              Book a 30-min call <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
            </BookCallLink>
            <Link
              href="/verify"
              className="inline-flex items-center gap-1.5 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
            >
              Verify a sample export <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
            </Link>
          </div>
        </Container>
      </section>

      <footer className="border-t border-re-border-subtle py-8">
        <Container width="tool">
          <p className="text-ui text-re-text-secondary">
            Pasadena, CA
          </p>
          <p className="mt-2 text-small text-re-text-tertiary">
            July 20, 2028 · §1.1455 we do not claim to meet · No seals, competitor table, revenue-at-risk calculator
          </p>
        </Container>
      </footer>
    </div>
  );
}
