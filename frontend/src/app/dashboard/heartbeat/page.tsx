'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { PageContainer } from '@/components/layout/page-container';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import {
    fetchComplianceScore,
    fetchAlerts,
} from '@/lib/api-hooks';
import {
    Shield,
    AlertTriangle,
    CheckCircle2,
    XCircle,
    Link2,
    Upload,
    Clock,
    RefreshCw,
    ArrowRight,
    Activity,
    TrendingUp,
    ChevronRight,
    Zap,
    BarChart3,
    FileText,
    ShieldCheck,
} from 'lucide-react';

// ── Types ──

interface BreakdownItem {
    score: number;
    detail: string;
}

interface ComplianceData {
    overall_score: number;
    grade: string;
    breakdown: {
        chain_integrity: BreakdownItem;
        export_readiness: BreakdownItem;
        product_coverage: BreakdownItem;
        kde_completeness: BreakdownItem;
        cte_completeness: BreakdownItem;
        obligation_coverage?: BreakdownItem;
    };
    events_analyzed: number;
    last_chain_hash: string | null;
    next_actions: Array<{ priority: string; action: string; impact: string }>;
}

interface Alert {
    id: string;
    severity: string;
    category: string;
    title: string;
    message: string;
    created_at: string;
    acknowledged: boolean;
}

// ── Helpers ──

function gradeColor(grade: string): string {
    if (grade === 'A' || grade === 'A+') return 'text-emerald-400';
    if (grade === 'B' || grade === 'B+') return 'text-green-400';
    if (grade === 'C' || grade === 'C+') return 'text-yellow-400';
    if (grade === 'D') return 'text-orange-400';
    return 'text-red-400';
}

function gradeGlow(grade: string): string {
    if (grade === 'A' || grade === 'A+') return 'drop-shadow-[0_0_12px_rgba(16,185,129,0.5)]';
    if (grade === 'B' || grade === 'B+') return 'drop-shadow-[0_0_12px_rgba(34,197,94,0.5)]';
    if (grade === 'C' || grade === 'C+') return 'drop-shadow-[0_0_12px_rgba(234,179,8,0.4)]';
    if (grade === 'D') return 'drop-shadow-[0_0_12px_rgba(249,115,22,0.4)]';
    return 'drop-shadow-[0_0_12px_rgba(239,68,68,0.4)]';
}

function scoreRingColor(score: number): string {
    if (score >= 80) return '#10b981';
    if (score >= 60) return '#eab308';
    if (score >= 40) return '#f97316';
    return '#ef4444';
}

function scoreRingTrack(score: number): string {
    if (score >= 80) return 'rgba(16,185,129,0.12)';
    if (score >= 60) return 'rgba(234,179,8,0.12)';
    if (score >= 40) return 'rgba(249,115,22,0.12)';
    return 'rgba(239,68,68,0.12)';
}

function severityConfig(severity: string) {
    const map: Record<string, { bg: string; border: string; text: string; dot: string }> = {
        critical: {
            bg: 'bg-red-500/10',
            border: 'border-l-red-500',
            text: 'text-red-400',
            dot: 'bg-red-500',
        },
        high: {
            bg: 'bg-orange-500/10',
            border: 'border-l-orange-500',
            text: 'text-orange-400',
            dot: 'bg-orange-500',
        },
        medium: {
            bg: 'bg-yellow-500/10',
            border: 'border-l-yellow-500',
            text: 'text-yellow-400',
            dot: 'bg-yellow-500',
        },
        low: {
            bg: 'bg-blue-500/10',
            border: 'border-l-blue-500',
            text: 'text-blue-400',
            dot: 'bg-blue-500',
        },
    };
    return map[severity] || map.low;
}

function timeAgo(dateStr: string): string {
    const now = Date.now();
    const then = new Date(dateStr).getTime();
    const diffMs = now - then;
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
}

// ── Animated Score Ring ──

