'use client';

import { useState, useRef, useEffect } from 'react';
import { Play, Download, CheckCircle2, Clock, RotateCcw, Lock, Inbox } from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardHeader } from '@/components/ui/card';
import { StatTile } from '@/components/ui/stat-tile';

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

export type RecallDrillResponse = {
    data_available: boolean;
    steps: RecallDrillApiStep[];
    time_to_trace_seconds: number | null;
    output_csv_url: string | null;
    lot_code: string | null;
    fda_24h_mandate_seconds: number;
    message: string;
    timestamp: string;
};

type DrillState = 'idle' | 'loading' | 'running' | 'done' | 'empty';

function normalizeStep(step: RecallDrillApiStep): DrillStep {
    return {
        label: step.name,
        detailLines: step.detail ? [step.detail] : [],
        durationMs: step.duration_ms,
        status: step.status,
    };
}

function normalizeSteps(data: RecallDrillResponse): DrillStep[] {
    return (data.steps ?? []).map(normalizeStep).filter((step) => step.durationMs >= 0);
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
            const steps = normalizeSteps(payload);
            setDrill(payload);
            setDrillSteps(steps);
            if (!payload.data_available || steps.length === 0) {
                setState('empty');
                return;
            }
            runAnimation(steps);
        } catch {
            setState('idle');
            setErrorMessage('Could not reach the public recall-drill endpoint. Try again shortly.');
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
    // Only show a trace time the API actually reported; never derive one.
    const traceSeconds = drill?.time_to_trace_seconds ?? null;
    const fdaMandateSeconds = drill?.fda_24h_mandate_seconds || 86400;
    const marginMultiple =
        traceSeconds != null && traceSeconds > 0 ? Math.round(fdaMandateSeconds / traceSeconds) : null;

    return (
        <div className="re-page min-h-screen pb-32">
            <Container className="pb-10 pt-14 sm:pt-20">
                <PageHeader
                    size="hero"
                    title="Public recall drill"
                    className="mb-0 border-b-0 pb-0"
                />
                <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
                    This public endpoint reads no customer data. It shows a drill only when the API
                    returns one; otherwise it tells you no drill data is available.
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
                    {(state === 'done' || state === 'empty') && (
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

            {state === 'empty' && drill && (
                <Container as="section" className="pb-10">
                    <Card className="flex items-start gap-3 p-6" data-testid="recall-drill-empty">
                        <Inbox className="mt-0.5 h-5 w-5 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                        <div>
                            <h2 className="mb-1 text-heading text-re-text-primary">No drill data</h2>
                            <p className="text-ui text-re-text-secondary">{drill.message}</p>
                        </div>
                    </Card>
                </Container>
            )}

            {(state === 'running' || state === 'done') && (
                <Container className="pb-10">
                    <Card className="overflow-hidden">
                        <CardHeader className="items-center py-3">
                            <span className="font-mono text-label uppercase text-re-text-muted">Drill log</span>
                            <span className="font-mono text-label uppercase tabular-nums text-re-text-tertiary">
                                {state === 'done'
                                    ? traceSeconds != null
                                        ? `done · ${formatSeconds(traceSeconds)}s total`
                                        : 'done'
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
                                                <CheckCircle2 className="h-4 w-4 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                                            ) : isActive ? (
                                                <Clock className="h-4 w-4 text-re-info" strokeWidth={1.75} aria-hidden="true" />
                                            ) : (
                                                <span className="font-mono text-label tabular-nums text-re-text-muted">{idx + 1}</span>
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

            {state === 'done' && drill && (
                <Container as="section" className="pb-10">
                    <div className="mb-8 grid grid-cols-1 gap-5 md:grid-cols-3">
                        {traceSeconds != null && (
                            <StatTile label="Time to trace" value={`${formatSeconds(traceSeconds)}s`}>
                                {drill.lot_code && (
                                    <p className="text-small text-re-text-tertiary">Lot {drill.lot_code}</p>
                                )}
                            </StatTile>
                        )}
                        <StatTile label="FDA records window" value="24 hours">
                            <p className="text-small text-re-text-tertiary">21 CFR 1.1455(c)(3)</p>
                        </StatTile>
                        {marginMultiple != null && (
                            <StatTile label="Margin" value={`${marginMultiple}× faster`}>
                                <p className="text-small text-re-text-tertiary">Headroom vs. regulatory window</p>
                            </StatTile>
                        )}
                    </div>

                    {drill.output_csv_url && (
                        <Card className="flex flex-col items-start justify-between gap-4 p-6 sm:flex-row sm:items-center">
                            <div className="text-subheading text-re-text-primary">Recall CSV ready</div>
                            <Button asChild size="lg" className="shrink-0">
                                <a href={drill.output_csv_url} download>
                                    <Download strokeWidth={1.75} aria-hidden="true" />
                                    Download recall CSV
                                </a>
                            </Button>
                        </Card>
                    )}
                </Container>
            )}

            <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-re-border-subtle bg-re-surface-card/95 backdrop-blur">
                <Container className="flex items-center justify-center gap-2 py-3 text-small text-re-text-tertiary">
                    <Lock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                    <span>This public page reads no customer data and shows only what the endpoint returns.</span>
                </Container>
            </div>
        </div>
    );
}
