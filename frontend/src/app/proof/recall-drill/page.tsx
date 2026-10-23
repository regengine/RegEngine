'use client';

import { useState, useRef, useEffect } from 'react';
import {
    AlertTriangle,
    Play,
    Download,
    CheckCircle2,
    Clock,
    ArrowRight,
    RotateCcw,
    Lock,
} from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardHeader } from '@/components/ui/card';
import { StatTile } from '@/components/ui/stat-tile';

const RECALL_CSV_URL = '/samples/sample_recall_drill.csv';
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

const DEFAULT_DRILL_STEPS: DrillStep[] = [
    {
        label: 'Identifying source lot',
        detailLines: [
            'Loaded contaminated lot: SV-20240115-001 (Romaine Lettuce, 500 cases)',
            'Origin: Sunny Valley Farms (GLN 1234567890128)',
        ],
        durationMs: 1200,
        status: 'ok',
    },
    {
        label: 'Tracing forward through 7 CTEs',
        detailLines: [
            'CTE-1 HARVESTING → CTE-2 COOLING → CTE-3 INITIAL_PACKING',
            'CTE-4 SHIPPING → CTE-5 RECEIVING → CTE-6 TRANSFORMATION → CTE-7 SHIPPING',
            'Resolved 2 child lots (FC-20240116-A, FC-20240116-B) at transformation node',
        ],
        durationMs: 2400,
        status: 'ok',
    },
    {
        label: 'Walking downstream graph edges',
        detailLines: [
            'Visited 11 events across 5 facilities',
            'Reached 3 receivers: Metro Foods, Valley Wholesale, SuperMart #42',
        ],
        durationMs: 1800,
        status: 'ok',
    },
    {
        label: 'Generating FDA-oriented sortable recall CSV from sample data',
        detailLines: [
            'Wrote 21 CFR §§1.1325 to 1.1350 Key Data Elements for each downstream lot',
            'Hash-anchored each record (SHA-256 chain integrity preserved)',
        ],
        durationMs: 1600,
        status: 'ok',
    },
];

/* Final trace nodes used in the result panel diagram. */
type TraceNode = {
    id: string;
    facility: string;
    cte: string;
    lot: string;
    qty: string;
};

const TRACE_NODES: TraceNode[] = [
    { id: 'h', facility: 'Sunny Valley Farms', cte: 'HARVESTING', lot: 'SV-20240115-001', qty: '500 cs' },
    { id: 's1', facility: 'Sunny Valley Farms', cte: 'SHIPPING', lot: 'SV-20240115-001', qty: '500 cs' },
    { id: 'r1', facility: 'Fresh Cut Co', cte: 'RECEIVING', lot: 'SV-20240115-001', qty: '500 cs' },
    { id: 't', facility: 'Fresh Cut Co', cte: 'TRANSFORMATION', lot: 'FC-20240116-A / -B', qty: '250 + 250 cs' },
    { id: 's2', facility: 'Fresh Cut Co', cte: 'SHIPPING', lot: 'FC-20240116-A', qty: '100 cs' },
    { id: 'r2', facility: 'Metro Foods', cte: 'RECEIVING', lot: 'FC-20240116-A', qty: '100 cs' },
    { id: 's3', facility: 'Metro Foods', cte: 'SHIPPING', lot: 'FC-20240116-A', qty: '50 cs' },
    { id: 'r3', facility: 'SuperMart #42', cte: 'RECEIVING', lot: 'FC-20240116-A', qty: '50 cs' },
];

const DEFAULT_DRILL_RESPONSE: RecallDrillResponse = {
    steps: DEFAULT_DRILL_STEPS.map((step) => ({
        name: step.label,
        duration_ms: step.durationMs,
        status: step.status,
        detail: step.detailLines.join(' '),
    })),
    time_to_trace_seconds: DEFAULT_DRILL_STEPS.reduce((acc, s) => acc + s.durationMs, 0) / 1000,
    output_csv_url: RECALL_CSV_URL,
    lot_code: 'SV-20240115-001',
    fda_24h_mandate_seconds: 86400,
    timestamp: '',
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
        steps: steps.length > 0 ? steps : DEFAULT_DRILL_STEPS,
    };
}

function formatSeconds(value: number): string {
    return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '');
}

