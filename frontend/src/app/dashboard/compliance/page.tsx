'use client';

import React from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import {
    Shield,
    ShieldCheck,
    ArrowRight,
    Download,
    FileText,
    Printer,
    Timer,
    CheckCircle2,
    AlertTriangle,
    Activity,
    TrendingUp,
    Zap,
} from 'lucide-react';

// Simulated compliance score data (in production, fetched from /api/v1/compliance/score/{tenant_id})
const MOCK_SCORE = {
    overall_score: 74,
    grade: 'C',
    breakdown: {
        product_coverage: { score: 75, detail: 'Product coverage needs FTL category mapping for full score' },
        cte_completeness: { score: 60, detail: 'Verify all 6 CTE types are being tracked' },
        kde_completeness: { score: 65, detail: 'Some events missing optional KDEs (GLN, temperature)' },
        chain_integrity: { score: 100, detail: 'All events verified — chain intact' },
        export_readiness: { score: 80, detail: 'Data available for FDA export' },
    },
    next_actions: [
        { priority: 'HIGH', action: 'Add Transformation CTE tracking', impact: '+10-15 pts' },
        { priority: 'HIGH', action: 'Add GLN to all location records', impact: '+5-10 pts' },
        { priority: 'MEDIUM', action: 'Run FTL Checker against all products', impact: '+10-25 pts' },
        { priority: 'MEDIUM', action: 'Run a 24-hour mock recall drill', impact: 'Validates readiness' },
    ],
};

const RECENT_EVENTS = [
    { cte: 'RECEIVING', tlc: 'TOM-0226-F3-001', product: 'Roma Tomatoes 12ct', time: '2 hours ago', status: 'valid' },
    { cte: 'SHIPPING', tlc: 'LET-0226-A2-003', product: 'Romaine Lettuce Hearts', time: '5 hours ago', status: 'valid' },
    { cte: 'COOLING', tlc: 'SAL-0226-B1-007', product: 'Atlantic Salmon Fillets', time: '1 day ago', status: 'warning' },
    { cte: 'TRANSFORMATION', tlc: 'SALAD-0226-001', product: 'Garden Salad Mix 16oz', time: '1 day ago', status: 'valid' },
    { cte: 'HARVESTING', tlc: 'CUC-0226-F2-015', product: 'English Cucumbers', time: '2 days ago', status: 'valid' },
];

