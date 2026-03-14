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
        url: 'https://www.regengine.co/trust',
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

export default function TrustCenterPage() {
    const capabilityCount = CAPABILITY_REGISTRY.length;

    return (
        <div className="re-page">
            <section className="relative z-[2] max-w-[860px] mx-auto pt-20 px-6 pb-14">
                <span className="text-[11px] font-mono font-medium text-re-text-disabled tracking-widest uppercase">
                    Trust Center
                </span>
                <h1 className="text-4xl font-bold text-re-text-primary mt-4 mb-4 leading-tight">
                    Customer diligence, without the guesswork
                </h1>
                <p className="text-base text-re-text-muted leading-relaxed max-w-[720px]">
                    RegEngine is a traceability evidence layer, not a magical system-of-record replacement.
                    This page explains product status, delivery modes, retention expectations, support posture,
                    and which diligence materials are public versus provided on request.
                </p>
                <div className="mt-6 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                        <div className="text-xs uppercase tracking-widest text-re-text-disabled">Capability Registry</div>
                        <div className="mt-2 text-2xl font-bold text-re-text-primary">{capabilityCount}</div>
                        <div className="text-sm text-re-text-muted mt-1">Customer-visible entries rendered from one shared status model</div>
                    </div>
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                        <div className="text-xs uppercase tracking-widest text-re-text-disabled">Retention Posture</div>
                        <div className="mt-2 text-2xl font-bold text-re-text-primary">90 days</div>
                        <div className="text-sm text-re-text-muted mt-1">Post-cancellation window before deletion unless customers export or archive externally</div>
                    </div>
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                        <div className="text-xs uppercase tracking-widest text-re-text-disabled">Data Residency</div>
                        <div className="mt-2 text-2xl font-bold text-re-text-primary">US</div>
                        <div className="text-sm text-re-text-muted mt-1">Default hosting posture is US-based infrastructure for current deployments</div>
                    </div>
                </div>
            </section>

            <section className="relative z-[2] max-w-[980px] mx-auto px-6 pb-14">
                <h2 className="text-2xl font-bold text-re-text-primary mb-4">Status model</h2>
                <div className="grid gap-3 md:grid-cols-2">
                    {STATUS_SUMMARY.map((item) => (
                        <div key={item.label} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                            <div className="text-sm font-semibold text-re-text-primary">{item.label}</div>
                            <p className="text-sm text-re-text-muted mt-1 leading-relaxed">{item.detail}</p>
                        </div>
                    ))}
                </div>
            </section>

            <section className="relative z-[2] border-t border-white/[0.06] bg-white/[0.01]">
                <div className="max-w-[980px] mx-auto py-14 px-6">
                    <h2 className="text-2xl font-bold text-re-text-primary mb-3">What RegEngine actually does in your stack</h2>
                    <p className="text-sm text-re-text-muted max-w-[720px] mb-6">
                        RegEngine ingests upstream traceability data, normalizes it into FSMA workflows, attaches audit-integrity metadata,
                        and prepares regulator- or retailer-ready exports. It still depends on upstream data quality, stable identities,
                        and review of missing or conflicting KDEs.
                    </p>
                    <div className="grid gap-4 md:grid-cols-2">
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5">
                            <h3 className="text-sm font-semibold text-re-text-primary">Operational realities</h3>
                            <ul className="mt-3 space-y-2 text-sm text-re-text-muted">
                                <li>Source-system fields must be mapped into FSMA CTE and KDE structures.</li>
                                <li>Lot codes, GLNs, product IDs, and facility identities have to be normalized.</li>
                                <li>Missing KDEs and conflicting facility matches still require human review.</li>
                                <li>Cryptographic hashing proves integrity after ingest, not truth of upstream data entry.</li>
                            </ul>
                        </div>
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5">
                            <h3 className="text-sm font-semibold text-re-text-primary">Retention and support boundaries</h3>
                            <ul className="mt-3 space-y-2 text-sm text-re-text-muted">
                                <li>Customers should schedule recurring exports and maintain off-platform archives from day one.</li>
                                <li>Public support windows are not a substitute for recall-readiness operations.</li>
                                <li>Enterprise escalation and SLA terms are contractual, not implied by public pricing copy.</li>
                                <li>Security and diligence materials are a mix of public pages and request/NDA workflows.</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </section>

            <section className="relative z-[2] max-w-[980px] mx-auto py-14 px-6">
                <div className="flex items-end justify-between gap-4 mb-5">
                    <div>
                        <h2 className="text-2xl font-bold text-re-text-primary">Artifacts and diligence materials</h2>
                        <p className="text-sm text-re-text-muted mt-1">Public pages are linked directly. Request and NDA items route through contact.</p>
                    </div>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                    {TRUST_ARTIFACTS.map((artifact) => (
                        <div key={artifact.id} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
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
            </section>

            <section className="relative z-[2] border-t border-white/[0.06] bg-white/[0.01]">
                <div className="max-w-[980px] mx-auto py-14 px-6">
                    <h2 className="text-2xl font-bold text-re-text-primary mb-4">Integration classification</h2>
                    <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                        Each integration is classified by both delivery mode and integration type. Integration type uses the procurement diligence taxonomy: Native Bidirectional, API-Based Custom, File-Based Import, or One-Way Export Adapter.
                    </p>

                    <div className="grid gap-3 md:grid-cols-2 mb-8">
                        {(Object.keys(INTEGRATION_TYPE_LABELS) as IntegrationType[]).map((type) => (
                            <div key={type} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                                <div className="text-sm font-semibold text-re-text-primary">{INTEGRATION_TYPE_LABELS[type]}</div>
                                <p className="text-sm text-re-text-muted mt-1">{INTEGRATION_TYPE_DESCRIPTIONS[type]}</p>
                                <p className="text-xs text-re-text-disabled mt-2">Verify: {INTEGRATION_TYPE_VERIFY[type]}</p>
                            </div>
                        ))}
                    </div>

                    <div className="overflow-x-auto rounded-xl border border-white/[0.06] bg-white/[0.02]">
                        <table className="w-full border-collapse">
                            <thead>
                                <tr className="border-b border-white/[0.06] text-left text-xs uppercase tracking-widest text-re-text-disabled">
                                    <th className="p-3">Capability</th>
                                    <th className="p-3">Status</th>
                                    <th className="p-3">Integration type</th>
                                    <th className="p-3">Delivery mode</th>
                                    <th className="p-3">Customer meaning</th>
                                </tr>
                            </thead>
                            <tbody>
                                {CAPABILITY_REGISTRY.map((item) => (
                                    <tr key={item.id} className="border-b border-white/[0.04] align-top">
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
            </section>

            <section className="relative z-[2] border-t border-white/[0.06] bg-white/[0.01]">
                <div className="max-w-[980px] mx-auto py-14 px-6">
                    <h2 className="text-2xl font-bold text-re-text-primary mb-4">Source-of-truth positioning</h2>
                    <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                        RegEngine is a compliance evidence layer, not a system-of-record replacement. This distinction drives retention, audit ownership, and liability boundaries.
                    </p>
                    <div className="grid gap-3 md:grid-cols-3">
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                            <div className="text-sm font-semibold text-re-text-primary">Evidence layer (current posture)</div>
                            <p className="text-sm text-re-text-muted mt-2">You own the data and compliance posture. RegEngine documents, normalizes, and exports it. Audit response liability remains with the customer.</p>
                        </div>
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                            <div className="text-sm font-semibold text-re-text-primary">Not a system of record</div>
                            <p className="text-sm text-re-text-muted mt-2">RegEngine does not replace your ERP, WMS, or operational food safety system. Source data quality is inherited from upstream systems.</p>
                        </div>
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                            <div className="text-sm font-semibold text-re-text-primary">Full data portability</div>
                            <p className="text-sm text-re-text-muted mt-2">All CTE events, KDE fields, lot records, and supplier relationships are exportable in EPCIS 2.0 JSON-LD, FDA sortable spreadsheet, or CSV.</p>
                        </div>
                    </div>
                </div>
            </section>

            <section className="relative z-[2] max-w-[980px] mx-auto py-14 px-6">
                <h2 className="text-2xl font-bold text-re-text-primary mb-4">Data portability and exit rights</h2>
                <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                    Export your data means more than downloading a CSV. RegEngine provides complete, integrity-verified exports that can reconstitute compliance records without vendor assistance.
                </p>
                <div className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                        <div className="text-sm font-semibold text-re-text-primary">Export formats</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>GS1 EPCIS 2.0 JSON-LD (industry standard)</li>
                            <li>FDA 21 CFR 1.1455 sortable spreadsheet</li>
                            <li>CSV with all CTE/KDE fields</li>
                            <li>Audit evidence bundle with manifest hashing</li>
                        </ul>
                    </div>
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                        <div className="text-sm font-semibold text-re-text-primary">Integrity and chain of custody</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>SHA-256 hash chain verification on all CTE records</li>
                            <li>Timestamped export manifests for audit trail</li>
                            <li>Export history log with verification endpoint</li>
                            <li>Records are self-describing and re-importable</li>
                        </ul>
                    </div>
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                        <div className="text-sm font-semibold text-re-text-primary">Automated export scheduling</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>Daily, weekly, or monthly export cadence</li>
                            <li>Object storage archive or downloadable bundle</li>
                            <li>Manifest hash included in every export run</li>
                            <li>Failed export runs flagged for re-processing</li>
                        </ul>
                    </div>
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                        <div className="text-sm font-semibold text-re-text-primary">Retention and deletion</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>90-day post-cancellation retention window</li>
                            <li>Customer-controlled archive exports from day one</li>
                            <li>Deletion policy documented in contract terms</li>
                            <li>No vendor lock-in on record format or schema</li>
                        </ul>
                    </div>
                </div>
            </section>

            <section className="relative z-[2] border-t border-white/[0.06] bg-white/[0.01]">
                <div className="max-w-[980px] mx-auto py-14 px-6">
                    <h2 className="text-2xl font-bold text-re-text-primary mb-4">Upstream data quality controls</h2>
                    <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                        RegEngine validates incoming CTE/KDE records at ingestion time. Incomplete or non-compliant records are rejected or flagged before they enter the compliance evidence chain.
                    </p>
                    <div className="grid gap-3 md:grid-cols-2">
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                            <div className="text-sm font-semibold text-re-text-primary">Ingestion validation</div>
                            <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                                <li>Per-CTE-type required KDE validation (7 CTE types)</li>
                                <li>GLN format and GS1 check-digit verification</li>
                                <li>Timestamp bounds checking (90-day historical, 24-hour future)</li>
                                <li>Unit of measure validation against FSMA 204 standard units</li>
                                <li>Location requirement validation per CTE</li>
                            </ul>
                        </div>
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                            <div className="text-sm font-semibold text-re-text-primary">Rejection and flagging</div>
                            <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                                <li>Missing required KDEs trigger event rejection with detailed error messages</li>
                                <li>Compliance alerts generated for obligation gaps</li>
                                <li>Batch deduplication prevents duplicate CTE submissions</li>
                                <li>Rejected events returned with status and actionable error detail</li>
                            </ul>
                        </div>
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                            <div className="text-sm font-semibold text-re-text-primary">Supplier data quality scoring</div>
                            <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                                <li>Per-supplier KDE completeness rate tracking</li>
                                <li>Drift detection for format changes and quality degradation</li>
                                <li>Supplier health dashboard sorted by alert severity</li>
                                <li>Volume anomaly detection for unusual submission patterns</li>
                            </ul>
                        </div>
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                            <div className="text-sm font-semibold text-re-text-primary">Compliance readiness scoring</div>
                            <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                                <li>Six-dimensional score: chain integrity, KDE completeness, CTE coverage, obligation coverage, product coverage, export readiness</li>
                                <li>Letter grade A-F with detailed breakdown</li>
                                <li>Actionable next steps for score improvement</li>
                                <li>Current calculation from the tenant data available in the active workspace</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </section>

            <section className="relative z-[2] max-w-[980px] mx-auto py-14 px-6">
                <h2 className="text-2xl font-bold text-re-text-primary mb-4">Regulatory interpretation tracking</h2>
                <p className="text-sm text-re-text-muted mb-6 max-w-[720px]">
                    FSMA 204 compliance logic embeds vendor interpretation of FDA guidance. RegEngine tracks and documents which guidance versions inform its validation rules, export formats, and compliance algorithms.
                </p>
                <div className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                        <div className="text-sm font-semibold text-re-text-primary">Current regulatory basis</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>FDA Final Rule: Requirements for Additional Traceability Records (21 CFR Part 1, Subpart S)</li>
                            <li>Compliance date: July 20, 2028 (extended from original January 2026)</li>
                            <li>Food Traceability List (FTL): 23 categories, last updated November 2022</li>
                            <li>FDA Guidance: Key Data Elements — March 2024 draft</li>
                        </ul>
                    </div>
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                        <div className="text-sm font-semibold text-re-text-primary">Update mechanism</div>
                        <ul className="mt-2 space-y-1 text-sm text-re-text-muted">
                            <li>Validation rules versioned with FDA guidance reference</li>
                            <li>Compliance logic updates tracked in release notes</li>
                            <li>FTL category definitions updated when FDA publishes changes</li>
                            <li>Customer notification for material compliance logic changes</li>
                        </ul>
                    </div>
                </div>
            </section>

            <section className="relative z-[2] border-t border-white/[0.06] bg-white/[0.01]">
                <div className="max-w-[980px] mx-auto py-14 px-6">
                    <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5">
                        <h2 className="text-2xl font-bold text-re-text-primary mb-2">Support and escalation</h2>
                        <p className="text-sm text-re-text-muted mb-4">
                            Support posture depends on plan tier. Customers should not rely on ad hoc vendor intervention to satisfy statutory retention or a live recall response.
                        </p>
                        <div className="space-y-3">
                            {SUPPORT_CHANNELS.map((channel) => (
                                <div key={channel.tier} className="rounded-lg border border-white/[0.06] bg-black/10 p-4">
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
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5">
                        <h2 className="text-2xl font-bold text-re-text-primary mb-2">Archive posture</h2>
                        <p className="text-sm text-re-text-muted mb-4">
                            The current product interface shows the export-job contract pattern: scheduled bundle configuration, manifest hashing, and external archive destinations. Persistent backend scheduling is separate follow-on work.
                        </p>
                        <div className="space-y-3">
                            {ARCHIVE_EXPORT_JOBS.map((job) => (
                                <div key={job.id} className="rounded-lg border border-white/[0.06] bg-black/10 p-4">
                                    <div className="flex items-center justify-between gap-3">
                                        <div className="text-sm font-semibold text-re-text-primary">{job.name}</div>
                                        <div className="text-[10px] uppercase tracking-widest text-re-text-disabled">{job.status.replaceAll('_', ' ')}</div>
                                    </div>
                                    <p className="text-sm text-re-text-muted mt-2">
                                        {job.format} · {job.cadence} · {job.destination}
                                    </p>
                                    <p className="text-xs text-re-text-disabled mt-2">
                                        Last run: {job.lastRun} · Next run: {job.nextRun}
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
        </div>
    );
}
