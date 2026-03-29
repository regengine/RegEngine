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
        description: 'Retention and export posture for RegEngine FSMA 204 compliance platform.',
        url: 'https://www.regengine.co/trust/retention',
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
        color: 'bg-emerald-500/15 text-emerald-400',
        detail: 'Full access to all CTE events, KDE records, compliance scores, audit logs, and export functions. Data is continuously backed up with point-in-time recovery.',
    },
    {
        phase: 'Post-cancellation window',
        duration: '90 days',
        icon: Clock,
        color: 'bg-amber-500/15 text-amber-400',
        detail: 'Read-only access to your workspace. All export functions remain available. This is your window to extract everything you need before deletion.',
    },
    {
        phase: 'Deletion',
        duration: 'After 90 days',
        icon: Trash2,
        color: 'bg-red-500/15 text-red-400',
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
        useCase: 'Complete export with SHA-256 manifest hash for tamper-evident archival and regulatory proof',
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
                <h1 className="text-4xl font-bold text-[var(--re-text-primary)] mt-4 mb-4 leading-tight">
                    Your data, your archives, your timeline
                </h1>
                <p className="text-base text-[var(--re-text-muted)] leading-relaxed max-w-[720px]">
                    FSMA 204 requires food companies to maintain traceability records for at least two years.
                    This page explains RegEngine&apos;s retention windows, export formats, and why you should maintain off-platform archives from day one.
                </p>
            </section>

            {/* Retention timeline */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">Retention timeline</h2>
                    <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                        RegEngine retains your data for the duration of your subscription plus a 90-day post-cancellation window. After that, data is permanently deleted.
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
                <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-4">Why off-platform archives matter</h2>
                <div className="grid gap-4 md:grid-cols-2">                    <div className={`${card} p-5`}>
                        <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">FSMA 204 requires 2-year retention</h3>
                        <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                            Under 21 CFR 1.1455, food companies must maintain traceability records for at least two years from the date they were created.
                            RegEngine is a compliance evidence layer, not a long-term archive. Your subscription may not span two years from initial data ingestion.
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
                            Every export bundle includes a SHA-256 manifest hash. You can verify that exported records were not modified after export — without contacting RegEngine
                            or requiring any vendor access. Records are self-describing and re-importable.
                        </p>
                    </div>
                    <div className={`${card} p-5`}>
                        <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">No vendor lock-in</h3>
                        <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                            Exports use industry-standard formats (EPCIS 2.0, FDA spreadsheet, CSV). Your data is portable to any other system without
                            proprietary conversion. Schema documentation is included in every export bundle.
                        </p>
                    </div>
                </div>
            </section>
            {/* Export formats */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">Export formats</h2>
                    <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                        All formats include complete CTE/KDE records and can reconstitute compliance evidence without vendor assistance.
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
                <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-4">Automated export scheduling</h2>                <div className="grid gap-3 md:grid-cols-3">
                    {[
                        { Icon: Calendar, label: 'Cadence options', value: 'Daily / Weekly / Monthly', detail: 'Set your export frequency per format and destination' },
                        { Icon: FolderArchive, label: 'Destinations', value: 'Download or object storage', detail: 'Archive to S3, GCS, or download bundles on demand' },
                        { Icon: Hash, label: 'Integrity', value: 'SHA-256 manifest', detail: 'Every export run includes a tamper-evident manifest hash' },
                        { Icon: RefreshCw, label: 'Retry', value: 'Automatic', detail: 'Failed exports are flagged and retried on next cycle' },
                        { Icon: Timer, label: 'History', value: 'Full log', detail: 'Export history with timestamps, sizes, and verification status' },
                        { Icon: Download, label: 'On-demand', value: 'Any time', detail: 'Manual export available regardless of schedule' },
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
                            Use the audit evidence bundle format — it includes the manifest hash and is self-verifying.
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
