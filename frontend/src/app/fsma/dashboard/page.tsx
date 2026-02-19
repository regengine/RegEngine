'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';

import { useAuth } from '@/lib/auth-context';
import { useComplianceScore } from '@/hooks/use-fsma';

import {
    Shield,
    AlertTriangle,
    ArrowLeft,
    ArrowRight,
    FileText,
    Lock,
    ClipboardCheck,
    Layers,
    TrendingUp,
    Calendar,
    CheckCircle2,
    Info,
} from 'lucide-react';

// ─── Score Ring (SVG) ──────────────────────────────────────────────────────────

function ScoreRing({ score, size = 180 }: { score: number; size?: number }) {
    const r = (size - 24) / 2;
    const circ = 2 * Math.PI * r;
    const filled = circ * (score / 100);
    const color =
        score >= 85 ? 'var(--re-brand)' : score >= 65 ? 'var(--re-warning)' : 'var(--re-danger)';

    return (
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
            {/* Track */}
            <circle
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke="var(--re-border-default)"
                strokeWidth={14}
            />
            {/* Fill */}
            <motion.circle
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={color}
                strokeWidth={14}
                strokeLinecap="round"
                strokeDasharray={circ}
                initial={{ strokeDashoffset: circ }}
                animate={{ strokeDashoffset: circ - filled }}
                transition={{ duration: 1.2, ease: 'easeOut' }}
                style={{ filter: `drop-shadow(0 0 8px ${color}60)` }}
            />
        </svg>
    );
}

// ─── Metric Card ──────────────────────────────────────────────────────────────

function MetricCard({
    label,
    value,
    icon: Icon,
    sub,
    color,
}: {
    label: string;
    value: number;
    icon: React.ElementType;
    sub?: string;
    color: string;
}) {
    return (
        <Card className="relative overflow-hidden border-[var(--re-border-default)] bg-[var(--re-surface-card)]">
            <div
                className="absolute inset-0 opacity-5"
                style={{ background: `radial-gradient(circle at top right, ${color}, transparent 70%)` }}
            />
            <CardHeader className="pb-2 flex-row items-center gap-2 space-y-0">
                <span className="p-1.5 rounded-md" style={{ background: `${color}20` }}>
                    <Icon className="h-4 w-4" style={{ color }} />
                </span>
                <CardTitle className="text-sm font-medium text-[var(--re-text-secondary)]">
                    {label}
                </CardTitle>
            </CardHeader>
            <CardContent>
                <div className="flex items-end gap-2 mb-3">
                    <span
                        className="text-3xl font-bold tabular-nums"
                        style={{ color: 'var(--re-text-primary)' }}
                    >
                        {value.toFixed(1)}
                    </span>
                    <span className="text-sm text-[var(--re-text-muted)] mb-1">/ 100</span>
                </div>
                <Progress
                    value={value}
                    className="h-1.5"
                    style={
                        { '--progress-fill': color } as React.CSSProperties
                    }
                />
                {sub && (
                    <p className="mt-2 text-xs text-[var(--re-text-tertiary)]">{sub}</p>
                )}
            </CardContent>
        </Card>
    );
}

// ─── Quick Action Card ────────────────────────────────────────────────────────

