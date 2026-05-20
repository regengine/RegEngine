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
        label: 'GA',
        detail: 'Core FSMA workspace, exports, dashboard flows, and public documentation surfaces.',
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
];
/* Card style helper — uses CSS variables for light+dark mode */
const card = 'rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-sm';
const cardInner = 'rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-4';
const sectionAlt = 'border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]';

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
                </p>                <div className="mt-6 grid gap-3 sm:grid-cols-3">
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
                        <div className="mt-2 text-2xl font-bold text-re-text-primary">US</div>
                        <div className="text-sm text-re-text-muted mt-1">US-based infrastructure.</div>
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
                            <p className="text-sm text-re-text-muted mt-2">All CTE events, KDE fields, lot records, and supplier relationships are exportable in EPCIS 2.0 JSON-LD, FDA sortable spreadsheet, or CSV.</p>
                        </div>
                        <div className={`${card} p-4`}>
                            <div className="text-sm font-semibold text-re-text-primary">Tenant isolation</div>
                            <p className="text-sm text-re-text-muted mt-2">PostgreSQL row-level policies and authenticated tenant context prevent cross-tenant reads. Identity-resolution and graph-layer hardening is in progress; details available under NDA.</p>
                        </div>
                    </div>
                </div>
            </section>
            {/* ─── RETENTION + SUPPORT BOUNDARIES (moved up) ─── */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                <h2 className="font-display text-2xl font-bold text-re-text-primary mb-3">What RegEngine actually does in your stack</h2>
                <p className="text-sm text-re-text-muted max-w-[720px] mb-6">
                    RegEngine ingests upstream traceability data, normalizes it into FSMA workflows, attaches audit-integrity metadata,
                    and prepares regulator- or retailer-ready exports. It still depends on upstream data quality, stable identities,
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
                    <div className="text-sm font-semibold text-re-text-primary">Verify any export yourself</div>
                    <p className="text-sm text-re-text-muted mt-2">
                        Drop a bundle into <Link href="/verify" className="text-re-brand hover:opacity-90">/verify</Link> or download a synthetic sample at <Link href="/proof" className="text-re-brand hover:opacity-90">/proof</Link>.
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
                            <li>FDA 21 CFR 1.1455 sortable spreadsheet</li>
                            <li>CSV with all CTE/KDE fields</li>
                            <li>Audit evidence bundle with manifest hashing</li>
                        </ul>
                    </div>
                    <div className={`${card} p-4`}>
                        <div className="text-sm font-semibold text-re-text-primary">Integrity and chain of custody</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>Events are SHA-256 hashed and chain-linked at ingest</li>
                            <li>Timestamped manifests are generated for export bundles</li>
                            <li>Public verification endpoint at <Link href="/verify" className="text-re-brand hover:opacity-90">/verify</Link></li>
                            <li>Downstream message-bus signature verification is rolling out across consumers and is not yet strict-mode by default</li>
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
                            <li>Compliance date: July 20, 2028 (extended from original January 2026)</li>
                            <li>Food Traceability List (FTL): 23 categories, per FDA FTL current as of April 2026</li>
                            <li>FDA Guidance: Key Data Elements — March 2024 draft</li>
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
                            Support posture depends on plan tier. Customers should not rely on ad hoc vendor intervention to satisfy statutory retention or a live recall response. Specific availability, latency, RPO, and RTO commitments are negotiated per contract; we do not publish SLA numbers we are not yet measuring against a public status page.
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
                            Examples of supported export configurations. Each scheduled export produces a
                            SHA-256 manifest for independent verification. Real run history for your workspace
                            is available in the dashboard.
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
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="font-display text-2xl font-bold text-re-text-primary mb-4">Infrastructure and subprocessors</h2>
                    <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                        Third-party services that process or store customer data. The authoritative list for
                        your contract is in your DPA — request the current subprocessor list if you need it
                        for diligence.
                    </p>
                    <div className="overflow-x-auto">
                        <table className={`w-full border-collapse ${card}`}>
                            <thead>
                                <tr className="border-b border-[var(--re-surface-border)] text-left text-xs uppercase tracking-widest text-re-text-disabled">
                                    <th className="p-3">Provider</th>
                                    <th className="p-3">Purpose</th>
                                    <th className="p-3">Data processed</th>
                                    <th className="p-3">Location</th>
                                </tr>
                            </thead>
                            <tbody className="text-sm">
                                <tr className="border-b border-[var(--re-surface-border)]">
                                    <td className="p-3 font-medium text-re-text-primary">Supabase</td>
                                    <td className="p-3 text-re-text-muted">Database, authentication, and row-level security. Supabase Auth password-reset email is routed through Resend as the SMTP transport.</td>
                                    <td className="p-3 text-re-text-muted">Tenant data, user accounts, recipient email for auth flows</td>
                                    <td className="p-3 text-re-text-muted">US (AWS us-east-2)</td>
                                </tr>
                                <tr className="border-b border-[var(--re-surface-border)]">
                                    <td className="p-3 font-medium text-re-text-primary">Railway</td>
                                    <td className="p-3 text-re-text-muted">Backend service hosting</td>
                                    <td className="p-3 text-re-text-muted">API request processing</td>
                                    <td className="p-3 text-re-text-muted">US (GCP)</td>
                                </tr>
                                <tr className="border-b border-[var(--re-surface-border)]">
                                    <td className="p-3 font-medium text-re-text-primary">Vercel</td>
                                    <td className="p-3 text-re-text-muted">Frontend hosting, API proxy</td>
                                    <td className="p-3 text-re-text-muted">Authenticated requests in transit</td>
                                    <td className="p-3 text-re-text-muted">US (AWS)</td>
                                </tr>
                                <tr className="border-b border-[var(--re-surface-border)]">
                                    <td className="p-3 font-medium text-re-text-primary">Sentry</td>
                                    <td className="p-3 text-re-text-muted">Error monitoring and session replay</td>
                                    <td className="p-3 text-re-text-muted">Backend stack traces; frontend errors; replays of authenticated sessions</td>
                                    <td className="p-3 text-re-text-muted">US</td>
                                </tr>
                                <tr className="border-b border-[var(--re-surface-border)]">
                                    <td className="p-3 font-medium text-re-text-primary">Resend</td>
                                    <td className="p-3 text-re-text-muted">Transactional email (invites, verifications, and Supabase Auth password-reset email via SMTP transport)</td>
                                    <td className="p-3 text-re-text-muted">Recipient email, invite metadata, and auth-flow recipient email</td>
                                    <td className="p-3 text-re-text-muted">US</td>
                                </tr>
                                <tr className="border-b border-[var(--re-surface-border)]">
                                    <td className="p-3 font-medium text-re-text-primary">PostHog</td>
                                    <td className="p-3 text-re-text-muted">Product analytics (post-consent)</td>
                                    <td className="p-3 text-re-text-muted">Product events after user consent</td>
                                    <td className="p-3 text-re-text-muted">US</td>
                                </tr>
                                <tr className="border-b border-[var(--re-surface-border)]">
                                    <td className="p-3 font-medium text-re-text-primary">OpenAI</td>
                                    <td className="p-3 text-re-text-muted">LLM extraction and label-image vision</td>
                                    <td className="p-3 text-re-text-muted">Document text and uploaded label images</td>
                                    <td className="p-3 text-re-text-muted">US (multi-region)</td>
                                </tr>
                                <tr className="border-b border-[var(--re-surface-border)]">
                                    <td className="p-3 font-medium text-re-text-primary">Google Cloud / Vertex AI</td>
                                    <td className="p-3 text-re-text-muted">Gemini-based extraction</td>
                                    <td className="p-3 text-re-text-muted">Document text submitted for extraction</td>
                                    <td className="p-3 text-re-text-muted">us-central1</td>
                                </tr>
                                <tr className="border-b border-[var(--re-surface-border)]">
                                    <td className="p-3 font-medium text-re-text-primary">Stripe</td>
                                    <td className="p-3 text-re-text-muted">Payment processing</td>
                                    <td className="p-3 text-re-text-muted">Billing identifiers and contact email</td>
                                    <td className="p-3 text-re-text-muted">US</td>
                                </tr>
                                <tr>
                                    <td className="p-3 font-medium text-re-text-primary">Redpanda</td>
                                    <td className="p-3 text-re-text-muted">Kafka-compatible event streaming</td>
                                    <td className="p-3 text-re-text-muted">Ingested events in transit</td>
                                    <td className="p-3 text-re-text-muted">US</td>
                                </tr>
                                <tr>
                                    <td className="p-3 font-medium text-re-text-primary">Cloudflare R2</td>
                                    <td className="p-3 text-re-text-muted">Object storage for ingested document artifacts</td>
                                    <td className="p-3 text-re-text-muted">Raw uploads, normalized JSON, parsed text extracts</td>
                                    <td className="p-3 text-re-text-muted">United States / global edge</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <p className="text-xs text-re-text-disabled mt-4">
                        Last reviewed: May 2026. The authoritative subprocessor list for your contract is in your DPA; the table above is informational and may lag the DPA. Notice periods for subprocessor changes are set in your agreement.
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
                            Each integration is classified by both delivery mode and integration type. Integration type uses the procurement diligence taxonomy: Native Bidirectional, API-Based Custom, File-Based Import, or One-Way Export Adapter.
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
