'use client';

import { useEffect, useMemo, useState } from 'react';
import { Archive, Download, ShieldCheck, Clock, PlusCircle } from 'lucide-react';
import type { ArchiveExportJob } from '@/lib/customer-readiness';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export default function ExportJobsPage() {
    const [name, setName] = useState('Weekly FSMA archive');
    const [cadence, setCadence] = useState<ArchiveExportJob['cadence']>('Weekly');
    const [format, setFormat] = useState<ArchiveExportJob['format']>('FDA Package');
    const [destination, setDestination] = useState<ArchiveExportJob['destination']>('Object storage archive');
    const [jobs, setJobs] = useState<ArchiveExportJob[]>([]);
    const [status, setStatus] = useState<'idle' | 'loading' | 'saving' | 'error'>('loading');

    const activeJobs = useMemo(
        () => jobs.filter((job) => job.status === 'active').length,
        [jobs]
    );

    useEffect(() => {
        let cancelled = false;

        async function loadJobs() {
            setStatus('loading');

            try {
                const response = await fetch('/api/fsma/customer-readiness/export-jobs');
                if (!response.ok) {
                    throw new Error('Failed to load export jobs');
                }

                const data = (await response.json()) as { jobs: ArchiveExportJob[] };
                if (!cancelled) {
                    setJobs(data.jobs);
                    setStatus('idle');
                }
            } catch {
                if (!cancelled) {
                    setStatus('error');
                }
            }
        }

        void loadJobs();

        return () => {
            cancelled = true;
        };
    }, []);

    async function handleSaveJob() {
        setStatus('saving');

        try {
            const response = await fetch('/api/fsma/customer-readiness/export-jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name,
                    cadence,
                    format,
                    destination,
                    tenantId: 'tenant_acme_001',
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to create export job');
            }

            const data = (await response.json()) as { job: ArchiveExportJob };
            setJobs((current) => [data.job, ...current]);
            setName('Weekly FSMA archive');
            setCadence('Weekly');
            setFormat('FDA Package');
            setDestination('Object storage archive');
            setStatus('idle');
        } catch {
            setStatus('error');
        }
    }

    return (
        <div className="min-h-screen bg-background py-8 sm:py-10 px-4 sm:px-6">
            <div className="max-w-5xl mx-auto space-y-6">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-3">
                            <Archive className="h-6 w-6 text-[var(--re-brand)]" />
                            Archive & Export Jobs
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Configure recurring FDA, EPCIS, and audit bundles against the current customer-readiness API contract so statutory retention does not depend on a live subscription.
                        </p>
                    </div>
                    <Button
                        className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl"
                        onClick={() => void handleSaveJob()}
                        disabled={status === 'saving' || status === 'loading'}
                    >
                        <PlusCircle className="h-4 w-4 mr-1" />
                        {status === 'saving' ? 'Saving...' : 'Save Export Job'}
                    </Button>
                </div>

                <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-4 text-sm text-muted-foreground">
                    Preview interface: this page exercises the current frontend contract route for export jobs. Persistent backend scheduling and audit events are not wired yet.
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                    <Card>
                        <CardContent className="pt-6">
                            <div className="text-xs uppercase tracking-widest text-muted-foreground">Active jobs</div>
                            <div className="text-3xl font-bold mt-2">{activeJobs}</div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <div className="text-xs uppercase tracking-widest text-muted-foreground">Archive posture</div>
                            <div className="text-lg font-semibold mt-2">External archive required</div>
                            <div className="text-sm text-muted-foreground mt-1">Use scheduled exports to maintain long-term retention outside the app.</div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <div className="text-xs uppercase tracking-widest text-muted-foreground">Integrity model</div>
                            <div className="text-lg font-semibold mt-2">Manifest hash per run</div>
                            <div className="text-sm text-muted-foreground mt-1">Every bundle exposes tenant context, timestamps, and integrity metadata.</div>
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
                    <CardContent className="grid gap-4 md:grid-cols-2">
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Job name</label>
                            <Input value={name} onChange={(e) => setName(e.target.value)} className="rounded-xl" />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Cadence</label>
                            <select
                                value={cadence}
                                onChange={(e) => setCadence(e.target.value as ArchiveExportJob['cadence'])}
                                className="flex h-10 w-full rounded-xl border border-input bg-background px-3 text-sm"
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
                                className="flex h-10 w-full rounded-xl border border-input bg-background px-3 text-sm"
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
                                className="flex h-10 w-full rounded-xl border border-input bg-background px-3 text-sm"
                            >
                                <option value="Object storage archive">Object storage archive</option>
                                <option value="Downloadable bundle">Downloadable bundle</option>
                            </select>
                        </div>
                    </CardContent>
                </Card>

                <div className="space-y-4">
                    {status === 'error' && (
                        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-200">
                            The export-job preview route did not respond. The page contract is present, but the interface data could not be loaded.
                        </div>
                    )}
                    {jobs.map((job) => (
                        <Card key={job.id}>
                            <CardContent className="pt-6">
                                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                    <div>
                                        <div className="flex items-center gap-3">
                                            <h2 className="text-lg font-semibold">{job.name}</h2>
                                            <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                                                {job.status.replaceAll('_', ' ')}
                                            </span>
                                        </div>
                                        <p className="text-sm text-muted-foreground mt-1">
                                            {job.format} · {job.cadence} · {job.destination}
                                        </p>
                                        <div className="mt-3 grid gap-2 text-sm text-muted-foreground md:grid-cols-2">
                                            <div className="flex items-center gap-2">
                                                <Clock className="h-4 w-4 text-[var(--re-brand)]" />
                                                Last run: {job.lastRun}
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <Download className="h-4 w-4 text-[var(--re-brand)]" />
                                                Next run: {job.nextRun}
                                            </div>
                                            <div className="flex items-center gap-2 md:col-span-2">
                                                <ShieldCheck className="h-4 w-4 text-[var(--re-brand)]" />
                                                Manifest integrity: {job.manifestHash}
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
                        <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-4 text-sm text-muted-foreground">
                            Loading export job preview data...
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
