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
        url: 'https://www.regengine.co/trust/architecture',
        type: 'website',
    },
};
const card = 'rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-sm';
const sectionAlt = 'border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]';

const STACK_LAYERS = [
    {
        Icon: Monitor,
        layer: 'Frontend',
        technology: 'Next.js 15 on Vercel',
        detail:
            'Server-side rendered React app with edge caching. All API calls route through serverless proxy functions — the browser never talks directly to backend services.',
    },
    {
        Icon: Server,
        layer: 'Ingestion Service',
        technology: 'FastAPI on Railway',
        detail:
            'Stateless Python service that handles CTE event ingestion, webhook validation, CSV parsing, compliance scoring, and alert generation. Horizontally scalable behind a load balancer.',
    },
    {
        Icon: Database,
        layer: 'Database',
        technology: 'PostgreSQL on Supabase',
        detail:
            'Row-Level Security enforces tenant isolation at the database layer. Immutable audit triggers prevent modification of compliance records. Connection pooling via PgBouncer.',
    },    {
        Icon: Cloud,
        layer: 'Infrastructure',
        technology: 'US-based hosting',
        detail:
            'All services run in US data centers. TLS 1.3 in transit, AES-256 at rest. No data leaves US jurisdiction in the default deployment posture.',
    },
];

const DATA_FLOW_STEPS = [
    {
        step: '1',
        title: 'Ingest',
        description: 'CTE events arrive via CSV upload, webhook, or API call. Each event is validated against FSMA 204 KDE requirements for its CTE type.',
        color: 'bg-blue-500/15 text-blue-400',
    },
    {
        step: '2',
        title: 'Normalize',
        description: 'Raw event data is mapped to FSMA CTE/KDE structures. Lot codes, GLNs, and facility identities are standardized. Missing required KDEs trigger rejection with actionable errors.',
        color: 'bg-purple-500/15 text-purple-400',
    },
    {
        step: '3',
        title: 'Hash & Chain',
        description: 'Each validated event is SHA-256 hashed and appended to a per-tenant hash chain. The chain is append-only — database triggers block updates and deletes on compliance tables.',
        color: 'bg-emerald-500/15 text-emerald-400',
    },    {
        step: '4',
        title: 'Score',
        description: 'The compliance engine evaluates six dimensions: chain integrity, KDE completeness, CTE completeness, obligation coverage, product coverage, and export readiness.',
        color: 'bg-amber-500/15 text-amber-400',
    },
    {
        step: '5',
        title: 'Export',
        description: 'Compliance records are exportable in EPCIS 2.0 JSON-LD, FDA sortable spreadsheet, or CSV. Each export includes a manifest hash for integrity verification.',
        color: 'bg-red-500/15 text-red-400',
    },
];

const ISOLATION_CONTROLS = [
    {
        Icon: Lock,
        title: 'Row-Level Security',
        detail: 'Every database query is scoped to the authenticated tenant at the PostgreSQL policy level. Cross-tenant data access is structurally impossible.',
    },
    {
        Icon: Hash,
        title: 'Per-tenant hash chains',
        detail: 'Each tenant has an independent SHA-256 hash chain. Chains are cryptographically isolated — one tenant\'s chain cannot reference another\'s records.',
    },    {
        Icon: Shield,
        title: 'API key scoping',
        detail: 'API keys are bound to a single tenant. The serverless proxy injects tenant context on every request — backend services never trust client-supplied tenant IDs.',
    },
    {
        Icon: ShieldCheck,
        title: 'Immutable audit trail',
        detail: 'Database triggers enforce append-only on compliance tables. No UPDATE or DELETE is possible on extracted facts, rule evaluations, or audit events.',
    },
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
                </span>                <h1 className="text-4xl font-bold text-[var(--re-text-primary)] mt-4 mb-4 leading-tight">
                    How RegEngine is built
                </h1>
                <p className="text-base text-[var(--re-text-muted)] leading-relaxed max-w-[720px]">
                    Service topology, data flow from ingest to export, tenant isolation model, and infrastructure posture.
                    This page is written for IT reviewers and security teams evaluating RegEngine for procurement.
                </p>
            </section>

            {/* Stack layers */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">Service topology</h2>
                    <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                        RegEngine runs as three services with strict separation of concerns. The browser never communicates directly with backend infrastructure.
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
                <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">Data flow: ingest to export</h2>
                <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                    Every CTE event follows the same five-stage pipeline. Records are immutable after stage 3 — the hash chain is append-only.
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
                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">Tenant isolation model</h2>
                    <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                        Isolation is enforced at the database layer, not the application layer. Even if application code has a bug, PostgreSQL RLS policies prevent cross-tenant data access.
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
                <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-4">Infrastructure controls</h2>
                <div className="grid gap-3 md:grid-cols-3">                    {[
                        { label: 'Encryption at rest', value: 'AES-256', detail: 'All database volumes and backups' },
                        { label: 'Encryption in transit', value: 'TLS 1.3', detail: 'All service-to-service and client connections' },
                        { label: 'Data residency', value: 'US', detail: 'Default posture for all deployments' },
                        { label: 'Backup cadence', value: 'Daily', detail: 'Point-in-time recovery via Supabase' },
                        { label: 'CI/CD security', value: 'SAST + secrets scan', detail: 'Every commit scanned before deploy' },
                        { label: 'Branch protection', value: 'Required reviews', detail: 'No force-push to main' },
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
                        Need more detail? The security page covers RLS testing, hash verification, and audit trail enforcement.
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
                </div>
            </section>
        </div>
    );
}
