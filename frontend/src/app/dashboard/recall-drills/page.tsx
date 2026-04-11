'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PlayCircle, ShieldAlert, TimerReset, FileText, Link2Off } from 'lucide-react';
import type { RecallDrillRun } from '@/lib/customer-readiness';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/lib/auth-context';

export default function RecallDrillsPage() {
    const { apiKey } = useAuth();
    const [scenario, setScenario] = useState('Weekend retailer trace-back');
    const [lots, setLots] = useState('');
    const [dateRange, setDateRange] = useState('');
    const queryClient = useQueryClient();

    const { data: drillsResponse, isLoading: runsLoading } = useQuery({
        queryKey: ['recall-drills'],
        queryFn: async () => {
            const response = await fetch('/api/fsma/customer-readiness/recall-drills', {
                headers: { 'X-RegEngine-API-Key': apiKey || '' },
            });
            if (!response.ok) return { items: [], meta: { status: 'error' } };
            return response.json() as Promise<{
                items?: RecallDrillRun[];
                drills?: RecallDrillRun[];
                meta?: { status?: string; message?: string };
            }>;
        },
    });

    const notConnected = drillsResponse?.meta?.status === 'not_connected';
    const runs: RecallDrillRun[] = drillsResponse?.items ?? drillsResponse?.drills ?? [];

    const startDrillMutation = useMutation({
        mutationFn: async () => {
            const response = await fetch('/api/fsma/customer-readiness/recall-drills', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey || '' },
                body: JSON.stringify({
                    scenario,
                    lots: lots.split(',').map((lot) => lot.trim()).filter(Boolean),
                    dateRange,
                }),
            });
            if (response.status === 501) {
                throw new Error('Recall drill automation is not yet available. Connect your supply chain data to enable this feature.');
            }
            if (!response.ok) throw new Error('Failed to start drill');
            return (await response.json()) as { drill: RecallDrillRun };
        },
        onSuccess: (data) => {
            queryClient.setQueryData<RecallDrillRun[]>(['recall-drills'], (old) => [data.drill, ...(old ?? [])]);
        },
    });

    const status: 'idle' | 'loading' | 'saving' | 'error' = runsLoading
        ? 'loading'
        : startDrillMutation.isPending
            ? 'saving'
            : startDrillMutation.isError
                ? 'error'
                : 'idle';

    function handleStartDrill() {
        startDrillMutation.mutate();
    }

    return (
        <div className="min-h-screen bg-background py-8 sm:py-10 px-4 sm:px-6">
            <div className="max-w-5xl mx-auto space-y-6">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2 sm:gap-3">
                            <ShieldAlert className="h-5 w-5 sm:h-6 sm:w-6 text-[var(--re-brand)]" />
                            Recall Drill Workspace
                        </h1>
                        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
                            Run customer lots through the current drill contract, capture elapsed time, and review generated export artifacts before a regulator or retailer request.
                        </p>
                    </div>
                    <Button
                        className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[48px] w-full sm:w-auto active:scale-[0.97]"
                        onClick={() => void handleStartDrill()}
                        disabled={status === 'saving' || status === 'loading' || notConnected}
                    >
                        <PlayCircle className="h-4 w-4 mr-1" />
                        {status === 'saving' ? 'Starting...' : 'Start drill'}
                    </Button>
                </div>

                {notConnected && (
                    <div className="rounded-xl border border-re-warning/20 bg-re-warning-muted0/[0.06] p-4 text-sm text-re-warning flex items-start gap-3">
                        <Link2Off className="h-4 w-4 mt-0.5 flex-shrink-0 text-re-warning" />
                        <span>
                            No recall drills have been run yet. Recall drill automation activates once your supply chain data is connected.
                        </span>
                    </div>
                )}

                <Card>
                    <CardHeader>
                        <CardTitle>Launch a drill</CardTitle>
                        <CardDescription>
                            Choose the lots, date range, and scenario you want to test. Drills run against your connected supply chain data and generate a timestamped audit artifact.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2">
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Scenario</label>
                            <Input value={scenario} onChange={(e) => setScenario(e.target.value)} className="rounded-xl min-h-[44px]" />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Lots (comma-separated)</label>
                            <Input value={lots} onChange={(e) => setLots(e.target.value)} placeholder="LOT-001, LOT-002" className="rounded-xl min-h-[44px]" />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Date range</label>
                            <Input value={dateRange} onChange={(e) => setDateRange(e.target.value)} placeholder="2026-03-01 to 2026-03-12" className="rounded-xl min-h-[44px]" />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Output package</label>
                            <select className="flex min-h-[44px] w-full rounded-xl border border-input bg-background px-3 text-sm">
                                <option>FDA package + manifest</option>
                                <option>EPCIS export + warning summary</option>
                                <option>Full audit bundle</option>
                            </select>
                        </div>
                    </CardContent>
                </Card>

                <div className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-3">
                    <Card>
                        <CardContent className="pt-4 sm:pt-6">
                            <div className="text-[11px] sm:text-xs uppercase tracking-widest text-muted-foreground">Response target</div>
                            <div className="text-base sm:text-lg font-semibold mt-1.5 sm:mt-2">Under 24 hours</div>
                            <div className="text-xs sm:text-sm text-muted-foreground mt-1">Test weekend, holiday, and supplier-delay conditions.</div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-4 sm:pt-6">
                            <div className="text-[11px] sm:text-xs uppercase tracking-widest text-muted-foreground">Artifacts</div>
                            <div className="text-base sm:text-lg font-semibold mt-1.5 sm:mt-2">Package + manifest</div>
                            <div className="text-xs sm:text-sm text-muted-foreground mt-1">Each drill records generated artifacts and missing-data warnings.</div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-4 sm:pt-6">
                            <div className="text-[11px] sm:text-xs uppercase tracking-widest text-muted-foreground">Escalation</div>
                            <div className="text-base sm:text-lg font-semibold mt-1.5 sm:mt-2">Support path documented</div>
                            <div className="text-xs sm:text-sm text-muted-foreground mt-1">Enterprise escalation is contractual; public support does not replace customer-run drills.</div>
                        </CardContent>
                    </Card>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Recent drill history</CardTitle>
                        <CardDescription>
                            Drill runs capture elapsed time, warnings, and generated artifacts from the current drill route so teams can measure operational readiness over time.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {runs.map((run) => (
                            <div key={run.id} className="rounded-xl border border-[var(--re-border-default)] p-3 sm:p-4">
                                <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                                    <div className="text-xs sm:text-sm font-semibold">{run.scenario}</div>
                                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{run.status.replaceAll('_', ' ')}</div>
                                </div>
                                <div className="mt-1.5 sm:mt-2 text-xs sm:text-sm text-muted-foreground break-all">
                                    Lots: {run.lots.join(', ')} · {run.dateRange}
                                </div>
                                <div className="mt-1.5 sm:mt-2 flex flex-wrap gap-3 sm:gap-4 text-xs sm:text-sm text-muted-foreground">
                                    <span className="inline-flex items-center gap-1"><TimerReset className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-[var(--re-brand)]" /> {run.elapsed}</span>
                                    <span className="inline-flex items-center gap-1"><FileText className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-[var(--re-brand)]" /> {run.artifacts.join(', ')}</span>
                                </div>
                                {run.warnings.length > 0 && (
                                    <div className="mt-3 rounded-lg border border-re-warning/20 bg-re-warning-muted0/10 p-3 text-sm text-re-warning">
                                        {run.warnings.join(' · ')}
                                    </div>
                                )}
                            </div>
                        ))}
                        {status === 'loading' && runs.length === 0 && (
                            <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-4 text-sm text-muted-foreground">
                                Loading drill history...
                            </div>
                        )}
                        {status !== 'loading' && runs.length === 0 && !notConnected && (
                            <div className="rounded-xl border border-dashed border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-8 text-center">
                                <ShieldAlert className="h-10 w-10 text-muted-foreground mx-auto mb-3 opacity-40" />
                                <p className="text-sm font-medium mb-1">No drills yet</p>
                                <p className="text-xs text-muted-foreground max-w-md mx-auto">
                                    Configure a scenario above and click &ldquo;Start drill&rdquo; to run your first recall drill. Results will appear here.
                                </p>
                            </div>
                        )}
                        {status === 'error' && (
                            <div className="rounded-xl border border-re-warning/20 bg-re-warning-muted0/10 p-4 text-sm text-re-warning">
                                {startDrillMutation.error?.message ?? 'Could not start the drill. Please check your inputs and try again.'}
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
