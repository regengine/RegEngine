import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Quickstart | RegEngine',
  description: 'Make your first RegEngine API calls: read your workspace records, then send one signed test event.',
  openGraph: {
    title: 'Quickstart',
    description: 'Make your first RegEngine API calls: read your workspace records, then send one signed test event.',
    url: 'https://regengine.co/docs/quickstart',
    type: 'website',
  },
};
import { ArrowLeft, Key, FileText, Code, ArrowRight } from 'lucide-react';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { CodeBlock } from '@/components/ui/code-block';
import { API_BASE } from '@/lib/api-base';
import { INGEST_CURL_SAMPLE, INGEST_ENV_SETUP, INGEST_RESPONSE_SAMPLE } from '@/lib/api-samples/ingest-samples';

/** Inline identifier — SPEC §2.3: every identifier is mono at 0.8125rem, on the inset well. */
const CODE =
    'rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary';

const NEXT_STEPS = [
    { title: 'FSMA 204 Guide', desc: 'Learn about CTEs, KDEs, and FDA Request Mode', href: '/docs/fsma-204', icon: FileText },
    { title: 'API Reference', desc: 'Explore all available endpoints', href: '/docs/api', icon: Code },
    { title: 'Authentication', desc: 'How keys, scopes and the signing secret work', href: '/docs/authentication', icon: Key },
];

