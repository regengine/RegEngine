'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Archive, Download, ShieldCheck, Clock, PlusCircle, Link2Off, Database, Upload, ArrowRight, CheckCircle2 } from 'lucide-react';
import type { ArchiveExportJob } from '@/lib/customer-readiness';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Field } from '@/components/ui/field';
import { StatTile } from '@/components/ui/stat-tile';
import { Button } from '@/components/ui/button';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { useAuth } from '@/lib/auth-context';
import { filterExperimentalLinks } from '@/lib/experimental-features';

export default function ExportJobsPage() {
    const { isAuthenticated } = useAuth();
    const [name, setName] = useState('Weekly FSMA archive');
    const [cadence, setCadence] = useState<ArchiveExportJob['cadence']>('Weekly');
    const [format, setFormat] = useState<ArchiveExportJob['format']>('FDA Package');
    const [destination, setDestination] = useState<ArchiveExportJob['destination']>('Object storage archive');

    const { data: exportResponse, isLoading: jobsLoading } = useQuery({
        queryKey: ['export-jobs'],
        queryFn: async () => ({
            jobs: [] as ArchiveExportJob[],
            meta: {
                status: 'not_connected',
                message: 'Scheduled export jobs are not available on this workspace.',
            },
        }),
        enabled: isAuthenticated,
        retry: false,
    });

    const notConnected = exportResponse?.meta?.status === 'not_connected';
    const jobs: ArchiveExportJob[] = useMemo(() => exportResponse?.jobs ?? [], [exportResponse?.jobs]);

    const activeJobs = useMemo(
        () => jobs.filter((job) => job.status === 'active').length,
        [jobs]
    );

    const createJobMutation = useMutation({
        mutationFn: async () => {
            throw new Error(
                'Export job scheduling is not yet available — records remain exportable on demand.',
            );
        },
    });

    const status: 'idle' | 'loading' | 'saving' | 'error' = jobsLoading
        ? 'loading'
        : createJobMutation.isPending
            ? 'saving'
            : createJobMutation.isError
                ? 'error'
                : 'idle';

    function handleSaveJob() {
        createJobMutation.mutate();
    }

    const exportPrereqs = filterExperimentalLinks([
        {
            title: 'Connect source data',
            detail: 'Use Inflow Lab or import tools to build the record set export jobs will package once scheduling ships.',
            href: '/dashboard/inflow-lab',
            action: 'Open Inflow Lab',
            icon: Database,
        },
        {
            title: 'Resolve open exceptions',
            detail: 'Incomplete lots stay visible for review and should not be treated as evidence-ready.',
            href: '/dashboard/compliance',
            action: 'Check readiness',
            icon: CheckCircle2,
        },
        {
            title: 'Choose an archive destination',
            detail: 'Pick downloadable bundles for manual review or object storage for long-term retention.',
            href: '/dashboard/settings',
            action: 'Review settings',
            icon: Upload,
        },
    ]);

    return (
        <PageContainer>
            <PageHeader
                title="Scheduled Exports"
                description="Configure export jobs for connected workspaces so off-platform retention does not depend on an active in-app subscription alone."
                primaryAction={
                    <Button
                        size="lg"
                        className="w-full sm:w-auto"
                        onClick={() => void handleSaveJob()}
                        disabled={status === 'saving' || status === 'loading' || notConnected}
                    >
                        <PlusCircle className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        {status === 'saving' ? 'Saving...' : 'Save export job'}
                    </Button>
                }
            />

            <div className="space-y-6">
                {notConnected ? (
                    <Callout
                        tone="warning"
                        icon={Link2Off}
                        title={"Scheduled export jobs aren't available on this workspace yet."}
                    >
                        Recurring archive scheduling is still in development — no amount of connected data unlocks it today. Your records stay exportable on demand from FDA Export, and this page will activate when scheduling ships.
                    </Callout>
                ) : (
                    <Callout tone="info" icon={Archive}>
                        Create export jobs for the connected data paths available on this workspace. Configure cadence, bundle type, and delivery destination below.
                    </Callout>
                )}

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <StatTile label="Active jobs" value={activeJobs} />
                    <StatTile label="Archive posture" value={<span className="text-heading">External archive required</span>}>
                        <p className="text-small text-re-text-tertiary">
                            Use scheduled exports to maintain long-term retention outside the app.
                        </p>
                    </StatTile>
                    <StatTile label="Integrity model" value={<span className="text-heading">Manifest hash per run</span>}>
                        <p className="text-small text-re-text-tertiary">
                            Each generated bundle can include workspace context, timestamps, and integrity metadata for that run.
                        </p>
                    </StatTile>
                </div>

                <Card>
                    <CardHeader className="flex-col items-start gap-1">
                        <CardTitle>Create recurring export job</CardTitle>
                        <CardDescription>
                            Available destinations on this surface are downloadable bundles and object-storage archives for connected workspaces.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        <Field label="Job name" htmlFor="export-job-name">
                            <Input size="lg" value={name} onChange={(e) => setName(e.target.value)} />
                        </Field>
                        <Field label="Cadence" htmlFor="export-job-cadence">
                            <select
                                value={cadence}
                                onChange={(e) => setCadence(e.target.value as ArchiveExportJob['cadence'])}
                                className={`${fieldControlClasses} h-11`}
                            >
                                <option value="Daily">Daily</option>
                                <option value="Weekly">Weekly</option>
                                <option value="Monthly">Monthly</option>
                            </select>
                        </Field>
                        <Field label="Export format" htmlFor="export-job-format">
                            <select
                                value={format}
                                onChange={(e) => setFormat(e.target.value as ArchiveExportJob['format'])}
                                className={`${fieldControlClasses} h-11`}
                            >
                                <option value="FDA Package">FDA Package</option>
                                <option value="GS1 EPCIS 2.0">GS1 EPCIS 2.0</option>
                                <option value="Audit Bundle">Audit Bundle</option>
                            </select>
                        </Field>
                        <Field label="Destination" htmlFor="export-job-destination">
                            <select
                                value={destination}
                                onChange={(e) => setDestination(e.target.value as ArchiveExportJob['destination'])}
                                className={`${fieldControlClasses} h-11`}
                            >
                                <option value="Object storage archive">Object storage archive</option>
                                <option value="Downloadable bundle">Downloadable bundle</option>
                            </select>
                        </Field>
                    </CardContent>
                </Card>

                <div className="space-y-4">
                    {status === 'error' && (
                        <Callout tone="warning" role="alert">
                            {createJobMutation.error?.message ?? 'Could not create the export job. Please check your inputs and try again.'}
                        </Callout>
                    )}

                    {jobs.map((job) => (
                        <Card key={job.id}>
                            <CardContent className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                <div className="min-w-0">
                                    <div className="flex flex-wrap items-center gap-3">
                                        <h2 className="text-subheading text-re-text-primary">{job.name}</h2>
                                        <Badge tone="neutral" size="sm">{job.status.replaceAll('_', ' ')}</Badge>
                                    </div>
                                    <p className="mt-1 text-ui text-re-text-secondary">
                                        {job.format} · {job.cadence} · {job.destination}
                                    </p>
                                    <div className="mt-3 grid gap-2 text-ui text-re-text-tertiary sm:grid-cols-2">
                                        <div className="flex items-center gap-2">
                                            <Clock className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                            Last run: {job.lastRun}
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Download className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                            Next run: {job.nextRun}
                                        </div>
                                        <div className="flex items-center gap-2 break-all sm:col-span-2">
                                            <ShieldCheck className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                            Manifest: <span className="truncate font-mono text-[0.8125rem]">{job.manifestHash}</span>
                                        </div>
                                    </div>
                                </div>
                                <Card variant="inset" padding="compact" className="text-small text-re-text-tertiary lg:max-w-[260px]">
                                    Customer action: verify this job points to an off-platform archive you control. RegEngine should not be your only retention location.
                                </Card>
                            </CardContent>
                        </Card>
                    ))}

                    {status === 'loading' && jobs.length === 0 && (
                        <Callout tone="neutral" icon={Clock} role="status" title="Loading export jobs">
                            Checking configured export jobs, archive destinations, and the latest manifest state returned for this workspace.
                        </Callout>
                    )}

                    {status !== 'loading' && jobs.length === 0 && !notConnected && (
                        <div className="space-y-4">
                            <EmptyState
                                icon={Archive}
                                title="No export jobs yet"
                                description="Export jobs package accepted traceability records into FDA, EPCIS, or audit bundles on a cadence. After the first successful job, run timing and manifest details will appear here."
                            />
                            <div className="grid gap-4 md:grid-cols-3">
                                {exportPrereqs.map((step) => (
                                    <Card key={step.title} padding="compact" className="flex flex-col gap-2">
                                        <step.icon
                                            className="h-4 w-4 text-re-text-tertiary"
                                            strokeWidth={1.75}
                                            aria-hidden="true"
                                        />
                                        <p className="text-ui font-medium text-re-text-primary">{step.title}</p>
                                        <p className="text-small text-re-text-tertiary">{step.detail}</p>
                                        <Button variant="link" size="sm" className="mt-auto self-start" asChild>
                                            <Link href={step.href}>
                                                {step.action}
                                                <ArrowRight className="ml-1 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                                            </Link>
                                        </Button>
                                    </Card>
                                ))}
                            </div>
                            <Card>
                                <CardHeader>
                                    <CardTitle>What a job will show</CardTitle>
                                </CardHeader>
                                <CardContent className="p-0">
                                    <dl className="divide-y divide-re-border-subtle">
                                        {[
                                            ['Cadence', 'Weekly / Daily / Monthly'],
                                            ['Bundle', 'FDA or EPCIS'],
                                            ['Integrity', 'Manifest hash'],
                                        ].map(([term, detail]) => (
                                            <div key={term} className="flex items-center justify-between gap-4 px-5 py-3 text-ui">
                                                <dt className="text-re-text-tertiary">{term}</dt>
                                                <dd className="font-medium text-re-text-primary">{detail}</dd>
                                            </div>
                                        ))}
                                    </dl>
                                </CardContent>
                            </Card>
                        </div>
                    )}
                </div>
            </div>
        </PageContainer>
    );
}
