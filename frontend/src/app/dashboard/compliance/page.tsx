'use client';

import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import { Spinner } from '@/components/ui/spinner';
import {
    Shield,
    ShieldAlert,
    ShieldX,
    ArrowRight,
    Download,
    FileText,
    Timer,
    Activity,
    TrendingUp,
    Zap,
    AlertTriangle,
    CheckCircle2,
    Upload,
    Info,
    RefreshCw,
} from 'lucide-react';

import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { fetchComplianceScore } from '@/lib/api-hooks';

/* ── Types matching ComplianceScoreResponse from backend ── */

interface ScoreBreakdownItem {
    score: number;
    detail: string;
}

interface NextAction {
    priority: string;
    action: string;
    impact: string;
}

interface ComplianceScore {
    tenant_id: string;
    overall_score: number;
    grade: string;
    breakdown: Record<string, ScoreBreakdownItem>;
    next_actions: NextAction[];
    events_analyzed: number;
    last_chain_hash: string | null;
}

/* ── Action → Route map ── */
function actionRoute(action: string): string | null {
    const a = action.toLowerCase();
    if (a.includes('receiv') || a.includes('inbound') || a.includes('ingest')) return '/dashboard/receiving';
    if (a.includes('supplier') || a.includes('facility') || a.includes('trading partner')) return '/dashboard/suppliers';
    if (a.includes('scan') || a.includes('barcode') || a.includes('label') || a.includes('capture')) return '/dashboard/scan';
    if (a.includes('recall') || a.includes('drill') || a.includes('mock')) return '/dashboard/recall-drills';
    if (a.includes('export') || a.includes('report') || a.includes('fda')) return '/dashboard/export-jobs';
    if (a.includes('setting') || a.includes('api') || a.includes('key') || a.includes('integrat')) return '/dashboard/settings';
    if (a.includes('event') || a.includes('record') || a.includes('data field')) return '/dashboard/receiving';
    return null;
}

/* ── Helpers ── */

function scoreColor(score: number) {
    if (score >= 80) return 'var(--re-brand)';
    if (score >= 60) return '#f59e0b';
    return '#ef4444';
}

function statusLevel(score: number): 'compliant' | 'at-risk' | 'critical' {
    if (score >= 80) return 'compliant';
    if (score >= 60) return 'at-risk';
    return 'critical';
}

const STATUS_CONFIG = {
    'compliant': {
        icon: Shield,
        label: 'FSMA 204 Compliant',
        desc: 'Your traceability program meets current FDA requirements.',
        bg: 'bg-re-brand-muted border-re-brand/30',
        text: 'text-re-brand',
    },
    'at-risk': {
        icon: ShieldAlert,
        label: 'At Risk — Action Needed',
        desc: 'Gaps in your traceability data could cause issues during an FDA inspection.',
        bg: 'bg-re-warning-muted0/10 border-re-warning/30',
        text: 'text-re-warning',
    },
    'critical': {
        icon: ShieldX,
        label: 'Critical — Not Compliant',
        desc: 'Significant gaps exist. Prioritize the actions below before your next audit.',
        bg: 'bg-re-danger-muted0/10 border-re-danger/30',
        text: 'text-re-danger',
    },
};

/* ── Dimension metadata ── */

const DIMENSION_META: Record<string, { label: string; weight: number; icon: string }> = {
    chain_integrity:     { label: 'Chain Integrity',     weight: 25, icon: '🔗' },
    kde_completeness:    { label: 'Data Fields Filled (KDE)',    weight: 20, icon: '📋' },
    cte_completeness:    { label: 'Events Recorded (CTE)',    weight: 20, icon: '📦' },
    obligation_coverage: { label: 'Obligation Coverage',  weight: 15, icon: '⚖️' },
    product_coverage:    { label: 'Product Coverage',     weight: 10, icon: '🏷️' },
    export_readiness:    { label: 'Export Readiness',     weight: 10, icon: '📤' },
};

/* ── Pure UI Components ── */