function ScoreGauge({ score, grade }: { score: number; grade: string }) {
    const circumference = 2 * Math.PI * 80;
    const offset = circumference - (score / 100) * circumference;
    const color = score >= 80 ? 'var(--re-brand)' : score >= 60 ? '#f59e0b' : '#ef4444';

    return (
        <div className="relative w-48 h-48 mx-auto">
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
                    className="text-4xl font-bold"
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

export default function ComplianceDashboardPage() {
    return (
        <div className="min-h-screen bg-background p-4 md:p-8 pt-4">
            <div className="mx-auto max-w-7xl space-y-6">
                <Breadcrumbs items={[
                    { label: 'Dashboard', href: '/dashboard' },
                    { label: 'Compliance' },
                ]} />

                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                    <div>
                        <h1 className="text-3xl font-semibold tracking-tight">
                            Compliance Dashboard
                        </h1>
                        <p className="mt-1 text-sm text-muted-foreground">
                            Real-time FSMA 204 compliance score and audit readiness
                        </p>
                    </div>
                    <Badge className="bg-[var(--re-brand)] rounded-xl py-1 px-3 w-fit">
                        <Shield className="mr-2 h-4 w-4 inline" />
                        FSMA 204 Compliant
                    </Badge>
                </div>

                {/* Score + Breakdown */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Score Gauge */}
                    <Card className="border-[var(--re-border-default)]">
                        <CardHeader>
                            <CardTitle className="text-base">Overall Readiness</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ScoreGauge score={MOCK_SCORE.overall_score} grade={MOCK_SCORE.grade} />
                            <div className="text-center text-xs text-muted-foreground mt-4">
                                Weighted: Integrity 30% · KDEs 25% · CTEs 25% · Coverage 10% · Export 10%
                            </div>
                        </CardContent>
                    </Card>

                    {/* Score Breakdown */}
                    <Card className="border-[var(--re-border-default)] lg:col-span-2">
                        <CardHeader>
                            <CardTitle className="text-base">Score Breakdown</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <ScoreBar label="Chain Integrity" score={MOCK_SCORE.breakdown.chain_integrity.score} />
                            <ScoreBar label="Export Readiness" score={MOCK_SCORE.breakdown.export_readiness.score} />
                            <ScoreBar label="Product Coverage" score={MOCK_SCORE.breakdown.product_coverage.score} />
                            <ScoreBar label="KDE Completeness" score={MOCK_SCORE.breakdown.kde_completeness.score} />
                            <ScoreBar label="CTE Completeness" score={MOCK_SCORE.breakdown.cte_completeness.score} />
                        </CardContent>
                    </Card>
                </div>

                {/* Quick Actions + Next Steps */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Quick Actions */}
                    <Card className="border-[var(--re-border-default)]">
                        <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2">
                                <Zap className="h-4 w-4 text-[var(--re-brand)]" />
                                Quick Actions
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="grid grid-cols-2 gap-3">
                            <Link href="/tools/drill-simulator">
                                <Button variant="outline" className="w-full h-auto py-4 flex flex-col gap-2 rounded-xl">
                                    <Timer className="h-5 w-5 text-[var(--re-brand)]" />
                                    <span className="text-xs">Run Mock Drill</span>
                                </Button>
                            </Link>
                            <Button variant="outline" className="h-auto py-4 flex flex-col gap-2 rounded-xl">
                                <Download className="h-5 w-5 text-[var(--re-brand)]" />
                                <span className="text-xs">FDA Report</span>
                            </Button>
                            <Button variant="outline" className="h-auto py-4 flex flex-col gap-2 rounded-xl">
                                <FileText className="h-5 w-5 text-[var(--re-brand)]" />
                                <span className="text-xs">EPCIS Export</span>
                            </Button>
                            <Link href="/tools/data-import">
                                <Button variant="outline" className="w-full h-auto py-4 flex flex-col gap-2 rounded-xl">
                                    <Printer className="h-5 w-5 text-[var(--re-brand)]" />
                                    <span className="text-xs">Import Data</span>
                                </Button>
                            </Link>
                        </CardContent>
                    </Card>

                    {/* Next Actions */}
                    <Card className="border-[var(--re-border-default)]">
                        <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2">
                                <TrendingUp className="h-4 w-4 text-[var(--re-brand)]" />
                                Improve Your Score
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ul className="space-y-3">
                                {MOCK_SCORE.next_actions.map((action, i) => (
                                    <li key={i} className="flex items-start gap-3 p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                        <Badge
                                            variant={action.priority === 'HIGH' ? 'default' : 'secondary'}
                                            className={`text-[9px] uppercase tracking-widest rounded-full mt-0.5 ${action.priority === 'HIGH' ? 'bg-red-600' : ''}`}
                                        >
                                            {action.priority}
                                        </Badge>
                                        <div className="flex-1">
                                            <div className="text-sm font-medium">{action.action}</div>
                                            <div className="text-xs text-muted-foreground">{action.impact}</div>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        </CardContent>
                    </Card>
                </div>

                {/* Recent Events */}
                <Card className="border-[var(--re-border-default)]">
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <CardTitle className="text-base flex items-center gap-2">
                                <Activity className="h-4 w-4 text-[var(--re-brand)]" />
                                Recent Events
                            </CardTitle>
                            <Link href="/tools/data-import">
                                <Button variant="ghost" size="sm" className="text-xs">
                                    Import More <ArrowRight className="ml-1 h-3 w-3" />
                                </Button>
                            </Link>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            {RECENT_EVENTS.map((event, i) => (
                                <motion.div
                                    key={i}
                                    initial={{ opacity: 0, x: -10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: i * 0.05 }}
                                    className="flex items-center justify-between p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]"
                                >
                                    <div className="flex items-center gap-3">
                                        {event.status === 'valid' ? (
                                            <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                                        ) : (
                                            <AlertTriangle className="h-4 w-4 text-amber-500 flex-shrink-0" />
                                        )}
                                        <div>
                                            <div className="text-sm font-medium">{event.product}</div>
                                            <div className="text-xs text-muted-foreground font-mono">{event.tlc}</div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <Badge variant="outline" className="text-[9px] uppercase tracking-widest">
                                            {event.cte}
                                        </Badge>
                                        <span className="text-xs text-muted-foreground">{event.time}</span>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
