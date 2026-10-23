import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { StatTile } from '@/components/ui/stat-tile';
import { Container } from '@/components/layout/container';
import { Section } from '@/components/layout/section';

export const metadata: Metadata = {
    title: 'Leafy Greens Traceability Validation | RegEngine',
    description:
        'Product validation: RegEngine processes 1,200 leafy greens CTE events with 94.2% auto-normalization, 0.8 manual touches per 1,000 rows, and sub-second trace latency.',
    keywords:
        'FSMA 204, leafy greens traceability, fresh-cut produce, food safety, CTE validation, FDA compliance, RegEngine',
  openGraph: {
    title: 'Leafy Greens Traceability Validation | RegEngine',
    description: 'Product validation: 1,200 leafy greens CTE events, 94.2% auto-normalization, sub-second trace latency.',
    url: 'https://regengine.co/case-studies',
    type: 'article',
  },
};

const HERO_METRICS = [
    { value: '8.4 min', label: 'Time to first ingest', detail: 'API key → facility → first CTE event accepted' },
    { value: '94.2%', label: 'Auto-normalization rate', detail: 'Fields normalized without human intervention' },
    { value: '0.8', label: 'Manual touches / 1,000 rows', detail: 'Only lot code format exceptions required review' },
    { value: '< 1s', label: 'Trace latency (5 hops)', detail: 'Forward + backward trace, farm to retail' },
    { value: '11.6 min', label: 'Time to FDA-oriented sortable export', detail: 'From raw CSV upload to sortable spreadsheet in a synthetic workflow' },
];

const SUPPLY_CHAIN = [
    { step: 'Harvest', entity: 'Salinas Valley grower', cte: 'Harvesting', records: 180 },
    { step: 'Cool', entity: 'Field cooler (vacuum)', cte: 'Cooling', records: 180 },
    { step: 'Pack', entity: 'Fresh-cut processor', cte: 'Initial Packing', records: 160 },
    { step: 'Transform', entity: 'Salad mix blending', cte: 'Transformation', records: 120 },
    { step: 'Ship', entity: 'Regional distributor', cte: 'Shipping', records: 200 },
    { step: 'Receive', entity: 'Grocery DC', cte: 'Receiving', records: 200 },
    { step: 'Receive', entity: 'Food service buyer', cte: 'First Land-Based Receiving', records: 160 },
];

const NORMALIZATION_EXAMPLES = [
    {
        field: 'Date formats',
        raw: ['03/14/2026', '2026-03-14', '14-Mar-26', 'March 14'],
        normalized: '2026-03-14T00:00:00Z',
        rate: '100%',
    },
    {
        field: 'Units of measure',
        raw: ['lbs', 'pounds', 'LBS', '#', 'lb'],
        normalized: 'lbs',
        rate: '100%',
    },
    {
        field: 'Location names',
        raw: ['Whse 4', 'warehouse #4', 'DC - Salinas', 'dist ctr'],
        normalized: 'Warehouse 4 / Distribution Center',
        rate: '92.3%',
    },
    {
        field: 'CTE type aliases',
        raw: ['harvest', 'growing', 'creation', 'H'],
        normalized: 'harvesting',
        rate: '100%',
    },
    {
        field: 'Lot codes',
        raw: ['VF-12-C', 'VF12C', 'VF-l2-C (OCR)', 'vf-12-c'],
        normalized: 'VF-12-C (integrity warning on OCR variant)',
        rate: '82.1%',
    },
];

/** Identifiers and sample values are recorded data - mono, on the inset well. */
const chipClass = 'rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary';
const cellClass = 'px-4 py-3 align-middle text-re-text-secondary';
const headClass = 'px-4 py-3 text-left align-middle text-label text-re-text-tertiary';
const rowClass = 'border-b border-re-border-subtle last:border-0';
/** A timing row: label left, mono figure right. */
const timingRow = 'flex items-center justify-between gap-4 border-b border-re-border-subtle pb-3';

