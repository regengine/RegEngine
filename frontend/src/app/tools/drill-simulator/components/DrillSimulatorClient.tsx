'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    ShieldAlert,
    Play,
    CheckCircle2,
    XCircle,
    AlertTriangle,
    FileText,
    ArrowRight,
    Clock,
    Loader2,
    Network,
} from 'lucide-react';
import { apiClient } from '@/lib/api-client';

type DrillPhase = 'ready' | 'active' | 'checklist' | 'graded';

const SCENARIOS = [
    {
        title: 'Outbreak Investigation — Romaine Lettuce',
        description:
            'FDA has identified a potential Salmonella link. Provide all traceability records for the flagged lot within 24 hours.',
        targetProduct: 'Romaine Lettuce',
        targetTLC: 'TLC1001',
        citation: '21 CFR 1.1455(a)',
    },
    {
        title: 'Routine Compliance Check — Fresh Tomatoes',
        description:
            'Routine FSMA 204 assessment. Demonstrate ability to trace product from receipt through distribution.',
        targetProduct: 'Roma Tomatoes',
        targetTLC: 'TOM-0226-F3-001',
        citation: '21 CFR 1.1455(a)',
    },
    {
        title: 'Retailer-Initiated Trace — Atlantic Salmon',
        description:
            'Temperature excursion flagged on imported seafood. Full chain-of-custody records requested.',
        targetProduct: 'Atlantic Salmon Fillets',
        targetTLC: 'SAL-0226-B1-007',
        citation: '21 CFR 1.1455(a), 21 CFR 1.1325(c)',
    },
];

const CHECKLIST_ITEMS = [
    { id: 'lot_genealogy', label: 'Lot Genealogy', description: 'Can trace lot from farm to current location', points: 20 },
    { id: 'electronic_records', label: 'Electronic Records', description: 'Records in electronic, sortable format', points: 20 },
    { id: 'all_ctes', label: 'All CTEs Present', description: 'Ship, Receive, and Transformation events tracked', points: 15 },
    { id: 'all_kdes', label: 'All KDEs Present', description: 'GLN, TLC source, timestamps on every event', points: 15 },
    { id: 'chain_verification', label: 'Chain Integrity', description: 'SHA-256 hash chain verified end-to-end', points: 15 },
    { id: 'epcis_export', label: 'EPCIS 2.0 Export', description: 'Can export in GS1 JSON-LD format', points: 15 },
];

