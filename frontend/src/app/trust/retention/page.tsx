import type { Metadata } from 'next';
import Link from 'next/link';
import {
    ArrowLeft,
    ArrowRight,
    Calendar,
    Clock,
    Download,
    FileCheck,
    FolderArchive,
    Hash,
    HardDrive,
    RefreshCw,
    ShieldCheck,
    Timer,
    Trash2,
} from 'lucide-react';

export const metadata: Metadata = {
    title: 'Retention & Export Guidance | RegEngine',
    description:
        'Data retention windows, export scheduling, format guarantees, and off-platform archive recommendations for FSMA 204 compliance.',
    openGraph: {
        title: 'Retention & Export Guidance | RegEngine',
        description: 'Retention windows, export formats, and archive guidance for RegEngine FSMA 204.',
        url: 'https://regengine.co/trust/retention',
        type: 'website',
    },
};
const card = 'rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-sm';
const sectionAlt = 'border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]';

const RETENTION_TIMELINE = [
    {
        phase: 'Active subscription',
        duration: 'Ongoing',
        icon: ShieldCheck,
        color: 'bg-re-brand/15 text-re-brand',
        detail: 'Access to the active workspace and configured export functions during the subscription term. Backup and recovery posture depend on the active hosting configuration.',
    },
    {
        phase: 'Post-cancellation window',
        duration: 'Contract-defined window',
        icon: Clock,
        color: 'bg-re-warning-muted0/15 text-re-warning',
        detail: 'The post-cancellation export window is set by the active commercial agreement and operating workflow for the workspace.',
    },
    {
        phase: 'Deletion',
        duration: 'After the contract-defined window',
        icon: Trash2,
        color: 'bg-re-danger-muted0/15 text-re-danger',
        detail: 'All tenant data is permanently deleted from production databases and backups. Deletion is irreversible. RegEngine cannot recover data after this point.',
    },
];
const EXPORT_FORMATS = [
    {
        format: 'EPCIS 2.0 JSON-LD',
        standard: 'GS1 industry standard',
        useCase: 'Interoperable with other FSMA 204 platforms, trading partner systems, and FDA submissions',
        icon: FileCheck,
    },
    {
        format: 'FDA sortable spreadsheet',
        standard: '21 CFR 1.1455',
        useCase: 'The exact format FDA inspectors expect during a traceability investigation or recall',
        icon: Download,
    },
    {
        format: 'CSV with all CTE/KDE fields',
        standard: 'Universal',
        useCase: 'For data warehouse import, internal analytics, or migration to another compliance tool',
        icon: HardDrive,
    },
    {
        format: 'Audit evidence bundle',
        standard: 'RegEngine manifest',
        useCase: 'Complete export with SHA-256 manifest hash for tamper-evident archival and audit support',
        icon: Hash,
    },
];
export default function RetentionPage() {
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
                    Retention &amp; Export
                </span>
                <h1 className="font-display text-4xl font-bold text-[var(--re-text-primary)] mt-4 mb-4 leading-tight">
                    Your data, your archives, your timeline
                </h1>
                <p className="text-base text-[var(--re-text-muted)] leading-relaxed max-w-[720px]">
                    FSMA 204 requires food companies to maintain traceability records for at least two years.
                    This page explains RegEngine&apos;s retention windows, export formats, and why you should maintain off-platform archives from day one.
                </p>
            </section>

            {/* Retention timeline */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">                    <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-2">Retention timeline</h2>
                    <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                        RegEngine retains data for the duration of your subscription plus a contract-defined post-cancellation export window. Specific durations are set in your commercial agreement.
                    </p>
                    <div className="space-y-3">
                        {RETENTION_TIMELINE.map((phase) => {
                            const Icon = phase.icon;
                            return (
                                <div key={phase.phase} className={`${card} p-5 flex gap-4`}>
                                    <div className={`w-10 h-10 rounded-xl ${phase.color} flex items-center justify-center flex-shrink-0`}>
                                        <Icon className="h-5 w-5" />
                                    </div>
                                    <div>
                                        <div className="flex items-center gap-3">
                                            <div className="text-sm font-semibold text-[var(--re-text-primary)]">{phase.phase}</div>
                                            <span className="text-xs font-medium text-[var(--re-text-disabled)] uppercase tracking-wider">{phase.duration}</span>
                                        </div>
                                        <p className="text-sm text-[var(--re-text-muted)] mt-1.5 leading-relaxed">{phase.detail}</p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </section>

            {/* FSMA retention obligation */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-4">Why off-platform archives matter</h2>
                <div className="grid gap-4 md:grid-cols-2">                    <div className={`${card} p-5`}>
                        <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">FSMA 204 requires 2-year retention</h3>
                        <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                            Under 21 CFR 1.1455, food companies must maintain traceability records for at least two years from the date they were created.
                            RegEngine is a compliance evidence layer, not a long-term archive. Your subscription may not span two years from initial data ingestion, so off-platform retention remains your responsibility.
                        </p>
                    </div>
                    <div className={`${card} p-5`}>
                        <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">Vendor continuity risk</h3>
                        <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                            No vendor should be a single point of failure for regulatory records. Schedule recurring exports and store them in your own infrastructure
                            from day one. If RegEngine is unavailable during an FDA investigation, your off-platform archives satisfy the requirement independently.
                        </p>
                    </div>
                    <div className={`${card} p-5`}>
                        <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">Export integrity verification</h3>
                        <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                            Export bundles are designed to include a SHA-256 manifest hash so records can be verified outside the product UI. Final artifact details depend on the export workflow configured for your deployment.
                        </p>
                    </div>
                    <div className={`${card} p-5`}>
                        <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">No vendor lock-in</h3>
                        <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                            Exports are intended to use industry-standard formats such as EPCIS 2.0, FDA spreadsheet layouts, and CSV. Exact format coverage depends on the workflow enabled for your account.
                        </p>
                    </div>
                </div>
            </section>
            {/* Export formats */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-2">Export formats</h2>
                    <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                        These are the export formats currently supported. Exact availability depends on plan, workflow, and deployment configuration.
                    </p>
                    <div className="grid gap-4 md:grid-cols-2">
                        {EXPORT_FORMATS.map((fmt) => {
                            const Icon = fmt.icon;
                            return (
                                <div key={fmt.format} className={`${card} p-5`}>
                                    <div className="flex items-center gap-2.5 mb-2">
                                        <Icon className="h-4 w-4 text-[var(--re-brand)]" />
                                        <div className="text-sm font-semibold text-[var(--re-text-primary)]">{fmt.format}</div>
                                    </div>
                                    <div className="text-xs text-[var(--re-text-disabled)] uppercase tracking-wider mb-2">{fmt.standard}</div>
                                    <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">{fmt.useCase}</p>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </section>

            {/* Export scheduling */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-4">Export scheduling</h2>                <div className="grid gap-3 md:grid-cols-3">
                        {[
                            { Icon: Calendar, label: 'Cadence options', value: 'Scoped per deployment', detail: 'Export frequency depends on the workflow configured for your account' },
                            { Icon: FolderArchive, label: 'Destinations', value: 'Varies by workflow', detail: 'Archive delivery may use object storage or downloadable bundles' },
                            { Icon: Hash, label: 'Integrity', value: 'Manifest hashing', detail: 'Integrity metadata is part of the target export design' },
                            { Icon: RefreshCw, label: 'Retry', value: 'Workflow dependent', detail: 'Retry behavior depends on the delivery path in use' },
                            { Icon: Timer, label: 'History', value: 'Tracked where enabled', detail: 'Export history visibility depends on the configured workflow' },
                            { Icon: Download, label: 'On-demand', value: 'Available in supported flows', detail: 'Manual export availability depends on the surfaces enabled for your plan' },
                        ].map((item) => {
                        const Icon = item.Icon;
                        return (
                            <div key={item.label} className={`${card} p-4`}>
                                <div className="flex items-center gap-2 mb-2">
                                    <Icon className="h-4 w-4 text-[var(--re-text-disabled)]" />
                                    <div className="text-xs uppercase tracking-widest text-[var(--re-text-disabled)]">{item.label}</div>
                                </div>
                                <div className="text-lg font-bold text-[var(--re-text-primary)]">{item.value}</div>
                                <div className="text-sm text-[var(--re-text-muted)] mt-1">{item.detail}</div>
                            </div>
                        );
                    })}
                </div>
            </section>
            {/* Recommendation */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[860px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <div className={`${card} p-6 border-[var(--re-brand)]/20`}>
                        <h3 className="text-lg font-bold text-[var(--re-text-primary)] mb-2">Our recommendation</h3>
                        <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                            Set up weekly automated exports to your own object storage within the first week of onboarding.
                            Use the audit evidence bundle format — it ships with a SHA-256 manifest so records can be verified out-of-band. Cryptographic signature verification across the message bus is rolling out.
                            This ensures you meet FSMA 204&apos;s two-year retention requirement regardless of your RegEngine subscription status.
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-3 justify-center mt-8">
                        <Link href="/dashboard/export-jobs">
                            <span className="inline-flex items-center gap-1.5 text-sm text-[var(--re-brand)] hover:opacity-80 transition-opacity">
                                Configure exports <ArrowRight className="h-3.5 w-3.5" />
                            </span>
                        </Link>
                        <Link href="/trust">
                            <span className="inline-flex items-center gap-1.5 text-sm text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors">
                                Trust Center <ArrowRight className="h-3.5 w-3.5" />
                            </span>
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
