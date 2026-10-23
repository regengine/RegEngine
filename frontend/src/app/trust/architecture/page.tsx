import type { Metadata } from 'next';
import Link from 'next/link';
import {
    ArrowLeft,
    ArrowRight,
    Cloud,
    Database,
    Globe,
    Hash,
    Layers,
    Lock,
    Monitor,
    Server,
    Shield,
    ShieldCheck,
    Workflow,
} from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Section } from '@/components/layout/section';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

export const metadata: Metadata = {
    title: 'Architecture Summary | RegEngine',
    description:
        'Service topology, data flow, tenant isolation, and infrastructure posture for RegEngine FSMA 204 deployments.',
    openGraph: {
        title: 'Architecture Summary | RegEngine',
        description: 'Technical architecture for RegEngine FSMA 204 compliance platform.',
        url: 'https://regengine.co/trust/architecture',
        type: 'website',
    },
};

const STACK_LAYERS = [
    {
        Icon: Monitor,
        layer: 'Frontend',
        technology: 'Next.js 16 on Vercel',
        detail:
            'Current deployment posture uses a server-rendered React app with edge caching and proxy-based API routing so browser traffic is mediated before it reaches backend services.',
    },
    {
        Icon: Server,
        layer: 'Backend',
        technology: 'FastAPI monolith on Railway',
        detail:
            'Single consolidated Python service for CTE ingestion, JSON events API validation, CSV parsing, compliance coverage and completeness checking, exports, and alert generation. The services directories are code-organization boundaries, not separate default deploys.',
    },
    {
        Icon: Database,
        layer: 'Database',
        technology: 'PostgreSQL on Railway',
        detail:
            'Current database posture uses PostgreSQL tenant-scoping controls, append-oriented audit protections, and managed connection pooling.',
    },
    {
        Icon: Cloud,
        layer: 'Infrastructure',
        technology: 'US-configured core hosting',
        detail:
            'Default active application/database hosting is US-based where configured. CDN, edge, AI, and object-storage processing locations vary by provider and executed DPA.',
    },
];

const DATA_FLOW_STEPS = [
    {
        step: '1',
        title: 'Ingest',
        description: 'CTE events arrive via CSV upload or the JSON events API. Both paths run validation synchronously and persist before coverage checks. EPCIS intake is in Preview; EDI and SFTP intake are on the roadmap.',
    },
    {
        step: '2',
        title: 'Normalize',
        description: 'Raw event data is mapped to FSMA CTE/KDE structures. Lot codes, GLNs, and facility identities may be standardized, with exceptions or missing KDEs surfaced for review.',
    },
    {
        step: '3',
        title: 'Hash & Chain',
        description: 'Validated events are SHA-256 hashed and chain-linked at ingest, scoped per tenant. Commit means accepted records are appended after checks you configure; this is not a certification. Independent verification of exported bundles is offered at /verify. Default deployments use PostgreSQL-backed task processing rather than a managed message bus.',
    },
    {
        step: '4',
        title: 'Coverage & Completeness Checklist',
        description: 'The compliance engine produces an advisory coverage and completeness checklist across six weighted dimensions: export-checklist completeness, KDE completeness, CTE coverage, chain integrity, obligation coverage, and FTL product-list overlap. This is not a readiness score, not a badge, not an FDA or buyer decision. FTL overlap is list-membership, not a covered-person determination. Per-dimension maturity varies; rule enforcement is opt-in per workflow and is advisory in production today.',
    },
    {
        step: '5',
        title: 'Export',
        description: 'Compliance records may be exported in one or more supported formats such as EPCIS 2.0, FDA-oriented spreadsheets, or CSV, depending on the enabled workflow.',
    },
];

const ISOLATION_CONTROLS = [
    {
        Icon: Lock,
        title: 'Row-Level Security',
        detail: 'PostgreSQL row-level policies and authenticated tenant context are designed and tested to restrict reads on core PostgreSQL-backed paths. Identity-resolution and graph-layer hardening is in progress; details available under NDA.',
    },
    {
        Icon: Hash,
        title: 'Per-tenant hash chains',
        detail: 'Integrity records are designed to remain tenant-scoped so one customer workspace does not depend on another customer\'s evidence chain.',
    },
    {
        Icon: Shield,
        title: 'API key scoping',
        detail: 'API credentials and tenant context are intended to be scoped per customer workspace, with server-side mediation preferred over trusting raw client context.',
    },
    {
        Icon: ShieldCheck,
        title: 'Append-oriented audit handling',
        detail: 'Compliance records are append-oriented after ingest; in-place mutation is not the supported path. Audit-chain coverage across review and admin surfaces is being expanded.',
    },
];