export default function RecallDrillPage() {
    const [state, setState] = useState<DrillState>('idle');
    const [activeStep, setActiveStep] = useState(-1);
    const [elapsedMs, setElapsedMs] = useState(0);
    const [drill, setDrill] = useState<RecallDrillResponse>(DEFAULT_DRILL_RESPONSE);
    const [drillSteps, setDrillSteps] = useState<DrillStep[]>(DEFAULT_DRILL_STEPS);
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
            runAnimation(normalized.steps);
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
    }

    const elapsedS = (elapsedMs / 1000).toFixed(1);
    const totalDurationS = drill.time_to_trace_seconds || (
        drillSteps.reduce((acc, s) => acc + s.durationMs, 0) / 1000
    );
    const finalSeconds = state === 'done' ? totalDurationS : Number(elapsedS);
    const outputCsvUrl = drill.output_csv_url || RECALL_CSV_URL;
    const fdaMandateSeconds = drill.fda_24h_mandate_seconds || 86400;
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
                            Live Recall Drill • Synthetic Data
                        </Badge>
                    }
                    title="Run a recall drill on synthetic supply-chain data."
                    className="mb-0 border-b-0 pb-0"
                />
                <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
                    Click <span className="font-medium text-re-text-primary">Start drill</span> and RegEngine
                    traces the contaminated lot through the applicable CTEs and produces an FDA-oriented sortable
                    recall CSV in under 60 seconds. Synthetic data, illustrative only.
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
            {(state === 'running' || state === 'done') && (
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
                    {/* Time-to-trace metric */}
                    <div className="mb-8 grid grid-cols-1 gap-5 md:grid-cols-3">
                        <StatTile label="Time to trace" value={`${finalSecondsLabel}s`}>
                            <p className="text-small text-re-text-tertiary">Synthetic lot {drill.lot_code}</p>
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
                        <div className="overflow-x-auto">
                            <div className="flex min-w-max items-stretch gap-2 pb-2">
                                {TRACE_NODES.map((n, i) => (
                                    <div key={n.id} className="flex items-stretch">
                                        <Card
                                            variant="inset"
                                            padding="compact"
                                            className={
                                                n.cte === 'TRANSFORMATION'
                                                    ? 'min-w-[170px] border-re-danger'
                                                    : 'min-w-[170px]'
                                            }
                                        >
                                            <div
                                                className={
                                                    n.cte === 'TRANSFORMATION'
                                                        ? 'mb-1 font-mono text-label uppercase text-re-danger'
                                                        : 'mb-1 font-mono text-label uppercase text-re-text-muted'
                                                }
                                            >
                                                {n.cte}
                                            </div>
                                            <div className="mb-1 text-subheading text-re-text-primary">
                                                {n.facility}
                                            </div>
                                            <div className="font-mono text-[0.8125rem] text-re-text-secondary">
                                                {n.lot}
                                            </div>
                                            <div className="font-mono text-[0.8125rem] tabular-nums text-re-text-tertiary">
                                                {n.qty}
                                            </div>
                                        </Card>
                                        {i < TRACE_NODES.length - 1 && (
                                            <div className="flex items-center justify-center px-1 text-re-text-muted">
                                                <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                        <p className="mt-3 text-small text-re-text-tertiary">
                            Red border = transformation node where a single inbound lot fans out
                            into multiple downstream lots.
                        </p>
                    </Card>

                    {/* CSV download */}
                    <Card className="flex flex-col items-start justify-between gap-4 p-6 sm:flex-row sm:items-center">
                        <div>
                            <div className="mb-1 text-subheading text-re-text-primary">
                                Recall CSV ready
                            </div>
                            <div className="text-ui text-re-text-secondary">
                                21 CFR §§1.1325 to 1.1350 Key Data Elements · 11 rows · synthetic data
                            </div>
                        </div>
                        <Button asChild size="lg" className="shrink-0">
                            <a href={outputCsvUrl} download>
                                <Download strokeWidth={1.75} aria-hidden="true" />
                                Download recall CSV
                            </a>
                        </Button>
                    </Card>
                </Container>
            )}

            {/* ─── Idle-state explainer ────────────────── */}
            {state === 'idle' && (
                <Container as="section" className="pb-10">
                    <Card className="p-6">
                        <h2 className="mb-3 text-heading text-re-text-primary">What happens when you click start</h2>
                        <ol className="flex flex-col gap-2 text-ui text-re-text-secondary">
                            <li>
                                <span className="font-mono tabular-nums text-re-text-primary">1.</span> RegEngine loads a known-contaminated lot
                                ({' '}
                                <code className="font-mono text-[0.8125rem] text-re-text-primary">SV-20240115-001</code>) from
                                the synthetic dataset.
                            </li>
                            <li>
                                <span className="font-mono tabular-nums text-re-text-primary">2.</span> The recall simulator walks downstream
                                through all 7 CTEs: harvesting, cooling, packing, shipping,
                                receiving, transformation, shipping again.
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
                        All data is synthetic. The drill runs on a frozen public dataset separate
                        from any customer data. Run as many times as you like; results are
                        deterministic.
                    </span>
                </Container>
            </div>
        </div>
    );
}
