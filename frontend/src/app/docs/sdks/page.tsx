import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'SDKs & Libraries | RegEngine',
  description: 'RegEngine client libraries for Python, Node.js, and Go are planned and not released yet. Use the REST API and the OpenAPI spec today.',
  openGraph: {
    title: 'SDKs & Libraries',
    description: 'RegEngine client libraries for Python, Node.js, and Go are planned and not released yet. Use the REST API and the OpenAPI spec today.',
    url: 'https://regengine.co/docs/sdks',
    type: 'website',
  },
};
import { ArrowLeft, Mail, GitBranch, FileText } from 'lucide-react';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

const SDKS = [
    { title: 'Python SDK', badge: 'Planned', planned: true },
    { title: 'Node.js SDK', badge: 'Planned', planned: true },
    { title: 'Go SDK', badge: 'Planned', planned: true },
    { title: 'REST Client', badge: 'Available now: OpenAPI 3.0 spec (Preview)', planned: false },
];

const CHROME_LINK =
    'inline-flex items-center gap-2 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none';

export default function SDKsDocsPage() {
    return (
        <>
            <PageHeader
                breadcrumbs={
                    <Link href="/docs" className={CHROME_LINK}>
                        <ArrowLeft aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
                        Back to Docs
                    </Link>
                }
                eyebrow="Roadmap"
                title="SDKs & Libraries"
                description="Client libraries are planned and not released yet. Use the REST API directly."
            />

            <div className="space-y-8">
                {/* SDK Preview */}
                <section>
                    <h2 className="mb-4 text-heading text-re-text-primary">Planned SDK Releases</h2>

                    <Card className="overflow-hidden">
                        <ul className="list-none p-0">
                            {SDKS.map((item) => (
                                <li
                                    key={item.title}
                                    className="flex flex-wrap items-center justify-between gap-3 border-b border-re-border-subtle px-5 py-4 last:border-0"
                                >
                                    <span
                                        className={
                                            item.planned
                                                ? 'text-ui font-medium text-re-text-tertiary'
                                                : 'text-ui font-medium text-re-text-primary'
                                        }
                                    >
                                        {item.title}
                                    </span>
                                    <Badge tone="neutral" size="sm" mono>
                                        {item.badge}
                                    </Badge>
                                </li>
                            ))}
                        </ul>
                    </Card>
                </section>

                {/* What to use now */}
                <Card>
                    <CardContent className="space-y-4">
                        <h3 className="text-subheading text-re-text-primary">What to Use Now</h3>
                        <p className="text-ui text-re-text-secondary">
                            Until SDKs are released, use our REST API directly or import the public OpenAPI 3.0 spec (Preview) into your client generator.
                        </p>
                        <div className="flex flex-wrap gap-5">
                            <Link href="/docs/api" className={CHROME_LINK}>
                                View API Reference →
                            </Link>
                            <a href="/openapi.json" className={CHROME_LINK} download>
                                <FileText aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
                                Download OpenAPI spec
                            </a>
                        </div>
                    </CardContent>
                </Card>

                {/* Notify CTA */}
                <Card padding="spacious" className="text-center">
                    <GitBranch aria-hidden="true" strokeWidth={1.75} className="mx-auto mb-4 h-6 w-6 text-re-text-muted" />
                    <h3 className="mb-2 text-subheading text-re-text-primary">
                        Get Notified on Release
                    </h3>
                    <p className="mx-auto mb-5 max-w-[48ch] text-ui text-re-text-tertiary">
                        Be the first to know when our official SDKs are available.
                    </p>
                    <Button asChild variant="primary" size="lg">
                        <a href="mailto:sdk@regengine.co?subject=SDK%20Release%20Notification" className="no-underline">
                            <Mail aria-hidden="true" strokeWidth={1.75} />
                            Notify Me
                        </a>
                    </Button>
                </Card>
            </div>
        </>
    );
}
