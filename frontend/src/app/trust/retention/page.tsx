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
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Section } from '@/components/layout/section';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';

export const metadata: Metadata = {
    title: 'Retention & Export Guidance | RegEngine',
    description:
        'Data retention windows, export scheduling, format availability, and off-platform archive recommendations for FSMA 204 compliance.',
    openGraph: {
        title: 'Retention & Export Guidance | RegEngine',
        description: 'Retention windows, export formats, and archive guidance for RegEngine FSMA 204.',
        url: 'https://regengine.co/trust/retention',
        type: 'website',
    },
};

const RETENTION_TIMELINE = [
    {
        phase: 'Active subscription',
        duration: 'Ongoing',
        icon: ShieldCheck,
        detail: 'Access to the active workspace and configured export functions during the subscription term. Backup and recovery posture depend on the active hosting configuration.',
    },
    {
        phase: 'Post-cancellation window',
        duration: 'Contract-defined window',
        icon: Clock,
        detail: 'The post-cancellation export window is set by the active commercial agreement and operating workflow for the workspace.',
    },
    {
        phase: 'Deletion',
        duration: 'After the contract-defined window',
        icon: Trash2,
        detail: 'Tenant data is scheduled for deletion from active systems after the contract-defined window. Provider backups, immutable logs, and disaster recovery copies expire on their normal cycles, and legal or regulatory holds may require longer retention.',
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
        useCase: 'FDA-oriented sortable spreadsheet aligned to 21 CFR 1.1455 where applicable',
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

const ARCHIVE_NOTES = [
    {
        title: 'FSMA 204 requires 2-year retention',
        body: 'Under 21 CFR 1.1455, food companies must maintain traceability records for at least two years from the date they were created. RegEngine is a compliance evidence layer, not a long-term archive. Your subscription may not span two years from initial data ingestion, so off-platform retention remains your responsibility.',
    },
    {
        title: 'Vendor continuity risk',
        body: 'No vendor should be a single point of failure for regulatory records. Schedule recurring exports and store them in your own infrastructure from day one. If RegEngine is unavailable during an FDA investigation, your off-platform archives help support retrieval and retention obligations.',
    },
    {
        title: 'Export integrity verification',
        body: 'Export bundles are designed to include a SHA-256 manifest hash so records can be verified outside the product UI. Final artifact details depend on the export workflow configured for your deployment.',
    },
    {
        title: 'No vendor lock-in',
        body: 'Exports are intended to use industry-standard formats such as EPCIS 2.0, FDA spreadsheet layouts, and CSV. Format coverage depends on the workflow enabled for your account.',
    },
];

const EXPORT_SCHEDULING = [
    { Icon: Calendar, label: 'Cadence options', value: 'Scoped per deployment', detail: 'Export frequency depends on the workflow configured for your account' },
    { Icon: FolderArchive, label: 'Destinations', value: 'Varies by workflow', detail: 'Archive delivery may use object storage or downloadable bundles' },
    { Icon: Hash, label: 'Integrity', value: 'Manifest hashing', detail: 'Integrity metadata is part of the target export design' },
    { Icon: RefreshCw, label: 'Retry', value: 'Workflow dependent', detail: 'Retry behavior depends on the delivery path in use' },
    { Icon: Timer, label: 'History', value: 'Tracked where enabled', detail: 'Export history visibility depends on the configured workflow' },
    { Icon: Download, label: 'On-demand', value: 'Available in supported flows', detail: 'Manual export availability depends on the surfaces enabled for your plan' },
];

const BACK_LINK =
    'inline-flex items-center gap-1.5 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none';

export default function RetentionPage() {
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
                    eyebrow={<span className="font-mono uppercase">Retention &amp; Export</span>}
                    title="Your data, your archives, your timeline"
                    description="FSMA 204 requires food companies to maintain traceability records for at least two years. This page explains RegEngine's retention windows, export formats, and why you should maintain off-platform archives from day one."
                    className="mb-0 border-b-0 pb-0"
                />
            </Container>

            {/* Retention timeline */}
            <Section
                width="marketing"
                title="Retention timeline"
                description="RegEngine retains data for the duration of your subscription plus a contract-defined post-cancellation export window. Specific durations are set in your commercial agreement."
            >
                <Card className="overflow-hidden">
                    {RETENTION_TIMELINE.map((phase) => {
                        const Icon = phase.icon;
                        return (
                            <div key={phase.phase} className="flex gap-4 border-b border-re-border-subtle p-5 last:border-0">
                                <Icon className="mt-0.5 h-5 w-5 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                <div>
                                    <div className="flex flex-wrap items-center gap-3">
                                        <div className="text-subheading text-re-text-primary">{phase.phase}</div>
                                        <span className="font-mono text-label uppercase text-re-text-muted">{phase.duration}</span>
                                    </div>
                                    <p className="mt-1.5 text-ui text-re-text-secondary">{phase.detail}</p>
                                </div>
                            </div>
                        );
                    })}
                </Card>
            </Section>

            {/* FSMA retention obligation */}
            <Section width="marketing" title="Why off-platform archives matter">
                <div className="grid gap-4 md:grid-cols-2">
                    {ARCHIVE_NOTES.map((note) => (
                        <Card key={note.title} className="p-5">
                            <h3 className="mb-2 text-subheading text-re-text-primary">{note.title}</h3>
                            <p className="text-ui text-re-text-secondary">{note.body}</p>
                        </Card>
                    ))}
                </div>
            </Section>

            {/* Export formats */}
            <Section
                width="marketing"
                title="Export formats"
                description="These are the export formats currently supported. Exact availability depends on plan, workflow, and deployment configuration."
            >
                <div className="grid gap-4 md:grid-cols-2">
                    {EXPORT_FORMATS.map((fmt) => {
                        const Icon = fmt.icon;
                        return (
                            <Card key={fmt.format} className="p-5">
                                <div className="mb-2 flex items-center gap-2.5">
                                    <Icon className="h-4 w-4 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                    <div className="text-subheading text-re-text-primary">{fmt.format}</div>
                                </div>
                                <div className="mb-2 font-mono text-label uppercase text-re-text-muted">{fmt.standard}</div>
                                <p className="text-ui text-re-text-secondary">{fmt.useCase}</p>
                            </Card>
                        );
                    })}
                </div>
            </Section>

            {/* Export scheduling */}
            <Section width="marketing" title="Export scheduling">
                <div className="grid gap-3 md:grid-cols-3">
                    {EXPORT_SCHEDULING.map((item) => {
                        const Icon = item.Icon;
                        return (
                            <Card key={item.label} padding="compact">
                                <div className="mb-2 flex items-center gap-2">
                                    <Icon className="h-4 w-4 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                    <div className="font-mono text-label uppercase text-re-text-muted">{item.label}</div>
                                </div>
                                <div className="text-subheading text-re-text-primary">{item.value}</div>
                                <div className="mt-1 text-ui text-re-text-secondary">{item.detail}</div>
                            </Card>
                        );
                    })}
                </div>
            </Section>

            {/* Recommendation */}
            <Section width="marketing">
                <Callout tone="info">
                    <h3 className="text-subheading text-re-text-primary">Our recommendation</h3>
                    <p className="mt-1">
                        Set up weekly automated exports to your own object storage within the first week of onboarding.
                        Use the audit evidence bundle format. It ships with a SHA-256 manifest so records can be verified out-of-band. Default deployments use PostgreSQL-backed task processing rather than a managed message bus.
                        This supports FSMA 204&apos;s two-year retention requirement regardless of your RegEngine subscription status.
                    </p>
                </Callout>
                <div className="mt-8 flex flex-wrap justify-center gap-3">
                    <Button asChild size="lg">
                        <Link href="/dashboard/export-jobs">
                            Configure exports <ArrowRight aria-hidden="true" strokeWidth={1.75} />
                        </Link>
                    </Button>
                    <Button asChild variant="ghost" size="lg">
                        <Link href="/trust">
                            Trust Center <ArrowRight aria-hidden="true" strokeWidth={1.75} />
                        </Link>
                    </Button>
                </div>
            </Section>
        </div>
    );
}
