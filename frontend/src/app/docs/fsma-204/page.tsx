import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'FSMA 204 Developer Integration Guide | RegEngine',
  description: 'Build your FSMA 204 traceability program on RegEngine APIs. CTEs, KDEs, FDA Request Mode, supply chain tracing, and hash-manifest verification.',
  openGraph: {
    title: 'FSMA 204 Developer Integration Guide | RegEngine',
    description: 'Build your FSMA 204 traceability program on RegEngine APIs: CTEs, KDEs, FDA Request Mode, and hash-manifest verification.',
    url: 'https://regengine.co/docs/fsma-204',
    type: 'article',
  },
};
import { ArrowLeft, CheckCircle, Clock, Zap, Shield, ExternalLink } from 'lucide-react';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { INGEST_CURL_SAMPLE, INGEST_ENV_SETUP, INGEST_RESPONSE_SAMPLE } from '@/lib/api-samples/ingest-samples';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';

const CITATION =
    'align-super text-small text-re-text-muted transition-colors duration-120 hover:text-re-brand motion-reduce:transition-none';

const CHROME_LINK =
    'inline-flex items-center gap-2 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none';

const PROSE_LINK =
    'text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand';

const FACTS = [
    { icon: Clock, label: '24-hour sortable-spreadsheet obligation' },
    { icon: Shield, label: 'Aligned to 21 CFR § 1.1455(c)' },
    { icon: CheckCircle, label: 'FDA enforcement not before July 20, 2028' },
];

const CTE_ROWS = [
    { cte: 'Harvesting', event: 'harvesting', kdes: 'Location, Harvest Date, Lot Code, Product' },
    { cte: 'Cooling', event: 'cooling', kdes: 'Location, Cooling Date, Lot Code, Product' },
    { cte: 'Initial Packing', event: 'initial_packing', kdes: 'Location, Pack Date, TLC, Quantity' },
    { cte: 'First Land-Based Receiving', event: 'first_land_based_receiving', kdes: 'Location, Landing Date, TLC, Quantity, Vessel Source' },
    { cte: 'Shipping', event: 'shipping', kdes: 'Ship From/To, TLC, Carrier, Date' },
    { cte: 'Receiving', event: 'receiving', kdes: 'Location, TLC, Source, Quantity, Date' },
    { cte: 'Transformation', event: 'transformation', kdes: 'Input TLCs, Output TLC, Date, Location' },
];

const RELATED_ENDPOINTS = [
    { path: 'POST /api/v1/webhooks/ingest', desc: 'Create compliance events' },
    { path: 'GET /api/v1/fda/export/recall', desc: 'Generate §1.1455-formatted sortable spreadsheet' },
    { path: 'GET /api/v1/fda/trace/{tlc}', desc: 'Upstream sources and downstream products for a lot' },
    { path: 'GET /api/v1/records', desc: 'List stored events for your workspace' },
];

const RECALL_SNIPPET = `curl -G https://regengine.co/api/v1/fda/export/recall \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -d "tenant_id=YOUR_WORKSPACE_ID" \\
  -d "tlc=<the lot code under recall>" \\
  -o fda_response.csv`;

/** A labelled code well — SPEC §5.1: code sits one surface step below the page. */
function CodePanel({ label, code }: { label: string; code: string }) {
    return (
        <Card variant="inset" className="overflow-hidden">
            <div className="border-b border-re-border-subtle px-4 py-2">
                <span className="font-mono text-label text-re-text-muted">{label}</span>
            </div>
            <pre className="m-0 overflow-x-auto p-4 font-mono text-[0.8125rem] leading-6 text-re-text-primary">
                <code>{code}</code>
            </pre>
        </Card>
    );
}