function ScoreGauge({ score, grade }: { score: number; grade: string }) {
    const circumference = 2 * Math.PI * 80;
    const offset = circumference - (score / 100) * circumference;
    const color = scoreColor(score);

    return (
        <div className="relative w-40 h-40 sm:w-52 sm:h-52 mx-auto">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 200 200">
                <circle cx="100" cy="100" r="80" stroke="var(--re-border-default)" strokeWidth="10" fill="none" opacity="0.3" />
                <motion.circle
                    cx="100" cy="100" r="80"
                    stroke={color}
                    strokeWidth="12"
                    fill="none"
                    strokeLinecap="round"
                    strokeDasharray={circumference}
                    initial={{ strokeDashoffset: circumference }}
                    animate={{ strokeDashoffset: offset }}
                    transition={{ duration: 1.5, ease: 'easeOut' }}
                />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
                <motion.div
                    className="text-4xl sm:text-5xl font-bold tabular-nums"
                    initial={{ opacity: 0, scale: 0.5 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.5, type: 'spring' }}
                    style={{ color }}
                >
                    {score}
                </motion.div>
                <motion.div
                    className="text-xs font-semibold tracking-wider uppercase mt-1"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.8 }}
                    style={{ color }}
                >
                    Grade {grade}
                </motion.div>
            </div>
        </div>
    );
}

function DimensionRow({ dimKey, item }: { dimKey: string; item: ScoreBreakdownItem }) {
    const meta = DIMENSION_META[dimKey] || { label: dimKey.replace(/_/g, ' '), weight: 0, icon: '📊' };
    const color = scoreColor(item.score);
    const isLow = item.score < 60;

    return (
        <motion.div
            className={`p-3 sm:p-4 rounded-xl border transition-colors ${isLow ? 'border-re-danger/30 bg-re-danger-muted0/[0.03]' : 'border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]'}`}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.4 }}
        >
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <span className="text-sm">{meta.icon}</span>
                    <span className="text-sm font-medium">{meta.label}</span>
                    <span className="text-[10px] text-muted-foreground bg-[var(--re-surface-card)] px-1.5 py-0.5 rounded-full">{meta.weight}%</span>
                </div>
                <div className="flex items-center gap-1.5">
                    {isLow && <AlertTriangle className="h-3.5 w-3.5 text-re-danger" />}
                    <span className="text-sm font-bold tabular-nums" style={{ color }}>{item.score}</span>
                </div>
            </div>
            <div className="h-2 rounded-full bg-[var(--re-surface-card)] overflow-hidden">
                <motion.div
                    className="h-full rounded-full"
                    style={{ backgroundColor: color }}
                    initial={{ width: 0 }}
                    animate={{ width: `${item.score}%` }}
                    transition={{ duration: 1, ease: 'easeOut', delay: 0.3 }}
                />
            </div>
            <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">{item.detail}</p>
        </motion.div>
    );
}

/* ── Page ── */

