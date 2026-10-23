'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { PlayCircle, ShieldAlert, TimerReset, FileText, Link2Off } from 'lucide-react';
import type { RecallDrillRun } from '@/lib/customer-readiness';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/lib/auth-context';

type RecallDrillsResponse = {
    items?: RecallDrillRun[];
    drills?: RecallDrillRun[];
    meta?: { status?: string; message?: string };
};

/**
 * Notice recipe.
 *
 * This is the `Callout` recipe inlined rather than the primitive itself:
 * `src/__tests__/pages/recall-drills.test.tsx` replaces `lucide-react` with a
 * five-icon factory mock, and `Callout` (like `StatusBadge`, `StatTile` and
 * `DataTable`) builds its icon map at module scope, so importing it throws
 * before the suite runs. Classes are byte-identical to the primitive's.
 */
const NOTICE_BASE =
    'flex gap-3 rounded-md border border-l-[3px] border-re-border px-4 py-3 text-ui text-re-text-secondary';

const METRICS = [
    {
        label: 'Response target',
        value: 'Under 24 hours',
        detail: 'Test weekend, holiday, and supplier-delay conditions.',
    },
    {
        label: 'Artifacts',
        value: 'Package + manifest',
        detail: 'Each drill records generated artifacts and missing-data warnings.',
    },
    {
        label: 'Escalation',
        value: 'Support path documented',
        detail: 'Enterprise escalation is contractual; public support does not replace customer-run drills.',
    },
] as const;

