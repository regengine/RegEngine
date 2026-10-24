import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Section } from "@/components/layout/section";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Proof: CSV to FDA row | RegEngine",
  description:
    "How a supplier CSV becomes an FDA-oriented sortable record in RegEngine. No worked example is published yet.",
  openGraph: {
    title: "How a supplier CSV becomes an FDA-oriented sortable record | RegEngine",
    description: "No worked example is published yet.",
    url: "https://regengine.co/proof/transformation",
    type: "website",
  },
};

export default function TransformationProofPage() {
  return (
    <div className="re-page min-h-screen">
      {/* Hero */}
      <header className="border-b border-re-border-subtle">
        <Container width="docs" className="py-16 md:py-20">
          <Link
            href="/proof"
            className="text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
          >
            &larr; Proof
          </Link>
          <PageHeader
            size="hero"
            title="How a supplier CSV becomes an FDA-oriented sortable record."
            className="mb-0 mt-4 border-b-0 pb-0"
          />
          <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
            The pipeline is: raw supplier CSV, canonical TraceabilityEvent, then
            the FDA-oriented sortable row. The canonical event shape lives in{" "}
            <code className="rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem]">
              services/shared/canonical_event.py
            </code>{" "}
            and the export columns in{" "}
            <code className="rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem]">
              services/ingestion/app/fda_export_service.py
            </code>
            .
          </p>
        </Container>
      </header>

      <Section width="docs" flush>
        <Card className="p-8 md:p-10">
          <p className="font-mono text-label uppercase text-re-text-muted">Worked example</p>
          <h2 className="mt-2 text-heading text-re-text-primary">No data yet</h2>
          <p className="mt-3 max-w-[68ch] text-body text-re-text-secondary">
            There is no worked example with real data to show here. Run the pipeline on your
            own records and verify the resulting export bundle yourself.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/verify">
                Verify an export bundle
                <ArrowRight aria-hidden="true" strokeWidth={1.75} />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/signup">
                Start setup
                <ArrowRight aria-hidden="true" strokeWidth={1.75} />
              </Link>
            </Button>
          </div>
        </Card>
      </Section>
    </div>
  );
}
