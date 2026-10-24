import type { Metadata } from 'next';
import Link from 'next/link';
import {
    ArrowRight, Braces, Cog, Users, FileSpreadsheet,
    BarChart3, GitBranch, Terminal, BookOpen,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cardVariants } from '@/components/ui/card';
import { Container } from '@/components/layout/container';
import { INGEST_CURL_SAMPLE, INGEST_ENV_SETUP } from '@/lib/api-samples/ingest-samples';

export const metadata: Metadata = {
    title: 'Developers | RegEngine FSMA 204 Compliance API',
    description:
        'Build on the RegEngine API: a JSON events API with KDE validation, 36 FSMA 204 rules, identity resolution, FDA export, compliance scoring, and request workflow management.',
    openGraph: {
        title: 'Developers | RegEngine FSMA 204 Compliance API',
        description:
            'Build on the RegEngine API: JSON events API, rules engine, identity resolution, FDA export, compliance scoring, and request workflow.',
        url: 'https://regengine.co/developers',
        type: 'website',
    },
};

/* ── API Capabilities ── */
const capabilities = [
    {
        Icon: Braces,
        title: 'JSON events API',
        description: 'POST CTE events as JSON with KDE validation. Inbound events are validated against FSMA 204 Key Data Elements; failures surface as exceptions before package assembly.',
    },
    {
        Icon: Cog,
        title: 'Rules Engine',
        description: '36 FSMA 204 validation rules (33 stateless + 3 cross-event) evaluate every ingested event. Missing required KDEs, invalid TLCs, and schema violations surface as exceptions in the dashboard.',
    },
    {
        Icon: Users,
        title: 'Identity Resolution',
        description: 'Fuzzy matching across trading partners with confidence scoring. Deduplicate facilities, carriers, and contacts.',
    },
    {
        Icon: FileSpreadsheet,
        title: 'Records Export',
        description: 'Generate FDA-oriented sortable spreadsheet records and EPCIS 2.0 (Preview) event exports where the enabled workflow and source data support them.',
    },
    {
        Icon: BarChart3,
        title: 'Readiness Scoring',
        description: 'Six-dimension internal readiness signal across export readiness, KDE completeness, CTE coverage, chain integrity, obligation coverage, and FTL product coverage. Not an FDA-issued rating.',
    },
    {
        Icon: GitBranch,
        title: 'Request Workflow',
        description: '10-state machine for FDA response management. Track requests from intake through investigation, response, and closure.',
    },
];

/* ── SDKs (planned, not yet released) ── */

/* ── Quick-start curl snippet ── */
/* Rendered from one payload: src/lib/api-samples/ingest-receiving.json. */
const curlSnippet = `${INGEST_ENV_SETUP}

${INGEST_CURL_SAMPLE}`;