function ActionCard({
    href,
    icon: Icon,
    title,
    description,
    accent,
}: {
    href: string;
    icon: React.ElementType;
    title: string;
    description: string;
    accent: string;
}) {
    return (
        <Link href={href}>
            <motion.div
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.98 }}
                transition={{ duration: 0.15 }}
            >
                <Card className="h-full cursor-pointer border-[var(--re-border-default)] bg-[var(--re-surface-card)] hover:border-[var(--re-border-subtle)] transition-colors duration-200 group">
                    <CardContent className="pt-6">
                        <div className="flex items-start gap-4">
                            <span
                                className="p-2.5 rounded-lg shrink-0 transition-transform duration-200 group-hover:scale-110"
                                style={{ background: `${accent}15` }}
                            >
                                <Icon className="h-5 w-5" style={{ color: accent }} />
                            </span>
                            <div>
                                <p className="font-semibold text-[var(--re-text-primary)]">{title}</p>
                                <p className="text-sm text-[var(--re-text-tertiary)] mt-0.5 leading-relaxed">
                                    {description}
                                </p>
                            </div>
                            <ArrowRight className="h-4 w-4 ml-auto shrink-0 text-[var(--re-text-muted)] group-hover:text-[var(--re-brand)] group-hover:translate-x-1 transition-all duration-200 mt-0.5" />
                        </div>
                    </CardContent>
                </Card>
            </motion.div>
        </Link>
    );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function FSMAPilotDashboard() {
    const { apiKey } = useAuth();
    const { data: score, isLoading, isError } = useComplianceScore(apiKey || '');

    const deadline = new Date('2028-07-01');
    const today = new Date();
    const daysLeft = Math.ceil((deadline.getTime() - today.getTime()) / 86_400_000);

    const overallColor =
        !score ? 'var(--re-text-muted)'
            : score.overall_score >= 85 ? 'var(--re-brand)'
                : score.overall_score >= 65 ? 'var(--re-warning)'
                    : 'var(--re-danger)';

    const overallLabel =
        !score ? '—'
            : score.overall_score >= 85 ? 'Strong'
                : score.overall_score >= 65 ? 'Needs Work'
                    : 'At Risk';

    return (
        <div className="min-h-screen" style={{ background: 'var(--re-surface-base)' }}>
            <PageContainer>
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4 }}
                    className="space-y-8 pb-16"
                >
                    {/* ── Back + Header ───────────────────────────────────────── */}
                    <div>
                        <Link href="/fsma">
                            <Button variant="ghost" size="sm" className="mb-5 text-[var(--re-text-tertiary)] hover:text-[var(--re-text-primary)]">
                                <ArrowLeft className="h-4 w-4 mr-2" />
                                FSMA 204 Operations
                            </Button>
                        </Link>

                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                            <div className="flex items-center gap-4">
                                <div
                                    className="p-3 rounded-xl"
                                    style={{ background: 'var(--re-success-muted)' }}
                                >
                                    <Shield className="h-7 w-7" style={{ color: 'var(--re-brand)' }} />
                                </div>
                                <div>
                                    <h1 className="text-3xl font-bold tracking-tight" style={{ color: 'var(--re-text-primary)' }}>
                                        Compliance Dashboard
                                    </h1>
                                    <p className="mt-0.5 text-sm" style={{ color: 'var(--re-text-tertiary)' }}>
                                        FSMA 204 · Pilot Overview · Obligation → Control → Evidence
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-center gap-3">
                                {score?.is_demo && (
                                    <Badge
                                        variant="outline"
                                        className="gap-1.5 border-[var(--re-warning)] text-[var(--re-warning)]"
                                    >
                                        <Info className="h-3 w-3" />
                                        Demo data
                                    </Badge>
                                )}
                                <div
                                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium"
                                    style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--re-border-default)' }}
                                >
                                    <Calendar className="h-4 w-4" style={{ color: 'var(--re-info)' }} />
                                    <span style={{ color: 'var(--re-text-secondary)' }}>
                                        {daysLeft.toLocaleString()} days to Jul&nbsp;2028
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* ── Score Hero ──────────────────────────────────────────── */}
                    <Card
                        className="border-[var(--re-border-default)]"
                        style={{ background: 'var(--re-surface-card)' }}
                    >
                        <CardContent className="pt-8 pb-8">
                            <div className="flex flex-col md:flex-row items-center gap-10">
                                {/* Ring */}
                                <div className="relative shrink-0">
                                    {isLoading ? (
                                        <Skeleton className="rounded-full" style={{ width: 180, height: 180 }} />
                                    ) : (
                                        <>
                                            <ScoreRing score={score?.overall_score ?? 0} size={180} />
                                            <div className="absolute inset-0 flex flex-col items-center justify-center" style={{ transform: 'rotate(0deg)' }}>
                                                <AnimatePresence mode="wait">
                                                    <motion.span
                                                        key={score?.overall_score}
                                                        initial={{ opacity: 0, scale: 0.8 }}
                                                        animate={{ opacity: 1, scale: 1 }}
                                                        className="text-4xl font-bold tabular-nums"
                                                        style={{ color: overallColor }}
                                                    >
                                                        {score?.overall_score.toFixed(1) ?? '—'}
                                                    </motion.span>
                                                </AnimatePresence>
                                                <span className="text-xs mt-0.5" style={{ color: 'var(--re-text-muted)' }}>
                                                    {overallLabel}
                                                </span>
                                            </div>
                                        </>
                                    )}
                                </div>

                                {/* Summary stats */}
                                <div className="flex-1 w-full grid grid-cols-1 sm:grid-cols-3 gap-6">
                                    {[
                                        { label: 'Obligations', value: score?.total_obligations, icon: FileText, color: 'var(--re-info)' },
                                        { label: 'Controls mapped', value: score?.controls_mapped, icon: ClipboardCheck, color: 'var(--re-brand)' },
                                        { label: 'Evidence items', value: score?.evidence_items, icon: Lock, color: 'var(--re-warning)' },
                                    ].map(({ label, value, icon: Icon, color }) => (
                                        <div
                                            key={label}
                                            className="flex items-center gap-4 p-4 rounded-xl"
                                            style={{ background: 'var(--re-surface-elevated)' }}
                                        >
                                            <span className="p-2 rounded-lg" style={{ background: `${color}18` }}>
                                                <Icon className="h-5 w-5" style={{ color }} />
                                            </span>
                                            <div>
                                                {isLoading ? (
                                                    <Skeleton className="h-7 w-12 mb-1" />
                                                ) : (
                                                    <p className="text-2xl font-bold tabular-nums" style={{ color: 'var(--re-text-primary)' }}>
                                                        {value ?? '—'}
                                                    </p>
                                                )}
                                                <p className="text-xs" style={{ color: 'var(--re-text-muted)' }}>{label}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* ── Dimension Metrics ──────────────────────────────────── */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {isLoading ? (
                            [1, 2, 3].map(i => <Skeleton key={i} className="h-36 rounded-xl" />)
                        ) : (
                            <>
                                <MetricCard
                                    label="Obligation Coverage"
                                    value={score?.obligation_coverage ?? 0}
                                    icon={ClipboardCheck}
                                    sub={`${score?.controls_mapped ?? 0} of ${score?.total_obligations ?? 0} obligations have controls`}
                                    color="var(--re-brand)"
                                />
                                <MetricCard
                                    label="Control Effectiveness"
                                    value={score?.control_effectiveness ?? 0}
                                    icon={Layers}
                                    sub="Average effectiveness score of mapped controls"
                                    color="var(--re-info)"
                                />
                                <MetricCard
                                    label="Evidence Freshness"
                                    value={score?.evidence_freshness ?? 0}
                                    icon={TrendingUp}
                                    sub="Evidence sealed within the last 90 days"
                                    color="var(--re-warning)"
                                />
                            </>
                        )}
                    </div>

                    {/* ── Quick Actions ──────────────────────────────────────── */}
                    <div>
                        <h2 className="text-base font-semibold mb-4" style={{ color: 'var(--re-text-secondary)' }}>
                            Next Steps
                        </h2>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                            <ActionCard
                                href="/ftl-checker"
                                icon={CheckCircle2}
                                title="FTL Applicability Wizard"
                                description="Check which foods are covered by FSMA 204"
                                accent="var(--re-brand)"
                            />
                            <ActionCard
                                href="/fsma/assessment"
                                icon={Shield}
                                title="Readiness Assessment"
                                description="Evaluate your 24-hour recall response posture"
                                accent="var(--re-info)"
                            />
                            <ActionCard
                                href="/fsma"
                                icon={Layers}
                                title="Traceability Dashboard"
                                description="Trace lots, run recall drills, view supply chain"
                                accent="var(--re-warning)"
                            />
                            <ActionCard
                                href="/compliance"
                                icon={FileText}
                                title="Compliance Checklists"
                                description="CTE/KDE obligations with gap analysis"
                                accent="#a78bfa"
                            />
                        </div>
                    </div>

                    {/* ── Error state ────────────────────────────────────────── */}
                    {isError && (
                        <Card className="border-[var(--re-danger)] bg-[var(--re-danger-muted)]">
                            <CardContent className="pt-4 pb-4 flex items-center gap-3">
                                <AlertTriangle className="h-5 w-5 shrink-0" style={{ color: 'var(--re-danger)' }} />
                                <p className="text-sm" style={{ color: 'var(--re-text-secondary)' }}>
                                    Could not load compliance score — showing demo data above. Ensure your API key is configured and the graph service is reachable.
                                </p>
                            </CardContent>
                        </Card>
                    )}
                </motion.div>
            </PageContainer>
        </div>
    );
}