function formatTime(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

interface LiveDrillResult {
    drill_id?: string;
    status?: string;
    impacted_count?: number;
    error?: string;
}

export function DrillSimulatorClient() {
    const [phase, setPhase] = useState<DrillPhase>('ready');
    const [selectedScenario, setSelectedScenario] = useState(0);
    const [timeRemaining, setTimeRemaining] = useState(24 * 60 * 60);
    const [startTime, setStartTime] = useState<Date | null>(null);
    const [checklist, setChecklist] = useState<Record<string, boolean>>({});
    const [grade, setGrade] = useState<{ score: number; grade: string; feedback: string[] } | null>(null);

    // Live recall drill state
    const [drillRunning, setDrillRunning] = useState(false);
    const [liveDrill, setLiveDrill] = useState<LiveDrillResult | null>(null);

    useEffect(() => {
        if (phase !== 'active' && phase !== 'checklist') return;
        const interval = setInterval(() => {
            setTimeRemaining((prev) => Math.max(0, prev - 1));
        }, 1000);
        return () => clearInterval(interval);
    }, [phase]);

    const runLiveDrill = useCallback(async (scenario: typeof SCENARIOS[0]) => {
        setDrillRunning(true);
        setLiveDrill(null);
        try {
            const result = await apiClient.createRecallDrill({
                type: 'forward_trace',
                target_tlc: scenario.targetTLC,
                severity: 'class_ii',
                reason: `${scenario.title} — drill`,
            });
            const impacted = result.impacted_lots?.length
                ?? result.nodes?.length
                ?? result.trace?.length
                ?? undefined;
            setLiveDrill({
                drill_id: result.drill_id || result.id,
                status: result.status,
                impacted_count: impacted,
            });
        } catch (err: any) {
            const msg = err?.response?.data?.detail || err?.message || 'Recall service unreachable';
            setLiveDrill({ error: msg });
        } finally {
            setDrillRunning(false);
        }
    }, []);

    const handleStartDrill = useCallback(() => {
        setPhase('active');
        setStartTime(new Date());
        setTimeRemaining(24 * 60 * 60);
        setChecklist({});
        setGrade(null);
        setLiveDrill(null);
        runLiveDrill(SCENARIOS[selectedScenario]);
    }, [selectedScenario, runLiveDrill]);

    const handleToggleItem = useCallback((id: string) => {
        setChecklist((prev) => ({ ...prev, [id]: !prev[id] }));
    }, []);

    const handleSubmitGrade = useCallback(() => {
        let score = 0;
        const feedback: string[] = [];

        CHECKLIST_ITEMS.forEach((item) => {
            if (checklist[item.id]) {
                score += item.points;
            } else {
                feedback.push(`Missing: ${item.label} — ${item.description}`);
            }
        });

        const elapsed = startTime ? (Date.now() - startTime.getTime()) / 1000 : 0;
        const elapsedHours = elapsed / 3600;
        if (elapsedHours <= 1) {
            feedback.unshift('Excellent — responded in under 1 hour');
        } else if (elapsedHours <= 4) {
            feedback.unshift('Good — responded within 4 hours');
        }

        const letterGrade = score >= 90 ? 'A' : score >= 80 ? 'B' : score >= 70 ? 'C' : score >= 60 ? 'D' : 'F';
        setGrade({ score, grade: letterGrade, feedback });
        setPhase('graded');
    }, [checklist, startTime]);

    const scenario = SCENARIOS[selectedScenario];
    const urgencyColor = timeRemaining < 3600 ? 'text-red-500' : timeRemaining < 14400 ? 'text-amber-500' : 'text-[var(--re-brand)]';

    return (
        <FreeToolPageShell
            title="Mock Audit Drill"
            subtitle="Simulate an FDA traceability records request. Test your 24-hour response readiness under realistic conditions."
            relatedToolIds={['ftl-checker', 'cte-mapper', 'kde-checker']}
        >
            <AnimatePresence mode="wait">
                {phase === 'ready' && (
                    <motion.div key="ready" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-6">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {SCENARIOS.map((s, i) => (
                                <button
                                    key={i}
                                    type="button"
                                    onClick={() => setSelectedScenario(i)}
                                    className={`text-left p-4 rounded-xl border transition-all ${selectedScenario === i
                                            ? 'border-[var(--re-brand)] bg-[color-mix(in_srgb,var(--re-brand)_5%,transparent)] shadow-lg'
                                            : 'border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] hover:border-[var(--re-brand)]'
                                        }`}
                                >
                                    <div className="text-sm font-bold mb-2">{s.title}</div>
                                    <div className="text-xs text-muted-foreground mb-3">{s.description}</div>
                                    <Badge variant="outline" className="text-[8px] uppercase tracking-widest">{s.citation}</Badge>
                                </button>
                            ))}
                        </div>
                        <Button
                            onClick={handleStartDrill}
                            className="w-full md:w-auto bg-red-600 hover:bg-red-700 text-white h-12 px-8 rounded-xl text-base font-bold"
                        >
                            <Play className="mr-2 h-5 w-5" />
                            Start Drill — 24 Hour Timer Begins
                        </Button>
                    </motion.div>
                )}

                {phase === 'active' && (
                    <motion.div key="active" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} className="space-y-6">
                        <Card className="border-red-500/30 bg-red-500/5">
                            <CardContent className="py-8">
                                <div className="flex flex-col items-center text-center gap-4">
                                    <ShieldAlert className="h-12 w-12 text-red-500" />
                                    <h2 className="text-xl font-bold">FDA RECORDS REQUEST</h2>
                                    <div className={`text-5xl font-mono font-bold ${urgencyColor}`}>
                                        {formatTime(timeRemaining)}
                                    </div>
                                    <div className="text-sm text-muted-foreground">Time Remaining</div>
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base">{scenario.title}</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <p className="text-sm text-muted-foreground">{scenario.description}</p>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                        <div className="text-xs text-muted-foreground">Target Product</div>
                                        <div className="text-sm font-bold">{scenario.targetProduct}</div>
                                    </div>
                                    <div className="p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                        <div className="text-xs text-muted-foreground">Lot Code</div>
                                        <div className="text-sm font-mono font-bold">{scenario.targetTLC}</div>
                                    </div>
                                </div>

                                {/* Live recall drill status */}
                                <div className={`flex items-center gap-3 p-3 rounded-xl border text-sm ${
                                    drillRunning
                                        ? 'border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]'
                                        : liveDrill?.error
                                        ? 'border-amber-500/30 bg-amber-500/5'
                                        : 'border-emerald-500/30 bg-emerald-500/5'
                                }`}>
                                    {drillRunning ? (
                                        <>
                                            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground shrink-0" />
                                            <span className="text-muted-foreground text-xs">Running live recall drill against graph service…</span>
                                        </>
                                    ) : liveDrill?.error ? (
                                        <>
                                            <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
                                            <div>
                                                <div className="text-xs font-medium">Graph service offline — drill running in simulation mode</div>
                                                <div className="text-xs text-muted-foreground">{liveDrill.error}</div>
                                            </div>
                                        </>
                                    ) : liveDrill ? (
                                        <>
                                            <Network className="h-4 w-4 text-emerald-500 shrink-0" />
                                            <div>
                                                <div className="text-xs font-medium text-emerald-700 dark:text-emerald-400">
                                                    Live recall drill active — {liveDrill.status ?? 'running'}
                                                </div>
                                                <div className="text-xs text-muted-foreground font-mono">
                                                    {liveDrill.drill_id && `ID: ${liveDrill.drill_id}`}
                                                    {liveDrill.impacted_count !== undefined && ` · ${liveDrill.impacted_count} impacted lots`}
                                                </div>
                                            </div>
                                        </>
                                    ) : null}
                                </div>

                                <Button
                                    onClick={() => setPhase('checklist')}
                                    className="w-full bg-[var(--re-brand)] hover:brightness-110 text-white h-12 rounded-xl font-bold"
                                >
                                    I Have My Records — Grade My Response
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Button>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {phase === 'checklist' && (
                    <motion.div key="checklist" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-6">
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-bold">Response Checklist</h2>
                            <div className={`flex items-center gap-2 text-sm font-mono font-bold ${urgencyColor}`}>
                                <Clock className="h-4 w-4" /> {formatTime(timeRemaining)}
                            </div>
                        </div>
                        <div className="space-y-3">
                            {CHECKLIST_ITEMS.map((item) => (
                                <button
                                    key={item.id}
                                    type="button"
                                    onClick={() => handleToggleItem(item.id)}
                                    className={`w-full text-left p-4 rounded-xl border transition-all flex items-center gap-4 ${checklist[item.id]
                                            ? 'border-emerald-500/50 bg-emerald-500/5'
                                            : 'border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] hover:border-[var(--re-brand)]'
                                        }`}
                                >
                                    {checklist[item.id] ? (
                                        <CheckCircle2 className="h-6 w-6 text-emerald-500 flex-shrink-0" />
                                    ) : (
                                        <div className="h-6 w-6 rounded-full border-2 border-[var(--re-border-default)] flex-shrink-0" />
                                    )}
                                    <div className="flex-1">
                                        <div className="text-sm font-medium">{item.label}</div>
                                        <div className="text-xs text-muted-foreground">{item.description}</div>
                                    </div>
                                    <Badge variant="outline" className="text-[9px]">{item.points} pts</Badge>
                                </button>
                            ))}
                        </div>
                        <Button
                            onClick={handleSubmitGrade}
                            className="w-full bg-[var(--re-brand)] hover:brightness-110 text-white h-12 rounded-xl font-bold"
                        >
                            Submit for Grading
                        </Button>
                    </motion.div>
                )}

                {phase === 'graded' && grade && (
                    <motion.div key="graded" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="space-y-6">
                        <Card className={`border-2 ${grade.score >= 70 ? 'border-emerald-500/30' : 'border-red-500/30'}`}>
                            <CardContent className="py-10">
                                <div className="flex flex-col items-center text-center gap-4">
                                    <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring' }}>
                                        {grade.score >= 70 ? (
                                            <CheckCircle2 className="h-16 w-16 text-emerald-500" />
                                        ) : (
                                            <XCircle className="h-16 w-16 text-red-500" />
                                        )}
                                    </motion.div>
                                    <div>
                                        <div className={`text-6xl font-bold ${grade.score >= 70 ? 'text-[var(--re-brand)]' : 'text-red-500'}`}>
                                            {grade.grade}
                                        </div>
                                        <div className="text-lg text-muted-foreground">{grade.score}/100</div>
                                    </div>
                                    <Badge className={grade.score >= 70 ? 'bg-emerald-600' : 'bg-red-600'}>
                                        {grade.score >= 70 ? 'PASSED — Audit Ready' : 'FAILED — Action Required'}
                                    </Badge>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Live drill result card */}
                        {liveDrill && !liveDrill.error && (
                            <Card className="border-[var(--re-border-default)]">
                                <CardHeader>
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <Network className="h-4 w-4 text-[var(--re-brand)]" />
                                        Live Recall Drill Result
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="grid grid-cols-2 gap-3 text-sm">
                                        <div className="p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                            <div className="text-xs text-muted-foreground mb-1">Status</div>
                                            <div className="font-medium capitalize">{liveDrill.status ?? '—'}</div>
                                        </div>
                                        <div className="p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                            <div className="text-xs text-muted-foreground mb-1">Impacted Lots</div>
                                            <div className="font-medium">{liveDrill.impacted_count ?? '—'}</div>
                                        </div>
                                        {liveDrill.drill_id && (
                                            <div className="col-span-2 p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                                <div className="text-xs text-muted-foreground mb-1">Drill ID</div>
                                                <div className="font-mono text-xs">{liveDrill.drill_id}</div>
                                            </div>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>
                        )}

                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base">Feedback</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ul className="space-y-2">
                                    {grade.feedback.map((item, i) => (
                                        <li key={i} className="flex items-start gap-2 text-sm">
                                            {item.startsWith('Missing') ? (
                                                <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
                                            ) : (
                                                <CheckCircle2 className="h-4 w-4 text-emerald-500 mt-0.5 flex-shrink-0" />
                                            )}
                                            <span>{item}</span>
                                        </li>
                                    ))}
                                </ul>
                            </CardContent>
                        </Card>

                        <Button onClick={() => setPhase('ready')} variant="outline" className="rounded-xl">
                            Run Another Drill
                        </Button>
                    </motion.div>
                )}
            </AnimatePresence>
        </FreeToolPageShell>
    );
}
