import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Clock, CheckCircle, AlertTriangle, FileText, Shield } from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";
import { JSONLD } from '@/components/seo/json-ld';
import { blogPostingJsonLd } from '@/lib/blog-jsonld';

export const metadata: Metadata = {
  title: "The FSMA 204 24-Hour Rule Explained | RegEngine Blog",
  description:
    "The FDA can request your traceability records within 24 hours of a recall or outbreak. Learn what records you need, how to organize them, and how to respond in time.",
  openGraph: {
    url: "https://regengine.co/blog/24-hour-rule",
    siteName: "RegEngine",
    title: "The FSMA 204 24-Hour Rule Explained",
    description: "What the FDA's 24-hour records request means for your food business.",
    type: "article",
    publishedTime: "2026-03-15T00:00:00Z",
  },
};

const KEY_RECORDS = [
  "Traceability Lot Codes (TLCs) for every product on the Food Traceability List",
  "Critical Tracking Events (CTEs): shipping, receiving, transformation, and more",
  "Key Data Elements (KDEs): who, what, when, where for each CTE",
  "Reference documents: BOLs, purchase orders, ASNs",
  "Location identifiers: GLNs or descriptive names for every facility",
];

const COMMON_MISTAKES = [
  {
    mistake: "Storing records in paper binders or disconnected spreadsheets",
    fix: "Use a centralized digital system that can export records instantly",
  },
  {
    mistake: "Relying on one person to know where everything is",
    fix: "Document your record-keeping process so anyone on your team can respond",
  },
  {
    mistake: "Not testing your recall readiness",
    fix: "Run a mock recall drill quarterly, as the FDA recommends",
  },
  {
    mistake: "Waiting for an FDA request to organize records",
    fix: "Keep records sortable by TLC, date range, and product from day one",
  },
];

export default function TwentyFourHourRulePage() {
  return (
    <div className="bg-re-surface-base">
      <JSONLD data={blogPostingJsonLd('24-hour-rule', 'The FDA can request your traceability records within 24 hours of a recall or outbreak. Learn what records you need, how to organize them, and how to respond in time.')} />
      <Container as="article" width="prose" className="py-12 sm:py-16">
        <Link
          href="/blog"
          className="mb-8 inline-flex items-center gap-1.5 text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" /> Back to Blog
        </Link>

        {/* Header */}
        <PageHeader
          title="The FSMA 204 24-Hour Rule: What It Really Means for Your Operation"
          description={
            <>
              When the FDA identifies a foodborne illness outbreak or contamination event,
              they can request your traceability records within <strong className="font-medium text-re-text-primary">24 hours</strong>.
              Here&apos;s what that means in practice.
            </>
          }
          meta={
            <>
              <span>March 15, 2026</span>
              <span className="inline-flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" /> 6 min read
              </span>
            </>
          }
        />

        <div className="space-y-12">
          {/* Section: What is the 24-hour rule? */}
          <section className="space-y-5">
            <h2 className="text-heading text-re-text-primary">What is the 24-Hour Rule?</h2>
            <p className="text-body text-re-text-secondary">
              Under 21 CFR 1.1455, the FDA can require any person who is subject to the
              food traceability requirements to provide, within 24 hours of a request,
              the information required to be maintained under the rule. This applies to
              all foods on the Food Traceability List (FTL).
            </p>
            <Callout tone="warning">
              <p>
                <strong className="font-medium text-re-text-primary">This is not optional.</strong> Failure to produce records within 24 hours
                can result in FDA enforcement actions, including warning letters, import alerts,
                and potential criminal referral for repeat violations.
              </p>
            </Callout>
            <p className="text-body text-re-text-secondary">
              The clock starts when the FDA sends the request, not when you read it.
              Weekends and holidays are not excluded. This means your traceability system
              needs to be accessible and queryable at any time.
            </p>
          </section>

          {/* Section: What records does the FDA want? */}
          <section className="space-y-5">
            <h2 className="text-heading text-re-text-primary">What Records Does the FDA Want?</h2>
            <p className="text-body text-re-text-secondary">
              The FDA will typically request records for a specific product, lot code,
              or time period. You need to provide:
            </p>
            <ul className="space-y-3">
              {KEY_RECORDS.map((record) => (
                <li key={record} className="flex items-start gap-3 text-body text-re-text-secondary">
                  <CheckCircle
                    className="mt-1 h-4 w-4 shrink-0 text-re-text-tertiary"
                    strokeWidth={1.75}
                    aria-hidden="true"
                  />
                  <span>{record}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* Section: Common mistakes */}
          <section className="space-y-5">
            <h2 className="text-heading text-re-text-primary">Common Mistakes That Slow Your Response</h2>
            <Card className="divide-y divide-re-border-subtle">
              {COMMON_MISTAKES.map((item) => (
                <div key={item.mistake} className="space-y-1.5 px-5 py-4">
                  <p className="flex items-start gap-2.5 text-subheading text-re-text-primary">
                    <AlertTriangle
                      className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary"
                      strokeWidth={1.75}
                      aria-hidden="true"
                    />
                    {item.mistake}
                  </p>
                  <p className="flex items-start gap-2.5 text-ui text-re-text-secondary">
                    <CheckCircle
                      className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary"
                      strokeWidth={1.75}
                      aria-hidden="true"
                    />
                    {item.fix}
                  </p>
                </div>
              ))}
            </Card>
          </section>

          {/* Section: How to prepare */}
          <section className="space-y-5">
            <h2 className="text-heading text-re-text-primary">How to Prepare</h2>
            <div className="space-y-4 text-body text-re-text-secondary">
              <p>
                <strong className="font-medium text-re-text-primary">1. Digitize your records.</strong> Paper-based systems cannot
                meet a 24-hour deadline at scale. You need a system that can query
                records by TLC, product, date range, and location.
              </p>
              <p>
                <strong className="font-medium text-re-text-primary">2. Run mock recalls.</strong> The FDA recommends periodic mock
                recall exercises. Use RegEngine&apos;s{" "}
                <Link
                  href="/tools/drill-simulator"
                  className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                >
                  Recall Drill Simulator
                </Link>{" "}
                to practice.
              </p>
              <p>
                <strong className="font-medium text-re-text-primary">3. Assign a response team.</strong> Designate who receives and
                responds to FDA requests. Include backup contacts for evenings and weekends.
              </p>
              <p>
                <strong className="font-medium text-re-text-primary">4. Pre-configure exports.</strong> Set up your system to produce
                sortable spreadsheets or electronic records that the FDA can review
                immediately. The FDA accepts CSV, Excel, and PDF formats.
              </p>
            </div>
          </section>

          {/* CTA */}
          <Card padding="spacious" className="text-center">
            <Shield
              className="mx-auto mb-3 h-6 w-6 text-re-text-tertiary"
              strokeWidth={1.75}
              aria-hidden="true"
            />
            <h3 className="text-heading text-re-text-primary">Test Your 24-Hour Readiness</h3>
            <p className="mx-auto mt-2 max-w-[48ch] text-ui text-re-text-secondary">
              RegEngine&apos;s free tools help you assess your compliance readiness
              before the FDA comes knocking.
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-3">
              <Button asChild size="lg">
                <Link href="/tools/drill-simulator">
                  <FileText className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" /> Run a Mock Recall
                </Link>
              </Button>
              <Button asChild variant="secondary" size="lg">
                <Link href="/tools/self-reported-checklist">Open Self Reported Checklist</Link>
              </Button>
            </div>
          </Card>
        </div>
      </Container>
    </div>
  );
}