export default function ComplianceDashboardPage() {
    const { isAuthenticated, apiKey } = useAuth();
    const { tenantId } = useTenant();
    const isLoggedIn = isAuthenticated;

    const POLL_MS = Number(process.env.NEXT_PUBLIC_POLL_SLOW_MS) || 60_000;

    const { data: score = null, isLoading: loading, error: scoreError, dataUpdatedAt, refetch: fetchScore } = useQuery({
        queryKey: ['compliance-score', tenantId],
        queryFn: async () => {
            const data = await fetchComplianceScore(tenantId, apiKey || '');
            return data as ComplianceScore;
        },
        enabled: isLoggedIn && !!tenantId,
        refetchInterval: POLL_MS,
    });

    const error = scoreError?.message ?? null;
    const lastFetched = dataUpdatedAt ? new Date(dataUpdatedAt) : null;

    // Ordered breakdown keys by weight (highest first)
    const breakdownKeys = useMemo(() => {
        if (!score) return [];
        return Object.keys(score.breakdown).sort((a, b) => {
            const wa = DIMENSION_META[a]?.weight ?? 0;
            const wb = DIMENSION_META[b]?.weight ?? 0;
            return wb - wa;
        });
    }, [score]);

    // Count dimensions below threshold
    const criticalDims = useMemo(() => {
        if (!score) return 0;
        return Object.values(score.breakdown).filter(d => d.score < 60).length;
    }, [score]);

    // Lowest-scoring dimension for CTA
    const lowestDim = useMemo(() => {
        if (!score) return null;
        let lowest: { key: string; score: number } | null = null;
        for (const [key, item] of Object.entries(score.breakdown)) {
            if (!lowest || item.score < lowest.score) lowest = { key, score: item.score };
        }
        return lowest ? { key: lowest.key, label: DIMENSION_META[lowest.key]?.label ?? lowest.key.replace(/_/g, ' ') } : null;
    }, [score]);

    const status = score ? statusLevel(score.overall_score) : null;
    const statusCfg = status ? STATUS_CONFIG[status] : null;

    return (
        <div className="min-h-screen bg-background p-4 md:p-8 pt-4">
            <div className="mx-auto max-w-7xl space-y-6">
                <Breadcrumbs items={[
                    { label: 'Dashboard', href: '/dashboard' },
                    { label: 'Compliance' },
                ]} />

                {/* Header */}
                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight">
                            Compliance Dashboard
                        </h1>
                        <p className="mt-1 text-sm text-muted-foreground">
                            Real-time FSMA 204 readiness score and audit preparedness
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        {lastFetched && (
                            <span className="text-[10px] text-muted-foreground">
                                Updated {lastFetched.toLocaleTimeString()}
                            </span>
                        )}
                        {score && (
                            <Button
                                variant="ghost" size="sm"
                                onClick={() => fetchScore()}
                                disabled={loading}
                                className="h-8 w-8 p-0"
                            >
                                <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                            </Button>
                        )}
                    </div>
                </div>

                {/* Auth gate */}
                {!isLoggedIn && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-6 text-center text-sm text-muted-foreground">
                            Sign in to view your compliance score.
                        </CardContent>
                    </Card>
                )}

                {/* Loading */}
                {loading && !score && (
                    <div className="flex flex-col items-center justify-center py-16 gap-3">
                        <Spinner size="lg" />
                        <p className="text-sm text-muted-foreground">Analyzing your traceability data...</p>
                    </div>
                )}

                {/* Error */}
                {error && (
                    <Card className="border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
                        <CardContent className="py-4">
                            <div className="flex items-center gap-3 text-muted-foreground">
                                <Info className="h-5 w-5 flex-shrink-0" />
                                <div>
                                    <p className="text-sm font-medium text-foreground">Compliance data is being set up. Check back shortly.</p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Score Content */}
                {score && !loading && (
                    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">

                        {/* Status Banner */}
                        {statusCfg && (
                            <motion.div
                                className={`flex items-center gap-3 p-4 rounded-xl border ${statusCfg.bg}`}
                                initial={{ opacity: 0, y: -10 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.2 }}
                            >
                                <statusCfg.icon className={`h-6 w-6 flex-shrink-0 ${statusCfg.text}`} />
                                <div className="flex-1 min-w-0">
                                    <div className={`text-sm font-bold ${statusCfg.text}`}>{statusCfg.label}</div>
                                    <div className="text-xs text-muted-foreground mt-0.5">{statusCfg.desc}</div>
                                </div>
                                {criticalDims > 0 && (
                                    <Badge variant="secondary" className="text-[10px] bg-re-danger-muted0/10 text-re-danger border-re-danger/20">
                                        {criticalDims} gap{criticalDims !== 1 ? 's' : ''}
                                    </Badge>
                                )}
                            </motion.div>
                        )}

                        {/* Score Gauge + Summary */}
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
                            <Card className="border-[var(--re-border-default)]">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-base">Overall Readiness</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <ScoreGauge score={score.overall_score} grade={score.grade} />
                                    <div className="text-center mt-4 space-y-1">
                                        <p className="text-xs text-muted-foreground">
                                            Based on <span className="font-semibold text-foreground">{score.events_analyzed.toLocaleString()}</span> traceability events
                                        </p>
                                        {score.last_chain_hash && (
                                            <p className="font-mono text-[10px] text-muted-foreground truncate px-4">
                                                Chain: {score.last_chain_hash.slice(0, 16)}...
                                            </p>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>

                            {/* Score Breakdown */}
                            <Card className="border-[var(--re-border-default)] lg:col-span-2">
                                <CardHeader className="pb-2">
                                    <div className="flex items-center justify-between">
                                        <CardTitle className="text-base">Score Breakdown</CardTitle>
                                        <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                                            <Info className="h-3 w-3" /> Weights shown as %
                                        </span>
                                    </div>
                                </CardHeader>
                                <CardContent className="space-y-2.5">
                                    {breakdownKeys.map((key, i) => (
                                        <motion.div key={key} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 * i }}>
                                            <DimensionRow dimKey={key} item={score.breakdown[key]} />
                                        </motion.div>
                                    ))}
                                </CardContent>
                            </Card>
                        </div>

                        {/* Quick Actions + Next Steps */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
                            <Card className="border-[var(--re-border-default)]">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <Zap className="h-4 w-4 text-[var(--re-brand)]" />
                                        Quick Actions
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="grid grid-cols-2 gap-2 sm:gap-3">
                                    <Link href="/tools/drill-simulator">
                                        <Button variant="outline" className="w-full h-auto min-h-[56px] py-3 flex flex-col gap-1.5 rounded-xl active:scale-[0.97] hover:border-[var(--re-brand)] transition-colors">
                                            <Timer className="h-5 w-5 text-[var(--re-brand)]" />
                                            <span className="text-xs font-medium">Mock Drill</span>
                                            <span className="text-[9px] text-muted-foreground">24-hr simulation</span>
                                        </Button>
                                    </Link>
                                    <Link href="/tools/data-import">
                                        <Button variant="outline" className="w-full h-auto min-h-[56px] py-3 flex flex-col gap-1.5 rounded-xl active:scale-[0.97] hover:border-[var(--re-brand)] transition-colors">
                                            <Upload className="h-5 w-5 text-[var(--re-brand)]" />
                                            <span className="text-xs font-medium">Import Data</span>
                                            <span className="text-[9px] text-muted-foreground">CSV / spreadsheet</span>
                                        </Button>
                                    </Link>
                                    <Button variant="outline" className="h-auto min-h-[56px] py-3 flex flex-col gap-1.5 rounded-xl opacity-60 cursor-not-allowed" disabled title="Coming in v1.1">
                                        <Download className="h-5 w-5 text-[var(--re-brand)]" />
                                        <span className="text-xs font-medium">FDA Report</span>
                                        <span className="text-[9px] text-muted-foreground">24-hr response</span>
                                    </Button>
                                    <Button variant="outline" className="h-auto min-h-[56px] py-3 flex flex-col gap-1.5 rounded-xl opacity-60 cursor-not-allowed" disabled title="Coming in v1.1">
                                        <FileText className="h-5 w-5 text-[var(--re-brand)]" />
                                        <span className="text-xs font-medium">EPCIS Export</span>
                                        <span className="text-[9px] text-muted-foreground">GS1 2.0 format</span>
                                    </Button>
                                </CardContent>
                            </Card>

                            {/* Next Actions */}
                            {score.next_actions.length > 0 && (
                                <Card className="border-[var(--re-border-default)]">
                                    <CardHeader className="pb-2">
                                        <div className="flex items-center justify-between">
                                            <CardTitle className="text-base flex items-center gap-2">
                                                <TrendingUp className="h-4 w-4 text-[var(--re-brand)]" />
                                                Improve Your Score
                                            </CardTitle>
                                            <Badge variant="secondary" className="text-[10px]">
                                                {score.next_actions.length} item{score.next_actions.length !== 1 ? 's' : ''}
                                            </Badge>
                                        </div>
                                    </CardHeader>
                                    <CardContent>
                                        <ul className="space-y-2">
                                            {score.next_actions.map((action, i) => {
                                                const route = actionRoute(action.action);
                                                const inner = (
                                                    <>
                                                        {action.priority === 'HIGH' ? (
                                                            <AlertTriangle className="h-4 w-4 text-re-danger mt-0.5 flex-shrink-0" />
                                                        ) : action.priority === 'MEDIUM' ? (
                                                            <Info className="h-4 w-4 text-re-warning mt-0.5 flex-shrink-0" />
                                                        ) : (
                                                            <CheckCircle2 className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                                                        )}
                                                        <div className="flex-1 min-w-0">
                                                            <div className="text-xs sm:text-sm font-medium leading-snug">{action.action}</div>
                                                            <div className="text-[11px] text-muted-foreground mt-0.5">{action.impact}</div>
                                                        </div>
                                                        <Badge
                                                            variant="secondary"
                                                            className={`text-[9px] uppercase tracking-widest rounded-full flex-shrink-0 ${
                                                                action.priority === 'HIGH' ? 'bg-re-danger-muted0/10 text-re-danger' :
                                                                action.priority === 'MEDIUM' ? 'bg-re-warning-muted0/10 text-re-warning' :
                                                                'bg-muted text-muted-foreground'
                                                            }`}
                                                        >
                                                            {action.priority}
                                                        </Badge>
                                                        {route && <ArrowRight className="h-3.5 w-3.5 text-muted-foreground mt-0.5 flex-shrink-0" />}
                                                    </>
                                                );
                                                return (
                                                    <motion.li
                                                        key={i}
                                                        initial={{ opacity: 0, x: 10 }}
                                                        animate={{ opacity: 1, x: 0 }}
                                                        transition={{ delay: 0.1 * i }}
                                                    >
                                                        {route ? (
                                                            <Link href={route} className="flex items-start gap-2.5 p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] hover:border-[var(--re-brand)] hover:bg-[var(--re-surface-card)] transition-colors cursor-pointer">
                                                                {inner}
                                                            </Link>
                                                        ) : (
                                                            <div className="flex items-start gap-2.5 p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                                                {inner}
                                                            </div>
                                                        )}
                                                    </motion.li>
                                                );
                                            })}
                                        </ul>
                                    </CardContent>
                                </Card>
                            )}
                        </div>

                        {/* Traceability Summary */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader className="pb-2">
                                <div className="flex items-center justify-between">
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <Activity className="h-4 w-4 text-[var(--re-brand)]" />
                                        Traceability Summary
                                    </CardTitle>
                                    <Link href="/tools/data-import">
                                        <Button variant="ghost" size="sm" className="text-xs h-8 active:scale-[0.97]">
                                            Import More <ArrowRight className="ml-1 h-3 w-3" />
                                        </Button>
                                    </Link>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-4">
                                    <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                                        <div className="text-2xl sm:text-3xl font-bold tabular-nums">{score.events_analyzed.toLocaleString()}</div>
                                        <div className="text-[11px] text-muted-foreground mt-1">Events Tracked</div>
                                    </div>
                                    <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                                        <div className="text-2xl sm:text-3xl font-bold" style={{ color: scoreColor(score.overall_score) }}>{score.grade}</div>
                                        <div className="text-[11px] text-muted-foreground mt-1">Current Grade</div>
                                    </div>
                                    <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                                        <div className="text-2xl sm:text-3xl font-bold tabular-nums">{breakdownKeys.length}</div>
                                        <div className="text-[11px] text-muted-foreground mt-1">Dimensions</div>
                                    </div>
                                    <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                                        <div className="text-2xl sm:text-3xl font-bold tabular-nums">{score.next_actions.filter(a => a.priority === 'HIGH').length}</div>
                                        <div className="text-[11px] text-muted-foreground mt-1">High Priority</div>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        {/* What This Means */}
                        <Card className="border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
                            <CardContent className="py-4">
                                <div className="flex items-start gap-3">
                                    <Info className="h-4 w-4 text-[var(--re-brand)] mt-0.5 flex-shrink-0" />
                                    <div className="text-xs text-muted-foreground leading-relaxed">
                                        <span className="font-medium text-foreground">What this score means: </span>
                                        {score.overall_score >= 80
                                            ? 'Your facility is well-prepared for an FDA inspection under FSMA 204. Continue maintaining your traceability records and running periodic mock drills.'
                                            : score.overall_score >= 60
                                            ? 'Your traceability program has a foundation but gaps remain. An FDA inspector could flag missing data fields or incomplete event records. Address the high-priority actions above.'
                                            : 'Significant compliance gaps exist. If the FDA initiated a 204 records request today, your facility would likely be unable to respond within the required 24 hours. Immediate action is recommended.'}
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Low-score CTA */}
                        {score.overall_score < 70 && lowestDim && (
                            <motion.div
                                className="flex items-center gap-4 p-4 sm:p-5 rounded-xl border border-re-warning/30 bg-re-warning-muted0/[0.05]"
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.6 }}
                            >
                                <div className="flex-1">
                                    <p className="text-sm font-medium">Your biggest gap is <span className="text-re-warning">{lowestDim.label}</span>.</p>
                                    <p className="text-xs text-muted-foreground mt-0.5">Scan labels or import data to improve this dimension.</p>
                                </div>
                                <Link href="/dashboard/scan">
                                    <Button size="sm" className="bg-[var(--re-brand)] hover:bg-[var(--re-brand)]/90 text-white text-xs whitespace-nowrap">
                                        Ingest Data <ArrowRight className="ml-1 h-3 w-3" />
                                    </Button>
                                </Link>
                            </motion.div>
                        )}

                    </motion.div>
                )}

                {/* Empty state — no score and not loading */}
                {!score && !loading && !error && isLoggedIn && (
                    <motion.div
                        className="flex flex-col items-center justify-center py-16 text-center"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                    >
                        <Shield className="h-12 w-12 text-muted-foreground/40 mb-4" />
                        <h2 className="text-lg font-semibold">Welcome to Compliance Status</h2>
                        <p className="text-sm text-muted-foreground mt-1 max-w-md">
                            Start tracking your FSMA 204 readiness by importing traceability data or scanning product labels.
                        </p>
                        <div className="flex gap-3 mt-6">
                            <Link href="/tools/data-import">
                                <Button variant="outline" size="sm">
                                    <Upload className="mr-1.5 h-3.5 w-3.5" /> Import Data
                                </Button>
                            </Link>
                            <Link href="/dashboard/scan">
                                <Button size="sm" className="bg-[var(--re-brand)] hover:bg-[var(--re-brand)]/90 text-white">
                                    <Activity className="mr-1.5 h-3.5 w-3.5" /> Scan Labels
                                </Button>
                            </Link>
                        </div>
                    </motion.div>
                )}

            </div>
        </div>
    );
}