const SYSTEM_FLOW = [
    {
        Icon: Globe,
        title: 'Source systems',
        detail: 'ERP, WMS, and supplier data sent as CSV uploads or JSON events API calls',
        boundary: 'Customer-owned data quality',
    },
    {
        Icon: Layers,
        title: 'App and API edge',
        detail: 'Next.js app, authenticated routes, and mediated API traffic',
        boundary: 'Session and request context',
    },
    {
        Icon: Server,
        title: 'Ingestion service',
        detail: 'FastAPI validation, mapping, coverage and completeness checking, and workflow orchestration',
        boundary: 'Server-side tenant context',
    },
    {
        Icon: Database,
        title: 'Tenant database',
        detail: 'PostgreSQL records, RLS policies, append-oriented evidence handling',
        boundary: 'Core data isolation layer',
    },
    {
        Icon: Workflow,
        title: 'Evidence exports',
        detail: 'FDA-oriented spreadsheets, EPCIS/CSV packages, and manifests where configured',
        boundary: 'Customer review and archive',
    },
];

const OPTIONAL_PROCESSORS = [
    'AI extraction where enabled',
    'Object storage where configured',
    'Transactional email where configured',
    'Analytics after consent or workspace enablement',
];

const INFRASTRUCTURE_CONTROLS = [
    { label: 'Encryption at rest', value: 'Managed-cloud default', detail: 'Encrypted storage is part of the current managed infrastructure posture' },
    { label: 'Encryption in transit', value: 'Encrypted transport', detail: 'Client and service connections are intended to use encrypted transport' },
    { label: 'Data residency', value: 'US default', detail: 'Current default posture for active deployments' },
    { label: 'Backup cadence', value: 'Platform managed', detail: 'Backup and recovery posture depends on the active hosting configuration' },
    { label: 'CI/CD security', value: 'Current workflow controls', detail: 'Secrets, SAST, and dependency gates run in CI; DAST, SBOM, and container scans run when configured or on scheduled/main-branch workflows' },
    { label: 'Branch protection', value: 'Repository controlled', detail: 'Review and merge controls are managed at the repository level' },
];

const BACK_LINK =
    'inline-flex items-center gap-1.5 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none';
const PROSE_LINK =
    'text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand';