/** A numbered step. The ordinal is a mono numeral, not a brand-filled disc (SPEC §1.6). */
function Step({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
    return (
        <section className="border-t border-re-border-subtle pt-6">
            <div className="flex items-baseline gap-3">
                <span aria-hidden="true" className="font-mono text-label text-re-text-muted">
                    {n}
                </span>
                <h2 className="text-heading text-re-text-primary">{title}</h2>
            </div>
            <div className="mt-3 space-y-4">{children}</div>
        </section>
    );
}

export default function QuickstartPage() {
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
                eyebrow="First call"
                title="Quickstart"
                description="Read your workspace records, then send one signed test event. You need the API key, workspace ID and signing secret RegEngine issues."
            />

            <div className="space-y-8">
                <Step n="1" title="Request access">
                    <p className="text-body text-re-text-secondary">
                        RegEngine issues API keys on request. There is no self-serve key creation. After you ask,
                        RegEngine sends you three things:
                    </p>
                    <ul className="list-disc space-y-1.5 pl-5 text-ui text-re-text-secondary marker:text-re-text-muted">
                        <li>
                            An <strong className="font-medium text-re-text-primary">API key</strong> that starts with{' '}
                            <code className={CODE}>rge_live_</code>.
                        </li>
                        <li>
                            Your <strong className="font-medium text-re-text-primary">workspace ID</strong>, a UUID. Calls infer the
                            workspace from the key; the ID is only a query parameter on a few endpoints.
                        </li>
                        <li>
                            The <strong className="font-medium text-re-text-primary">signing secret</strong> RegEngine issues for ingest.
                            You use it to sign the body of every ingest request.
                        </li>
                    </ul>
                    <Button asChild variant="primary" size="lg">
                        <Link href="/contact" className="no-underline">
                            <Key aria-hidden="true" strokeWidth={1.75} />
                            Request developer access
                        </Link>
                    </Button>
                </Step>

                <Step n="2" title="Set your environment variables">
                    <p className="text-body text-re-text-secondary">
                        Keep both values out of version control and out of client-side code. Anyone who holds the API key and the
                        signing secret can send events into the workspace that key belongs to. If you think either value is exposed,
                        tell RegEngine right away.
                    </p>
                    <CodeBlock code={INGEST_ENV_SETUP} language="bash" />
                    <p className="text-ui text-re-text-secondary">
                        Do not send an <code className={CODE}>X-Tenant-ID</code> header. RegEngine takes the workspace from your
                        key, and a value that differs from it is refused with a 403.
                    </p>
                </Step>

                <Step n="3" title="Make a read call (writes nothing)">
                    <p className="text-body text-re-text-secondary">
                        Start with a read to confirm the key works:
                    </p>
                    <CodeBlock
                        code={`curl -s "${API_BASE}/records?limit=1" \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY"`}
                        language="bash"
                    />
                    <p className="text-ui text-re-text-secondary">
                        Expect a <code className={CODE}>200</code> with your workspace ID in{' '}
                        <code className={CODE}>tenant_id</code>. A new workspace has no events yet:
                    </p>
                    <CodeBlock
                        code={`{
  "tenant_id": "<your workspace ID>",
  "events": [],
  "total": 0
}`}
                        language="json"
                    />
                    <p className="text-ui text-re-text-secondary">
                        Send the key in <code className={CODE}>X-RegEngine-API-Key</code>. An{' '}
                        <code className={CODE}>Authorization</code> header is not accepted. A <code className={CODE}>401</code> means
                        the key is missing or not recognized; a <code className={CODE}>403</code> means the key lacks the{' '}
                        <code className={CODE}>records.read</code> scope.
                    </p>
                </Step>

                <Step n="4" title="Send one signed test event (this writes)">
                    <Callout tone="warning" title="Writes are permanent and can be billed">
                        <p className="text-ui text-re-text-secondary">
                            Accepted events are appended to your workspace&apos;s hash chain and may be billed. There is no endpoint
                            to delete an ingested event. Use a separate test workspace (ask RegEngine for one) and keep the{' '}
                            <code className={CODE}>TEST-</code> prefix on lot codes.
                        </p>
                    </Callout>
                    <p className="text-body text-re-text-secondary">
                        Post to <code className={CODE}>/api/v1/webhooks/ingest</code>. The sample builds a current timestamp,
                        signs the exact body, and sends the same bytes with <code className={CODE}>--data-binary</code>:
                    </p>

                    <CodeBlock code={INGEST_CURL_SAMPLE} language="bash" />

                    <p className="text-ui text-re-text-secondary">
                        A <code className={CODE}>200</code> carries one result per event:
                    </p>
                    <CodeBlock code={INGEST_RESPONSE_SAMPLE} language="json" />

                    <div className="space-y-3">
                        <h3 className="text-subheading text-re-text-primary">What the request needs</h3>
                        <ul className="list-disc space-y-1.5 pl-5 text-ui text-re-text-secondary marker:text-re-text-muted">
                            <li>
                                <code className={CODE}>X-RegEngine-API-Key</code> with the{' '}
                                <code className={CODE}>webhooks.ingest</code> scope.
                            </li>
                            <li>
                                <code className={CODE}>X-Webhook-Signature</code>: <code className={CODE}>sha256=</code> followed by the
                                HMAC-SHA256 hex digest of the exact request body bytes, keyed with the signing secret RegEngine issues. A missing
                                or wrong signature returns <code className={CODE}>401</code>.
                            </li>
                            <li>
                                <code className={CODE}>Idempotency-Key</code>: required (<code className={CODE}>400</code> if missing,
                                255 characters at most). Use a new UUID for every new payload. Repeating a key with the same bytes
                                within 24 hours replays the first successful response, including a <code className={CODE}>200</code>{' '}
                                that rejected events. Repeating it with different bytes returns <code className={CODE}>409</code>.
                                After you fix a rejected event, send it with a new key.
                            </li>
                            <li>
                                Each event <code className={CODE}>timestamp</code> must fall within the last 90 days and no more than
                                24 hours ahead. An event older than 90 days comes back with{' '}
                                <code className={CODE}>status: &quot;rejected&quot;</code> inside a <code className={CODE}>200</code>.
                                An event more than 24 hours ahead fails the whole request with a <code className={CODE}>422</code>{' '}
                                and nothing is stored.
                            </li>
                            <li>
                                A RECEIVING event needs <code className={CODE}>receive_date</code>,{' '}
                                <code className={CODE}>receiving_location</code>, <code className={CODE}>immediate_previous_source</code>,{' '}
                                <code className={CODE}>reference_document</code> and <code className={CODE}>tlc_source_reference</code>{' '}
                                (21 CFR §1.1345). Other event types need different KDEs; the{' '}
                                <Link
                                    href="/docs/api#required-kdes"
                                    className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                                >
                                    API reference lists them
                                </Link>
                                .
                            </li>
                        </ul>
                        <p className="text-ui text-re-text-secondary">
                            A <code className={CODE}>200</code> does not mean every event was accepted. Check{' '}
                            <code className={CODE}>status</code> on each event: a rejected one has <code className={CODE}>errors</code>{' '}
                            explaining why, for example{' '}
                            <code className={CODE}>Missing required KDE &apos;reference_document&apos; for receiving CTE</code>. A{' '}
                            <code className={CODE}>402</code> means the workspace has no active subscription; contact RegEngine. If you
                            get a <code className={CODE}>429</code>, stop for 60 seconds before retrying; see{' '}
                            <Link
                                href="/docs/rate-limits"
                                className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                            >
                                Rate Limits
                            </Link>
                            . Python and JavaScript versions of this call are on the{' '}
                            <Link
                                href="/docs"
                                className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                            >
                                docs home page
                            </Link>
                            .
                        </p>
                    </div>
                </Step>

                <Step n="5" title="Read the event back">
                    <p className="text-body text-re-text-secondary">
                        Filter the records endpoint by lot code:
                    </p>
                    <CodeBlock
                        code={`curl -s "${API_BASE}/records?tlc=TEST-00012345678901-LOT-001" \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY"`}
                        language="bash"
                    />
                    <CodeBlock
                        code={`{
  "tenant_id": "<your workspace ID>",
  "events": [
    {
      "event_id": "0b9c2f4e-6d1a-4c53-9a7e-5f3d8e21c7ab",
      "event_type": "receiving",
      "traceability_lot_code": "TEST-00012345678901-LOT-001",
      "product_reference": "Romaine Lettuce",
      "quantity": 500.0,
      "unit_of_measure": "cases",
      "event_timestamp": "<the timestamp you sent>",
      "source_system": "webhook_api",
      "status": "active"
    }
  ],
  "total": 1
}`}
                        language="json"
                    />
                    <p className="text-ui text-re-text-secondary">
                        The list also carries <code className={CODE}>from_facility_reference</code>,{' '}
                        <code className={CODE}>to_facility_reference</code>, <code className={CODE}>confidence_score</code>,{' '}
                        <code className={CODE}>schema_version</code> and <code className={CODE}>created_at</code>; they are left out
                        above. Each record&apos;s <code className={CODE}>event_id</code> opens the full record with provenance at{' '}
                        <code className={CODE}>GET /api/v1/records/&#123;event_id&#125;</code>.
                    </p>
                </Step>

                {/* Next Steps */}
                <section className="border-t border-re-border-subtle pt-6">
                    <h2 className="text-heading text-re-text-primary">Next Steps</h2>

                    <ul className="mt-3 list-none border-t border-re-border-subtle p-0">
                        {NEXT_STEPS.map((item) => (
                            <li key={item.href}>
                                <Link
                                    href={item.href}
                                    className="group flex items-center gap-4 border-b border-re-border-subtle px-1 py-4 no-underline transition-colors duration-120 hover:bg-re-surface-inset motion-reduce:transition-none"
                                >
                                    <item.icon aria-hidden="true" strokeWidth={1.75} className="h-4 w-4 shrink-0 text-re-text-muted" />
                                    <span className="min-w-0 flex-1">
                                        <span className="block text-ui font-medium text-re-text-primary">{item.title}</span>
                                        <span className="block text-small text-re-text-tertiary">{item.desc}</span>
                                    </span>
                                    <ArrowRight
                                        aria-hidden="true"
                                        strokeWidth={1.75}
                                        className="h-4 w-4 shrink-0 text-re-text-muted transition-colors duration-120 group-hover:text-re-text-primary motion-reduce:transition-none"
                                    />
                                </Link>
                            </li>
                        ))}
                    </ul>
                </section>
            </div>
        </>
    );
}
