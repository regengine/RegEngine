'use client';

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import { Spinner } from '@/components/ui/spinner';
import {
    Shield,
    ArrowRight,
    Download,
    FileText,
    Printer,
    Timer,
    Activity,
    TrendingUp,
    Zap,
    AlertTriangle,
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

/* ── Pure UI Components ── */

function ScoreGauge({ score, grade }: { score: number; grade: string }) {
    const circumference = 2 * Math.PI * 80;
    const offset = circumference - (score / 100) * circumference;
    const color = score >= 80 ? 'var(--re-brand)' : score >= 60 ? '#f59e0b' : '#ef4444';

    return (
        <div className="relative w-36 h-36 sm:w-48 sm:h-48 mx-auto">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 200 200">
                <circle cx="100" cy="100" r="80" stroke="var(--re-border-default)" strokeWidth="12" fill="none" />
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
                    className="text-3xl sm:text-4xl font-bold"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.5 }}
                    style={{ color }}
                >
                    {score}
                </motion.div>
                <div className="text-sm text-muted-foreground">Grade: {grade}</div>
            </div>
        </div>
    );
}

function ScoreBar({ label, score }: { label: string; score: number }) {
    const color = score >= 80 ? 'var(--re-brand)' : score >= 60 ? '#f59e0b' : '#ef4444';
    return (
        <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
                <span className="font-medium">{label}</span>
                <span style={{ color }}>{score}%</span>
            </div>
            <div className="h-2 rounded-full bg-[var(--re-surface-elevated)] overflow-hidden">
                <motion.div
                    className="h-full rounded-full"
                    style={{ backgroundColor: color }}
                    initial={{ width: 0 }}
                    animate={{ width: `${score}%` }}
                    transition={{ duration: 1, ease: 'easeOut', delay: 0.3 }}
                />
            </div>
        </div>
    );
}

const BREAKDOWN_LABELS: Record<string, string> = {
    chain_integrity: 'Chain Integrity',
    export_readiness: 'Export Readiness',
    product_coverage: 'Product Coverage',
    kde_completeness: 'KDE Completeness',
    cte_completeness: 'CTE Completeness',
};

/* ── Page ── */

