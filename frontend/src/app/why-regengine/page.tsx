import type { Metadata } from 'next';
import Link from 'next/link';
import {
    Check,
    X,
    Zap,
    Code2,
    DollarSign,
    Lightbulb,
    Lock,
    CheckCircle,
    AlertCircle,
    ArrowRight,
    Workflow,
} from 'lucide-react';
import { Container } from '@/components/layout/container';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

export const metadata: Metadata = {
    title: 'Why RegEngine | FSMA 204 Compliance, API-First',
    description: 'API-first architecture, published pricing, and a self-serve path to your first FSMA 204 export. See how RegEngine compares to Trustwell, SafetyChain, and ReposiTrak.',
    openGraph: {
        title: 'Why RegEngine | FSMA 204 Compliance Built Different',
        description: 'API-first, transparent pricing, and a self-serve path to a first FSMA 204 export in days. See how RegEngine outpaces Trustwell, SafetyChain, and legacy competitors.',
        url: 'https://regengine.co/why-regengine',
        type: 'website',
    },
};

interface ComparisonRow {
    feature: string;
    regengine: boolean | string;
    trustwell: boolean | string;
    safetychain: boolean | string;
    repositrak: boolean | string;
}

const COMPARISON_DATA: ComparisonRow[] = [
    {
        feature: 'REST API + Webhooks',
        regengine: true,
        trustwell: false,
        safetychain: false,
        repositrak: false,
    },
    {
        feature: 'Transparent, Published Pricing',
        regengine: 'List price from $849/mo (partner rates from $425/mo)',
        trustwell: 'Contact sales',
        safetychain: 'Contact sales',
        repositrak: 'Contact sales',
    },
    {
        feature: 'Time to first export',
        regengine: 'Days (self-serve)',
        trustwell: 'Sales-led implementation',
        safetychain: 'Sales-led implementation',
        repositrak: 'Retailer-coordinated',
    },
    {
        feature: 'All 7 FSMA 204 CTE Types',
        regengine: 'Full coverage',
        trustwell: 'Verify with vendor',
        safetychain: 'Verify with vendor',
        repositrak: 'Verify with vendor',
    },
    {
        feature: 'EPCIS 2.0 Native',
        regengine: true,
        trustwell: 'Verify with vendor',
        safetychain: 'Verify with vendor',
        repositrak: 'Verify with vendor',
    },
    {
        feature: 'CSV Import + Mapping',
        regengine: true,
        trustwell: true,
        safetychain: true,
        repositrak: true,
    },
    {
        feature: 'Works with Existing ERP/WMS',
        regengine: 'By design',
        trustwell: 'Verify with vendor',
        safetychain: 'Verify with vendor',
        repositrak: 'Verify with vendor',
    },
    {
        feature: 'Self-Serve Onboarding',
        regengine: true,
        trustwell: 'Sales-led',
        safetychain: 'Sales-led',
        repositrak: 'Retailer-mediated',
    },
    {
        feature: 'Per-CTE KDE Validation',
        regengine: true,
        trustwell: 'Verify with vendor',
        safetychain: 'Verify with vendor',
        repositrak: 'Verify with vendor',
    },
    {
    feature: 'FDA-Oriented Sortable Export',
        regengine: true,
        trustwell: true,
        safetychain: true,
        repositrak: true,
    },
    {
        feature: 'Recall Drill Workflows',
        regengine: true,
        trustwell: true,
        safetychain: true,
        repositrak: false,
    },
    {
        feature: 'No Multi-Year Lock-In',
        regengine: true,
        trustwell: false,
        safetychain: false,
        repositrak: false,
    },
];

