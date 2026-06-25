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
const card = 'rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-sm';
const sectionAlt = 'border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]';

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
            'Single consolidated Python service for CTE ingestion, webhook validation, CSV parsing, compliance scoring, exports, and alert generation. The services directories are code-organization boundaries, not separate default deploys.',
    },
    {
        Icon: Database,
        layer: 'Database',
        technology: 'PostgreSQL on Supabase',
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
        description: 'CTE events arrive via CSV upload, webhook, or EPCIS. CSV and webhook paths run validation synchronously; EPCIS validation runs asynchronously. All paths persist before scoring.',
        color: 'bg-re-info-muted0/15 text-re-info',
    },
    {
        step: '2',
        title: 'Normalize',
        description: 'Raw event data is mapped to FSMA CTE/KDE structures. Lot codes, GLNs, and facility identities may be standardized, with exceptions or missing KDEs surfaced for review.',
        color: 'bg-purple-500/15 text-purple-400',
    },
    {
        step: '3',
        title: 'Hash & Chain',
        description: 'Validated events are SHA-256 hashed and chain-linked at ingest, scoped per tenant. Independent verification of exported bundles is offered at /verify. Default deployments use PostgreSQL-backed task processing rather than a managed message bus.',
        color: 'bg-re-brand/15 text-re-brand',
    },
    {
        step: '4',
        title: 'Score',
        description: 'The compliance engine produces an advisory readiness signal across six weighted dimensions: export readiness, KDE completeness, CTE coverage, chain integrity, obligation coverage, and FTL product coverage. Per-dimension maturity varies; rule enforcement is opt-in per workflow and is advisory in production today.',
        color: 'bg-re-warning-muted0/15 text-re-warning',
    },
    {
        step: '5',
        title: 'Export',
        description: 'Compliance records may be exported in one or more supported formats such as EPCIS 2.0, FDA-oriented spreadsheets, or CSV, depending on the enabled workflow.',
        color: 'bg-re-danger-muted0/15 text-re-danger',
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
        detail: 'ERP, WMS, supplier files, webhooks, or EPCIS feeds',
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
        detail: 'FastAPI validation, mapping, scoring, and workflow orchestration',
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

export default function ArchitecturePage() {
    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            {/* Header */}
            <section className="relative z-[2] max-w-[860px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-10 sm:pb-14">
                <Link
                    href="/trust"
                    className="inline-flex items-center gap-1.5 text-sm text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors mb-6"
                >
                    <ArrowLeft className="h-3.5 w-3.5" />
                    Trust Center
                </Link>
                <span className="block text-[11px] font-mono font-medium text-[var(--re-text-disabled)] tracking-widest uppercase">
                    Architecture
                </span>                <h1 className="font-display text-4xl font-bold text-[var(--re-text-primary)] mt-4 mb-4 leading-tight">
                    How RegEngine is built
                </h1>
                <p className="text-base text-[var(--re-text-muted)] leading-relaxed max-w-[720px]">
                    Service topology, data flow from ingest to export, tenant isolation model, and infrastructure posture.
                    This page is written for IT reviewers and security teams evaluating RegEngine for procurement.
                </p>
            </section>

            {/* System flow diagram */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[1180px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <div className="mb-6 max-w-[760px]">
                        <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-2">
                            System flow at a glance
                        </h2>
                        <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                            The core path keeps customer-owned source data, authenticated request context, PostgreSQL
                            tenant controls, and export review boundaries visually separate. Optional processors sit
                            outside the default core path unless they are enabled or configured for a workspace.
                        </p>
                    </div>
                    <div className={`${card} overflow-hidden`}>
                        <div className="grid gap-0 lg:grid-cols-5">
                            {SYSTEM_FLOW.map((step, index) => {
                                const Icon = step.Icon;
                                return (
                                    <div
                                        key={step.title}
                                        className="relative border-b border-[var(--re-surface-border)] p-5 last:border-b-0 lg:border-b-0 lg:border-r lg:last:border-r-0"
                                    >
                                        {index < SYSTEM_FLOW.length - 1 && (
                                            <ArrowRight className="absolute right-[-10px] top-8 z-[1] hidden h-5 w-5 rounded-full border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-0.5 text-[var(--re-text-disabled)] lg:block" />
                                        )}
                                        <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--re-brand)]/10">
                                            <Icon className="h-5 w-5 text-[var(--re-brand)]" />
                                        </div>
                                        <h3 className="text-sm font-semibold text-[var(--re-text-primary)]">{step.title}</h3>
                                        <p className="mt-2 text-sm leading-relaxed text-[var(--re-text-muted)]">{step.detail}</p>
                                        <p className="mt-4 text-[11px] font-mono uppercase tracking-normal text-[var(--re-text-disabled)]">
                                            {step.boundary}
                                        </p>
                                    </div>
                                );
                            })}
                        </div>
                        <div className="border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-4">
                            <div className="mb-3 text-[11px] font-mono uppercase tracking-widest text-[var(--re-text-disabled)]">
                                Conditional processors
                            </div>
                            <div className="flex flex-wrap gap-2">
                                {OPTIONAL_PROCESSORS.map((processor) => (
                                    <span
                                        key={processor}
                                        className="rounded-full border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] px-3 py-1.5 text-xs text-[var(--re-text-muted)]"
                                    >
                                        {processor}
                                    </span>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Stack layers */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-2">Service topology</h2>
                    <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                        This page describes the current service topology and intended control boundaries. Exact infrastructure details can vary by deployment and environment.
                    </p>
                    <div className="grid gap-4 md:grid-cols-2">
                        {STACK_LAYERS.map((layer) => {
                            const Icon = layer.Icon;
                            return (
                                <div key={layer.layer} className={`${card} p-5`}>
                                    <div className="flex items-center gap-3 mb-3">
                                        <div className="w-9 h-9 rounded-lg bg-[var(--re-brand)]/10 flex items-center justify-center">
                                            <Icon className="h-4.5 w-4.5 text-[var(--re-brand)]" />
                                        </div>
                                        <div>
                                            <div className="text-sm font-semibold text-[var(--re-text-primary)]">{layer.layer}</div>
                                            <div className="text-xs text-[var(--re-text-disabled)]">{layer.technology}</div>                                        </div>
                                    </div>
                                    <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">{layer.detail}</p>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </section>

            {/* Data flow */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-2">Data flow: ingest to export</h2>
                <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                    The current product posture aims for a consistent five-stage pipeline from ingest to export, with integrity controls applied after validation.
                </p>
                <div className="space-y-3">
                    {DATA_FLOW_STEPS.map((step, i) => (
                        <div key={step.step} className={`${card} p-5 flex gap-4`}>
                            <div className={`w-8 h-8 rounded-lg ${step.color} flex items-center justify-center text-sm font-bold flex-shrink-0 mt-0.5`}>
                                {step.step}
                            </div>
                            <div>
                                <div className="text-sm font-semibold text-[var(--re-text-primary)]">{step.title}</div>
                                <p className="text-sm text-[var(--re-text-muted)] mt-1 leading-relaxed">{step.description}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </section>
            {/* Tenant isolation */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-2">Tenant isolation model</h2>
                    <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                        Isolation is intended to be enforced as close to the data layer as possible rather than depending solely on application logic.
                    </p>
                    <div className="grid gap-4 md:grid-cols-2">
                        {ISOLATION_CONTROLS.map((control) => {
                            const Icon = control.Icon;
                            return (
                                <div key={control.title} className={`${card} p-5`}>
                                    <div className="flex items-center gap-2.5 mb-2">
                                        <Icon className="h-4 w-4 text-[var(--re-brand)]" />
                                        <div className="text-sm font-semibold text-[var(--re-text-primary)]">{control.title}</div>
                                    </div>
                                    <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">{control.detail}</p>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </section>

            {/* Infrastructure */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-4">Infrastructure controls</h2>
                <div className="grid gap-3 md:grid-cols-3">                    {[
                        { label: 'Encryption at rest', value: 'Managed-cloud default', detail: 'Encrypted storage is part of the current managed infrastructure posture' },
                        { label: 'Encryption in transit', value: 'Encrypted transport', detail: 'Client and service connections are intended to use encrypted transport' },
                        { label: 'Data residency', value: 'US default', detail: 'Current default posture for active deployments' },
                        { label: 'Backup cadence', value: 'Platform managed', detail: 'Backup and recovery posture depends on the active hosting configuration' },
                        { label: 'CI/CD security', value: 'Current workflow controls', detail: 'Secrets, SAST, and dependency gates run in CI; DAST, SBOM, and container scans run when configured or on scheduled/main-branch workflows' },
                        { label: 'Branch protection', value: 'Repository controlled', detail: 'Review and merge controls are managed at the repository level' },
                    ].map((item) => (
                        <div key={item.label} className={`${card} p-4`}>
                            <div className="text-xs uppercase tracking-widest text-[var(--re-text-disabled)]">{item.label}</div>
                            <div className="mt-2 text-xl font-bold text-[var(--re-text-primary)]">{item.value}</div>
                            <div className="text-sm text-[var(--re-text-muted)] mt-1">{item.detail}</div>
                        </div>
                    ))}
                </div>
            </section>

            {/* CTA */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[860px] mx-auto py-10 sm:py-14 px-4 sm:px-6 text-center">
                    <p className="text-sm text-[var(--re-text-muted)] mb-4">
                        Need more detail? The security page covers RLS testing, hash verification, and audit trail posture.
                    </p>
                    <div className="flex flex-wrap gap-3 justify-center">
                        <Link href="/security">
                            <span className="inline-flex items-center gap-1.5 text-sm text-[var(--re-brand)] hover:opacity-80 transition-opacity">
                                Security overview <ArrowRight className="h-3.5 w-3.5" />
                            </span>
                        </Link>                        <Link href="/trust">
                            <span className="inline-flex items-center gap-1.5 text-sm text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors">
                                Trust Center <ArrowRight className="h-3.5 w-3.5" />
                            </span>
                        </Link>
                        <Link href="/contact">
                            <span className="inline-flex items-center gap-1.5 text-sm text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors">
                                Request diligence materials <ArrowRight className="h-3.5 w-3.5" />
                            </span>
                        </Link>
                    </div>
                    <p className="text-sm text-[var(--re-text-muted)] mt-6">
                        Verify supported evidence export bundles yourself: drop a supported bundle into{' '}
                        <Link href="/verify" className="text-[var(--re-brand)] hover:opacity-80">/verify</Link>{' '}
                        or download a synthetic sample at{' '}
                        <Link href="/proof" className="text-[var(--re-brand)] hover:opacity-80">/proof</Link>.
                    </p>
                </div>
            </section>
        </div>
    );
}
