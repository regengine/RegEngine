import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Outbound Webhooks (Planned) | RegEngine',
  description: 'Planned: notifications from RegEngine to your systems. Not available yet. To send events into RegEngine, use POST /api/v1/webhooks/ingest.',
  openGraph: {
    title: 'Outbound Webhooks (Planned)',
    description: 'Planned: notifications from RegEngine to your systems. Not available yet. To send events into RegEngine, use POST /api/v1/webhooks/ingest.',
    url: 'https://regengine.co/docs/webhooks',
    type: 'website',
  },
};
import { ArrowLeft, Webhook, Mail } from 'lucide-react';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';

const EVENT_TYPES = [
    { event: 'record.created', desc: 'New compliance record created' },
    { event: 'record.chain_extended', desc: 'Record appended to the hash chain' },
    { event: 'compliance.alert', desc: 'Regulatory change detected' },
    { event: 'document.ingested', desc: 'New document processed' },
    { event: 'fact.extracted', desc: 'Compliance fact extracted from document' },
];

const SAMPLE_PAYLOAD = `{
  "id": "evt_3x7Kp9mN2vL",
  "type": "compliance.alert",
  "created": "2026-03-15T14:23:01Z",
  "data": {
    "framework": "FSMA_204",
    "change_type": "guidance_updated",
    "previous_value": "draft-guidance-2024-09",
    "new_value": "draft-guidance-2026-02",
    "source_url": "fda.gov/..."
  }
}`;

export default function WebhooksDocsPage() {
    return (
        <>
            <PageHeader
                breadcrumbs={
                    <Link
                        href="/docs"
                        className="inline-flex items-center gap-2 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                    >
                        <ArrowLeft aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
                        Back to Docs
                    </Link>
                }
                eyebrow="Roadmap"
                title="Outbound webhooks (planned)"
                description="Notifications from RegEngine to your systems. These are not available yet."
            />

            <div className="space-y-8">
                <Callout tone="info" title="Sending events to RegEngine?">
                    <p className="text-ui text-re-text-secondary">
                        That is ingestion, and it is available now:{' '}
                        <code className="rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary">
                            POST /api/v1/webhooks/ingest
                        </code>
                        . See the{' '}
                        <Link
                            href="/docs/quickstart"
                            className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                        >
                            Quickstart
                        </Link>{' '}
                        and the{' '}
                        <Link
                            href="/docs/api"
                            className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                        >
                            API reference
                        </Link>
                        .
                    </p>
                </Callout>

                {/* Event Types Preview */}
                <section>
                    <h2 className="mb-4 text-heading text-re-text-primary">Planned Event Types</h2>

                    <Card className="overflow-hidden">
                        <ul className="list-none p-0">
                            {EVENT_TYPES.map((item) => (
                                <li
                                    key={item.event}
                                    className="flex flex-wrap items-center justify-between gap-3 border-b border-re-border-subtle px-5 py-4 last:border-0"
                                >
                                    <code className="rounded-sm border border-re-border-subtle bg-re-surface-inset px-2 py-1 font-mono text-[0.8125rem] text-re-text-tertiary">
                                        {item.event}
                                    </code>
                                    <span className="text-small text-re-text-tertiary">{item.desc}</span>
                                </li>
                            ))}
                        </ul>
                    </Card>
                </section>

                {/* Payload Preview */}
                <section>
                    <h2 className="mb-4 text-heading text-re-text-primary">Sample Payload (Planned)</h2>

                    <Card variant="inset" className="overflow-hidden">
                        <div className="border-b border-re-border-subtle px-4 py-2">
                            <span className="font-mono text-label text-re-text-muted">
                                POST (to your endpoint)
                            </span>
                        </div>
                        <pre className="m-0 overflow-x-auto p-4 font-mono text-[0.8125rem] leading-6 text-re-text-tertiary">
                            <code>{SAMPLE_PAYLOAD}</code>
                        </pre>
                    </Card>
                </section>

                {/* Notify CTA */}
                <Card padding="spacious" className="text-center">
                    <Webhook aria-hidden="true" strokeWidth={1.75} className="mx-auto mb-4 h-6 w-6 text-re-text-muted" />
                    <h3 className="mb-2 text-subheading text-re-text-primary">
                        Get Notified on Release
                    </h3>
                    <p className="mx-auto mb-5 max-w-[48ch] text-ui text-re-text-tertiary">
                        Be the first to know when webhooks are available.
                    </p>
                    <Button asChild variant="primary" size="lg">
                        <a href="mailto:webhooks@regengine.co?subject=Webhooks%20Interest" className="no-underline">
                            <Mail aria-hidden="true" strokeWidth={1.75} />
                            Notify Me
                        </a>
                    </Button>
                </Card>
            </div>
        </>
    );
}
