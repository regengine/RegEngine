'use client';

import { useEffect, useState } from 'react';
import { PlayCircle, ShieldAlert, TimerReset, FileText } from 'lucide-react';
import type { RecallDrillRun } from '@/lib/customer-readiness';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export default function RecallDrillsPage() {
    const [scenario, setScenario] = useState('Weekend retailer trace-back');
    const [lots, setLots] = useState('TOM-0226-F3-001, LET-0310-WH-21');
    const [dateRange, setDateRange] = useState('2026-03-01 to 2026-03-12');
    const [runs, setRuns] = useState<RecallDrillRun[]>([]);
    const [status, setStatus] = useState<'idle' | 'loading' | 'saving' | 'error'>('loading');

    useEffect(() => {
        let cancelled = false;

        async function loadRuns() {
            setStatus('loading');

            try {
                const response = await fetch('/api/fsma/customer-readiness/recall-drills');
                if (!response.ok) {
                    throw new Error('Failed to load drills');
                }

                const data = (await response.json()) as { drills: RecallDrillRun[] };
                if (!cancelled) {
                    setRuns(data.drills);
                    setStatus('idle');
                }
            } catch {
                if (!cancelled) {
                    setStatus('error');
                }
            }
        }

        void loadRuns();

        return () => {
            cancelled = true;
        };
    }, []);

    async function handleStartDrill() {
        setStatus('saving');

        try {
            const response = await fetch('/api/fsma/customer-readiness/recall-drills', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    scenario,
                    lots: lots.split(',').map((lot) => lot.trim()).filter(Boolean),
                    dateRange,
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to start drill');
            }

            const data = (await response.json()) as { drill: RecallDrillRun };
            setRuns((current) => [data.drill, ...current]);
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
                        disabled={status === 'saving' || status === 'loading'}
                    >
                        <PlayCircle className="h-4 w-4 mr-1" />
                        {status === 'saving' ? 'Starting...' : 'Start drill'}
                    </Button>
                </div>

                <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-4 text-sm text-muted-foreground">
                    Preview interface: the workflow below exercises the current frontend drill route. Full backend execution, artifact persistence, and audit events are still separate follow-on work.
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Launch a drill</CardTitle>
                        <CardDescription>
                            Choose the lots, date range, and scenario you want to test. The current route returns a drill workspace contract so teams can validate the flow before backend automation is wired.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2">
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Scenario</label>
                            <Input value={scenario} onChange={(e) => setScenario(e.target.value)} className="rounded-xl min-h-[44px]" />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Lots</label>
                            <Input value={lots} onChange={(e) => setLots(e.target.value)} className="rounded-xl min-h-[44px]" />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Date range</label>
                            <Input value={dateRange} onChange={(e) => setDateRange(e.target.value)} className="rounded-xl min-h-[44px]" />
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
                                    <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-200">
                                        {run.warnings.join(' · ')}
                                    </div>
                                )}
                            </div>
                        ))}
                        {status === 'loading' && runs.length === 0 && (
                            <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-4 text-sm text-muted-foreground">
                                Loading drill preview data...
                            </div>
                        )}
                        {status === 'error' && (
                            <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-200">
                                The recall-drill contract route did not respond. Existing public recall posture should not be read as completed backend execution.
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
