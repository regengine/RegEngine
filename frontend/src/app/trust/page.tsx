import type { Metadata } from 'next';
import Link from 'next/link';
import {
    ARCHIVE_EXPORT_JOBS,
    CAPABILITY_REGISTRY,
    DELIVERY_MODE_LABELS,
    INTEGRATION_TYPE_LABELS,
    INTEGRATION_TYPE_DESCRIPTIONS,
    INTEGRATION_TYPE_VERIFY,
    STATUS_LABELS,
    SUPPORT_CHANNELS,
    TRUST_ARTIFACTS,
} from '@/lib/customer-readiness';
import type { IntegrationType } from '@/lib/customer-readiness';
import { TRUST_SUBPROCESSORS } from '@/lib/trust-subprocessors';

export const metadata: Metadata = {
    title: 'Trust Center | RegEngine',
    description: 'Customer diligence surface for product status, retention, support, deployment posture, and available security artifacts.',
    openGraph: {
        title: 'Trust Center | RegEngine',
        description: 'Customer diligence surface for RegEngine FSMA 204 deployments and support posture.',
        url: 'https://regengine.co/trust',
        type: 'website',
    },
};
const STATUS_SUMMARY = [
    {
        label: 'Implemented',
        detail: 'Core FSMA workspace, exports, dashboard flows, and public documentation surfaces are available for contracted workspaces.',
    },
    {
        label: 'Supported',
        detail: 'Capability is available where the relevant workspace, plan, or workflow has been enabled.',
    },
    {
        label: 'Pilot',
        detail: 'Capability exists but should be treated as guided rollout or customer-specific onboarding work.',
    },
    {
        label: 'Design Partner',
        detail: 'Reserved for customers needing custom integration, implementation support, or pilot collaboration.',
    },
    {
        label: 'Export Supported',
        detail: 'RegEngine can prepare outbound packages, but does not claim a managed portal integration.',
    },
    {
        label: 'File Import Supported',
        detail: 'Customer data can be onboarded through CSV or SFTP with mapping review and exception handling.',
    },
    {
        label: 'Custom Scoped',
        detail: 'Requires customer-specific mapping, implementation, or support before production use.',
    },
    {
        label: 'Preparation',
        detail: 'Roadmap or diligence-preparation item; not a public commitment unless included in an executed agreement.',
    },
    {
        label: 'Contract-only',
        detail: 'Available commitments are governed by the executed agreement, DPA, or NDA package.',
    },
];

const TRUST_AT_A_GLANCE = [
    {
        tier: 'Public',
        title: 'Published diligence pages',
        detail: 'Trust, Security, DPA, Privacy, Terms, Architecture, Retention, and Support pages are available for buyer review.',
    },
    {
        tier: 'Request/NDA',
        title: 'Security evidence package',
        detail: 'Approved diligence materials, identity/graph hardening notes, and completed artifacts are shared when applicable.',
    },
    {
        tier: 'Contract-only',
        title: 'Binding commitments',
        detail: 'SLA, retention, deletion, subprocessor notice, escalation, and support terms live in the executed agreement or DPA.',
    },
    {
        tier: 'Not claimed',
        title: 'No overclaim posture',
        detail: 'No SOC 2 certification, third-party penetration-test report, FDA endorsement, or public availability commitment is claimed.',
    },
];

const DILIGENCE_SHORTCUTS = [
    { title: 'Security', detail: 'Controls, verifier posture, disclosure path', href: '/security', tier: 'Public' },
    { title: 'DPA', detail: 'Processor terms and subprocessor summary', href: '/dpa', tier: 'Public' },
    { title: 'Subprocessors', detail: 'Shared vendor list and locations', href: '#subprocessors', tier: 'Public' },
    { title: 'Retention', detail: 'Deletion, return, backup, and archive boundaries', href: '/trust/retention', tier: 'Public' },
    { title: 'Architecture', detail: 'Topology, data flow, and tenant isolation', href: '/trust/architecture', tier: 'Public' },
    { title: 'Claims matrix', detail: 'Allowed wording and evidence owner map', href: '/contact', tier: 'Request/NDA' },
];

/* Card style helper — uses CSS variables for light+dark mode */
const card = 'rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-sm';
const cardInner = 'rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-4';
const sectionAlt = 'border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]';
const tierChip = 'rounded-full border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-re-text-disabled';