const DIFFERENTIATORS = [
    {
        icon: Code2,
        title: 'API-First Architecture',
        description:
            'REST APIs, webhooks, and CSV templates. Integrate RegEngine with your existing ERP, WMS, or custom systems. No rip-and-replace required.',
        detail: 'Technical teams can be live in hours. Sales ops teams use our CSV templates. Everyone gets FSMA 204 compliance their way.',
    },
    {
        icon: DollarSign,
        title: 'Transparent Pricing',
        description:
            'No hidden sales calls. Plans from $425/mo (billed annually) for Founding Design Partners. Pricing is published — no "contact sales" required.',
        detail: 'Compare directly to competitors who make you "contact sales." We believe pricing transparency builds trust and moves faster.',
    },
    {
        icon: Zap,
        title: 'Self-serve, days not months',
        description:
            'Get from signup to a first FSMA 204 export in days. CSV upload or API payload → validation → export. No 3–6 month enterprise implementation.',
        detail: 'Major retailers and FDA enforcement deadlines arrive on calendar dates; teams ship sooner when the platform is self-serve.',
    },
    {
        icon: Lock,
        title: 'Full CTE/KDE Coverage',
        description:
            'All 7 FSMA 204 CTE types. Per-CTE KDE validation (not batch). Incomplete CTEs are a common gap teams discover during recall drills.',
        detail: 'Every field in every CTE type is validated individually so gaps are visible before you submit.',
    },
    {
        icon: Workflow,
        title: 'EPCIS 2.0 Native',
        description:
            "EPCIS 2.0 support for trading-partner interoperability. Verify each enabled workflow against your retailer and buyer requirements.",
        detail: 'We started on EPCIS 2.0; verify EPCIS coverage with each vendor for your stack.',
    },
    {
        icon: CheckCircle,
        title: 'Built for SMBs',
        description:
            'Not enterprise-only. Small produce distributors, regional suppliers, emerging brands. Self-serve signup, no minimum spend.',
        detail: 'You don\'t need a 50-person implementation team. You need FSMA 204 compliance fast, cheaply, and without bureaucracy.',
    },
];