function ScoreRing({ score, grade, size = 200 }: { score: number; grade: string; size?: number }) {
    const radius = (size - 24) / 2;
    const circumference = 2 * Math.PI * radius;
    const progress = (score / 100) * circumference;
    const color = scoreRingColor(score);
    const trackColor = scoreRingTrack(score);

    return (
        <div className="relative inline-flex items-center justify-center">
            <svg width={size} height={size} className="-rotate-90">
                {/* Track */}
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke={trackColor}
                    strokeWidth="12"
                />
                {/* Progress */}
                <motion.circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke={color}
                    strokeWidth="12"
                    strokeLinecap="round"
                    strokeDasharray={circumference}
                    initial={{ strokeDashoffset: circumference }}
                    animate={{ strokeDashoffset: circumference - progress }}
                    transition={{ duration: 1.4, ease: [0.34, 1.56, 0.64, 1] }}
                    style={{ filter: `drop-shadow(0 0 8px ${color}40)` }}
                />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
                <motion.span
                    className={`text-5xl font-bold tracking-tight ${gradeColor(grade)} ${gradeGlow(grade)}`}
                    initial={{ scale: 0.5, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ duration: 0.6, delay: 0.8, ease: 'easeOut' }}
                >
                    {grade}
                </motion.span>
                <motion.span
                    className="text-xl font-semibold text-foreground/80 tabular-nums"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.4, delay: 1.0 }}
                >
                    {score}%
                </motion.span>
            </div>
        </div>
    );
}

// ── Breakdown Bar ──

function BreakdownBar({ label, value, detail, delay = 0 }: { label: string; value: number; detail?: string; delay?: number }) {
    const barColor =
        value >= 80
            ? 'from-emerald-500 to-emerald-400'
            : value >= 60
                ? 'from-yellow-500 to-yellow-400'
                : value >= 40
                    ? 'from-orange-500 to-orange-400'
                    : 'from-red-500 to-red-400';

    const dotColor =
        value >= 80 ? 'bg-emerald-500' : value >= 60 ? 'bg-yellow-500' : value >= 40 ? 'bg-orange-500' : 'bg-red-500';

    return (
        <motion.div
            className="space-y-1.5 group"
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.4, delay }}
        >
            <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
                    {label}
                </span>
                <span className="font-semibold tabular-nums">{value}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted/20 overflow-hidden">
                <motion.div
                    className={`h-full rounded-full bg-gradient-to-r ${barColor}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.max(value, 2)}%` }}
                    transition={{ duration: 0.8, ease: [0.34, 1.56, 0.64, 1], delay: delay + 0.2 }}
                />
            </div>
            {detail && (
                <p className="text-[11px] text-muted-foreground/70 leading-tight opacity-0 group-hover:opacity-100 transition-opacity">
                    {detail}
                </p>
            )}
        </motion.div>
    );
}

// ── Status Row ──

function StatusRow({ icon: Icon, label, value, status }: {
    icon: React.ComponentType<{ className?: string }>;
    label: string;
    value: string | number;
    status: 'good' | 'warn' | 'neutral';
}) {
    const statusColors = {
        good: 'bg-emerald-500/10 border-emerald-500/20',
        warn: 'bg-amber-500/10 border-amber-500/20',
        neutral: 'bg-muted/30 border-transparent',
    };
    const iconColors = {
        good: 'text-emerald-500',
        warn: 'text-amber-500',
        neutral: 'text-muted-foreground',
    };

    return (
        <div className={`flex items-center justify-between p-3 rounded-xl border ${statusColors[status]} transition-colors`}>
            <div className="flex items-center gap-2.5">
                <Icon className={`h-4.5 w-4.5 ${iconColors[status]}`} />
                <span className="text-sm font-medium">{label}</span>
            </div>
            <span className="text-sm font-bold tabular-nums">{value}</span>
        </div>
    );
}

// ── Loading Skeleton ──

