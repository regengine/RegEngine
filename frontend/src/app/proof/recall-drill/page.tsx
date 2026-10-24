'use client';

import { useState, useRef, useEffect } from 'react';
import {
    AlertTriangle,
    Play,
    Download,
    CheckCircle2,
    Clock,
    RotateCcw,
    Lock,
} from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardHeader } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { StatTile } from '@/components/ui/stat-tile';
import { NO_DATA_YET } from '@/lib/empty-values';

const PROOF_RECALL_ENDPOINT = '/api/ingestion/api/v1/proof/recall-drill';

type DrillStep = {
    label: string;
    detailLines: string[];
    durationMs: number;
    status: 'ok' | 'warning' | 'error';
};

type RecallDrillApiStep = {
    name: string;
    duration_ms: number;
    status: 'ok' | 'warning' | 'error';
    detail?: string | null;
};

type RecallDrillResponse = {
    steps: RecallDrillApiStep[];
    time_to_trace_seconds: number;
    output_csv_url: string;
    lot_code: string;
    fda_24h_mandate_seconds: number;
    timestamp: string;
};

type DrillState = 'idle' | 'loading' | 'running' | 'done';

function normalizeStep(step: RecallDrillApiStep): DrillStep {
    return {
        label: step.name,
        detailLines: step.detail ? [step.detail] : [],
        durationMs: step.duration_ms,
        status: step.status,
    };
}

function normalizeDrill(data: RecallDrillResponse): {
    response: RecallDrillResponse;
    steps: DrillStep[];
} {
    const steps = data.steps.map(normalizeStep).filter((step) => step.durationMs >= 0);
    return {
        response: data,
        steps,
    };
}

function formatSeconds(value: number): string {
    return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '');
}