export default function TrustCenterPage() {
    const capabilityCount = CAPABILITY_REGISTRY.length;

    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            {/* ─── HEADER ─── */}
            <section className="relative z-[2] max-w-[860px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-10 sm:pb-14">
                <h1 className="font-display text-4xl font-bold text-re-text-primary mt-4 mb-4 leading-tight">
                    Trust Center
                </h1>
                <p className="text-base text-re-text-muted leading-relaxed max-w-[720px]">
                    Product status, data ownership, retention terms, and diligence materials in one place. Specific
                    commitments — SLAs, retention, security obligations — live in your contract; this page
                    is a starting point for diligence, not a substitute for it.
                </p>
                <div className={`${card} mt-6 border-re-warning/30 bg-re-warning-muted0/10 p-5`}>
                    <div className="text-sm font-semibold text-re-text-primary">Pre-production trust posture</div>
                    <p className="mt-2 text-sm leading-relaxed text-re-text-muted">
                        RegEngine is a design-partner oriented FSMA 204 evidence layer. Public pages describe
                        implemented and supported capabilities, not binding service-level commitments. RegEngine does not
                        currently claim SOC 2 certification, a completed third-party penetration test, FDA
                        endorsement, or a public availability commitment. Binding commitments are controlled
                        by the executed agreement, order form, or DPA.
                    </p>
                </div>
                <div className="mt-6 grid gap-3 md:grid-cols-2">
                    {TRUST_AT_A_GLANCE.map((item) => (
                        <div key={item.tier} className={`${card} p-4`}>
                            <div className="flex items-start justify-between gap-3">
                                <div className="text-sm font-semibold text-re-text-primary">{item.title}</div>
                                <span className={tierChip}>{item.tier}</span>
                            </div>
                            <p className="mt-2 text-sm leading-relaxed text-re-text-muted">{item.detail}</p>
                        </div>
                    ))}
                </div>
                <div className="mt-6 grid gap-3 sm:grid-cols-3">
                    <div className={`${card} p-4`}>
                        <div className="text-xs uppercase tracking-widest text-re-text-disabled">Capability Registry</div>
                        <div className="mt-2 text-2xl font-bold text-re-text-primary">{capabilityCount}</div>
                        <div className="text-sm text-re-text-muted mt-1">Customer-visible entries rendered from one shared status model</div>
                    </div>
                    <div className={`${card} p-4`}>
                        <div className="text-xs uppercase tracking-widest text-re-text-disabled">Retention</div>
                        <div className="mt-2 text-2xl font-bold text-re-text-primary">Per contract</div>
                        <div className="text-sm text-re-text-muted mt-1">Post-cancellation retention is set in your agreement.</div>
                    </div>
                    <div className={`${card} p-4`}>
                        <div className="text-xs uppercase tracking-widest text-re-text-disabled">Data Residency</div>
                        <div className="mt-2 text-2xl font-bold text-re-text-primary">US-configured core</div>
                        <div className="text-sm text-re-text-muted mt-1">CDN, edge, AI, and storage locations vary by provider and executed DPA.</div>
                    </div>
                </div>
                <div className="mt-6">
                    <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-re-text-disabled">
                        Diligence shortcuts
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {DILIGENCE_SHORTCUTS.map((shortcut) => (
                            <Link key={shortcut.title} href={shortcut.href} className={`${card} block p-4 no-underline transition-colors hover:border-[var(--re-brand)]/40`}>
                                <div className="flex items-start justify-between gap-3">
                                    <div className="text-sm font-semibold text-re-text-primary">{shortcut.title}</div>
                                    <span className={tierChip}>{shortcut.tier}</span>
                                </div>
                                <p className="mt-2 text-sm leading-relaxed text-re-text-muted">{shortcut.detail}</p>
                            </Link>
                        ))}
                    </div>
                </div>
            </section>
            {/* ─── SOURCE-OF-TRUTH POSITIONING (moved up) ─── */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="font-display text-2xl font-bold text-re-text-primary mb-4">Source-of-truth positioning</h2>
                    <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                        RegEngine is a compliance evidence layer, not a system-of-record replacement. This distinction drives retention, audit ownership, and liability boundaries.
                    </p>
                    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                        <div className={`${card} p-4`}>
                            <div className="text-sm font-semibold text-re-text-primary">Evidence layer (current posture)</div>
                            <p className="text-sm text-re-text-muted mt-2">You own the data and compliance posture. RegEngine documents, normalizes, and exports it. Audit response liability remains with the customer.</p>
                        </div>
                        <div className={`${card} p-4`}>
                            <div className="text-sm font-semibold text-re-text-primary">Not a system of record</div>
                            <p className="text-sm text-re-text-muted mt-2">RegEngine does not replace your ERP, WMS, or operational food safety system. Source data quality is inherited from upstream systems.</p>
                        </div>
                        <div className={`${card} p-4`}>
                            <div className="text-sm font-semibold text-re-text-primary">Full data portability</div>
                            <p className="text-sm text-re-text-muted mt-2">Supported workflows can export CTE events, KDE fields, lot records, and supplier relationships in EPCIS 2.0 JSON-LD, FDA-oriented sortable spreadsheet, or CSV.</p>
                        </div>
                        <div className={`${card} p-4`}>
                            <div className="text-sm font-semibold text-re-text-primary">Tenant isolation</div>
                            <p className="text-sm text-re-text-muted mt-2">PostgreSQL row-level policies and authenticated tenant context are designed and tested to restrict cross-tenant reads on core PostgreSQL-backed paths. Identity-resolution and graph-layer hardening is in progress; details available under NDA.</p>
                        </div>
                    </div>
                </div>
            </section>
            {/* ─── RETENTION + SUPPORT BOUNDARIES (moved up) ─── */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                <h2 className="font-display text-2xl font-bold text-re-text-primary mb-3">What RegEngine actually does in your stack</h2>
                <p className="text-sm text-re-text-muted max-w-[720px] mb-6">
                    RegEngine ingests upstream traceability data, normalizes it into FSMA workflows, attaches audit-integrity metadata,
                    and prepares FDA- or retailer-oriented exports. It still depends on upstream data quality, stable identities,
                    and review of missing or conflicting KDEs.
                </p>
                <div className="grid gap-4 md:grid-cols-2">
                    <div className={`${card} p-5`}>
                        <h3 className="text-sm font-semibold text-re-text-primary">Operational realities</h3>
                        <ul className="mt-3 space-y-2 text-sm text-re-text-muted">
                            <li>Source-system fields must be mapped into FSMA CTE and KDE structures.</li>
                            <li>Lot codes, GLNs, product IDs, and facility identities have to be normalized.</li>
                            <li>Missing KDEs and conflicting facility matches still require human review.</li>
                            <li>Cryptographic hashing provides tamper-evidence after ingest, not proof of upstream data entry.</li>
                        </ul>
                    </div>
                    <div className={`${card} p-5`}>
                        <h3 className="text-sm font-semibold text-re-text-primary">Retention and support boundaries</h3>
                        <ul className="mt-3 space-y-2 text-sm text-re-text-muted">
                            <li>Customers should schedule recurring exports and maintain off-platform archives from day one.</li>
                            <li>Public support windows are not a substitute for recall-readiness operations.</li>
                            <li>Premium escalation and SLA terms are contractual, not implied by public pricing copy.</li>
                            <li>Security and diligence materials are a mix of public pages and request/NDA workflows.</li>
                        </ul>
                    </div>
                </div>
            </section>
            {/* ─── PUBLIC PROOF SURFACE CALLOUT ─── */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-6 sm:py-8 px-4 sm:px-6">
                <div className={`${card} p-5`}>
                    <div className="text-sm font-semibold text-re-text-primary">Verify supported evidence bundles yourself</div>
                    <p className="text-sm text-re-text-muted mt-2">
                        Supported evidence export workflows can include SHA-256 manifests for independent verification. Drop a supported bundle into <Link href="/verify" className="text-re-brand hover:opacity-90">/verify</Link> or download a synthetic sample at <Link href="/proof" className="text-re-brand hover:opacity-90">/proof</Link>.
                    </p>
                </div>
            </section>
            {/* ─── ARTIFACTS ─── */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <div className="flex items-end justify-between gap-4 mb-5">
                        <div>
                            <h2 className="font-display text-2xl font-bold text-re-text-primary">Artifacts and diligence materials</h2>
                            <p className="text-sm text-re-text-muted mt-1">Public pages are linked directly. Request and NDA items route through contact.</p>
                        </div>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                        {TRUST_ARTIFACTS.map((artifact) => (
                            <div key={artifact.id} className={`${card} p-4`}>
                                <div className="flex items-center justify-between gap-3">
                                    <div className="text-sm font-semibold text-re-text-primary">{artifact.title}</div>
                                    <span className="text-[10px] uppercase tracking-widest text-re-text-disabled">{artifact.access}</span>
                                </div>
                                <p className="text-sm text-re-text-muted mt-2 leading-relaxed">{artifact.summary}</p>
                                <Link href={artifact.href} className="inline-block mt-3 text-sm text-re-brand hover:opacity-90">
                                    Open →
                                </Link>
                            </div>
                        ))}
                    </div>
                </div>
            </section>
            {/* ─── DATA PORTABILITY ─── */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                <h2 className="font-display text-2xl font-bold text-re-text-primary mb-4">Data portability and exit rights</h2>
                <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                    Exports use open standards (GS1 EPCIS 2.0, the FDA sortable spreadsheet, CSV) so records
                    can be read and stored outside RegEngine. Re-import into another system depends on that
                    system&apos;s ingest support for the chosen format.
                </p>
                <div className="grid gap-3 md:grid-cols-2">
                    <div className={`${card} p-4`}>
                        <div className="text-sm font-semibold text-re-text-primary">Export formats</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>GS1 EPCIS 2.0 JSON-LD (industry standard)</li>
                            <li>FDA-oriented sortable spreadsheet aligned to 21 CFR 1.1455 where applicable</li>
                            <li>CSV with all CTE/KDE fields</li>
                            <li>Audit evidence bundle with manifest hashing</li>
                        </ul>
                    </div>
                    <div className={`${card} p-4`}>
                        <div className="text-sm font-semibold text-re-text-primary">Integrity and chain of custody</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>Supported evidence workflows can hash and chain-link accepted events</li>
                            <li>Timestamped manifests are generated where the configured export workflow supports them</li>
                            <li>Public verification endpoint at <Link href="/verify" className="text-re-brand hover:opacity-90">/verify</Link></li>
                            <li>Legacy Kafka-compatible signing exists for opt-in deployments; the default deployment uses PostgreSQL-backed task processing instead of a managed message bus</li>
                        </ul>
                    </div>                    <div className={`${card} p-4`}>
                        <div className="text-sm font-semibold text-re-text-primary">Automated export scheduling</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>Export cadence can be scoped per deployment</li>
                            <li>Archive delivery may use object storage or downloadable bundles</li>
                            <li>Manifest hashing is part of the intended export posture</li>
                            <li>Monitoring and retry behavior depend on the configured delivery path</li>
                        </ul>
                    </div>
                </div>
            </section>
            {/* ─── UPSTREAM DATA QUALITY ─── */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="font-display text-2xl font-bold text-re-text-primary mb-4">Upstream data quality controls</h2>
                    <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                        RegEngine validates incoming CTE/KDE records at ingestion time. Incomplete or non-compliant records are rejected or flagged before they enter the compliance evidence chain.
                    </p>
                    <div className="grid gap-3 md:grid-cols-2">
                        <div className={`${card} p-4`}>
                            <div className="text-sm font-semibold text-re-text-primary">Ingestion validation</div>
                            <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                                <li>Per-CTE-type required KDE validation (7 CTE types)</li>
                                <li>GLN format and GS1 check-digit verification</li>
                                <li>Rejects events more than 24 hours in the future or more than 90 days old (configurable)</li>
                                <li>Unit of measure validation against FSMA 204 standard units</li>
                                <li>Location requirement validation per CTE</li>
                            </ul>
                        </div>
                        <div className={`${card} p-4`}>
                            <div className="text-sm font-semibold text-re-text-primary">Rejection and flagging</div>
                            <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                                <li>Missing required KDEs trigger event rejection with detailed error messages</li>
                                <li>Obligation-gap alerts are surfaced asynchronously; rule enforcement is configurable per deployment and is advisory in production today</li>
                                <li>Batch deduplication prevents duplicate CTE submissions</li>
                                <li>Rejected events returned with status and actionable error detail</li>
                            </ul>
                        </div>                        <div className={`${card} p-4`}>
                            <div className="text-sm font-semibold text-re-text-primary">Supplier data quality</div>
                            <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                                <li>Per-supplier KDE completeness tracking</li>
                                <li>Submission history retained for review</li>
                                <li>Specific scoring and alerting features ship per workspace configuration</li>
                            </ul>
                        </div>
                        <div className={`${card} p-4`}>
                            <div className="text-sm font-semibold text-re-text-primary">Compliance readiness scoring</div>
                            <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                                <li>Six weighted signals: export readiness (30%), KDE completeness (25%), CTE coverage (15%), chain integrity (10%), obligation coverage (10%), FTL product coverage (10%)</li>
                                <li>Calculated from data in the active workspace</li>
                                <li>Internal readiness signal, not an FDA endorsement</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </section>
            {/* ─── REGULATORY INTERPRETATION ─── */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                <h2 className="font-display text-2xl font-bold text-re-text-primary mb-4">Regulatory interpretation tracking</h2>
                <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                    FSMA 204 compliance logic embeds vendor interpretation of FDA guidance. RegEngine tracks and documents which guidance versions inform its validation rules, export formats, and compliance algorithms.
                </p>
                <div className="grid gap-3 md:grid-cols-2">
                    <div className={`${card} p-4`}>
                        <div className="text-sm font-semibold text-re-text-primary">Current regulatory basis</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>FDA Final Rule: Requirements for Additional Traceability Records (21 CFR Part 1, Subpart S)</li>
                            <li>Original compliance date: January 20, 2026; FDA has proposed a 30-month extension and Congress directed FDA not to enforce before July 20, 2028</li>
                            <li>Food Traceability List (FTL): reviewed against FDA publications current as of April 1, 2026</li>
                            <li>FDA Q&amp;A draft guidance: February 2026; FAQ updates reviewed June 2026</li>
                        </ul>
                    </div>
                    <div className={`${card} p-4`}>
                        <div className="text-sm font-semibold text-re-text-primary">Update mechanism</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>Validation rules are versioned and reference the underlying FDA guidance</li>
                            <li>Compliance logic changes are documented in the changelog</li>
                            <li>FTL category definitions are reviewed against current FDA publications</li>
                            <li>Customers are responsible for confirming their own regulatory interpretation</li>
                        </ul>
                    </div>
                </div>
            </section>
            {/* ─── SUPPORT + ARCHIVE ─── */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
                    <div className={`${card} p-5`}>
                        <h2 className="font-display text-2xl font-bold text-re-text-primary mb-2">Support and escalation</h2>
                        <p className="text-sm text-re-text-muted mb-4">
                            Support posture depends on plan tier. Customers should not rely on ad hoc vendor intervention for statutory retention or a live recall response. Specific availability, latency, RPO, and RTO commitments are negotiated per contract; we do not publish SLA numbers we are not yet measuring against a public status page.
                        </p>
                        <div className="space-y-3">
                            {SUPPORT_CHANNELS.map((channel) => (
                                <div key={channel.tier} className={cardInner}>
                                    <div className="flex items-center justify-between gap-3">
                                        <div className="text-sm font-semibold text-re-text-primary">{channel.tier}</div>
                                        <div className="text-xs text-re-text-disabled">{channel.responseWindow}</div>
                                    </div>
                                    <p className="text-sm text-re-text-muted mt-2">{channel.escalation}</p>
                                    <p className="text-xs text-re-text-disabled mt-2">{channel.notes}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className={`${card} p-5`}>
                        <h2 className="font-display text-2xl font-bold text-re-text-primary mb-2">Scheduled exports</h2>
                        <p className="text-sm text-re-text-muted mb-4">
                            Examples of supported export configurations. Hashing, manifests, run history, and
                            scheduled delivery depend on the configured workflow and customer agreement.
                        </p>
                        <div className="space-y-3">
                            {ARCHIVE_EXPORT_JOBS.map((job) => (
                                <div key={job.id} className={cardInner}>
                                    <div className="text-sm font-semibold text-re-text-primary">{job.name}</div>
                                    <p className="text-sm text-re-text-muted mt-2">
                                        {job.format} · {job.cadence} · {job.destination}
                                    </p>
                                </div>
                            ))}
                        </div>
                        <Link href="/dashboard/export-jobs" className="inline-block mt-4 text-sm text-re-brand hover:opacity-90">
                            Open export jobs →
                        </Link>
                    </div>
                    </div>
                </div>
            </section>
            {/* Subprocessors */}
            <section id="subprocessors" className={`relative z-[2] scroll-mt-24 ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="font-display text-2xl font-bold text-re-text-primary mb-4">Infrastructure and subprocessors</h2>
                    <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                        Third-party services that process or store customer data. This table is rendered from the
                        same shared list used by the public DPA page, but your executed DPA remains the contractual
                        source of truth.
                    </p>
                    <div className="overflow-x-auto">
                        <table className={`w-full border-collapse ${card}`}>
                            <thead>
                                <tr className="border-b border-[var(--re-surface-border)] text-left text-xs uppercase tracking-widest text-re-text-disabled">
                                    <th className="p-3">Provider</th>
                                    <th className="p-3">Use</th>
                                    <th className="p-3">Purpose</th>
                                    <th className="p-3">Data processed</th>
                                    <th className="p-3">Location</th>
                                </tr>
                            </thead>
                            <tbody className="text-sm">
                                {TRUST_SUBPROCESSORS.map((sp) => (
                                    <tr key={sp.name} className="border-b border-[var(--re-surface-border)] last:border-0">
                                        <td className="p-3 font-medium text-re-text-primary">{sp.name}</td>
                                        <td className="p-3 text-re-text-muted">{sp.availabilityLabel}</td>
                                        <td className="p-3 text-re-text-muted">{sp.purpose}</td>
                                        <td className="p-3 text-re-text-muted">{sp.dataProcessed}</td>
                                        <td className="p-3 text-re-text-muted">{sp.location}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <p className="text-xs text-re-text-disabled mt-4">
                        Last reviewed: June 2026. The authoritative subprocessor list for your contract is in your executed DPA; the table above is informational and may lag the DPA. Notice periods for subprocessor changes are set in your agreement.
                    </p>
                </div>
            </section>

            {/* ─── CAPABILITY REGISTRY (collapsible for technical diligence) ─── */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                <details className={`${card} overflow-hidden`}>
                    <summary className="cursor-pointer p-5 flex items-center justify-between gap-4 select-none">
                        <div>
                            <h2 className="font-display text-2xl font-bold text-re-text-primary inline">Full Capability Registry</h2>
                            <span className="text-sm text-re-text-muted ml-2">(for technical diligence)</span>
                        </div>
                        <span className="text-re-text-disabled text-sm shrink-0">Click to expand</span>
                    </summary>
                    <div className="px-5 pb-5">
                        {/* Status model */}
                        <h3 className="text-lg font-bold text-re-text-primary mb-3">Status model</h3>
                        <div className="grid gap-3 md:grid-cols-2 mb-8">
                            {STATUS_SUMMARY.map((item) => (
                                <div key={item.label} className={`${card} p-4`}>
                                    <div className="text-sm font-semibold text-re-text-primary">{item.label}</div>
                                    <p className="text-sm text-re-text-muted mt-1 leading-relaxed">{item.detail}</p>
                                </div>
                            ))}
                        </div>
                        {/* Integration classification */}
                        <h3 className="text-lg font-bold text-re-text-primary mb-3">Integration classification</h3>
                        <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                            Each integration is classified by both delivery mode and integration type. Integration type uses the procurement diligence taxonomy: Standards-Based Ingest / Export, API-Based Custom, File-Based Import, or One-Way Export Adapter.
                        </p>
                        <div className="grid gap-3 md:grid-cols-2 mb-8">
                            {(Object.keys(INTEGRATION_TYPE_LABELS) as IntegrationType[]).map((type) => (
                                <div key={type} className={`${card} p-4`}>
                                    <div className="text-sm font-semibold text-re-text-primary">{INTEGRATION_TYPE_LABELS[type]}</div>
                                    <p className="text-sm text-re-text-muted mt-1">{INTEGRATION_TYPE_DESCRIPTIONS[type]}</p>
                                    <p className="text-xs text-re-text-disabled mt-2">Verify: {INTEGRATION_TYPE_VERIFY[type]}</p>
                                </div>
                            ))}
                        </div>
                        {/* Full capability table */}
                        <div className={`overflow-x-auto ${card}`}>
                            <table className="w-full border-collapse">
                                <thead>
                                    <tr className="border-b border-[var(--re-surface-border)] text-left text-xs uppercase tracking-widest text-re-text-disabled">
                                        <th className="p-3">Capability</th>
                                        <th className="p-3">Status</th>
                                        <th className="p-3">Integration type</th>
                                        <th className="p-3">Delivery mode</th>
                                        <th className="p-3">Customer meaning</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {CAPABILITY_REGISTRY.map((item) => (
                                        <tr key={item.id} className="border-b border-[var(--re-border-subtle)] align-top">
                                            <td className="p-3 text-sm font-medium text-re-text-primary">{item.name}</td>
                                            <td className="p-3 text-sm text-re-text-muted">{STATUS_LABELS[item.status]}</td>
                                            <td className="p-3 text-sm text-re-text-muted">{INTEGRATION_TYPE_LABELS[item.integration_type]}</td>
                                            <td className="p-3 text-sm text-re-text-muted">{DELIVERY_MODE_LABELS[item.delivery_mode]}</td>
                                            <td className="p-3 text-sm text-re-text-muted">{item.customer_copy}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </details>
            </section>
        </div>
    );
}