function HeartbeatSkeleton() {
    return (
        <div className="space-y-6">
            {/* Header skeleton */}
            <div className="flex justify-between items-start">
                <div className="space-y-2">
                    <Skeleton className="h-8 w-56" />
                    <Skeleton className="h-4 w-80" />
                </div>
                <Skeleton className="h-9 w-24 rounded-lg" />
            </div>

            {/* Cards skeleton */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Score card */}
                <div className="rounded-xl border bg-card p-6 flex flex-col items-center gap-4">
                    <Skeleton className="h-[200px] w-[200px] rounded-full" />
                    <Skeleton className="h-4 w-32" />
                </div>
                {/* Breakdown card */}
                <div className="rounded-xl border bg-card p-6 space-y-4">
                    {[1, 2, 3, 4, 5].map(i => (
                        <div key={i} className="space-y-2">
                            <div className="flex justify-between">
                                <Skeleton className="h-4 w-28" />
                                <Skeleton className="h-4 w-10" />
                            </div>
                            <Skeleton className="h-2 w-full rounded-full" />
                        </div>
                    ))}
                </div>
                {/* Status card */}
                <div className="rounded-xl border bg-card p-6 space-y-3">
                    {[1, 2, 3].map(i => (
                        <Skeleton key={i} className="h-12 w-full rounded-xl" />
                    ))}
                    <Skeleton className="h-16 w-full rounded-xl" />
                </div>
            </div>

            {/* Bottom row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {[1, 2].map(i => (
                    <div key={i} className="rounded-xl border bg-card p-6 space-y-3">
                        <Skeleton className="h-5 w-32" />
                        {[1, 2, 3].map(j => (
                            <Skeleton key={j} className="h-14 w-full rounded-lg" />
                        ))}
                    </div>
                ))}
            </div>
        </div>
    );
}

// ── Page ──

export default function HeartbeatPage() {
    const { user, isHydrated, apiKey } = useAuth();
    const { tenantId } = useTenant();
    const router = useRouter();

    const effectiveUser = user;
    const effectiveTenantId = tenantId;

    const [compliance, setCompliance] = useState<ComplianceData | null>(null);
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
    const [isRefreshing, setIsRefreshing] = useState(false);

    useEffect(() => {
        if (isHydrated && !effectiveUser) {
            router.push(`/login?next=${encodeURIComponent('/dashboard/heartbeat')}`);
        }
    }, [isHydrated, effectiveUser, router]);

    const loadData = useCallback(async (isManualRefresh = false) => {
        if (!effectiveTenantId) return;
        if (isManualRefresh) {
            setIsRefreshing(true);
        } else {
            setLoading(true);
        }
        setError(null);
        try {
            const [scoreData, alertsData] = await Promise.allSettled([
                fetchComplianceScore(effectiveTenantId, apiKey || ''),
                fetchAlerts(effectiveTenantId, apiKey || '', { acknowledged: false }),
            ]);

            if (scoreData.status === 'fulfilled') {
                setCompliance(scoreData.value as ComplianceData);
            }
            if (alertsData.status === 'fulfilled') {
                const raw = alertsData.value as any;
                setAlerts(Array.isArray(raw) ? raw : raw?.alerts ?? []);
            }
            setLastRefresh(new Date());
        } catch {
            setError('Failed to load compliance data');
        } finally {
            setLoading(false);
            setIsRefreshing(false);
        }
    }, [effectiveTenantId]);

    useEffect(() => {
        if (effectiveTenantId) {
            loadData();
        }
    }, [effectiveTenantId, loadData]);

    // Auto-refresh every 60s
    useEffect(() => {
        const interval = setInterval(() => loadData(true), 60_000);
        return () => clearInterval(interval);
    }, [loadData]);

    const criticalAlerts = useMemo(() =>
        alerts.filter(a => a.severity === 'critical' || a.severity === 'high').slice(0, 5),
        [alerts],
    );

    const recentAlerts = useMemo(() => alerts.slice(0, 6), [alerts]);

    if (!isHydrated || !effectiveUser) return null;

    const now = new Date();
    const greeting = now.getHours() < 12 ? 'Good morning' : now.getHours() < 17 ? 'Good afternoon' : 'Good evening';

    return (
        <div className="min-h-screen bg-gradient-to-b from-background via-background to-muted/10">
            <PageContainer>
                <AnimatePresence mode="wait">
                    {loading && !compliance ? (
                        <motion.div
                            key="skeleton"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                        >
                            <HeartbeatSkeleton />
                        </motion.div>
                    ) : (
                        <motion.div
                            key="content"
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, ease: 'easeOut' }}
                            className="space-y-6"
                        >
                            {/* ── Header ── */}
                            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                                <div>
                                    <div className="flex items-center gap-2.5 mb-1">
                                        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Daily Heartbeat</h1>
                                        <span className="relative flex h-2.5 w-2.5">
                                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                                            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
                                        </span>
                                    </div>
                                    <p className="text-sm text-muted-foreground">
                                        {greeting}. Compliance pulse for{' '}
                                        <span className="font-medium text-foreground/80">
                                            {now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
                                        </span>
                                    </p>
                                </div>
                                <div className="flex items-center gap-3">
                                    <span className="text-[11px] text-muted-foreground tabular-nums">
                                        {lastRefresh.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}
                                    </span>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => loadData(true)}
                                        disabled={isRefreshing}
                                        className="gap-1.5 h-8 px-3 text-xs rounded-lg border-[var(--re-border-default)] hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] transition-all"
                                    >
                                        <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
                                        Refresh
                                    </Button>
                                </div>
                            </div>

                            {/* ── Error Banner ── */}
                            <AnimatePresence>
                                {error && (
                                    <motion.div
                                        initial={{ opacity: 0, height: 0 }}
                                        animate={{ opacity: 1, height: 'auto' }}
                                        exit={{ opacity: 0, height: 0 }}
                                    >
                                        <Card className="border-red-500/30 bg-red-500/5">
                                            <CardContent className="py-3">
                                                <div className="flex items-center gap-2 text-red-400">
                                                    <XCircle className="h-4 w-4 flex-shrink-0" />
                                                    <p className="text-sm">{error} — showing cached data if available.</p>
                                </div>
                                            </CardContent>
                                        </Card>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            {/* ── Top Row: Score + Breakdown + Status ── */}
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                                {/* Compliance Score Gauge */}
                                <Card className="overflow-hidden border-[var(--re-border-default)] hover:border-[var(--re-border-subtle)] transition-colors">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-sm font-semibold flex items-center gap-2 text-muted-foreground">
                                            <Shield className="h-4 w-4 text-[var(--re-brand)]" />
                                            FSMA 204 Score
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        {compliance ? (
                                            <div className="flex flex-col items-center gap-3">
                                                <ScoreRing score={compliance.overall_score} grade={compliance.grade} />
                                                <div className="text-center space-y-1">
                                                    <p className="text-xs text-muted-foreground tabular-nums">
                                                        {compliance.events_analyzed.toLocaleString()} events analyzed
                                                    </p>
                                                </div>
                                                <Link href="/dashboard/compliance" className="w-full">
                                                    <Button variant="ghost" size="sm" className="w-full gap-1 text-xs text-muted-foreground hover:text-[var(--re-brand)]">
                                                        Full Report <ChevronRight className="h-3 w-3" />
                                                    </Button>
                                                </Link>
                                            </div>
                                        ) : (
                                            <div className="flex flex-col items-center py-10 text-muted-foreground">
                                                <div className="w-16 h-16 rounded-2xl bg-muted/20 flex items-center justify-center mb-3">
                                                    <Shield className="h-8 w-8 opacity-30" />
                                                </div>
                                                <p className="text-sm font-medium mb-1">No data yet</p>
                                                <p className="text-xs text-muted-foreground/60 mb-3">Import traceability events to get started</p>
                                                <Link href="/tools/data-import">
                                                    <Button size="sm" className="gap-1.5 bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white">
                                                        <Upload className="h-3.5 w-3.5" /> Import Data
                                                    </Button>
                                                </Link>
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>

                                {/* Score Breakdown */}
                                <Card className="overflow-hidden border-[var(--re-border-default)] hover:border-[var(--re-border-subtle)] transition-colors">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-sm font-semibold flex items-center gap-2 text-muted-foreground">
                                            <BarChart3 className="h-4 w-4 text-blue-500" />
                                            Score Breakdown
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        {compliance ? (
                                            <div className="space-y-3.5">
                                                <BreakdownBar
                                                    label="Chain Integrity"
                                                    value={compliance.breakdown.chain_integrity?.score ?? 0}
                                                    detail={compliance.breakdown.chain_integrity?.detail}
                                                    delay={0}
                                                />
                                                <BreakdownBar
                                                    label="KDE Completeness"
                                                    value={compliance.breakdown.kde_completeness?.score ?? 0}
                                                    detail={compliance.breakdown.kde_completeness?.detail}
                                                    delay={0.1}
                                                />
                                                <BreakdownBar
                                                    label="CTE Completeness"
                                                    value={compliance.breakdown.cte_completeness?.score ?? 0}
                                                    detail={compliance.breakdown.cte_completeness?.detail}
                                                    delay={0.2}
                                                />
                                                <BreakdownBar
                                                    label="Export Readiness"
                                                    value={compliance.breakdown.export_readiness?.score ?? 0}
                                                    detail={compliance.breakdown.export_readiness?.detail}
                                                    delay={0.3}
                                                />
                                                <BreakdownBar
                                                    label="Product Coverage"
                                                    value={compliance.breakdown.product_coverage?.score ?? 0}
                                                    detail={compliance.breakdown.product_coverage?.detail}
                                                    delay={0.4}
                                                />
                                            </div>
                                        ) : (
                                            <div className="space-y-3.5">
                                                {[1, 2, 3, 4, 5].map(i => (
                                                    <div key={i} className="space-y-2">
                                                        <div className="flex justify-between">
                                                            <Skeleton className="h-4 w-28" />
                                                            <Skeleton className="h-4 w-10" />
                                                        </div>
                                                        <Skeleton className="h-2 w-full rounded-full" />
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>

                                {/* System Status */}
                                <Card className="overflow-hidden border-[var(--re-border-default)] hover:border-[var(--re-border-subtle)] transition-colors">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-sm font-semibold flex items-center gap-2 text-muted-foreground">
                                            <Activity className="h-4 w-4 text-purple-500" />
                                            System Status
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent className="space-y-2.5">
                                        <StatusRow
                                            icon={Link2}
                                            label="Hash Chain"
                                            value={compliance ? `${compliance.breakdown.chain_integrity?.score ?? 0}%` : '—'}
                                            status={compliance && (compliance.breakdown.chain_integrity?.score ?? 0) >= 80 ? 'good' : 'warn'}
                                        />
                                        <StatusRow
                                            icon={FileText}
                                            label="CTE Events"
                                            value={compliance?.events_analyzed?.toLocaleString() ?? '—'}
                                            status={compliance && compliance.events_analyzed > 0 ? 'good' : 'neutral'}
                                        />
                                        <StatusRow
                                            icon={AlertTriangle}
                                            label="Open Alerts"
                                            value={alerts.length}
                                            status={criticalAlerts.length > 0 ? 'warn' : alerts.length === 0 ? 'good' : 'neutral'}
                                        />

                                        {/* Last Chain Hash */}
                                        {compliance?.last_chain_hash && (
                                            <motion.div
                                                className="p-3 rounded-xl bg-muted/10 border border-[var(--re-border-default)]"
                                                initial={{ opacity: 0 }}
                                                animate={{ opacity: 1 }}
                                                transition={{ delay: 0.6 }}
                                            >
                                                <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1 font-medium">Latest Chain Hash</p>
                                                <code className="text-[11px] font-mono text-foreground/60 break-all leading-relaxed">
                                                    {compliance.last_chain_hash.slice(0, 40)}...
                                                </code>
                                            </motion.div>
                                        )}
                                    </CardContent>
                                </Card>
                            </div>

                            {/* ── Bottom Row: Alerts + Actions ── */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                                {/* Recent Alerts */}
                                <Card className="overflow-hidden border-[var(--re-border-default)] hover:border-[var(--re-border-subtle)] transition-colors">
                                    <CardHeader className="pb-2">
                                        <div className="flex items-center justify-between">
                                            <CardTitle className="text-sm font-semibold flex items-center gap-2 text-muted-foreground">
                                                <AlertTriangle className="h-4 w-4 text-amber-500" />
                                                Recent Alerts
                                                {criticalAlerts.length > 0 && (
                                                    <Badge className="text-[10px] px-1.5 py-0 bg-red-500/15 text-red-400 border-red-500/20 ml-1">
                                                        {criticalAlerts.length} urgent
                                                    </Badge>
                                                )}
                                            </CardTitle>
                                            <Link href="/dashboard/alerts">
                                                <Button variant="ghost" size="sm" className="text-xs gap-1 text-muted-foreground hover:text-[var(--re-brand)] h-7 px-2">
                                                    View All <ArrowRight className="h-3 w-3" />
                                                </Button>
                                            </Link>
                                        </div>
                                    </CardHeader>
                                    <CardContent>
                                        {recentAlerts.length > 0 ? (
                                            <div className="space-y-1">
                                                {recentAlerts.map((alert, i) => {
                                                    const sev = severityConfig(alert.severity);
                                                    return (
                                                        <motion.div
                                                            key={alert.id}
                                                            initial={{ opacity: 0, x: -8 }}
                                                            animate={{ opacity: 1, x: 0 }}
                                                            transition={{ delay: i * 0.04 }}
                                                            className={`flex items-start gap-3 p-2.5 rounded-lg border-l-2 ${sev.border} hover:bg-muted/20 transition-colors cursor-default`}
                                                        >
                                                            <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${sev.dot}`} />
                                                            <div className="flex-1 min-w-0">
                                                                <p className="text-sm font-medium truncate">{alert.title || alert.message}</p>
                                                                <p className="text-[11px] text-muted-foreground mt-0.5 truncate">{alert.category}</p>
                                                            </div>
                                                            <span className="text-[10px] text-muted-foreground/60 flex-shrink-0 mt-0.5 tabular-nums">
                                                                {alert.created_at ? timeAgo(alert.created_at) : ''}
                                                            </span>
                                                        </motion.div>
                                                    );
                                                })}
                                            </div>
                                        ) : (
                                            <div className="flex flex-col items-center py-10 text-muted-foreground">
                                                <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 flex items-center justify-center mb-3">
                                                    <CheckCircle2 className="h-6 w-6 text-emerald-400" />
                                                </div>
                                                <p className="text-sm font-medium">All clear</p>
                                                <p className="text-xs text-muted-foreground/60 mt-0.5">No open alerts right now</p>
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>

                                {/* Priority Actions */}
                                <Card className="overflow-hidden border-[var(--re-border-default)] hover:border-[var(--re-border-subtle)] transition-colors">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-sm font-semibold flex items-center gap-2 text-muted-foreground">
                                            <Zap className="h-4 w-4 text-indigo-500" />
                                            Priority Actions
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        {compliance?.next_actions && compliance.next_actions.length > 0 ? (
                                            <div className="space-y-1.5">
                                                {compliance.next_actions.slice(0, 5).map((action, i) => (
                                                    <motion.div
                                                        key={i}
                                                        initial={{ opacity: 0, x: -8 }}
                                                        animate={{ opacity: 1, x: 0 }}
                                                        transition={{ delay: i * 0.06 }}
                                                        className="flex items-start gap-3 p-3 rounded-lg hover:bg-muted/20 transition-colors"
                                                    >
                                                        <span className={`inline-flex items-center justify-center w-5 h-5 rounded-md text-[10px] font-bold flex-shrink-0 mt-0.5 ${
                                                            action.priority === 'HIGH'
                                                                ? 'bg-red-500/15 text-red-400'
                                                                : action.priority === 'MEDIUM'
                                                                    ? 'bg-yellow-500/15 text-yellow-400'
                                                                    : 'bg-blue-500/15 text-blue-400'
                                                        }`}>
                                                            {i + 1}
                                                        </span>
                                                        <div className="flex-1 min-w-0">
                                                            <p className="text-sm font-medium leading-snug">{action.action}</p>
                                                            <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">{action.impact}</p>
                                                        </div>
                                                    </motion.div>
                                                ))}
                                            </div>
                                        ) : (
                                            <div className="flex flex-col items-center py-10 text-muted-foreground">
                                                <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 flex items-center justify-center mb-3">
                                                    <ShieldCheck className="h-6 w-6 text-emerald-400" />
                                                </div>
                                                <p className="text-sm font-medium">On track</p>
                                                <p className="text-xs text-muted-foreground/60 mt-0.5">No pending compliance actions</p>
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>
                            </div>

                            {/* ── Quick Links ── */}
                            <motion.div
                                className="flex flex-wrap gap-2 justify-center pt-1 pb-4"
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                transition={{ delay: 0.6 }}
                            >
                                {[
                                    { label: 'Full Dashboard', href: '/dashboard', icon: BarChart3 },
                                    { label: 'Import Data', href: '/tools/data-import', icon: Upload },
                                    { label: 'Audit Log', href: '/dashboard/audit-log', icon: FileText },
                                    { label: 'Mock Drill', href: '/dashboard/recall-drills', icon: ShieldCheck },
                                ].map(link => {
                                    const LinkIcon = link.icon;
                                    return (
                                        <Link key={link.href} href={link.href}>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="text-xs gap-1.5 h-8 text-muted-foreground hover:text-[var(--re-brand)] hover:bg-[var(--re-brand)]/5"
                                            >
                                                <LinkIcon className="h-3 w-3" />
                                                {link.label}
                                            </Button>
                                        </Link>
                                    );
                                })}
                            </motion.div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </PageContainer>
        </div>
    );
}
