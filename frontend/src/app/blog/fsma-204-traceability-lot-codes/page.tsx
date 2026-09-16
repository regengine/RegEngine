import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Clock, CheckCircle, Tag, Layers, ArrowRight } from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "FSMA 204 Traceability Lot Codes (TLCs): A Complete Guide | RegEngine Blog",
  description:
    "Learn how to assign, track, and maintain Traceability Lot Codes under FSMA 204. Covers TLC requirements, best practices, and common mistakes for food businesses.",
  openGraph: {
    url: "https://regengine.co/blog/fsma-204-traceability-lot-codes",
    siteName: "RegEngine",
    title: "FSMA 204 Traceability Lot Codes (TLCs): A Complete Guide",
    description: "Everything food businesses need to know about TLCs under the FDA Food Traceability Rule.",
    type: "article",
    publishedTime: "2026-03-01T00:00:00Z",
  },
};

const TLC_REQUIREMENTS = [
  {
    cte: "Harvesting",
    who: "Farms & growers",
    requirement: "Assign a TLC at harvest. The TLC must uniquely identify the lot — typically a combination of farm, field, date, and commodity.",
  },
  {
    cte: "Cooling",
    who: "Coolers & packhouses",
    requirement: "Maintain the TLC assigned at harvest. If lots are not commingled, the TLC carries through.",
  },
  {
    cte: "Initial Packing",
    who: "Packhouses",
    requirement: "If you create new consumer-facing lots, assign a new TLC. Record the link between the original harvest TLC and the new pack TLC.",
  },
  {
    cte: "Shipping",
    who: "Any shipper",
    requirement: "Include the TLC on shipping documents (BOL, ASN). The receiver must be able to trace back to your TLC.",
  },
  {
    cte: "Receiving",
    who: "Any receiver",
    requirement: "Record the TLC from the shipper. If you assign your own internal lot code, maintain the mapping to the original TLC.",
  },
  {
    cte: "Transformation",
    who: "Manufacturers & processors",
    requirement: "When inputs are combined into a new product, assign a new TLC. Record all input TLCs that went into the output.",
  },
];

const BEST_PRACTICES = [
  {
    title: "Use a consistent format",
    description: "Standardize your TLC format across facilities. A common pattern: FACILITY-DATE-SEQ (e.g., SAL-20260301-001).",
  },
  {
    title: "Include the date",
    description: "Embedding the production or harvest date in the TLC makes sorting and filtering much faster during a recall.",
  },
  {
    title: "Avoid reuse",
    description: "Never reuse a TLC, even across years. If you harvest romaine on March 1 every year, each year's lot must have a distinct code.",
  },
  {
    title: "Make it scannable",
    description: "Encode your TLC in a barcode (GS1-128 or DataMatrix) so it can be captured at receiving without manual entry.",
  },
  {
    title: "Document your scheme",
    description: "Write down your TLC assignment logic. The FDA may ask how you generate codes during an inspection.",
  },
];

export default function TLCGuidePage() {
  return (
    <div className="bg-re-surface-base">
      <Container as="article" width="prose" className="py-12 sm:py-16">
        <Link
          href="/blog"
          className="mb-8 inline-flex items-center gap-1.5 text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" /> Back to Blog
        </Link>

        {/* Header */}
        <PageHeader
          title="FSMA 204 Traceability Lot Codes (TLCs): A Complete Guide"
          description={
            <>
              Traceability Lot Codes are the connective tissue of FSMA 204. Every
              Critical Tracking Event requires one. Here&apos;s how to get them right.
            </>
          }
          meta={
            <>
              <span>March 1, 2026</span>
              <span className="inline-flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" /> 8 min read
              </span>
            </>
          }
        />

        <div className="space-y-12">
          {/* What is a TLC? */}
          <section className="space-y-5">
            <h2 className="text-heading text-re-text-primary">What Is a Traceability Lot Code?</h2>
            <p className="text-body text-re-text-secondary">
              A Traceability Lot Code (TLC) is a descriptor — often a number, code,
              or combination — used to identify a traceability lot. Under 21 CFR 1.1310,
              every food on the Food Traceability List must carry a TLC that connects it
              to the Critical Tracking Events (CTEs) in its supply chain.
            </p>
            <Callout tone="neutral">
              <p>
                <strong className="font-medium text-re-text-primary">Think of a TLC as a lot&apos;s passport.</strong> It travels with the
                food from farm to fork. When the FDA needs to trace a contaminated product,
                the TLC is how they follow the trail.
              </p>
            </Callout>
          </section>

          {/* TLC Requirements by CTE */}
          <section className="space-y-5">
            <h2 className="text-heading text-re-text-primary">TLC Requirements by Critical Tracking Event</h2>
            <Card className="divide-y divide-re-border-subtle">
              {TLC_REQUIREMENTS.map((item) => (
                <div key={item.cte} className="space-y-2 px-5 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Layers className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                    <span className="text-subheading text-re-text-primary">{item.cte}</span>
                    <Badge size="sm">{item.who}</Badge>
                  </div>
                  <p className="text-ui text-re-text-secondary">{item.requirement}</p>
                </div>
              ))}
            </Card>
          </section>

          {/* The Transformation Problem */}
          <section className="space-y-5">
            <h2 className="text-heading text-re-text-primary">The Transformation Challenge</h2>
            <p className="text-body text-re-text-secondary">
              Transformation CTEs are where TLC tracking gets complex. When you combine
              romaine from three different harvest lots into a single salad kit, you must:
            </p>
            <ol className="list-inside list-decimal space-y-2 text-body text-re-text-secondary">
              <li>Assign a <strong className="font-medium text-re-text-primary">new TLC</strong> to the output product</li>
              <li>Record <strong className="font-medium text-re-text-primary">all input TLCs</strong> that went into it</li>
              <li>Maintain this mapping for <strong className="font-medium text-re-text-primary">at least 2 years</strong></li>
            </ol>
            <Callout tone="warning">
              <p>
                This input-to-output TLC mapping is what the FDA uses to trace contamination
                backwards through your supply chain. Missing or incomplete mappings are the
                #1 compliance gap we see in food manufacturing operations.
              </p>
            </Callout>
          </section>

          {/* Best Practices */}
          <section className="space-y-5">
            <h2 className="text-heading text-re-text-primary">TLC Best Practices</h2>
            <div className="space-y-4">
              {BEST_PRACTICES.map((item) => (
                <div key={item.title} className="flex items-start gap-3">
                  <CheckCircle
                    className="mt-1 h-4 w-4 shrink-0 text-re-text-tertiary"
                    strokeWidth={1.75}
                    aria-hidden="true"
                  />
                  <div className="space-y-1">
                    <p className="text-subheading text-re-text-primary">{item.title}</p>
                    <p className="text-ui text-re-text-secondary">{item.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* CTA */}
          <Card padding="spacious" className="text-center">
            <Tag className="mx-auto mb-3 h-6 w-6 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            <h3 className="text-heading text-re-text-primary">Validate Your TLCs</h3>
            <p className="mx-auto mt-2 max-w-[48ch] text-ui text-re-text-secondary">
              Use RegEngine&apos;s free TLC Validator to check your lot codes against
              FSMA 204 requirements.
            </p>
            <div className="mt-5 flex justify-center">
              <Button asChild size="lg">
                <Link href="/tools/tlc-validator">
                  Open TLC Validator <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                </Link>
              </Button>
            </div>
          </Card>
        </div>
      </Container>
    </div>
  );
}