export default function ArchitecturePage() {
    return (
        <div className="re-page min-h-screen">
            {/* Header */}
            <Container className="pb-10 pt-14 sm:pb-14 sm:pt-20">
                <PageHeader
                    breadcrumbs={
                        <Link href="/trust" className={BACK_LINK}>
                            <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                            Trust Center
                        </Link>
                    }
                    size="hero"
                    eyebrow={<span className="font-mono uppercase">Architecture</span>}
                    title="How RegEngine is built"
                    description="Service topology, data flow from ingest to export, tenant isolation model, and infrastructure posture. This page is written for IT reviewers and security teams evaluating RegEngine for procurement."
                    className="mb-0 border-b-0 pb-0"
                />
            </Container>

            {/* System flow diagram */}
            <Section
                width="marketing"
                title="System flow at a glance"
                description="The core path keeps customer-owned source data, authenticated request context, PostgreSQL tenant controls, and export review boundaries visually separate. Optional processors sit outside the default core path unless they are enabled or configured for a workspace."
            >
                <Card className="overflow-hidden">
                    <div className="grid gap-0 lg:grid-cols-5">
                        {SYSTEM_FLOW.map((step) => {
                            const Icon = step.Icon;
                            return (
                                <div
                                    key={step.title}
                                    className="border-b border-re-border-subtle p-5 last:border-b-0 lg:border-b-0 lg:border-r lg:last:border-r-0"
                                >
                                    <Icon className="mb-4 h-5 w-5 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                    <h3 className="text-subheading text-re-text-primary">{step.title}</h3>
                                    <p className="mt-2 text-ui text-re-text-secondary">{step.detail}</p>
                                    <p className="mt-4 font-mono text-label uppercase text-re-text-muted">
                                        {step.boundary}
                                    </p>
                                </div>
                            );
                        })}
                    </div>
                    <div className="border-t border-re-border-subtle bg-re-surface-inset p-4">
                        <div className="mb-3 font-mono text-label uppercase text-re-text-muted">
                            Conditional processors
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {OPTIONAL_PROCESSORS.map((processor) => (
                                <Badge key={processor} tone="neutral">
                                    {processor}
                                </Badge>
                            ))}
                        </div>
                    </div>
                </Card>
            </Section>

            {/* Stack layers */}
            <Section
                width="marketing"
                title="Service topology"
                description="This page describes the current service topology and intended control boundaries. Exact infrastructure details can vary by deployment and environment."
            >
                <div className="grid gap-4 md:grid-cols-2">
                    {STACK_LAYERS.map((layer) => {
                        const Icon = layer.Icon;
                        return (
                            <Card key={layer.layer} className="p-5">
                                <div className="mb-3 flex items-center gap-3">
                                    <Icon className="h-5 w-5 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                    <div>
                                        <div className="text-subheading text-re-text-primary">{layer.layer}</div>
                                        <div className="font-mono text-[0.8125rem] text-re-text-tertiary">{layer.technology}</div>
                                    </div>
                                </div>
                                <p className="text-ui text-re-text-secondary">{layer.detail}</p>
                            </Card>
                        );
                    })}
                </div>
            </Section>

            {/* Data flow */}
            <Section
                width="marketing"
                title="Data flow: ingest to export"
                description="The current product posture aims for a consistent five-stage pipeline from ingest to export, with integrity controls applied after validation."
            >
                <Card className="overflow-hidden">
                    {DATA_FLOW_STEPS.map((step) => (
                        <div key={step.step} className="flex gap-4 border-b border-re-border-subtle p-5 last:border-0">
                            <span className="w-6 shrink-0 font-mono text-label uppercase tabular-nums text-re-text-muted">
                                {step.step}
                            </span>
                            <div>
                                <div className="text-subheading text-re-text-primary">{step.title}</div>
                                <p className="mt-1 text-ui text-re-text-secondary">{step.description}</p>
                            </div>
                        </div>
                    ))}
                </Card>
            </Section>

            {/* Tenant isolation */}
            <Section
                width="marketing"
                title="Tenant isolation model"
                description="Isolation is intended to be enforced as close to the data layer as possible rather than depending solely on application logic."
            >
                <div className="grid gap-4 md:grid-cols-2">
                    {ISOLATION_CONTROLS.map((control) => {
                        const Icon = control.Icon;
                        return (
                            <Card key={control.title} className="p-5">
                                <div className="mb-2 flex items-center gap-2.5">
                                    <Icon className="h-4 w-4 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                    <div className="text-subheading text-re-text-primary">{control.title}</div>
                                </div>
                                <p className="text-ui text-re-text-secondary">{control.detail}</p>
                            </Card>
                        );
                    })}
                </div>
            </Section>

            {/* Infrastructure */}
            <Section width="marketing" title="Infrastructure controls">
                <div className="grid gap-3 md:grid-cols-3">
                    {INFRASTRUCTURE_CONTROLS.map((item) => (
                        <Card key={item.label} padding="compact">
                            <div className="font-mono text-label uppercase text-re-text-muted">{item.label}</div>
                            <div className="mt-2 text-subheading text-re-text-primary">{item.value}</div>
                            <div className="mt-1 text-ui text-re-text-secondary">{item.detail}</div>
                        </Card>
                    ))}
                </div>
            </Section>

            {/* CTA */}
            <Section width="marketing">
                <div className="text-center">
                    <p className="mx-auto max-w-[68ch] text-ui text-re-text-secondary">
                        Need more detail? The security page covers RLS testing, hash verification, and audit trail posture.
                    </p>
                    <div className="mt-4 flex flex-wrap justify-center gap-3">
                        <Button asChild size="lg">
                            <Link href="/security">
                                Security overview <ArrowRight aria-hidden="true" strokeWidth={1.75} />
                            </Link>
                        </Button>
                        <Button asChild variant="ghost" size="lg">
                            <Link href="/trust">
                                Trust Center <ArrowRight aria-hidden="true" strokeWidth={1.75} />
                            </Link>
                        </Button>
                        <Button asChild variant="ghost" size="lg">
                            <Link href="/contact">
                                Request diligence materials <ArrowRight aria-hidden="true" strokeWidth={1.75} />
                            </Link>
                        </Button>
                    </div>
                    <p className="mx-auto mt-6 max-w-[68ch] text-ui text-re-text-secondary">
                        Verify supported evidence export bundles yourself: drop a supported bundle into{' '}
                        <Link href="/verify" className={PROSE_LINK}>/verify</Link>{' '}
                        or download a synthetic sample at{' '}
                        <Link href="/proof" className={PROSE_LINK}>/proof</Link>.
                    </p>
                </div>
            </Section>
        </div>
    );
}
