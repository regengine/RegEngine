'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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

/* ─────────────────────────────────────────────────────────────
   DESIGN TOKENS (matches /verify and /proof family)
   ───────────────────────────────────────────────────────────── */
const T = {
    bg: 'var(--re-surface-base)',
    surface: 'rgba(255,255,255,0.02)',
    elevated: 'rgba(255,255,255,0.05)',
    border: 'rgba(255,255,255,0.06)',
    borderHover: 'rgba(255,255,255,0.12)',
    text: 'var(--re-text-primary)',
    textDim: 'var(--re-text-tertiary)',
    textMuted: 'var(--re-text-muted)',
    accent: 'var(--re-success)',
    accentDim: 'rgba(34,197,94,0.12)',
    danger: 'var(--re-danger)',
    dangerDim: 'rgba(239,68,68,0.12)',
    info: 'var(--re-info)',
    mono: "'SF Mono', 'Fira Code', 'JetBrains Mono', Consolas, monospace",
    brand: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
};

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
            'Wrote 21 CFR §§1.1325–1.1350 Key Data Elements for each downstream lot',
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
        <div className="min-h-screen pb-32" style={{ background: T.bg, color: T.text }}>
            {/* ─── Hero ──────────────────────────────────────────────── */}
            <section className="max-w-[960px] mx-auto text-center px-6 pt-20 pb-10">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                >
                    <div
                        className="inline-flex items-center gap-2 px-4 py-1.5 rounded-[20px] text-[13px] font-medium mb-6"
                        style={{ background: T.dangerDim, color: T.danger }}
                    >
                        <AlertTriangle size={14} />
                        Live Recall Drill • Synthetic Data
                    </div>

                    <h1
                        className="text-[clamp(32px,5vw,56px)] font-bold leading-[1.1] mb-4"
                        style={{ fontFamily: T.brand }}
                    >
                        Run a recall drill on synthetic supply-chain data.
                    </h1>

                    <p
                        className="text-lg max-w-[680px] mx-auto mb-8 leading-relaxed"
                        style={{ color: T.textDim }}
                    >
                        Click <span className="font-semibold" style={{ color: T.text }}>Start drill</span> — RegEngine
                        traces the contaminated lot through the applicable CTEs and produces an FDA-oriented sortable
                        recall CSV in under 60 seconds. Synthetic data — illustrative only.
                    </p>

                    <div className="flex gap-3 justify-center flex-wrap">
                        {state === 'idle' && (
                            <button
                                onClick={startDrill}
                                className="inline-flex items-center gap-2 px-6 py-3 rounded-lg text-[15px] font-semibold cursor-pointer text-black border-none"
                                style={{ background: T.accent }}
                            >
                                <Play size={16} fill="currentColor" />
                                Start drill
                            </button>
                        )}
                        {state === 'running' && (
                            <button
                                disabled
                                className="inline-flex items-center gap-2 px-6 py-3 rounded-lg text-[15px] font-semibold border-none"
                                style={{ background: T.elevated, color: T.textDim, cursor: 'not-allowed' }}
                            >
                                <Clock size={16} className="animate-pulse" />
                                Drill in progress · {elapsedS}s
                            </button>
                        )}
                        {state === 'loading' && (
                            <button
                                disabled
                                className="inline-flex items-center gap-2 px-6 py-3 rounded-lg text-[15px] font-semibold border-none"
                                style={{ background: T.elevated, color: T.textDim, cursor: 'not-allowed' }}
                            >
                                <Clock size={16} className="animate-pulse" />
                                Starting endpoint run…
                            </button>
                        )}
                        {state === 'done' && (
                            <button
                                onClick={resetDrill}
                                className="inline-flex items-center gap-2 px-6 py-3 rounded-lg text-[15px] font-medium cursor-pointer border-none"
                                style={{
                                    background: T.elevated,
                                    border: `1px solid ${T.border}`,
                                    color: T.text,
                                }}
                            >
                                <RotateCcw size={16} />
                                Run again
                            </button>
                        )}
                    </div>
                    {errorMessage && (
                        <p
                            className="text-sm mt-4 mb-0"
                            style={{ color: T.danger }}
                            role="alert"
                        >
                            {errorMessage}
                        </p>
                    )}
                </motion.div>
            </section>

            {/* ─── Progress / Steps ─────────────────────────────────── */}
            {(state === 'running' || state === 'done') && (
                <section className="max-w-[760px] mx-auto px-4 sm:px-6 pb-10">
                    <div
                        className="rounded-xl overflow-hidden"
                        style={{ background: T.surface, border: `1px solid ${T.border}` }}
                    >
                        <div
                            className="flex items-center justify-between px-5 py-3"
                            style={{ borderBottom: `1px solid ${T.border}`, background: T.elevated }}
                        >
                            <span className="text-xs uppercase tracking-wider" style={{ color: T.textMuted }}>
                                Drill log
                            </span>
                            <span
                                className="text-xs"
                                style={{ fontFamily: T.mono, color: T.textDim }}
                            >
                                {state === 'done'
                                    ? `done · ${totalDurationLabel}s total`
                                    : `running · ${elapsedS}s`}
                            </span>
                        </div>
                        <div className="p-5 flex flex-col gap-3">
                            {drillSteps.map((step, idx) => {
                                const isComplete = activeStep > idx || state === 'done';
                                const isActive = activeStep === idx && state === 'running';
                                const isPending = activeStep < idx && state === 'running';
                                return (
                                    <div key={idx} className="flex items-start gap-3">
                                        <div
                                            className="w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5"
                                            style={{
                                                background: isComplete
                                                    ? T.accentDim
                                                    : isActive
                                                        ? T.dangerDim
                                                        : T.elevated,
                                                color: isComplete
                                                    ? T.accent
                                                    : isActive
                                                        ? T.danger
                                                        : T.textMuted,
                                            }}
                                        >
                                            {isComplete ? (
                                                <CheckCircle2 size={14} />
                                            ) : isActive ? (
                                                <Clock size={12} className="animate-pulse" />
                                            ) : (
                                                <span className="text-[11px]">{idx + 1}</span>
                                            )}
                                        </div>
                                        <div className="flex-1">
                                            <div
                                                className="text-[14px] font-medium"
                                                style={{
                                                    color: isPending ? T.textMuted : T.text,
                                                }}
                                            >
                                                {step.label}
                                                {isActive && '…'}
                                            </div>
                                            {(isComplete || isActive) && (
                                                <div
                                                    className="mt-1 text-[12.5px] leading-relaxed"
                                                    style={{ color: T.textDim, fontFamily: T.mono }}
                                                >
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
                    </div>
                </section>
            )}

            {/* ─── Result panel (after done) ────────────────────────── */}
            <AnimatePresence>
                {state === 'done' && (
                    <motion.section
                        initial={{ opacity: 0, y: 24 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4 }}
                        className="max-w-[960px] mx-auto px-4 sm:px-6 pb-10"
                    >
                        {/* Time-to-trace metric */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
                            <MetricCard
                                label="Time to trace"
                                value={`${finalSecondsLabel}s`}
                                sub={`Synthetic lot ${drill.lot_code}`}
                                tone="success"
                            />
                            <MetricCard
                                label="FDA mandate"
                                value="24 hours"
                                sub="§ 204 — produce records on request"
                                tone="info"
                            />
                            <MetricCard
                                label="Margin"
                                value={`${marginMultiple}× faster`}
                                sub="Headroom vs. regulatory window"
                                tone="success"
                            />
                        </div>

                        {/* Trace diagram */}
                        <div
                            className="rounded-xl p-6 mb-8"
                            style={{ background: T.surface, border: `1px solid ${T.border}` }}
                        >
                            <h2 className="text-[18px] font-semibold mb-4">Forward trace graph</h2>
                            <div className="overflow-x-auto">
                                <div className="flex items-stretch gap-2 min-w-max pb-2">
                                    {TRACE_NODES.map((n, i) => (
                                        <div key={n.id} className="flex items-stretch">
                                            <div
                                                className="rounded-lg p-3 min-w-[170px]"
                                                style={{
                                                    background: T.elevated,
                                                    border: `1px solid ${
                                                        n.cte === 'TRANSFORMATION' ? T.danger : T.border
                                                    }`,
                                                }}
                                            >
                                                <div
                                                    className="text-[10px] uppercase tracking-wider mb-1"
                                                    style={{
                                                        color: n.cte === 'TRANSFORMATION' ? T.danger : T.textMuted,
                                                        fontFamily: T.mono,
                                                    }}
                                                >
                                                    {n.cte}
                                                </div>
                                                <div className="text-[13px] font-semibold mb-1">
                                                    {n.facility}
                                                </div>
                                                <div
                                                    className="text-[11px]"
                                                    style={{ color: T.textDim, fontFamily: T.mono }}
                                                >
                                                    {n.lot}
                                                </div>
                                                <div
                                                    className="text-[11px]"
                                                    style={{ color: T.textMuted }}
                                                >
                                                    {n.qty}
                                                </div>
                                            </div>
                                            {i < TRACE_NODES.length - 1 && (
                                                <div
                                                    className="flex items-center justify-center px-1"
                                                    style={{ color: T.textMuted }}
                                                >
                                                    <ArrowRight size={14} />
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                            <p
                                className="mt-3 text-[12px]"
                                style={{ color: T.textMuted }}
                            >
                                Red border = transformation node where a single inbound lot fans out
                                into multiple downstream lots.
                            </p>
                        </div>

                        {/* CSV download */}
                        <div
                            className="rounded-xl p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
                            style={{ background: T.surface, border: `1px solid ${T.border}` }}
                        >
                            <div>
                                <div className="text-[15px] font-semibold mb-1">
                                    Recall CSV ready
                                </div>
                                <div className="text-[13px]" style={{ color: T.textDim }}>
                                    21 CFR §§1.1325–1.1350 Key Data Elements · 11 rows · synthetic data
                                </div>
                            </div>
                            <a
                                href={outputCsvUrl}
                                download
                                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-[14px] font-semibold no-underline text-black"
                                style={{ background: T.accent }}
                            >
                                <Download size={15} />
                                Download recall CSV
                            </a>
                        </div>
                    </motion.section>
                )}
            </AnimatePresence>

            {/* ─── Idle-state explainer ─────────────────────────────── */}
            {state === 'idle' && (
                <section className="max-w-[820px] mx-auto px-4 sm:px-6 pb-10">
                    <div
                        className="rounded-xl p-6"
                        style={{ background: T.surface, border: `1px solid ${T.border}` }}
                    >
                        <h2 className="text-[18px] font-semibold mb-3">What happens when you click start</h2>
                        <ol className="flex flex-col gap-2 text-[14px]" style={{ color: T.textDim }}>
                            <li>
                                <span style={{ color: T.text }}>1.</span> RegEngine loads a known-contaminated lot
                                ({' '}
                                <code style={{ fontFamily: T.mono, color: T.accent }}>SV-20240115-001</code>) from
                                the synthetic dataset.
                            </li>
                            <li>
                                <span style={{ color: T.text }}>2.</span> The recall simulator walks downstream
                                through all 7 CTEs — harvesting, cooling, packing, shipping,
                                receiving, transformation, shipping again.
                            </li>
                            <li>
                                <span style={{ color: T.text }}>3.</span> Every receiver of the contaminated lot
                                (and any downstream lot derived from it via transformation) is
                                identified.
                            </li>
                            <li>
                                <span style={{ color: T.text }}>4.</span> The output is a recall CSV in the format
                                FDA inspectors will request under § 204.
                            </li>
                        </ol>
                    </div>
                </section>
            )}

            {/* ─── Sticky footer ───────────────────────────────────── */}
            <div
                className="fixed bottom-0 left-0 right-0 z-40 px-4 py-3 flex items-center justify-center gap-2 text-[12.5px]"
                style={{
                    background: 'rgba(0,0,0,0.65)',
                    backdropFilter: 'blur(8px)',
                    borderTop: `1px solid ${T.border}`,
                    color: T.textDim,
                }}
            >
                <Lock size={12} />
                <span>
                    All data is synthetic. The drill runs on a frozen public dataset separate
                    from any customer data. Run as many times as you like — results are
                    deterministic.
                </span>
            </div>
        </div>
    );
}

/* ───────────────────────────────────────────── helpers ──── */

function MetricCard({
    label,
    value,
    sub,
    tone,
}: {
    label: string;
    value: string;
    sub: string;
    tone: 'success' | 'info';
}) {
    const color = tone === 'success' ? T.accent : T.info;
    const bg = tone === 'success' ? T.accentDim : 'rgba(59,130,246,0.10)';
    return (
        <div
            className="rounded-xl p-5"
            style={{ background: T.surface, border: `1px solid ${T.border}` }}
        >
            <div
                className="text-[11px] uppercase tracking-wider mb-2"
                style={{ color: T.textMuted }}
            >
                {label}
            </div>
            <div
                className="text-[28px] font-bold mb-1 inline-block px-2 py-0.5 rounded-md"
                style={{ color, background: bg }}
            >
                {value}
            </div>
            <div className="text-[12.5px]" style={{ color: T.textDim }}>
                {sub}
            </div>
        </div>
    );
}