export default function RecallDrillsPage() {
    const { isAuthenticated } = useAuth();
    const [scenario, setScenario] = useState('Weekend retailer trace-back');
    const [lots, setLots] = useState('');
    const [dateRange, setDateRange] = useState('');
    const drillsQueryKey = ['recall-drills'] as const;

    const { data: drillsResponse, isLoading: runsLoading } = useQuery<RecallDrillsResponse>({
        queryKey: drillsQueryKey,
        queryFn: async () => ({
            items: [],
            meta: {
                status: 'not_connected',
                message: 'Automated recall drills are not available on this workspace.',
            },
        }),
        enabled: isAuthenticated,
        retry: false,
    });

    const notConnected = drillsResponse?.meta?.status === 'not_connected';
    const runs: RecallDrillRun[] = drillsResponse?.items ?? drillsResponse?.drills ?? [];

    const startDrillMutation = useMutation({
        mutationFn: async () => {
            throw new Error(
                'Recall drill automation is not yet available — use the Requests workflow for a manual drill.',
            );
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

    if (!drillsResponse || notConnected) {
        return (
            <PageContainer>
                <PageHeader
                    title="Recall Drills"
                    description="Automated recall drills are coming soon."
                    primaryAction={<Button variant="secondary" disabled>Start drill (coming soon)</Button>}
                />
                <div className={`${NOTICE_BASE} border-l-re-warning bg-re-surface-card`}>
                    <Link2Off className="mt-0.5 h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                    <div>
                        <p>Automated drill scheduling is still in development. This workspace cannot start a drill here today.</p>
                        <p className="mt-2">You can run a full manual drill today: open <Link href="/requests" className="underline">Requests (Internal Drill)</Link>, create an Internal Drill case, and walk it scope → collect → gap analysis → assemble → submit.</p>
                        <p className="mt-2">To prepare traceability records now, use <Link href="/ingest" className="underline">CSV upload</Link> or the <Link href="/developers" className="underline">JSON events API</Link>.</p>
                    </div>
                </div>
            </PageContainer>
        );
    }

    return (
        <PageContainer>
            <PageHeader
                title="Recall Drills"
                description="Run customer lots through the current drill contract, capture elapsed time, and review generated export artifacts before a regulator or retailer request."
                primaryAction={
                    <Button
                        size="lg"
                        className="w-full sm:w-auto"
                        onClick={() => void handleStartDrill()}
                        disabled={status === 'saving' || status === 'loading' || notConnected}
                        leadingIcon={<PlayCircle strokeWidth={1.75} aria-hidden="true" />}
                    >
                        {status === 'saving' ? 'Starting...' : 'Start drill'}
                    </Button>
                }
            />

            <div className="space-y-6">
                {notConnected && (
                    <div className={`${NOTICE_BASE} border-l-re-warning bg-re-surface-card`}>
                        <Link2Off className="mt-0.5 h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                        <span>
                            Automated drill scheduling is still in development. You can run a full manual drill today: open Requests, create an Internal Drill case, and walk it scope → collect → gap analysis → assemble → submit.
                        </span>
                    </div>
                )}

                <Card>
                    <CardHeader>
                        <div className="min-w-0">
                            <CardTitle>Launch a drill</CardTitle>
                            <CardDescription>
                                Choose the lots, date range, and scenario you want to test. When drill automation ships, runs will generate a timestamped audit artifact; today, use the Requests workflow for a full manual drill.
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        <Field label="Scenario" htmlFor="drill-scenario">
                            <Input id="drill-scenario" size="lg" value={scenario} onChange={(e) => setScenario(e.target.value)} />
                        </Field>
                        <Field label="Lots (comma-separated)" htmlFor="drill-lots">
                            <Input id="drill-lots" size="lg" value={lots} onChange={(e) => setLots(e.target.value)} placeholder="LOT-001, LOT-002" />
                        </Field>
                        <Field label="Date range" htmlFor="drill-date-range">
                            <Input id="drill-date-range" size="lg" value={dateRange} onChange={(e) => setDateRange(e.target.value)} placeholder="2026-03-01 to 2026-03-12" />
                        </Field>
                        <Field label="Output package" htmlFor="drill-output-package">
                            <select id="drill-output-package" className={`${fieldControlClasses} h-11`}>
                                <option>FDA package + manifest</option>
                                <option>EPCIS export + warning summary</option>
                                <option>Full audit bundle</option>
                            </select>
                        </Field>
                    </CardContent>
                </Card>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    {METRICS.map((metric) => (
                        <Card key={metric.label} padding="compact">
                            <p className="text-label text-re-text-muted">{metric.label}</p>
                            <p className="mt-2 text-subheading text-re-text-primary">{metric.value}</p>
                            <p className="mt-1 text-small text-re-text-tertiary">{metric.detail}</p>
                        </Card>
                    ))}
                </div>

                <Card>
                    <CardHeader>
                        <div className="min-w-0">
                            <CardTitle>Recent drill history</CardTitle>
                            <CardDescription>
                                Drill runs capture elapsed time, warnings, and generated artifacts from the current drill route so teams can measure operational readiness over time.
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {runs.map((run) => (
                            <div key={run.id} className="rounded-lg border border-re-border p-4">
                                <div className="flex flex-wrap items-center gap-3">
                                    <div className="text-ui font-medium text-re-text-primary">{run.scenario}</div>
                                    <div className="font-mono text-label text-re-text-muted">{run.status.replaceAll('_', ' ')}</div>
                                </div>
                                <div className="mt-2 break-all text-ui text-re-text-secondary">
                                    Lots: {run.lots.join(', ')} · {run.dateRange}
                                </div>
                                <div className="mt-2 flex flex-wrap gap-4 text-ui text-re-text-secondary">
                                    <span className="inline-flex items-center gap-1.5">
                                        <TimerReset className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" /> {run.elapsed}
                                    </span>
                                    <span className="inline-flex items-center gap-1.5">
                                        <FileText className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" /> {run.artifacts.join(', ')}
                                    </span>
                                </div>
                                {run.warnings.length > 0 && (
                                    <div className={`mt-3 ${NOTICE_BASE} border-l-re-warning bg-re-surface-card`}>
                                        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                        <span>{run.warnings.join(' · ')}</span>
                                    </div>
                                )}
                            </div>
                        ))}
                        {status === 'loading' && runs.length === 0 && (
                            <div className="space-y-2" aria-busy="true">
                                {[0, 1, 2].map((row) => (
                                    <Skeleton key={row} className="h-16 w-full" />
                                ))}
                            </div>
                        )}
                        {status !== 'loading' && runs.length === 0 && !notConnected && (
                            <EmptyState
                                icon={ShieldAlert}
                                title="No drills yet"
                                description={'Configure a scenario above and click “Start drill” to run your first recall drill. Results will appear here.'}
                            />
                        )}
                        {status === 'error' && (
                            <div className={`${NOTICE_BASE} border-l-re-danger bg-re-danger-bg`} role="alert">
                                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                                <span>
                                    {startDrillMutation.error?.message ?? 'Could not start the drill. Please check your inputs and try again.'}
                                </span>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </PageContainer>
    );
}