export default function DevelopersPage() {
    return (
        <div className="bg-re-surface-base text-re-text-secondary">
            {/* ═══ HERO ═══ */}
            <Container as="section" width="marketing" className="grid items-start gap-8 pb-10 pt-12 sm:pb-14 sm:pt-16 lg:grid-cols-[0.95fr_1fr]">
                <div>
                    <Badge tone="brand" className="mb-5">
                        <Terminal className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                        Developer Platform
                    </Badge>
                    <h1 className="re-hero-title">
                        Build on RegEngine
                    </h1>
                    <p className="re-hero-copy mt-5">
                        Developer preview for FSMA 204 traceability teams. Scope your
                        ingestion path, validate event payloads, and plan FDA-oriented sortable
                        export workflows with the RegEngine team.
                    </p>
                    <div className="mt-8 flex flex-wrap gap-3">
                        <Button asChild size="lg">
                            <Link href="/contact" className="no-underline">
                                Request Developer Access
                                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/docs" className="no-underline">
                                <BookOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                Full Documentation
                            </Link>
                        </Button>
                    </div>
                </div>

                <aside className={cardVariants({ className: "overflow-hidden" })}>
                    <div className="border-b border-re-border-subtle px-4 py-3">
                        <p className="font-mono text-label uppercase text-re-text-muted">
                            Integration path
                        </p>
                    </div>
                    {[
                        ['Ingest', 'POST critical tracking events with tenant scope.'],
                        ['Validate', 'Run KDE, TLC, and rule checks before evidence commit.'],
                        ['Export', 'Generate FDA-oriented sortable records where configured data supports the request.'],
                    ].map(([label, detail], index) => (
                        <div key={label} className="grid grid-cols-[28px_1fr] gap-x-3 gap-y-1 border-b border-re-border-subtle px-4 py-4 last:border-b-0 sm:grid-cols-[28px_110px_1fr]">
                            <span className="font-mono text-label text-re-text-muted">
                                {index + 1}
                            </span>
                            <span className="text-ui font-medium text-re-text-primary">{label}</span>
                            <span className="col-start-2 text-ui leading-6 text-re-text-secondary sm:col-start-3">{detail}</span>
                        </div>
                    ))}
                </aside>
            </Container>

            {/* ═══ QUICK START CURL ═══ */}
            <Container as="section" width="tool" className="pb-10 sm:pb-14">
                <h2 className="mb-3 text-center font-display text-heading-lg text-re-text-primary">Quick start</h2>
                <p className="mx-auto mb-8 max-w-[60ch] text-center text-ui text-re-text-secondary">
                    Record a critical tracking event with one signed request. RegEngine issues your API key, workspace ID, and
                    signing secret on request. This call writes a permanent record and can be billed, so use a test workspace and
                    keep the <code className="font-mono text-[0.8125rem] text-re-text-primary">TEST-</code> lot prefix. The{' '}
                    <Link href="/docs/quickstart" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">Quickstart</Link>{' '}
                    starts with a read-only call.
                </p>
                <div className="overflow-hidden rounded-lg border border-re-border">
                    <div className="flex items-center gap-2 border-b border-re-border-subtle bg-re-surface-card px-4 py-2.5">
                        <Terminal className="h-3.5 w-3.5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                        <span className="font-mono text-label text-re-text-muted">bash</span>
                    </div>
                    <pre className="overflow-x-auto bg-re-surface-inset p-4 font-mono text-[0.8125rem] leading-relaxed text-re-text-secondary sm:p-5">
                        <code>{curlSnippet}</code>
                    </pre>
                </div>
            </Container>

            {/* ═══ API CAPABILITIES GRID ═══ */}
            <Container as="section" width="marketing" className="pb-12 sm:pb-16">
                <h2 className="mb-3 text-center font-display text-heading-lg text-re-text-primary">API capabilities</h2>
                <p className="mx-auto mb-10 max-w-[68ch] text-center text-ui text-re-text-secondary">
                    Six core capabilities, one unified API. The building blocks for FSMA 204 traceability workflows, supplier readiness, and FDA response prep.
                </p>
                <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
                    {capabilities.map((cap) => (
                        <article key={cap.title} className={cardVariants({ padding: "spacious", className: "flex flex-col" })}>
                            <div className="mb-4 flex items-center gap-3">
                                <cap.Icon className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <h3 className="text-subheading text-re-text-primary">{cap.title}</h3>
                            </div>
                            <p className="text-ui leading-relaxed text-re-text-secondary">{cap.description}</p>
                        </article>
                    ))}
                </div>
            </Container>

            {/* ═══ SDKs Coming Soon ═══ */}
            <section className="border-t border-re-border-subtle">
                <Container width="tool" className="py-16 text-center">
                    <h2 className="mb-3 font-display text-heading-lg text-re-text-primary">SDKs Coming Soon</h2>
                    <p className="mx-auto mb-6 max-w-[60ch] text-ui text-re-text-secondary">
                        Official client libraries for Python, Node.js, and Go are planned.
                        In the meantime, use our REST API directly. All endpoints accept and return JSON.
                    </p>
                    <Button asChild variant="secondary" size="lg">
                        <Link href="/docs/sdks" className="no-underline">
                            Get Notified When SDKs Launch
                        </Link>
                    </Button>
                </Container>
            </section>

            {/* ═══ RATE LIMITS ═══ */}
            <section className="border-t border-re-border-subtle">
                <Container width="tool" className="py-16">
                    <h2 className="mb-3 text-center font-display text-heading-lg text-re-text-primary">Rate limits</h2>
                    <p className="mx-auto mb-6 max-w-[60ch] text-center text-ui text-re-text-secondary">
                        API requests are rate limited.
                        If you hit a limit, the API returns a <code className="font-mono text-[0.8125rem] text-re-text-primary">429</code>. Stop sending for 60 seconds, then retry.
                    </p>
                    <p className="mx-auto max-w-[60ch] text-center text-ui text-re-text-secondary">
                        Need higher throughput?{' '}
                        <Link href="/contact" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">Contact us</Link> to discuss your requirements.
                    </p>
                </Container>
            </section>

            {/* ═══ CTA ═══ */}
            <section className="border-t border-re-border-subtle bg-re-surface-inset">
                <Container width="prose" className="py-16 text-center">
                    <Badge tone="brand" className="mb-4">
                        Ready to integrate?
                    </Badge>
                    <h2 className="mb-2 font-display text-heading-lg text-re-text-primary">Start building on RegEngine</h2>
                    <p className="mx-auto mb-6 max-w-[60ch] text-ui text-re-text-secondary">
                        Request preview access and we&apos;ll scope your first integration path, credentials, and payload contract with you.
                    </p>
                    <div className="flex flex-wrap justify-center gap-3">
                        <Button asChild size="lg">
                            <Link href="/contact" className="no-underline">
                                Request Developer Access
                                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/docs/quickstart" className="no-underline">
                                <BookOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                Read the Quickstart
                            </Link>
                        </Button>
                    </div>
                    <p className="mt-6 text-small text-re-text-tertiary">
                        Have a RegEngine workspace?{' '}
                        <Link href="/login" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">
                            Sign in
                        </Link>
                        {' '}&middot;{' '}
                        <Link href="/docs" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">
                            Read the docs
                        </Link>
                    </p>
                </Container>
            </section>
        </div>
    );
}