export default function FSMA204GuidePage() {
    return (
        <>
            <PageHeader
                breadcrumbs={
                    <Link href="/docs" className={CHROME_LINK}>
                        <ArrowLeft aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
                        Back to Docs
                    </Link>
                }
                eyebrow="Developer Guide"
                title="FSMA 204 Integration Guide"
                description="Build your FSMA 204 traceability program on RegEngine's Food Safety APIs"
            />

            {/* Proof row — mono facts separated by rules, not cards (SPEC §6). */}
            <ul className="mb-6 flex list-none flex-col gap-3 border-y border-re-border-subtle py-4 sm:flex-row sm:flex-wrap sm:gap-x-8">
                {FACTS.map((fact) => (
                    <li key={fact.label} className="flex items-center gap-2">
                        <fact.icon aria-hidden="true" strokeWidth={1.75} className="h-4 w-4 shrink-0 text-re-text-muted" />
                        <span className="text-ui text-re-text-secondary">{fact.label}</span>
                    </li>
                ))}
            </ul>

            {/* Non-technical redirect */}
            <div className="mb-8 flex flex-wrap items-center gap-3">
                <span className="text-ui text-re-text-secondary">Not a developer?</span>
                <Link href="/fsma-204" className={PROSE_LINK}>
                    Read the plain-English FSMA 204 guide →
                </Link>
            </div>

            <div className="space-y-10">
                {/* What is FSMA 204? */}
                <section>
                    <h2 className="mb-3 text-heading text-re-text-primary">What is FSMA 204?</h2>
                    <p className="mb-4 text-body text-re-text-secondary">
                        The FDA Food Safety Modernization Act Section 204 (FSMA 204) requires companies handling foods on
                        the <strong className="font-medium text-re-text-primary">Food Traceability List (FTL)</strong> <a href="https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list" target="_blank" rel="noopener noreferrer" className={CITATION} title="FDA Food Traceability List">[FDA]</a> to maintain standardized
                        traceability records <a href="https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1320" target="_blank" rel="noopener noreferrer" className={CITATION} title="21 CFR § 1.1320-1.1350 Requirement">[FDA]</a>. In a recall, you must provide the FDA with a sortable spreadsheet within
                        <strong className="font-medium text-re-text-primary"> 24 hours</strong> <a href="https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455#p-1.1455(c)" target="_blank" rel="noopener noreferrer" className={CITATION} title="21 CFR § 1.1455(c) Requirement">[FDA]</a>.
                    </p>

                    <Callout tone="warning" title="Enforcement Delayed">
                        <p className="text-ui text-re-text-secondary">
                            The compliance date under the rule remains January 20, 2026 (87 FR 70910). The 30-month extension is only proposed (90 FR 38084).
                            FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive.
                            RegEngine tracks FDA timing changes so your team isn&apos;t relying on stale dates.
                        </p>
                    </Callout>
                </section>

                {/* Quick Start */}
                <section>
                    <h2 className="mb-3 text-heading text-re-text-primary">Quick Start: Record a CTE</h2>
                    <p className="mb-4 text-body text-re-text-secondary">
                        Critical Tracking Events (CTEs) are the building blocks of FSMA 204 compliance.
                        Here&apos;s how to record a receiving event. RegEngine issues the API key and signing secret on request;
                        the{' '}
                        <Link href="/docs/quickstart" className={PROSE_LINK}>Quickstart</Link>
                        {' '}explains the signature, the idempotency key and the test workspace, and{' '}
                        <Link href="/docs/api#required-kdes" className={PROSE_LINK}>the API reference</Link>
                        {' '}lists the required KDEs for every event type.
                    </p>

                    <div className="space-y-4">
                        <CodePanel label="Environment" code={INGEST_ENV_SETUP} />
                        <CodePanel label="POST /api/v1/webhooks/ingest" code={INGEST_CURL_SAMPLE} />
                        <CodePanel label="200 OK" code={INGEST_RESPONSE_SAMPLE} />
                    </div>
                </section>

                {/* CTEs and KDEs */}
                <section>
                    <h2 className="mb-3 text-heading text-re-text-primary">Critical Tracking Events (CTEs)</h2>
                    <p className="mb-4 text-body text-re-text-secondary">
                        FSMA 204 defines specific events that must be recorded at each point in the supply chain:
                    </p>

                    <Card className="overflow-hidden">
                        <Table className="min-w-[34rem]">
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-[13rem]">CTE</TableHead>
                                    <TableHead className="w-[14rem]">event_type</TableHead>
                                    <TableHead>Required KDEs</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {CTE_ROWS.map((row) => (
                                    <TableRow key={row.event}>
                                        <TableCell>{row.cte}</TableCell>
                                        <TableCell>
                                            <code className="rounded-sm border border-re-border-subtle bg-re-surface-inset px-2 py-1 font-mono text-[0.8125rem] text-re-text-primary">
                                                {row.event}
                                            </code>
                                        </TableCell>
                                        <TableCell>{row.kdes}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </Card>
                </section>

                {/* FDA Request Mode */}
                <section>
                    <h2 className="mb-3 text-heading text-re-text-primary">FDA Request Mode</h2>
                    <p className="mb-4 text-body text-re-text-secondary">
                        When the FDA requests traceability data during a recall, you have <strong className="font-medium text-re-text-primary">24 hours</strong> <a href="https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455#p-1.1455(c)" target="_blank" rel="noopener noreferrer" className={CITATION} title="21 CFR § 1.1455(c) Requirement">[FDA]</a> to
                        provide an electronic sortable spreadsheet per 21 CFR 1.1455(c). RegEngine generates this with one API call
                        (the <code className="font-mono text-[0.8125rem] text-re-text-primary">fda.export</code> scope and an active subscription are required):
                    </p>

                    <CodePanel label="GET /api/v1/fda/export/recall" code={RECALL_SNIPPET} />

                    <p className="mb-4 mt-4 text-body text-re-text-secondary">
                        The export includes traceability fields such as the following; FDA does not mandate this particular column layout:
                    </p>

                    <Card variant="inset">
                        <div className="overflow-x-auto p-4">
                            <code className="font-mono text-[0.8125rem] leading-6 text-re-text-secondary">Traceability Lot Code, Event Type (CTE), Product Description, Quantity, Unit of Measure, Location Description, Location Identifier (GLN), Date, Time, Reference Document Type, Reference Document Number</code>
                        </div>
                    </Card>
                </section>

                {/* Supply Chain Tracing */}
                <section>
                    <h2 className="mb-3 text-heading text-re-text-primary">Supply Chain Tracing</h2>
                    <p className="mb-4 text-body text-re-text-secondary">
                        RegEngine performs graph-based tracing over your event data to trace products forward and backward through your supply chain:
                    </p>

                    <CodePanel
                        label="Trace a lot (where did it come from, where did it go?)"
                        code={`curl -G https://regengine.co/api/v1/fda/trace/<the-lot-code> \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -d "tenant_id=YOUR_WORKSPACE_ID"`}
                    />
                </section>

                {/* Verify Don't Trust */}
                <section>
                    <h2 className="mb-3 text-heading text-re-text-primary">Verify, Don&apos;t Trust</h2>
                    <p className="text-body text-re-text-secondary">
                        Ingested events are SHA-256 hashed and chain-linked, and export bundles ship with a
                        timestamped manifest. You can verify a downloaded bundle out-of-band via{' '}
                        <Link href="/verify" className={PROSE_LINK}>/verify</Link>.
                    </p>
                </section>

                {/* API Reference Links */}
                <section>
                    <h2 className="mb-3 text-heading text-re-text-primary">Related Endpoints</h2>

                    <Card className="overflow-hidden">
                        <ul className="list-none p-0">
                            {RELATED_ENDPOINTS.map((ep) => (
                                <li
                                    key={ep.path}
                                    className="flex flex-wrap items-center justify-between gap-3 border-b border-re-border-subtle px-4 py-3 last:border-0"
                                >
                                    <code className="font-mono text-[0.8125rem] text-re-text-primary">{ep.path}</code>
                                    <span className="text-small text-re-text-tertiary">{ep.desc}</span>
                                </li>
                            ))}
                        </ul>
                    </Card>
                </section>

                {/* Next Steps */}
                <Card padding="spacious">
                    <h3 className="mb-4 text-subheading text-re-text-primary">Next Steps</h3>
                    <div className="flex flex-wrap gap-3">
                        <Button asChild variant="primary" size="lg">
                            <Link href="/contact" className="no-underline">
                                <Zap aria-hidden="true" strokeWidth={1.75} />
                                Request Developer Access
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/docs/api" className="no-underline">
                                Full API Reference →
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/tools/ftl-checker" className="no-underline">
                                <ExternalLink aria-hidden="true" strokeWidth={1.75} />
                                FTL Checker Tool
                            </Link>
                        </Button>
                    </div>
                </Card>
            </div>
        </>
    );
}