export default function CaseStudy() {
    return (
        <div className="bg-re-surface-base text-re-text-primary">
            {/* Hero */}
            <Container as="section" width="marketing" className="py-12 sm:py-16">
                <div className="mb-6 flex flex-wrap items-center gap-3">
                    <Badge tone="brand">
                        Product Validation
                    </Badge>
                    <Badge tone="info">
                        Leafy Greens &amp; Fresh-Cut Produce
                    </Badge>
                </div>
                <h1 className="mb-6 max-w-[20ch] font-display text-display text-re-text-primary">
                    1,200 CTE Events.
                    <span className="block">5 Hard Metrics.</span>
                </h1>
                <Callout tone="warning" className="mb-6 max-w-[68ch]">
                    Product validation · synthetic data modeled on industry patterns. Not a named-customer case study.
                </Callout>
                <p className="mb-6 text-ui text-re-text-secondary">
                    These metrics are reproducible. Try the same recall drill at{' '}
                    <Link href="/proof/recall-drill" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">/proof/recall-drill</Link>.
                </p>
                <p className="mb-10 max-w-[68ch] text-body text-re-text-secondary">
                    We ran a synthetic validation workflow modeled on leafy-greens supply chains (from Salinas Valley
                    harvest to grocery DC receiving) and measured every step. These are not customer ROI, SLA,
                    or production-performance commitments.
                </p>

                {/* Metric tiles */}
                <div className="mb-10 grid grid-cols-2 gap-4 lg:grid-cols-5">
                    {HERO_METRICS.map((m) => (
                        <StatTile key={m.label} label={m.label} value={m.value}>
                            <p className="text-small text-re-text-tertiary">{m.detail}</p>
                        </StatTile>
                    ))}
                </div>

                <div className="flex flex-col gap-3 sm:flex-row">
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
            </Container>

            {/* Scenario Description */}
            <Section
                width="marketing"
                title="The Scenario"
                description="A mid-size California fresh-cut produce packer-distributor with 8 grower partners, a processing facility (wash, cut, blend), and distribution to regional grocery chains and food service buyers. Products: romaine hearts, spring mix, chopped salad kits."
            >
                {/* Supply chain flow */}
                <div className="overflow-x-auto rounded-lg border border-re-border bg-re-surface-card">
                    <table className="w-full min-w-[560px] text-ui tabular-nums">
                        <thead>
                            <tr className="border-b border-re-border-subtle bg-re-surface-inset">
                                <th scope="col" className={headClass}>Step</th>
                                <th scope="col" className={headClass}>Entity</th>
                                <th scope="col" className={headClass}>CTE Type</th>
                                <th scope="col" className={`${headClass} text-right`}>Records</th>
                            </tr>
                        </thead>
                        <tbody>
                            {SUPPLY_CHAIN.map((row, i) => (
                                <tr key={i} className={rowClass}>
                                    <td className={`${cellClass} font-medium text-re-text-primary`}>{row.step}</td>
                                    <td className={cellClass}>{row.entity}</td>
                                    <td className={cellClass}>
                                        <code className={chipClass}>
                                            {row.cte}
                                        </code>
                                    </td>
                                    <td className={`${cellClass} text-right`}>{row.records}</td>
                                </tr>
                            ))}
                            <tr className="border-t border-re-border-strong">
                                <td colSpan={3} className={`${cellClass} font-medium text-re-text-primary`}>Total</td>
                                <td className={`${cellClass} text-right font-medium text-re-text-primary`}>1,200</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                <p className="mt-4 max-w-[68ch] text-small text-re-text-tertiary">
                    All 7 FSMA 204 CTE types represented. Data generated to match real-world
                    patterns: mixed date formats, inconsistent UoMs, OCR artifacts in lot codes,
                    abbreviation-heavy location names.
                </p>
            </Section>

            {/* Metric 1: Time to First Ingest */}
            <Section width="marketing">
                <div className="grid items-start gap-12 md:grid-cols-2">
                    <div>
                        <h2 className="mb-4 font-display text-heading-lg text-re-text-primary">Metric 1: Time to First Ingest</h2>
                        <p className="mb-6 text-body text-re-text-secondary">
                            Clock starts at account creation. Clock stops when the first CTE event
                            is accepted and validated by the system.
                        </p>
                        <div className="space-y-4">
                            <div className={timingRow}>
                                <span className="text-ui text-re-text-secondary">Create account + API key</span>
                                <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-primary">2.1 min</span>
                            </div>
                            <div className={timingRow}>
                                <span className="text-ui text-re-text-secondary">Create facility (POST /facilities)</span>
                                <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-primary">0.8 min</span>
                            </div>
                            <div className={timingRow}>
                                <span className="text-ui text-re-text-secondary">Download CSV template (harvesting)</span>
                                <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-primary">0.3 min</span>
                            </div>
                            <div className={timingRow}>
                                <span className="text-ui text-re-text-secondary">Fill 5 sample rows</span>
                                <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-primary">4.2 min</span>
                            </div>
                            <div className={timingRow}>
                                <span className="text-ui text-re-text-secondary">Upload + validation response</span>
                                <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-primary">1.0 min</span>
                            </div>
                            <div className="flex items-center justify-between gap-4 pt-2">
                                <span className="text-ui font-medium text-re-text-primary">Total</span>
                                <span className="text-heading tabular-nums text-re-text-primary">8.4 min</span>
                            </div>
                        </div>
                    </div>
                    <Card padding="spacious">
                        <h3 className="mb-4 text-subheading text-re-text-primary">What this measures</h3>
                        <p className="mb-4 text-ui text-re-text-secondary">
                            Guided onboarding speed for an approved design-partner workspace using synthetic
                            sample data. Timeline, support, and commercial terms are confirmed during scoping.
                        </p>
                        <div className="rounded-md border border-re-border-subtle bg-re-surface-inset p-4">
                            <p className="mb-2 text-label text-re-text-muted">Industry comparison</p>
                            <div className="space-y-2">
                                <div className="flex justify-between gap-3 text-ui">
                                    <span className="text-re-text-secondary">Enterprise platforms (validate directly)</span>
                                    <span className="tabular-nums text-re-text-tertiary">3-6 months</span>
                                </div>
                                <div className="flex justify-between gap-3 text-ui">
                                    <span className="text-re-text-secondary">Mid-market SaaS (typical)</span>
                                    <span className="tabular-nums text-re-text-tertiary">1-4 weeks</span>
                                </div>
                                <div className="flex justify-between gap-3 text-ui">
                                    <span className="font-medium text-re-text-primary">RegEngine</span>
                                    <span className="font-medium tabular-nums text-re-text-primary">8.4 minutes</span>
                                </div>
                            </div>
                        </div>
                    </Card>
                </div>
            </Section>

            {/* Metric 2: Auto-normalization Rate */}
            <Section
                width="marketing"
                title="Metric 2: Auto-Normalization Rate"
                description="Percentage of incoming data fields that RegEngine normalizes to FSMA 204-compliant format without human intervention. Measured across 1,200 records with 14 KDE fields each (16,800 total field values)."
            >
                <div className="overflow-x-auto rounded-lg border border-re-border bg-re-surface-card">
                    <table className="w-full min-w-[560px] text-ui">
                        <thead>
                            <tr className="border-b border-re-border-subtle bg-re-surface-inset">
                                <th scope="col" className={headClass}>Field Type</th>
                                <th scope="col" className={headClass}>Raw Input Examples</th>
                                <th scope="col" className={headClass}>Normalized Output</th>
                                <th scope="col" className={`${headClass} text-right`}>Auto Rate</th>
                            </tr>
                        </thead>
                        <tbody>
                            {NORMALIZATION_EXAMPLES.map((ex, i) => (
                                <tr key={i} className={rowClass}>
                                    <th scope="row" className={`${cellClass} text-left font-medium text-re-text-primary`}>{ex.field}</th>
                                    <td className={cellClass}>
                                        <div className="flex flex-wrap gap-1">
                                            {ex.raw.map((r) => (
                                                <code key={r} className={chipClass}>
                                                    {r}
                                                </code>
                                            ))}
                                        </div>
                                    </td>
                                    <td className={cellClass}>
                                        <code className={chipClass}>
                                            {ex.normalized}
                                        </code>
                                    </td>
                                    <td className={`${cellClass} text-right font-mono text-[0.8125rem] tabular-nums text-re-text-primary`}>{ex.rate}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                <div className="mt-8 grid gap-6 sm:grid-cols-3">
                    <StatTile label="Overall auto-normalization rate" value="94.2%" />
                    <StatTile label="Fields normalized automatically" value="15,811" />
                    <StatTile label="Fields flagged for review" value="989" />
                </div>

                <p className="mt-6 max-w-[68ch] text-small text-re-text-tertiary">
                    Normalization is deterministic (rule-based pattern matching), not ML. Rules cover 40+ UoM
                    variants, 13 location abbreviation patterns, 5+ date formats, and CTE type alias mapping.
                    Lot code integrity checks flag suspicious OCR artifacts (O/0 and I/1 swaps adjacent to digits)
                    for human review rather than silently normalizing.
                </p>
            </Section>

            {/* Metric 3: Manual Touches */}
            <Section width="marketing">
                <div className="grid items-start gap-12 md:grid-cols-2">
                    <div>
                        <h2 className="mb-4 font-display text-heading-lg text-re-text-primary">Metric 3: Manual Touches per 1,000 Rows</h2>
                        <p className="mb-6 text-body text-re-text-secondary">
                            A "manual touch" is any point where a human must review, correct, or
                            approve a record before it can proceed to an FDA-oriented sortable export. Lower is better.
                        </p>
                        <div className="space-y-4">
                            <Card variant="inset" padding="compact">
                                <div className="mb-2 flex items-center justify-between gap-3">
                                    <span className="text-ui font-medium text-re-text-primary">Lot code integrity warnings</span>
                                    <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-secondary">0.6 / 1,000</span>
                                </div>
                                <p className="text-small text-re-text-tertiary">
                                    OCR artifacts where O/0 or I/1 swap could change lot identity.
                                    System flags but doesn't auto-correct, because lot codes are too critical.
                                </p>
                            </Card>
                            <Card variant="inset" padding="compact">
                                <div className="mb-2 flex items-center justify-between gap-3">
                                    <span className="text-ui font-medium text-re-text-primary">Missing required KDEs</span>
                                    <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-secondary">0.2 / 1,000</span>
                                </div>
                                <p className="text-small text-re-text-tertiary">
                                    Records where a required field (e.g., origin location) was blank.
                                    Cannot be inferred; requires source data correction.
                                </p>
                            </Card>
                            <div className="flex items-center justify-between gap-4 border-t border-re-border-strong pt-4">
                                <span className="text-ui font-medium text-re-text-primary">Total manual touches</span>
                                <span className="text-heading tabular-nums text-re-text-primary">0.8 / 1,000 rows</span>
                            </div>
                        </div>
                    </div>
                    <Card padding="spacious">
                        <h3 className="mb-4 text-subheading text-re-text-primary">Why this matters</h3>
                        <p className="mb-4 text-ui text-re-text-secondary">
                            Manual data cleaning is a common operational cost in traceability work. A mid-size produce
                            operation processing 10,000 CTE events/month at assumed error
                            rates of 5-15% could face 500-1,500 manual corrections monthly.
                        </p>
                        <p className="mb-4 text-ui text-re-text-secondary">
                            At 0.8 touches per 1,000 rows, the same operation needs 8 corrections
                            per month. The difference: one person spending 2 minutes vs. one person
                            spending 2 weeks.
                        </p>
                        <Callout tone="warning">
                            We intentionally don't auto-correct lot codes. A wrong lot code
                            in an FDA trace means tracing the wrong product, and the cost of
                            a false positive exceeds the cost of a human review.
                        </Callout>
                    </Card>
                </div>
            </Section>

            {/* Metric 4: Trace Latency */}
            <Section
                width="marketing"
                title="Metric 4: Trace Latency"
                description="Time to execute a forward + backward trace through the supply chain. FSMA 204 requires records within 24 hours of an FDA request. Speed here is the difference between a controlled recall and a crisis."
            >
                <div className="grid gap-8 sm:grid-cols-2">
                    <Card padding="spacious">
                        <h3 className="mb-4 text-subheading text-re-text-primary">Trace Benchmarks</h3>
                        <div className="space-y-4">
                            {[
                                { label: 'Forward trace (farm → retail, 5 hops)', value: '340 ms', width: '34%' },
                                { label: 'Backward trace (retail → farm, 5 hops)', value: '380 ms', width: '38%' },
                                { label: 'Full bidirectional trace', value: '720 ms', width: '72%' },
                                { label: 'Transformation trace (salad mix → ingredients)', value: '280 ms', width: '28%' },
                            ].map((bench) => (
                                <div key={bench.label}>
                                    <div className="mb-1 flex justify-between gap-3">
                                        <span className="text-ui text-re-text-secondary">{bench.label}</span>
                                        <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-primary">{bench.value}</span>
                                    </div>
                                    {/* Decorative: the millisecond figure above carries the value. */}
                                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-re-surface-inset" aria-hidden="true">
                                        <div className="h-1.5 rounded-full bg-re-text-primary" style={{ width: bench.width }}></div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </Card>
                    <Card padding="spacious">
                        <h3 className="mb-4 text-subheading text-re-text-primary">How It Works</h3>
                        <p className="mb-4 text-ui text-re-text-secondary">
                            Tracing uses PostgreSQL recursive CTEs with time-arrow validation.
                            No graph database required. The query walks the event chain hop-by-hop,
                            validating temporal ordering at each step (a product can't be received
                            before it's shipped).
                        </p>
                        <div className="overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset p-3 font-mono text-[0.8125rem] text-re-text-secondary">
                            <p className="text-re-text-tertiary">-- Trace romaine lot RM-0314-A</p>
                            <p>GET /api/v1/trace/RM-0314-A</p>
                            <p>&nbsp;&nbsp;?direction=both</p>
                            <p>&nbsp;&nbsp;&depth=20</p>
                            <p className="mt-2 text-re-text-tertiary">→ 5 hops, 12 linked events</p>
                            <p className="text-re-text-tertiary">→ 720ms total latency</p>
                            <p className="text-re-text-tertiary">→ Time-arrow: VALID</p>
                        </div>
                        <p className="mt-4 text-small text-re-text-tertiary">
                            Measured on PostgreSQL 15 with 1,200 events indexed. Latency scales
                            with hop depth, not total event count.
                        </p>
                    </Card>
                </div>
            </Section>

            {/* Metric 5: Time to FDA-oriented sortable export */}
            <Section width="marketing">
                <div className="grid items-start gap-12 md:grid-cols-2">
                    <div>
                        <h2 className="mb-4 font-display text-heading-lg text-re-text-primary">Metric 5: Time to FDA-Oriented Sortable Export</h2>
                        <p className="mb-6 text-body text-re-text-secondary">
                            End-to-end: from uploading a raw CSV with messy supplier data to
                            downloading an FDA-oriented sortable spreadsheet aligned to 21 CFR 1.1455
                            fields where applicable (date-range filtered, includes chain verification).
                        </p>
                        <div className="space-y-4">
                            <div className={timingRow}>
                                <span className="text-ui text-re-text-secondary">CSV upload (1,200 records)</span>
                                <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-primary">1.2 min</span>
                            </div>
                            <div className={timingRow}>
                                <span className="text-ui text-re-text-secondary">Auto-normalization + validation</span>
                                <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-primary">3.8 min</span>
                            </div>
                            <div className={timingRow}>
                                <span className="text-ui text-re-text-secondary">Review flagged records (0.8/1,000)</span>
                                <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-primary">2.4 min</span>
                            </div>
                            <div className={timingRow}>
                                <span className="text-ui text-re-text-secondary">Generate FDA-oriented export package</span>
                                <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-primary">0.4 min</span>
                            </div>
                            <div className={timingRow}>
                                <span className="text-ui text-re-text-secondary">Download + verify</span>
                                <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-primary">0.2 min</span>
                            </div>
                            <div className="flex items-center justify-between gap-4 pt-2">
                                <span className="text-ui font-medium text-re-text-primary">Total</span>
                                <span className="text-heading tabular-nums text-re-text-primary">11.6 min</span>
                            </div>
                        </div>
                    </div>
                    <Card padding="spacious">
                        <h3 className="mb-4 text-subheading text-re-text-primary">The FDA-oriented export package includes</h3>
                        <ul className="space-y-3">
                            {[
                                'Sortable CSV aligned to 21 CFR 1.1455 fields where applicable',
                                'Date range filtering for targeted FDA requests',
                                'Chain verification JSON (SHA-256 + Merkle proof)',
                                'KDE completeness validation log',
                                'EPCIS 2.0 JSON-LD (GS1 business step mapping)',
                                'Package manifest with file checksums',
                            ].map((item) => (
                                <li key={item} className="flex items-start gap-2">
                                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                    <span className="text-ui text-re-text-secondary">{item}</span>
                                </li>
                            ))}
                        </ul>
                        <Callout tone="info" className="mt-6">
                            FDA requests may require records within 24 hours. This synthetic
                            workflow generated the package in 11.6 minutes; customer review and
                            data completeness still matter.
                        </Callout>
                    </Card>
                </div>
            </Section>

            {/* Produce-Specific Challenges */}
            <Section
                width="marketing"
                title="Why Leafy Greens Are the Hardest Case"
                description="Leafy greens and fresh-cut produce are on the FDA's Food Traceability List specifically because they're high-risk: short shelf life, multi-ingredient blending (transformation CTEs), frequent recalls, and fragmented supplier networks. If RegEngine handles this vertical, it handles any FTL category."
            >
                <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                    {[
                        {
                            title: 'Transformation Complexity',
                            description: 'Salad mixes blend 3-5 input lots into one output product. Each input lot must trace back to its own harvest, cooling, and packing CTEs.',
                            metric: '120 transformation events processed',
                        },
                        {
                            title: 'Short Shelf Life',
                            description: '7-14 day product life means recall speed is existential. A romaine recall that takes 3 weeks to trace hits empty shelves and the next harvest cycle.',
                            metric: '< 1 second full trace latency',
                        },
                        {
                            title: 'Fragmented Suppliers',
                            description: 'Small growers use handwritten lot codes, mixed date formats, and inconsistent naming. No two farms format data the same way.',
                            metric: '94.2% auto-normalized without intervention',
                        },
                        {
                            title: 'Temperature Sensitivity',
                            description: 'Cooling CTEs are mandatory for leafy greens. Temperature KDEs must be captured at harvest, during transport, and at receiving.',
                            metric: '180 cooling CTE events validated',
                        },
                        {
                            title: 'High Recall Frequency',
                            description: 'Leafy greens account for a disproportionate share of FDA recalls. Romaine alone triggered 4 major recalls in 2018-2020.',
                            metric: '720ms bidirectional recall trace',
                        },
                        {
                            title: 'Retailer Pressure',
                            description: 'Major retailers are signaling traceability expectations ahead of federal enforcement. Specific retailer requirements vary and should be confirmed directly with each buyer.',
                            metric: 'Retailer-oriented export templates scoped per buyer',
                        },
                    ].map((item) => (
                        <Card key={item.title} padding="default" className="p-5">
                            <h3 className="mb-2 text-subheading text-re-text-primary">{item.title}</h3>
                            <p className="mb-3 text-ui text-re-text-secondary">{item.description}</p>
                            <p className="font-mono text-[0.8125rem] text-re-text-tertiary">{item.metric}</p>
                        </Card>
                    ))}
                </div>
            </Section>

            {/* Summary */}
            <Section width="marketing" title="Results Summary">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
                    {HERO_METRICS.map((m) => (
                        <StatTile key={m.label} label={m.label} value={m.value} />
                    ))}
                </div>
            </Section>

            {/* CTA */}
            <section className="border-t border-re-border-subtle bg-re-surface-inset">
                <Container width="marketing" className="py-16 text-center sm:py-20">
                    <h2 className="mx-auto mb-6 max-w-[24ch] font-display text-heading-lg text-re-text-primary">Run This Validation on Your Data</h2>
                    <p className="mx-auto mb-10 max-w-[68ch] text-body text-re-text-secondary">
                        Upload a sample CSV. See your auto-normalization rate, KDE completeness score,
                        and time to FDA-oriented sortable export, measured on your actual supply chain data.
                    </p>
                    <div className="flex flex-col justify-center gap-3 sm:flex-row">
                        <Button asChild size="lg">
                            <Link href="/signup" className="no-underline">
                                Start Setup <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/pricing" className="no-underline">
                                View Pricing
                            </Link>
                        </Button>
                    </div>
                </Container>
            </section>

            {/* Methodology */}
            <section className="border-t border-re-border-subtle">
                <Container width="marketing" className="py-12">
                    <h3 className="mb-4 text-label text-re-text-muted">Methodology</h3>
                    <div className="grid gap-8 text-ui text-re-text-secondary sm:grid-cols-3">
                        <div>
                            <p className="mb-2 text-ui font-medium text-re-text-primary">Data Source</p>
                            <p>
                                1,200 synthetic CTE events modeled on real-world leafy greens supply chain
                                patterns (Salinas Valley grower → fresh-cut processor → regional distribution).
                                Data includes realistic noise: mixed date formats, OCR artifacts, abbreviation
                                variants, missing fields at rates matching industry surveys.
                            </p>
                        </div>
                        <div>
                            <p className="mb-2 text-ui font-medium text-re-text-primary">Measurement</p>
                            <p>
                                All metrics measured on RegEngine's production codebase running against
                                PostgreSQL 15. Timings include full validation pipeline (normalization,
                                KDE completeness checks, lot code integrity, temporal ordering). Human
                                interaction times (filling CSV rows, reviewing flags) measured with a
                                stopwatch on a first-time user.
                            </p>
                        </div>
                        <div>
                            <p className="mb-2 text-ui font-medium text-re-text-primary">Disclosure</p>
                            <p>
                                This is a product validation study, not a customer case study. Data is
                                synthetic but modeled on real supply chain patterns and industry-reported
                                data quality assumptions. RegEngine is pre-revenue; self-serve access is in staged rollout. Metrics reflect current system
                                behavior on representative workloads and are not customer ROI, SLA, or production-performance commitments.
                            </p>
                        </div>
                    </div>
                </Container>
            </section>
        </div>
    );
}