export default function WhyRegEnginePage() {
    return (
        <main className="min-h-screen bg-re-surface-base">
            {/* Hero Section */}
            <section className="border-b border-re-border-subtle py-16 sm:py-20">
                <Container width="marketing">
                    <div className="inline-flex items-center gap-2 mb-6">
                        <Badge>
                            Built for FSMA 204
                        </Badge>
                    </div>
                    <h1 className="mb-6 max-w-[20ch] font-display text-display text-re-text-primary">
                        FSMA 204 Compliance,{' '}
                        <span>
                            Built for You
                        </span>
                    </h1>
                    <p className="mb-8 max-w-[68ch] text-body text-re-text-secondary">
                        RegEngine pairs an API-first architecture with published pricing and a self-serve onboarding path designed to get your first FSMA 204 export ready for review in days, not months.
                    </p>
                    <div className="flex flex-col gap-3 sm:flex-row">
                        <Button asChild size="lg">
                            <Link href="/signup">
                                Start Setup
                                <ArrowRight className="ml-2 h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/pricing">
                                View Pricing
                            </Link>
                        </Button>
                    </div>
                </Container>
            </section>

            {/* Differentiators Grid */}
            <section className="border-b border-re-border-subtle py-16 sm:py-20">
                <Container width="marketing">
                    <div className="mb-10 max-w-[68ch]">
                        <h2 className="mb-3 font-display text-heading-lg text-re-text-primary">
                            Six Reasons Teams Choose RegEngine
                        </h2>
                        <p className="text-body text-re-text-secondary">
                            We built RegEngine for technical teams, ops managers, and founders who need compliance fast without compromise.
                        </p>
                    </div>

                    <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
                        {DIFFERENTIATORS.map((item, idx) => {
                            const Icon = item.icon;
                            return (
                                <Card key={idx} variant="interactive" padding="compact">
                                    <div className="flex items-start gap-3">
                                        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <div className="flex-1">
                                            <h3 className="mb-2 text-subheading text-re-text-primary">
                                                {item.title}
                                            </h3>
                                            <p className="mb-3 text-ui text-re-text-secondary">
                                                {item.description}
                                            </p>
                                            <p className="text-small text-re-text-tertiary">
                                                {item.detail}
                                            </p>
                                        </div>
                                    </div>
                                </Card>
                            );
                        })}
                    </div>
                </Container>
            </section>

            {/* Comparison Section */}
            <section className="border-b border-re-border-subtle py-16 sm:py-20">
                <Container width="marketing">
                    <div className="mb-10 max-w-[68ch]">
                        <h2 className="mb-3 font-display text-heading-lg text-re-text-primary">
                            Feature-by-Feature Comparison
                        </h2>
                        <p className="text-body text-re-text-secondary">
                            See how RegEngine stacks up against the industry standard and legacy competitors.
                        </p>
                    </div>

                    <Table className="min-w-[720px]">
                        <TableHeader>
                            <TableRow>
                                <TableHead>
                                    Feature
                                </TableHead>
                                <TableHead className="text-center">
                                    RegEngine
                                </TableHead>
                                <TableHead className="text-center">
                                    Trustwell
                                </TableHead>
                                <TableHead className="text-center">
                                    SafetyChain
                                </TableHead>
                                <TableHead className="text-center">
                                    ReposiTrak
                                </TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                                {COMPARISON_DATA.map((row, idx) => (
                                    <TableRow key={idx}>
                                        <TableCell>
                                            {row.feature}
                                        </TableCell>
                                        <TableCell className="text-center">
                                            {typeof row.regengine === 'boolean' ? (
                                                row.regengine ? (
                                                    <>
                                                        <Check className="mx-auto h-4 w-4 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                                                        <span className="sr-only">Yes</span>
                                                    </>
                                                ) : (
                                                    <>
                                                        <X className="mx-auto h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                        <span className="sr-only">No</span>
                                                    </>
                                                )
                                            ) : (
                                                <span className="text-small text-re-text-tertiary">
                                                    {row.regengine}
                                                </span>
                                            )}
                                        </TableCell>
                                        <TableCell className="text-center">
                                            {typeof row.trustwell === 'boolean' ? (
                                                row.trustwell ? (
                                                    <>
                                                        <Check className="mx-auto h-4 w-4 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                                                        <span className="sr-only">Yes</span>
                                                    </>
                                                ) : (
                                                    <>
                                                        <X className="mx-auto h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                        <span className="sr-only">No</span>
                                                    </>
                                                )
                                            ) : (
                                                <span className="text-small text-re-text-tertiary">
                                                    {row.trustwell}
                                                </span>
                                            )}
                                        </TableCell>
                                        <TableCell className="text-center">
                                            {typeof row.safetychain === 'boolean' ? (
                                                row.safetychain ? (
                                                    <>
                                                        <Check className="mx-auto h-4 w-4 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                                                        <span className="sr-only">Yes</span>
                                                    </>
                                                ) : (
                                                    <>
                                                        <X className="mx-auto h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                        <span className="sr-only">No</span>
                                                    </>
                                                )
                                            ) : (
                                                <span className="text-small text-re-text-tertiary">
                                                    {row.safetychain}
                                                </span>
                                            )}
                                        </TableCell>
                                        <TableCell className="text-center">
                                            {typeof row.repositrak === 'boolean' ? (
                                                row.repositrak ? (
                                                    <>
                                                        <Check className="mx-auto h-4 w-4 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                                                        <span className="sr-only">Yes</span>
                                                    </>
                                                ) : (
                                                    <>
                                                        <X className="mx-auto h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                        <span className="sr-only">No</span>
                                                    </>
                                                )
                                            ) : (
                                                <span className="text-small text-re-text-tertiary">
                                                    {row.repositrak}
                                                </span>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                ))}
                        </TableBody>
                    </Table>

                    <Callout tone="info" className="mt-8">
                        <p>
                            <strong>Note:</strong> Comparison data is based on public pricing and vendor documentation as of April 2026. Competitor features change; if you spot an error, email{' '}
                            <a
                                href="mailto:support@regengine.co"
                                className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                            >
                                support@regengine.co
                            </a>
                            .
                        </p>
                    </Callout>
                </Container>
            </section>

            {/* Detailed Differentiator Sections */}
            <section className="border-b border-re-border-subtle py-16 sm:py-20">
                <Container width="marketing" className="space-y-16">
                    {/* API-First */}
                    <div className="grid items-center gap-8 md:grid-cols-2">
                        <div>
                            <h3 className="mb-4 font-display text-heading-lg text-re-text-primary">
                                API-First, Not UI-Only
                            </h3>
                            <p className="mb-4 max-w-[68ch] text-body text-re-text-secondary">
                                Every feature in RegEngine has an API. REST endpoints. Webhooks for real-time events. CSV templates for ops teams. Your developers can integrate in hours, not months.
                            </p>
                            <p className="mb-6 max-w-[68ch] text-ui text-re-text-tertiary">
                                RegEngine started with APIs and added the dashboard on top, so every dashboard action is reachable programmatically. Verify API surface depth with each vendor for your stack.
                            </p>
                            <ul className="space-y-2">
                                {[
                                    'Full REST API for CTEs, suppliers, compliance status',
                                    'Event webhooks for recall triggers and compliance alerts',
                                    'CSV import with smart field mapping',
                                    'Native integrations with Shopify, WooCommerce (coming soon)',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-3 text-ui text-re-text-secondary">
                                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                        <Card padding="spacious" className="hidden md:block">
                            <code className="block font-mono text-small leading-relaxed text-re-text-secondary">
                                {`POST /api/ctes
Content-Type: application/json

{
  "traceability_lot_code": "LOT-2026-001",
  "product": "Organic spinach",
  "supplier_gln": "5012345678909",
  "received_date": "2026-04-05",
  "location_gln": "5012345678909"
}

HTTP 201
{
  "cte_id": "cte_abc123def456",
  "status": "validated",
  "missing_kdes": []
}`}
                            </code>
                        </Card>
                    </div>

                    {/* Pricing */}
                    <div className="grid items-center gap-8 md:grid-cols-2">
                        <Card padding="spacious" className="order-2 hidden md:order-1 md:block">
                            <div className="space-y-4">
                                <Card variant="inset" padding="compact">
                                    <p className="mb-1 font-mono text-label uppercase text-re-text-muted">Base Plan</p>
                                    <p className="text-title tabular-nums text-re-text-primary">$425/mo <span className="text-ui font-normal text-re-text-tertiary line-through">$849/mo</span></p>
                                    <p className="mt-2 text-small text-re-text-tertiary">Founding design partner rate, billed annually ($499/mo monthly) • 1 facility • 500 CTEs/mo</p>
                                </Card>
                                <Card variant="inset" padding="compact">
                                    <p className="mb-1 font-mono text-label uppercase text-re-text-muted">Standard Plan</p>
                                    <p className="text-title tabular-nums text-re-text-primary">$549/mo <span className="text-ui font-normal text-re-text-tertiary line-through">$1,099/mo</span></p>
                                    <p className="mt-2 text-small text-re-text-tertiary">Founding design partner rate, billed annually ($649/mo monthly) • 2–3 facilities • Unlimited CTEs</p>
                                </Card>
                                <Card variant="inset" padding="compact">
                                    <p className="mb-1 font-mono text-label uppercase text-re-text-muted">Premium Plan</p>
                                    <p className="text-title tabular-nums text-re-text-primary">$639/mo <span className="text-ui font-normal text-re-text-tertiary line-through">$1,275/mo</span></p>
                                    <p className="mt-2 text-small text-re-text-tertiary">Founding design partner rate, billed annually ($749/mo monthly) • 4+ facilities • Dedicated support</p>
                                </Card>
                            </div>
                        </Card>
                        <div className="order-1 md:order-2">
                            <h3 className="mb-4 font-display text-heading-lg text-re-text-primary">
                                Pricing You Can See Before You Sign
                            </h3>
                            <p className="mb-4 max-w-[68ch] text-body text-re-text-secondary">
                                Open pricing builds trust. We list prices on our website. No "contact sales" gatekeeping. No surprise enterprise minimums.
                            </p>
                            <p className="mb-6 max-w-[68ch] text-ui text-re-text-tertiary">
                                Founding Design Partners get preferred pricing for the life of their account. Plans start at $425/mo (billed annually) or $499/mo monthly. Honest pricing for honest work.
                            </p>
                            <ul className="space-y-2">
                                {[
                                    'Simple design-partner agreements — no multi-year lock-in',
                                    'API access for contracted workspaces',
                                    'Founding Design Partner rate never increases',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-3 text-ui text-re-text-secondary">
                                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>

                    {/* Speed */}
                    <div className="grid items-center gap-8 md:grid-cols-2">
                        <div>
                            <h3 className="mb-4 font-display text-heading-lg text-re-text-primary">
                                Self-serve onboarding, days not months
                            </h3>
                            <p className="mb-4 max-w-[68ch] text-body text-re-text-secondary">
                                When a deadline approaches, every week matters. RegEngine takes teams from signup to mapped supplier data and retailer-readiness review in days. Once records are mapped, FSMA-formatted exports build in minutes.
                            </p>
                            <p className="mb-6 max-w-[68ch] text-ui text-re-text-tertiary">
                                Sales-led platforms typically run multi-month implementations. Verify timelines with each vendor.
                            </p>
                            <div className="space-y-3">
                                {[
                                    { step: '1', label: 'Sign up, create a facility' },
                                    { step: '2', label: 'Upload your CTEs (CSV or API)' },
                                    { step: '3', label: 'RegEngine validates all KDEs' },
                                    { step: '4', label: 'Export §1.1455-formatted trace data' },
                                ].map((item) => (
                                    <div key={item.step} className="flex gap-4 items-start">
                                        <div aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-re-border font-mono text-ui tabular-nums text-re-text-muted">
                                            {item.step}
                                        </div>
                                        <p className="pt-1 text-ui text-re-text-secondary">{item.label}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <Card variant="inset" padding="spacious">
                            <div className="text-center">
                                <p className="mb-2 font-mono text-label uppercase text-re-text-muted">Onboarding model</p>
                                <div className="space-y-4">
                                    <div>
                                        <p className="mb-1 text-heading text-re-text-primary">Self-serve</p>
                                        <p className="text-small text-re-text-tertiary">RegEngine</p>
                                    </div>
                                    <div className="h-px bg-re-border-subtle" />
                                    <div>
                                        <p className="mb-1 text-heading text-re-text-tertiary">Sales-led</p>
                                        <p className="text-small text-re-text-muted">Trustwell, SafetyChain (per their public materials)</p>
                                    </div>
                                    <div>
                                        <p className="mb-1 text-heading text-re-text-tertiary">Retailer-coordinated</p>
                                        <p className="text-small text-re-text-muted">ReposiTrak (per their public materials)</p>
                                    </div>
                                </div>
                                <p className="mt-4 text-label text-re-text-muted">
                                    Competitors named are trademarks of their respective owners. Verify current onboarding timelines directly with each vendor.
                                </p>
                            </div>
                        </Card>
                    </div>

                    {/* CTE Coverage */}
                    <div className="grid items-center gap-8 md:grid-cols-2">
                        <Card padding="spacious" className="order-2 md:order-1">
                            <h4 className="mb-6 text-subheading text-re-text-primary">All 7 FSMA 204 CTE Types</h4>
                            <div className="space-y-3">
                                {[
                                    'Harvesting',
                                    'Cooling',
                                    'Initial Packing',
                                    'First Land-Based Receiving',
                                    'Shipping',
                                    'Receiving',
                                    'Transformation',
                                ].map((item, idx) => (
                                    <div key={idx} className="flex gap-2 text-ui text-re-text-secondary">
                                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span className="text-ui text-re-text-secondary">{item}</span>
                                    </div>
                                ))}
                            </div>
                        </Card>
                        <div className="order-1 md:order-2">
                            <h3 className="mb-4 font-display text-heading-lg text-re-text-primary">
                                Complete CTE/KDE Coverage
                            </h3>
                            <p className="mb-4 max-w-[68ch] text-body text-re-text-secondary">
                                All 7 FSMA 204 CTE types, fully implemented. Every field validated individually (not batch). Incomplete CTEs are a common gap teams discover during recall drills.
                            </p>
                            <p className="mb-6 max-w-[68ch] text-ui text-re-text-tertiary">
                                Verify CTE coverage and validation depth with each vendor for your stack. RegEngine covers all 7 with per-CTE KDE validation that surfaces errors before submission.
                            </p>
                            <ul className="space-y-2">
                                {[
                                    'Per-CTE key data element validation',
                                    'Supplier relationship mapping across all CTEs',
                                    'Location traceability from source to receiver',
                                    'FDA 204 naming conventions built in',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-3 text-ui text-re-text-secondary">
                                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>

                    {/* EPCIS */}
                    <div className="grid items-center gap-8 md:grid-cols-2">
                        <div>
                            <h3 className="mb-4 font-display text-heading-lg text-re-text-primary">
                                EPCIS 2.0 Native
                            </h3>
                            <p className="mb-4 max-w-[68ch] text-body text-re-text-secondary">
                                EPCIS 2.0 can support trading-partner interoperability. RegEngine treats EPCIS 2.0 as a supported schema where the enabled workflow and source data allow it.
                            </p>
                            <p className="mb-6 max-w-[68ch] text-ui text-re-text-tertiary">
                                Verify EPCIS coverage with each vendor; some platforms layer EPCIS over legacy schemas, which can introduce conversion edges.
                            </p>
                            <ul className="space-y-2">
                                {[
                                    'EPCIS 2.0 XML + JSON serialization',
                                    'Traceability event export support',
                                    'No third-party conversion needed',
                                    'Designed for buyer and trading-partner interoperability checks',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-3 text-ui text-re-text-secondary">
                                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                        <Card padding="spacious" className="hidden md:block">
                            <code className="block overflow-auto font-mono text-small leading-relaxed text-re-text-secondary">
                                {`<events>
  <EPCISEvent>
    <eventTime>2026-04-05T...</eventTime>
    <eventType>
      ObjectEvent
    </eventType>
    <epcList>
      <epc>
        urn:epc:id:sgtin:...
      </epc>
    </epcList>
    <action>OBSERVE</action>
    <bizStep>
      urn:epcglobal:cbv:bizstep:...
    </bizStep>
  </EPCISEvent>
</events>`}
                            </code>
                        </Card>
                    </div>

                    {/* SMB Focus */}
                    <div className="grid items-center gap-8 md:grid-cols-2">
                        <Card padding="spacious" className="order-2 md:order-1">
                            <p className="mb-4 text-ui text-re-text-tertiary">RegEngine is built for companies like:</p>
                            <ul className="space-y-2">
                                {[
                                    'Regional produce distributors ($5M–$50M annual revenue)',
                                    'Specialty food brands and co-packers',
                                    'Organic/specialty retailers and wholesalers',
                                    'Small farms and grower cooperatives',
                                    'Emerging CPG brands reaching FDA compliance',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-2 text-ui text-re-text-secondary">
                                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </Card>
                        <div className="order-1 md:order-2">
                            <h3 className="mb-4 font-display text-heading-lg text-re-text-primary">
                                Built for SMBs, Not Enterprises Only
                            </h3>
                            <p className="mb-4 max-w-[68ch] text-body text-re-text-secondary">
                                Compliance shouldn't require a 50-person implementation team. You need FSMA 204 compliance, fast and cheap. Self-serve signup, no minimums, no sales calls.
                            </p>
                            <p className="mb-6 max-w-[68ch] text-ui text-re-text-tertiary">
                                Legacy platforms built for 100+ facility enterprises. RegEngine scales from 1 to 1,000 facilities. You start small; you grow without ripping out the platform.
                            </p>
                            <ul className="space-y-2">
                                {[
                                    'Self-serve signup with onboarding support when needed',
                                    'No implementation services required',
                                    'Scales from 1 to 1,000 facilities',
                                    'Direct support channel based on plan and rollout scope',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-3 text-ui text-re-text-secondary">
                                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </Container>
            </section>

            {/* Honest Positioning */}
            <section className="border-b border-re-border-subtle py-16 sm:py-20">
                <Container width="marketing">
                    <Card padding="spacious">
                        <h2 className="mb-3 font-display text-heading-lg text-re-text-primary">
                            What RegEngine Is NOT
                        </h2>
                        <p className="mb-8 max-w-[68ch] text-body text-re-text-secondary">
                            RegEngine is a compliance layer, not a replacement for your ERP or WMS. We work alongside your existing systems, filling the traceability gaps that packaged software doesn't solve.
                        </p>
                        <div className="space-y-4">
                            {[
                                {
                                    title: 'We are NOT an ERP replacement',
                                    detail: 'Your inventory, financials, and order management stay in Shopify, NetSuite, or QuickBooks. RegEngine handles traceability.',
                                },
                                {
                                    title: 'We are NOT a supply chain analytics platform',
                                    detail: 'We focus on advisory compliance validation and FDA-oriented sortable exports. Advanced forecasting and sourcing tools live elsewhere.',
                                },
                                {
                                    title: 'We do NOT promise 100% FDA audit success',
                                    detail: 'Compliance is a process, not a product. We validate data and generate FDA exports. Audits require auditors.',
                                },
                                {
                                    title: 'We do NOT lock you in',
                                    detail: 'Simple design-partner agreements — no multi-year lock-in. Export all your data anytime. Your data is yours.',
                                },
                            ].map((item, idx) => (
                                <div key={idx} className="flex gap-4">
                                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                    <div>
                                        <p className="text-subheading text-re-text-primary">{item.title}</p>
                                        <p className="text-ui text-re-text-secondary">{item.detail}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </Card>
                </Container>
            </section>

            {/* Social Proof / Industry Fit */}
            <section className="border-b border-re-border-subtle py-16 sm:py-20">
                <Container width="marketing">
                    <h2 className="mb-3 font-display text-heading-lg text-re-text-primary">
                        Who's RegEngine For?
                    </h2>
                    <p className="mb-10 max-w-[68ch] text-body text-re-text-secondary">
                        If you fit any of these categories, RegEngine is built for you.
                    </p>
                    <div className="grid gap-5 sm:grid-cols-2">
                        {[
                            {
                                Icon: Code2,
                                title: 'Technical Buyers',
                                detail: 'Your team owns integrations. You want APIs, webhooks, and source control. RegEngine gives you that.',
                            },
                            {
                                Icon: Workflow,
                                title: 'Operations Teams',
                                detail: 'You need FSMA 204 compliance done quickly. CSV upload is fast enough. No custom dev needed.',
                            },
                            {
                                Icon: Zap,
                                title: 'Founders & SMBs',
                                detail: 'You need compliance but can\'t afford enterprise fees. Founding Design Partner rates from $425/mo (billed annually) get you live. Scale as you grow.',
                            },
                            {
                                Icon: Lightbulb,
                                title: 'Compliance Officers',
                                detail: 'You need per-CTE validation and FDA-oriented sortable exports. RegEngine gives you audit trails and supporting records.',
                            },
                        ].map((item, idx) => (
                            <Card key={idx} variant="interactive" padding="compact">
                                <item.Icon className="mb-3 h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <h3 className="mb-2 text-subheading text-re-text-primary">
                                    {item.title}
                                </h3>
                                <p className="text-ui text-re-text-secondary">{item.detail}</p>
                            </Card>
                        ))}
                    </div>
                </Container>
            </section>

            {/* CTA Section */}
            <section className="py-16 sm:py-20">
                <Container width="marketing" className="text-center">
                    <h2 className="mb-3 font-display text-heading-lg text-re-text-primary">
                        Ready to Get Compliant?
                    </h2>
                    <p className="mx-auto mb-8 max-w-[68ch] text-body text-re-text-secondary">
                        Request access in minutes. Start with the onboarding path that fits your team. Simple design-partner agreements — no multi-year lock-in.
                    </p>
                    <div className="flex flex-col justify-center gap-3 sm:flex-row">
                        <Button asChild size="lg">
                            <Link href="/signup">
                                Start Setup
                                <ArrowRight className="ml-2 h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/contact">
                                Talk to Us
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/pricing">
                                View Pricing
                            </Link>
                        </Button>
                    </div>
                    <p className="mt-8 text-ui text-re-text-muted">
                        Questions? Email{' '}
                        <a href="mailto:support@regengine.co" className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand">
                            support@regengine.co
                        </a>
                        {' '}for rollout or integration questions.
                    </p>
                </Container>
            </section>
        </main>
    );
}
