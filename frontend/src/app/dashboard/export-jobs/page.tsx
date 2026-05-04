'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Archive, Download, ShieldCheck, Clock, PlusCircle, Link2Off, Database, Upload, ArrowRight, CheckCircle2 } from 'lucide-react';
import type { ArchiveExportJob } from '@/lib/customer-readiness';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';

export default function ExportJobsPage() {
    const { apiKey } = useAuth();
    const { tenantId } = useTenant();
    const [name, setName] = useState('Weekly FSMA archive');
    const [cadence, setCadence] = useState<ArchiveExportJob['cadence']>('Weekly');
    const [format, setFormat] = useState<ArchiveExportJob['format']>('FDA Package');
    const [destination, setDestination] = useState<ArchiveExportJob['destination']>('Object storage archive');
    const queryClient = useQueryClient();

    const { data: exportResponse, isLoading: jobsLoading } = useQuery({
        queryKey: ['export-jobs'],
        queryFn: async () => {
            const response = await fetchWithCsrf('/api/fsma/customer-readiness/export-jobs', {
                headers: { 'X-RegEngine-API-Key': apiKey || '' },
            });
            if (!response.ok) return { jobs: [], meta: { status: 'error' } };
            return response.json() as Promise<{
                jobs?: ArchiveExportJob[];
                meta?: { status?: string; message?: string };
            }>;
        },
    });

    const notConnected = exportResponse?.meta?.status === 'not_connected';
    const jobs: ArchiveExportJob[] = useMemo(() => exportResponse?.jobs ?? [], [exportResponse?.jobs]);

    const activeJobs = useMemo(
        () => jobs.filter((job) => job.status === 'active').length,
        [jobs]
    );

    const createJobMutation = useMutation({
        mutationFn: async () => {
            const response = await fetchWithCsrf('/api/fsma/customer-readiness/export-jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey || '' },
                body: JSON.stringify({
                    name,
                    cadence,
                    format,
                    destination,
                    tenantId: tenantId || '',
                }),
            });
            if (response.status === 501) {
                throw new Error('Export job scheduling is not yet available. Connect your supply chain data to enable this feature.');
            }
            if (!response.ok) throw new Error('Failed to create export job');
            return (await response.json()) as { job: ArchiveExportJob };
        },
        onSuccess: (data) => {
            queryClient.setQueryData<{
                jobs?: ArchiveExportJob[];
                meta?: { status?: string; message?: string };
            }>(['export-jobs'], (old) => ({
                ...(old ?? { meta: { status: 'ok' } }),
                jobs: [data.job, ...(old?.jobs ?? [])],
            }));
            setName('Weekly FSMA archive');
            setCadence('Weekly');
            setFormat('FDA Package');
            setDestination('Object storage archive');
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

    const exportPrereqs = [
        {
            title: 'Connect source data',
            detail: 'Use Inflow Lab or import tools so export jobs have accepted records to package.',
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
    ];

    return (
        <div className="min-h-screen bg-background py-8 sm:py-10 px-4 sm:px-6">
            <div className="max-w-5xl mx-auto space-y-6">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2 sm:gap-3">
                            <Archive className="h-5 w-5 sm:h-6 sm:w-6 text-[var(--re-brand)]" />
                            Archive &amp; Export Jobs
                        </h1>
                        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
                            Configure recurring FDA, EPCIS, and audit bundles against the current customer-readiness API contract so statutory retention does not depend on a live subscription.
                        </p>
                    </div>
                    <Button
                        className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[48px] w-full sm:w-auto active:scale-[0.97]"
                        onClick={() => void handleSaveJob()}
                        disabled={status === 'saving' || status === 'loading' || notConnected}
                    >
                        <PlusCircle className="h-4 w-4 mr-1" />
                        {status === 'saving' ? 'Saving...' : 'Save Export Job'}
                    </Button>
                </div>

                {notConnected ? (
                    <div className="rounded-xl border border-re-warning/20 bg-re-warning-muted0/[0.06] p-4 text-sm text-re-warning">
                        <div className="flex items-start gap-3">
                            <Link2Off className="h-4 w-4 mt-0.5 flex-shrink-0 text-re-warning" />
                            <div>
                                <p className="font-semibold">Export scheduling is waiting for connected supply-chain data.</p>
                                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                                    Create jobs after at least one supplier feed, import, or validated Inflow Lab run exists. This keeps empty schedules from looking like audit evidence.
                                </p>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="rounded-xl border border-[var(--re-brand)]/20 bg-[var(--re-brand)]/[0.04] p-4 text-sm text-muted-foreground">
                        Schedule automated FDA exports, EPCIS packages, and compliance reports. Configure cadence, format, and delivery destination below.
                    </div>
                )}

                <div className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-3">
                    <Card>
                        <CardContent className="pt-4 sm:pt-6">
                            <div className="text-[11px] sm:text-xs uppercase tracking-widest text-muted-foreground">Active jobs</div>
                            <div className="text-2xl sm:text-3xl font-bold mt-1.5 sm:mt-2">{activeJobs}</div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-4 sm:pt-6">
                            <div className="text-[11px] sm:text-xs uppercase tracking-widest text-muted-foreground">Archive posture</div>
                            <div className="text-base sm:text-lg font-semibold mt-1.5 sm:mt-2">External archive required</div>
                            <div className="text-xs sm:text-sm text-muted-foreground mt-1">Use scheduled exports to maintain long-term retention outside the app.</div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-4 sm:pt-6">
                            <div className="text-[11px] sm:text-xs uppercase tracking-widest text-muted-foreground">Integrity model</div>
                            <div className="text-base sm:text-lg font-semibold mt-1.5 sm:mt-2">Manifest hash per run</div>
                            <div className="text-xs sm:text-sm text-muted-foreground mt-1">Every bundle exposes tenant context, timestamps, and integrity metadata.</div>
                        </CardContent>
                    </Card>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Create recurring export job</CardTitle>
                        <CardDescription>
                            Default destinations are downloadable bundle and object-storage archive. This is the current customer-facing contract surface for retention readiness.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2">
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Job name</label>
                            <Input value={name} onChange={(e) => setName(e.target.value)} className="rounded-xl min-h-[44px]" />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Cadence</label>
                            <select
                                value={cadence}
                                onChange={(e) => setCadence(e.target.value as ArchiveExportJob['cadence'])}
                                className="flex min-h-[44px] w-full rounded-xl border border-input bg-background px-3 text-sm"
                            >
                                <option value="Daily">Daily</option>
                                <option value="Weekly">Weekly</option>
                                <option value="Monthly">Monthly</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Export format</label>
                            <select
                                value={format}
                                onChange={(e) => setFormat(e.target.value as ArchiveExportJob['format'])}
                                className="flex min-h-[44px] w-full rounded-xl border border-input bg-background px-3 text-sm"
                            >
                                <option value="FDA Package">FDA Package</option>
                                <option value="GS1 EPCIS 2.0">GS1 EPCIS 2.0</option>
                                <option value="Audit Bundle">Audit Bundle</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Destination</label>
                            <select
                                value={destination}
                                onChange={(e) => setDestination(e.target.value as ArchiveExportJob['destination'])}
                                className="flex min-h-[44px] w-full rounded-xl border border-input bg-background px-3 text-sm"
                            >
                                <option value="Object storage archive">Object storage archive</option>
                                <option value="Downloadable bundle">Downloadable bundle</option>
                            </select>
                        </div>
                    </CardContent>
                </Card>

                <div className="space-y-4">
                    {status === 'error' && (
                        <div className="rounded-xl border border-re-warning/20 bg-re-warning-muted0/10 p-4 text-sm text-re-warning">
                            {createJobMutation.error?.message ?? 'Could not create the export job. Please check your inputs and try again.'}
                        </div>
                    )}
                    {jobs.map((job) => (
                        <Card key={job.id}>
                            <CardContent className="pt-4 sm:pt-6">
                                <div className="flex flex-col gap-3 sm:gap-4 lg:flex-row lg:items-start lg:justify-between">
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
                                            <h2 className="text-base sm:text-lg font-semibold">{job.name}</h2>
                                            <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                                                {job.status.replaceAll('_', ' ')}
                                            </span>
                                        </div>
                                        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
                                            {job.format} · {job.cadence} · {job.destination}
                                        </p>
                                        <div className="mt-2 sm:mt-3 grid gap-1.5 sm:gap-2 text-xs sm:text-sm text-muted-foreground sm:grid-cols-2">
                                            <div className="flex items-center gap-2">
                                                <Clock className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-[var(--re-brand)] flex-shrink-0" />
                                                Last run: {job.lastRun}
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <Download className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-[var(--re-brand)] flex-shrink-0" />
                                                Next run: {job.nextRun}
                                            </div>
                                            <div className="flex items-center gap-2 sm:col-span-2 break-all">
                                                <ShieldCheck className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-[var(--re-brand)] flex-shrink-0" />
                                                Manifest: <span className="truncate">{job.manifestHash}</span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-3 text-xs text-muted-foreground lg:max-w-[260px]">
                                        Customer action: verify this job points to an off-platform archive you control. RegEngine should not be your only retention location.
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                    {status === 'loading' && jobs.length === 0 && (
                        <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-5">
                            <div className="flex items-start gap-3">
                                <Clock className="mt-0.5 h-4 w-4 animate-pulse text-[var(--re-brand)]" />
                                <div>
                                    <p className="text-sm font-semibold">Loading export jobs</p>
                                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                                        Checking scheduled exports, archive destinations, and the latest manifest state.
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}
                    {status !== 'loading' && jobs.length === 0 && (
                        <div className="rounded-xl border border-dashed border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-5 sm:p-6">
                            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
                                <div>
                                    <div className="flex items-start gap-3">
                                        <Archive className="mt-0.5 h-8 w-8 text-[var(--re-brand)]" />
                                        <div>
                                            <p className="text-sm font-semibold">No export jobs yet</p>
                                            <p className="mt-1 max-w-2xl text-xs leading-5 text-muted-foreground">
                                                Export jobs package accepted traceability records into FDA, EPCIS, or audit bundles on a cadence. Set one up after your first clean source is connected, then every run will appear here with timing and manifest details.
                                            </p>
                                        </div>
                                    </div>
                                    <div className="mt-5 grid gap-3 md:grid-cols-3">
                                        {exportPrereqs.map((step) => (
                                            <div key={step.title} className="rounded-xl border border-[var(--re-border-default)] bg-background p-3 text-left">
                                                <step.icon className="h-4 w-4 text-[var(--re-brand)]" />
                                                <p className="mt-3 text-xs font-semibold">{step.title}</p>
                                                <p className="mt-1 text-[11px] leading-4 text-muted-foreground">{step.detail}</p>
                                                <Link href={step.href}>
                                                    <Button variant="ghost" size="sm" className="mt-3 h-7 px-0 text-[11px] text-[var(--re-brand)] hover:bg-transparent">
                                                        {step.action} <ArrowRight className="ml-1 h-3 w-3" />
                                                    </Button>
                                                </Link>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                                <div className="rounded-xl border border-[var(--re-border-default)] bg-background p-4">
                                    <p className="text-sm font-semibold">What a job will show</p>
                                    <div className="mt-3 space-y-2 text-xs leading-5 text-muted-foreground">
                                        <div className="flex items-center justify-between rounded-lg bg-[var(--re-surface-elevated)] px-3 py-2">
                                            <span>Cadence</span>
                                            <span className="font-medium text-foreground">Weekly / Daily / Monthly</span>
                                        </div>
                                        <div className="flex items-center justify-between rounded-lg bg-[var(--re-surface-elevated)] px-3 py-2">
                                            <span>Bundle</span>
                                            <span className="font-medium text-foreground">FDA or EPCIS</span>
                                        </div>
                                        <div className="flex items-center justify-between rounded-lg bg-[var(--re-surface-elevated)] px-3 py-2">
                                            <span>Integrity</span>
                                            <span className="font-medium text-foreground">Manifest hash</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