export default function RecallDrillPage() {
    const [state, setState] = useState<DrillState>('idle');
    const [activeStep, setActiveStep] = useState(-1);
    const [elapsedMs, setElapsedMs] = useState(0);
    const [drill, setDrill] = useState<RecallDrillResponse | null>(null);
    const [drillSteps, setDrillSteps] = useState<DrillStep[]>([]);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const startedAtRef = useRef<number | null>(null);
    const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const stepTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

    useEffect(() => {
        return () => {
            if (tickRef.current) clearInterval(tickRef.current);
            stepTimers.current.forEach((t) => clearTimeout(t));
        };
    }, []);

    function clearTimers() {
        stepTimers.current.forEach((t) => clearTimeout(t));
        stepTimers.current = [];
        if (tickRef.current) clearInterval(tickRef.current);
        tickRef.current = null;
    }

    function runAnimation(steps: DrillStep[]) {
        setState('running');
        setActiveStep(0);
        setElapsedMs(0);
        startedAtRef.current = performance.now();

        tickRef.current = setInterval(() => {
            if (startedAtRef.current != null) {
                setElapsedMs(performance.now() - startedAtRef.current);
            }
        }, 100);

        let cumulative = 0;
        steps.forEach((step, idx) => {
            cumulative += step.durationMs;
            const isLast = idx === steps.length - 1;
            const t = setTimeout(() => {
                if (isLast) {
                    setActiveStep(steps.length);
                    setElapsedMs(cumulative);
                    setState('done');
                    if (tickRef.current) {
                        clearInterval(tickRef.current);
                        tickRef.current = null;
                    }
                } else {
                    setActiveStep(idx + 1);
                }
            }, cumulative);
            stepTimers.current.push(t);
        });
    }

    async function startDrill() {
        clearTimers();
        setErrorMessage(null);
        setState('loading');
        setActiveStep(-1);
        setElapsedMs(0);

        try {
            const response = await fetch(PROOF_RECALL_ENDPOINT, {
                method: 'POST',
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const payload = (await response.json()) as RecallDrillResponse;
            const normalized = normalizeDrill(payload);
            setDrill(normalized.response);
            setDrillSteps(normalized.steps);
            if (normalized.steps.length > 0) {
                runAnimation(normalized.steps);
            } else {
                setState('done');
            }
        } catch {
            setState('idle');
            setErrorMessage(
                'Could not start the public recall-drill endpoint. Try again shortly.',
            );
        }
    }

    function resetDrill() {
        clearTimers();
        startedAtRef.current = null;
        setState('idle');
        setActiveStep(-1);
        setElapsedMs(0);
        setErrorMessage(null);
        setDrill(null);
        setDrillSteps([]);
    }

    const elapsedS = (elapsedMs / 1000).toFixed(1);
    const totalDurationS = drill?.time_to_trace_seconds ?? (
        drillSteps.reduce((acc, s) => acc + s.durationMs, 0) / 1000
    );
    const finalSeconds = state === 'done' ? totalDurationS : Number(elapsedS);
    const fdaMandateSeconds = drill?.fda_24h_mandate_seconds || 86400;
    const finalSecondsLabel = formatSeconds(finalSeconds);
    const totalDurationLabel = formatSeconds(totalDurationS);
    const marginMultiple = finalSeconds > 0 ? Math.round(fdaMandateSeconds / finalSeconds) : 0;

    return (
        <div className="re-page min-h-screen pb-32">
            {/* ─── Hero ────────────────────────────────── */}
            <Container className="pb-10 pt-14 sm:pt-20">
                <PageHeader
                    size="hero"
                    eyebrow={
                        <Badge tone="warning">
                            <AlertTriangle className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                            Live Recall Drill
                        </Badge>
                    }
                    title="Run a recall drill."
                    className="mb-0 border-b-0 pb-0"
                />
                <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
                    Click <span className="font-medium text-re-text-primary">Start drill</span> and RegEngine
                    asks the recall-drill endpoint to trace a contaminated lot through its Critical Tracking
                    Events and produce an FDA-oriented sortable recall CSV. If no drill data exists yet,
                    the page shows an empty state instead of placeholder content.
                </p>

                <div className="mt-8 flex flex-wrap gap-3">
                    {state === 'idle' && (
                        <Button
                            size="lg"
                            onClick={startDrill}
                            leadingIcon={<Play fill="currentColor" strokeWidth={1.75} aria-hidden="true" />}
                        >
                            Start drill
                        </Button>
                    )}
                    {state === 'running' && (
                        <Button
                            size="lg"
                            variant="secondary"
                            disabled
                            leadingIcon={<Clock strokeWidth={1.75} aria-hidden="true" />}
                        >
                            Drill in progress · {elapsedS}s
                        </Button>
                    )}
                    {state === 'loading' && (
                        <Button size="lg" variant="secondary" loading>
                            Starting endpoint run…
                        </Button>
                    )}
                    {state === 'done' && (
                        <Button
                            size="lg"
                            variant="secondary"
                            onClick={resetDrill}
                            leadingIcon={<RotateCcw strokeWidth={1.75} aria-hidden="true" />}
                        >
                            Run again
                        </Button>
                    )}
                </div>
                {errorMessage && (
                    <Callout tone="danger" role="alert" className="mt-4">
                        {errorMessage}
                    </Callout>
                )}
            </Container>

            {/* ─── Progress / Steps ───────────────────── */}
            {(state === 'running' || state === 'done') && drillSteps.length > 0 && (
                <Container className="pb-10">
                    <Card className="overflow-hidden">
                        <CardHeader className="items-center py-3">
                            <span className="font-mono text-label uppercase text-re-text-muted">
                                Drill log
                            </span>
                            <span className="font-mono text-label uppercase tabular-nums text-re-text-tertiary">
                                {state === 'done'
                                    ? `done · ${totalDurationLabel}s total`
                                    : `running · ${elapsedS}s`}
                            </span>
                        </CardHeader>
                        <div className="flex flex-col gap-3 p-5">
                            {drillSteps.map((step, idx) => {
                                const isComplete = activeStep > idx || state === 'done';
                                const isActive = activeStep === idx && state === 'running';
                                const isPending = activeStep < idx && state === 'running';
                                return (
                                    <div key={idx} className="flex items-start gap-3">
                                        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center">
                                            {isComplete ? (
                                                <CheckCircle2
                                                    className="h-4 w-4 text-re-success"
                                                    strokeWidth={1.75}
                                                    aria-hidden="true"
                                                />
                                            ) : isActive ? (
                                                <Clock
                                                    className="h-4 w-4 text-re-info"
                                                    strokeWidth={1.75}
                                                    aria-hidden="true"
                                                />
                                            ) : (
                                                <span className="font-mono text-label tabular-nums text-re-text-muted">
                                                    {idx + 1}
                                                </span>
                                            )}
                                        </span>
                                        <div className="min-w-0 flex-1">
                                            <div
                                                className={
                                                    isPending
                                                        ? 'text-ui text-re-text-muted'
                                                        : 'text-ui font-medium text-re-text-primary'
                                                }
                                            >
                                                {step.label}
                                                {isActive && '…'}
                                            </div>
                                            {(isComplete || isActive) && (
                                                <div className="mt-1 font-mono text-[0.8125rem] leading-6 text-re-text-secondary">
                                                    {step.detailLines.map((line, j) => (
                                                        <div key={j}>{line}</div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </Card>
                </Container>
            )}

            {/* ─── Result panel (after done) ────────────── */}
            {state === 'done' && (
                <Container as="section" className="pb-10">
                    {!drill || drillSteps.length === 0 ? (
                        <EmptyState
                            icon={AlertTriangle}
                            titleAs="h2"
                            title={NO_DATA_YET}
                            description="The recall-drill endpoint returned no trace steps. There is no drill data to show yet."
                        />
                    ) : (
                        <>
                            {/* Time-to-trace metric */}
                            <div className="mb-8 grid grid-cols-1 gap-5 md:grid-cols-3">
                                <StatTile label="Time to trace" value={`${finalSecondsLabel}s`}>
                                    <p className="text-small text-re-text-tertiary">Lot {drill.lot_code}</p>
                                </StatTile>
                                <StatTile label="FDA mandate" value="24 hours">
                                    <p className="text-small text-re-text-tertiary">§ 204: produce records on request</p>
                                </StatTile>
                                <StatTile label="Margin" value={`${marginMultiple}× faster`}>
                                    <p className="text-small text-re-text-tertiary">Headroom vs. regulatory window</p>
                                </StatTile>
                            </div>

                            {/* Trace diagram */}
                            <Card className="mb-8 p-6">
                                <h2 className="mb-4 text-heading text-re-text-primary">Forward trace graph</h2>
                                <EmptyState
                                    bare
                                    size="sm"
                                    title={NO_DATA_YET}
                                    description="The recall-drill endpoint does not return per-facility trace nodes yet."
                                />
                            </Card>

                            {/* CSV download */}
                            <Card className="flex flex-col items-start justify-between gap-4 p-6 sm:flex-row sm:items-center">
                                <div>
                                    <div className="mb-1 text-subheading text-re-text-primary">
                                        Recall CSV
                                    </div>
                                    <div className="text-ui text-re-text-secondary">
                                        21 CFR §§1.1325 to 1.1350 Key Data Elements
                                    </div>
                                </div>
                                {drill.output_csv_url ? (
                                    <Button asChild size="lg" className="shrink-0">
                                        <a href={drill.output_csv_url} download>
                                            <Download strokeWidth={1.75} aria-hidden="true" />
                                            Download recall CSV
                                        </a>
                                    </Button>
                                ) : (
                                    <span className="text-ui text-re-text-tertiary">{NO_DATA_YET}</span>
                                )}
                            </Card>
                        </>
                    )}
                </Container>
            )}

            {/* ─── Idle-state explainer ────────────────── */}
            {state === 'idle' && (
                <Container as="section" className="pb-10">
                    <Card className="p-6">
                        <h2 className="mb-3 text-heading text-re-text-primary">What happens when you click start</h2>
                        <ol className="flex flex-col gap-2 text-ui text-re-text-secondary">
                            <li>
                                <span className="font-mono tabular-nums text-re-text-primary">1.</span> RegEngine asks the recall-drill
                                endpoint to identify the contaminated lot to trace.
                            </li>
                            <li>
                                <span className="font-mono tabular-nums text-re-text-primary">2.</span> The trace walks downstream
                                through every Critical Tracking Event (CTE) recorded for that lot.
                            </li>
                            <li>
                                <span className="font-mono tabular-nums text-re-text-primary">3.</span> Every receiver of the contaminated lot
                                (and any downstream lot derived from it via transformation) is
                                identified.
                            </li>
                            <li>
                                <span className="font-mono tabular-nums text-re-text-primary">4.</span> The output is a recall CSV in the format
                                FDA inspectors will request under § 204.
                            </li>
                        </ol>
                    </Card>
                </Container>
            )}

            {/* ─── Sticky footer ─────────────────────── */}
            <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-re-border-subtle bg-re-surface-card/95 backdrop-blur">
                <Container className="flex items-center justify-center gap-2 py-3 text-small text-re-text-tertiary">
                    <Lock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                    <span>
                        Results come from the live recall-drill endpoint. When no drill data
                        exists yet, this page shows an empty state instead of placeholder content.
                    </span>
                </Container>
            </div>
        </div>
    );
}
