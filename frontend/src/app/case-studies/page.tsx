import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';

export const metadata: Metadata = {
    title: 'Product Validation | RegEngine',
    description:
        'RegEngine product validation. No published validation study yet; run the workflow on your own data.',
    keywords:
        'FSMA 204, traceability validation, food safety, CTE validation, FDA compliance, RegEngine',
  openGraph: {
    title: 'Product Validation | RegEngine',
    description: 'No published validation study yet; run the RegEngine workflow on your own data.',
    url: 'https://regengine.co/case-studies',
    type: 'article',
  },
};

export default function CaseStudy() {
    return (
        <div className="bg-re-surface-base text-re-text-primary">
            <Container as="section" width="marketing" className="py-12 sm:py-16">
                <PageHeader
                    size="hero"
                    title="Product validation"
                    description="RegEngine is pre-revenue. There is no published validation study with customer or production data yet."
                    className="mb-0 border-b-0 pb-0"
                />
                <Card padding="spacious" className="mt-10 max-w-[68ch]">
                    <p className="font-mono text-label uppercase text-re-text-muted">Validation data</p>
                    <h2 className="mt-2 text-heading text-re-text-primary">No data yet</h2>
                    <p className="mt-3 text-ui text-re-text-secondary">
                        RegEngine is pre-revenue; self-serve access is in staged rollout. We do not
                        publish invented metrics. When a validation study runs against real
                        workloads, the results will appear here. Until then, the honest way to evaluate
                        RegEngine is to run it on your own supply chain data.
                    </p>
                    <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                        <Button asChild size="lg">
                            <Link href="/signup" className="no-underline">
                                Run Your Own Validation <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/tools/ftl-checker" className="no-underline">
                                Test with Your Data
                            </Link>
                        </Button>
                    </div>
                </Card>
            </Container>
        </div>
    );
}