export default function ComplianceDashboardPage() {
    const { apiKey } = useAuth();
    const { tenantId } = useTenant();
    const isLoggedIn = Boolean(apiKey);

    const [score, setScore] = useState<ComplianceScore | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!isLoggedIn || !tenantId) return;

        let cancelled = false;
        setLoading(true);
        setError(null);

        fetchComplianceScore(tenantId)
            .then((data) => {
                if (!cancelled) setScore(data as ComplianceScore);
            })
            .catch((err) => {
                if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load compliance score');
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });

        return () => { cancelled = true; };
    }, [isLoggedIn, tenantId]);

    // Ordered breakdown keys (highest weight first)
    const breakdownKeys = score
        ? Object.keys(score.breakdown).sort((a, b) => score.breakdown[b].score - score.breakdown[a].score)
        : [];

    return (
        <div className="min-h-screen bg-background p-4 md:p-8 pt-4">
            <div className="mx-auto max-w-7xl space-y-6">
                <Breadcrumbs items={[
                    { label: 'Dashboard', href: '/dashboard' },
                    { label: 'Compliance' },
                ]} />

                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight">
                            Compliance Dashboard
                        </h1>
                        <p className="mt-1 text-sm text-muted-foreground">
                            Real-time FSMA 204 compliance score and audit readiness
                        </p>
                    </div>
                    {score && score.overall_score >= 80 && (
                        <Badge className="bg-[var(--re-brand)] rounded-xl py-1 px-3 w-fit">
                            <Shield className="mr-2 h-4 w-4 inline" />
                            FSMA 204 Compliant
                        </Badge>
                    )}
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
                {loading && (
                    <div className="flex justify-center py-16">
                        <Spinner size="lg" />
                    </div>
                )}

                {/* Error */}
                {error && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-4">
                            <div className="flex items-center gap-3 text-orange-600 dark:text-orange-400">
                                <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                                <p className="text-sm">{error}</p>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Score Content */}
                {score && !loading && (
                    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                        {/* Score + Breakdown */}
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
                            <Card className="border-[var(--re-border-default)]">
                                <CardHeader>
                                    <CardTitle className="text-base">Overall Readiness</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <ScoreGauge score={score.overall_score} grade={score.grade} />
                                    <div className="text-center text-xs text-muted-foreground mt-4">
                                        {score.events_analyzed} events analyzed
                                        {score.last_chain_hash && (
                                            <span className="block font-mono text-[10px] mt-1 truncate">
                                                Chain: {score.last_chain_hash}
                                            </span>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>

                            <Card className="border-[var(--re-border-default)] lg:col-span-2">
                                <CardHeader>
                                    <CardTitle className="text-base">Score Breakdown</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    {breakdownKeys.map((key) => (
                                        <div key={key}>
                                            <ScoreBar
                                                label={BREAKDOWN_LABELS[key] || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                                                score={score.breakdown[key].score}
                                            />
                                            <p className="text-[10px] text-muted-foreground mt-0.5 ml-0.5">
                                                {score.breakdown[key].detail}
                                            </p>
                                        </div>
                                    ))}
                                </CardContent>
                            </Card>
                        </div>

                        {/* Quick Actions + Next Steps */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
                            <Card className="border-[var(--re-border-default)]">
                                <CardHeader>
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <Zap className="h-4 w-4 text-[var(--re-brand)]" />
                                        Quick Actions
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="grid grid-cols-2 gap-2 sm:gap-3">
                                    <Link href="/tools/drill-simulator">
                                        <Button variant="outline" className="w-full h-auto min-h-[48px] py-3 sm:py-4 flex flex-col gap-1.5 sm:gap-2 rounded-xl active:scale-[0.97]">
                                            <Timer className="h-4 w-4 sm:h-5 sm:w-5 text-[var(--re-brand)]" />
                                            <span className="text-[11px] sm:text-xs">Run Mock Drill</span>
                                        </Button>
                                    </Link>
                                    <Button disabled title="Coming Soon" variant="outline" className="h-auto min-h-[48px] py-3 sm:py-4 flex flex-col gap-1.5 sm:gap-2 rounded-xl">
                                        <Download className="h-4 w-4 sm:h-5 sm:w-5 text-[var(--re-brand)]" />
                                        <span className="text-[11px] sm:text-xs">FDA Report</span>
                                    </Button>
                                    <Button disabled title="Coming Soon" variant="outline" className="h-auto min-h-[48px] py-3 sm:py-4 flex flex-col gap-1.5 sm:gap-2 rounded-xl">
                                        <FileText className="h-4 w-4 sm:h-5 sm:w-5 text-[var(--re-brand)]" />
                                        <span className="text-[11px] sm:text-xs">EPCIS Export</span>
                                    </Button>
                                    <Link href="/tools/data-import">
                                        <Button variant="outline" className="w-full h-auto min-h-[48px] py-3 sm:py-4 flex flex-col gap-1.5 sm:gap-2 rounded-xl active:scale-[0.97]">
                                            <Printer className="h-4 w-4 sm:h-5 sm:w-5 text-[var(--re-brand)]" />
                                            <span className="text-[11px] sm:text-xs">Import Data</span>
                                        </Button>
                                    </Link>
                                </CardContent>
                            </Card>

                            {score.next_actions.length > 0 && (
                                <Card className="border-[var(--re-border-default)]">
                                    <CardHeader>
                                        <CardTitle className="text-base flex items-center gap-2">
                                            <TrendingUp className="h-4 w-4 text-[var(--re-brand)]" />
                                            Improve Your Score
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <ul className="space-y-3">
                                            {score.next_actions.map((action, i) => (
                                                <li key={i} className="flex items-start gap-2 sm:gap-3 p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] min-h-[48px]">
                                                    <Badge
                                                        variant={action.priority === 'HIGH' ? 'default' : 'secondary'}
                                                        className={`text-[9px] uppercase tracking-widest rounded-full mt-0.5 flex-shrink-0 ${action.priority === 'HIGH' ? 'bg-red-600' : ''}`}
                                                    >
                                                        {action.priority}
                                                    </Badge>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="text-xs sm:text-sm font-medium">{action.action}</div>
                                                        <div className="text-[11px] sm:text-xs text-muted-foreground">{action.impact}</div>
                                                    </div>
                                                </li>
                                            ))}
                                        </ul>
                                    </CardContent>
                                </Card>
                            )}
                        </div>

                        {/* Events Summary */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <div className="flex items-center justify-between">
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <Activity className="h-4 w-4 text-[var(--re-brand)]" />
                                        Traceability Summary
                                    </CardTitle>
                                    <Link href="/tools/data-import">
                                        <Button variant="ghost" size="sm" className="text-xs min-h-[44px] active:scale-[0.97]">
                                            Import More <ArrowRight className="ml-1 h-3 w-3" />
                                        </Button>
                                    </Link>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-4">
                                    <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                                        <div className="text-xl sm:text-2xl font-bold">{score.events_analyzed}</div>
                                        <div className="text-[11px] sm:text-xs text-muted-foreground mt-1">Events Analyzed</div>
                                    </div>
                                    <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                                        <div className="text-xl sm:text-2xl font-bold">{score.grade}</div>
                                        <div className="text-[11px] sm:text-xs text-muted-foreground mt-1">Current Grade</div>
                                    </div>
                                    <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                                        <div className="text-xl sm:text-2xl font-bold">{breakdownKeys.length}</div>
                                        <div className="text-[11px] sm:text-xs text-muted-foreground mt-1">Score Dimensions</div>
                                    </div>
                                    <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                                        <div className="text-xl sm:text-2xl font-bold">{score.next_actions.length}</div>
                                        <div className="text-[11px] sm:text-xs text-muted-foreground mt-1">Action Items</div>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}
            </div>
        </div>
    );
}
