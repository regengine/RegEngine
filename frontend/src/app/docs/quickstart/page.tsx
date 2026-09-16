import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Quickstart | RegEngine',
  description: 'Create your first traceability event with a chained SHA-256 hash in under 5 minutes with the RegEngine API.',
  openGraph: {
    title: 'Quickstart',
    description: 'Create your first traceability event with a chained SHA-256 hash in under 5 minutes with the RegEngine API.',
    url: 'https://regengine.co/docs/quickstart',
    type: 'website',
  },
};
import { ArrowLeft, Key, FileText, Code, ArrowRight } from 'lucide-react';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { CodeBlock } from '@/components/ui/code-block';

/** Inline identifier — SPEC §2.3: every identifier is mono at 0.8125rem, on the inset well. */
const CODE =
    'rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary';

const NEXT_STEPS = [
    { title: 'FSMA 204 Guide', desc: 'Learn about CTEs, KDEs, and FDA Request Mode', href: '/docs/fsma-204', icon: FileText },
    { title: 'API Reference', desc: 'Explore all available endpoints', href: '/docs/api', icon: Code },
    { title: 'Authentication', desc: 'Learn about API key management', href: '/docs/authentication', icon: Key },
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
                eyebrow="5 min setup"
                title="Quickstart"
                description="Create your first traceability event with a chained SHA-256 hash in under 5 minutes"
            />

            <div className="space-y-8">
                <Step n="1" title="Get your API key">
                    <p className="text-body text-re-text-secondary">
                        Sign up for a RegEngine account and generate an API key from your dashboard.
                    </p>
                    <Button asChild variant="primary" size="lg">
                        <Link href="/api-keys" className="no-underline">
                            <Key aria-hidden="true" strokeWidth={1.75} />
                            Get API Key
                        </Link>
                    </Button>
                </Step>

                <Step n="2" title="Set your environment variable">
                    <p className="text-body text-re-text-secondary">
                        Store your API key securely. Never commit it to version control.
                    </p>
                    <CodeBlock
                        code={`export REGENGINE_API_KEY="rge_your_key_here"
export REGENGINE_TENANT_ID="11111111-1111-1111-1111-111111111111"`}
                        language="bash"
                    />
                </Step>

                <Step n="3" title="Create your first compliance record">
                    <p className="text-body text-re-text-secondary">
                        Use the <code className={CODE}>/api/v1/webhooks/ingest</code> endpoint
                        to create a compliant traceability event:
                    </p>

                    <div className="space-y-3">
                        <CodeBlock
                            code={`curl -X POST https://regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -H "X-Tenant-ID: $REGENGINE_TENANT_ID" \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -H "Content-Type: application/json" \\
  -d '{
    "source": "erp",
    "events": [
      {
        "cte_type": "receiving",
        "traceability_lot_code": "00012345678901-LOT-2026-001",
        "product_description": "Romaine Lettuce",
        "quantity": 500,
        "unit_of_measure": "cases",
        "location_name": "Distribution Center #4",
        "timestamp": "2026-02-05T14:23:00Z",
        "kdes": {
          "receive_date": "2026-02-05",
          "receiving_location": "Distribution Center #4",
          "immediate_previous_source": "GreenLeaf Farms LLC",
          "reference_document": "ASN-2026-02-05-00123",
          "tlc_source_reference": "GLF-2026-001"
        }
      }
    ]
  }'`}
                            language="curl"
                        />
                        <p className="text-ui text-re-text-secondary">
                            <strong className="font-medium text-re-text-primary">Heads up:</strong> the <code className={CODE}>Idempotency-Key</code> header
                            is required on webhook ingest — successful (2xx) responses are cached for 24 hours per tenant
                            and replayed on retry. On other POST endpoints it is optional (max length 255). Generate a
                            fresh UUID per logical request. RECEIVING events require <code className={CODE}>immediate_previous_source</code>,{' '}
                            <code className={CODE}>reference_document</code>, and{' '}
                            <code className={CODE}>tlc_source_reference</code> per 21 CFR §1.1345(c).
                        </p>
                    </div>

                    {/* Response */}
                    <CodeBlock
                        code={`{
  "accepted": 1,
  "rejected": 0,
  "total": 1,
  "events": [
    {
      "traceability_lot_code": "00012345678901-LOT-2026-001",
      "cte_type": "receiving",
      "status": "accepted",
      "event_id": "a1b2c3d4-...",
      "sha256_hash": "a3f2b891c4d5e6f7...",
      "chain_hash": "7f6e5d4c3b2a1908..."
    }
  ]
}`}
                        language="json"
                    />

                    <div className="space-y-3">
                        <p className="text-ui text-re-text-secondary">
                            When present on a 200 response, RegEngine exposes <code className={CODE}>X-RateLimit-Remaining</code> so
                            clients can back off before hitting a 429. Always guard for absence — coverage is rolling out per route. See{' '}
                            <Link
                                href="/docs/rate-limits"
                                className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                            >
                                Rate Limits
                            </Link>{' '}
                            for the full header set.
                        </p>
                        <CodeBlock
                            code={`const resp = await fetch("https://regengine.co/api/v1/webhooks/ingest", requestOptions);
// When present on a 200 response, RegEngine exposes X-RateLimit-Remaining.
// Always treat the header as optional; not every route emits it yet.
const remaining = resp.headers.get("X-RateLimit-Remaining");
console.log(\`Requests left in this window: \${remaining ?? "unknown"}\`);`}
                            language="javascript"
                        />
                    </div>
                </Step>

                <Step n="4" title="Verify your record">
                    <p className="text-body text-re-text-secondary">
                        Every ingested event is cryptographically hashed. Verify integrity independently from an export file:
                    </p>
                    <CodeBlock
                        code={`python verify_chain.py --file export_2026_02.json --offline

# Output:
# ✓ Chain re-hashed; no mismatches detected
# ✓ 1847 records re-hashed against export
# Note: integrity check is offline and advisory; tampering before ingest is out of scope.`}
                        language="bash"
                    />
                </Step>

                {/* Success */}
                <Callout tone="success">
                    <h3 className="text-subheading text-re-text-primary">You&apos;re all set!</h3>
                    <p className="mt-1 text-ui text-re-text-secondary">
                        You&apos;ve created your first traceability event with a chained SHA-256 hash. The record is now
                        part of an append-only chain you can re-hash offline against your export to confirm nothing changed in transit.
                    </p>
                </Callout>

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
