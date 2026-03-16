'use client';

import { useEffect, useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { PageContainer } from '@/components/layout/page-container';
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
    if (grade === 'A' || grade === 'A+') return 'text-emerald-500';
    if (grade === 'B' || grade === 'B+') return 'text-green-500';
    if (grade === 'C' || grade === 'C+') return 'text-yellow-500';
    if (grade === 'D') return 'text-orange-500';
    return 'text-red-500';
}

function scoreRingColor(score: number): string {
    if (score >= 80) return '#10b981';
    if (score >= 60) return '#eab308';
    if (score >= 40) return '#f97316';
    return '#ef4444';
}

function severityBadge(severity: string) {
    const map: Record<string, string> = {
        critical: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
        high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
        medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
        low: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
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

// ── Score Ring SVG ──

function ScoreRing({ score, grade, size = 180 }: { score: number; grade: string; size?: number }) {
    const radius = (size - 20) / 2;
    const circumference = 2 * Math.PI * radius;
    const progress = (score / 100) * circumference;
    const color = scoreRingColor(score);

    return (
        <div className="relative inline-flex items-center justify-center">
            <svg width={size} height={size} className="-rotate-90">
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="10"
                    className="text-muted/20"
                />
                <motion.circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke={color}
                    strokeWidth="10"
                    strokeLinecap="round"
                    strokeDasharray={circumference}
                    initial={{ strokeDashoffset: circumference }}
                    animate={{ strokeDashoffset: circumference - progress }}
                    transition={{ duration: 1.2, ease: 'easeOut' }}
                />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className={`text-4xl font-bold ${gradeColor(grade)}`}>{grade}</span>
                <span className="text-2xl font-semibold text-foreground">{score}%</span>
            </div>
        </div>
    );
}

// ── Breakdown Bar ──

function BreakdownBar({ label, value }: { label: string; value: number }) {
    const color = value >= 80 ? 'bg-emerald-500' : value >= 60 ? 'bg-yellow-500' : value >= 40 ? 'bg-orange-500' : 'bg-red-500';
    return (
        <div className="space-y-1">
            <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">{label}</span>
                <span className="font-medium">{value}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted/30 overflow-hidden">
                <motion.div
                    className={`h-full rounded-full ${color}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${value}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut', delay: 0.3 }}
                />
            </div>
        </div>
    );
}

// ── Page ──

export default function HeartbeatPage() {
    const { user, isHydrated } = useAuth();
    const { tenantId } = useTenant();
    const router = useRouter();

    const [compliance, setCompliance] = useState<ComplianceData | null>(null);
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

    useEffect(() => {
        if (isHydrated && !user) {
            router.push(`/login?next=${encodeURIComponent('/dashboard/heartbeat')}`);
        }
    }, [isHydrated, user, router]);

    const loadData = async () => {
        if (!tenantId) return;
        setLoading(true);
        setError(null);
        try {
            const [scoreData, alertsData] = await Promise.allSettled([
                fetchComplianceScore(tenantId),
                fetchAlerts(tenantId, { acknowledged: false }),
            ]);

            if (scoreData.status === 'fulfilled') {
                setCompliance(scoreData.value as ComplianceData);
            }
            if (alertsData.status === 'fulfilled') {
                const raw = alertsData.value as any;
                setAlerts(Array.isArray(raw) ? raw : raw?.alerts ?? []);
            }
            setLastRefresh(new Date());
        } catch (e) {
            setError('Failed to load compliance data');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (tenantId) {
            loadData();
        }
    }, [tenantId]);

    // Auto-refresh every 60s
    useEffect(() => {
        const interval = setInterval(loadData, 60_000);
        return () => clearInterval(interval);
    }, [tenantId]);

    const criticalAlerts = useMemo(() =>
        alerts.filter(a => a.severity === 'critical' || a.severity === 'high').slice(0, 5),
        [alerts],
    );

    const recentAlerts = useMemo(() => alerts.slice(0, 8), [alerts]);

    if (!isHydrated || !user) return null;

    const now = new Date();
    const greeting = now.getHours() < 12 ? 'Good morning' : now.getHours() < 17 ? 'Good afternoon' : 'Good evening';

    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <PageContainer>
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="space-y-6"
                >
                    {/* Header */}
                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                        <div>
                            <h1 className="text-2xl sm:text-3xl font-bold">Daily Heartbeat</h1>
                            <p className="text-muted-foreground mt-1">
                                {greeting}. Here&apos;s your compliance pulse for {now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}.
                            </p>
                        </div>
                        <div className="flex items-center gap-3">
                            <span className="text-xs text-muted-foreground">
                                Updated {lastRefresh.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}
                            </span>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={loadData}
                                disabled={loading}
                                className="gap-1.5"
                            >
                                <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                                Refresh
                            </Button>
                        </div>
                    </div>

                    {error && (
                        <Card className="border-red-200 bg-red-50 dark:bg-red-900/10 dark:border-red-800">
                            <CardContent className="pt-4 pb-4">
                                <div className="flex items-center gap-2 text-red-700 dark:text-red-400">
                                    <XCircle className="h-4 w-4 flex-shrink-0" />
                                    <p className="text-sm">{error} — showing cached data if available.</p>
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Top Row: Score + Chain + Events */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        {/* Compliance Score Gauge */}
                        <Card className="lg:row-span-1">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Shield className="h-4 w-4 text-emerald-500" />
                                    Compliance Score
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                {loading && !compliance ? (
                                    <div className="flex justify-center py-8">
                                        <div className="h-[180px] w-[180px] rounded-full border-4 border-muted animate-pulse" />
                                    </div>
                                ) : compliance ? (
                                    <div className="flex flex-col items-center gap-4">
                                        <ScoreRing score={compliance.overall_score} grade={compliance.grade} />
                                        <div className="text-center">
                                            <p className="text-sm text-muted-foreground">
                                                {compliance.events_analyzed} events analyzed
                                            </p>
                                        </div>
                                        <Link href="/dashboard/compliance" className="w-full">
                                            <Button variant="ghost" size="sm" className="w-full gap-1 text-xs">
                                                View Full Breakdown <ChevronRight className="h-3 w-3" />
                                            </Button>
                                        </Link>
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center py-8 text-muted-foreground">
                                        <Shield className="h-10 w-10 mb-2 opacity-30" />
                                        <p className="text-sm">No score data yet</p>
                                        <Link href="/tools/data-import" className="mt-2">
                                            <Button variant="outline" size="sm" className="gap-1.5">
                                                <Upload className="h-3.5 w-3.5" /> Import Data
                                            </Button>
                                        </Link>
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Score Breakdown */}
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base flex items-center gap-2">
                                    <TrendingUp className="h-4 w-4 text-blue-500" />
                                    Score Breakdown
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                {compliance ? (
                                    <>
                                        <BreakdownBar label="Chain Integrity" value={compliance.breakdown.chain_integrity?.score ?? 0} />
                                        <BreakdownBar label="KDE Completeness" value={compliance.breakdown.kde_completeness?.score ?? 0} />
                                        <BreakdownBar label="CTE Completeness" value={compliance.breakdown.cte_completeness?.score ?? 0} />
                                        <BreakdownBar label="Export Readiness" value={compliance.breakdown.export_readiness?.score ?? 0} />
                                        <BreakdownBar label="Product Coverage" value={compliance.breakdown.product_coverage?.score ?? 0} />
                                    </>
                                ) : (
                                    <div className="space-y-3">
                                        {[1, 2, 3, 4, 5].map(i => (
                                            <div key={i} className="space-y-1">
                                                <div className="h-4 bg-muted/30 rounded w-1/3 animate-pulse" />
                                                <div className="h-2 bg-muted/20 rounded animate-pulse" />
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Chain & System Status */}
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Link2 className="h-4 w-4 text-purple-500" />
                                    System Status
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                {/* Chain Integrity */}
                                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                                    <div className="flex items-center gap-2">
                                        {compliance && (compliance.breakdown.chain_integrity?.score ?? 0) >= 80 ? (
                                            <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                                        ) : (
                                            <XCircle className="h-5 w-5 text-amber-500" />
                                        )}
                                        <span className="text-sm font-medium">Hash Chain</span>
                                    </div>
                                    <Badge variant="outline" className={
                                        compliance && (compliance.breakdown.chain_integrity?.score ?? 0) >= 80
                                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                                            : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                                    }>
                                        {compliance ? `${compliance.breakdown.chain_integrity?.score ?? 0}%` : '—'}
                                    </Badge>
                                </div>

                                {/* Events Count */}
                                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                                    <div className="flex items-center gap-2">
                                        <Activity className="h-5 w-5 text-blue-500" />
                                        <span className="text-sm font-medium">CTE Events</span>
                                    </div>
                                    <span className="text-sm font-bold">
                                        {compliance?.events_analyzed?.toLocaleString() ?? '—'}
                                    </span>
                                </div>

                                {/* Alert Summary */}
                                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                                    <div className="flex items-center gap-2">
                                        <AlertTriangle className="h-5 w-5 text-amber-500" />
                                        <span className="text-sm font-medium">Open Alerts</span>
                                    </div>
                                    <span className="text-sm font-bold">
                                        {alerts.length}
                                    </span>
                                </div>

                                {/* Last Chain Hash (truncated) */}
                                {compliance?.last_chain_hash && (
                                    <div className="p-3 rounded-lg bg-muted/30">
                                        <p className="text-xs text-muted-foreground mb-1">Latest Chain Hash</p>
                                        <code className="text-xs font-mono break-all">
                                            {compliance.last_chain_hash.slice(0, 32)}...
                                        </code>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>

                    {/* Bottom Row: Alerts + Next Actions */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Recent Alerts */}
                        <Card>
                            <CardHeader className="pb-2">
                                <div className="flex items-center justify-between">
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <AlertTriangle className="h-4 w-4 text-amber-500" />
                                        Recent Alerts
                                        {criticalAlerts.length > 0 && (
                                            <Badge variant="destructive" className="text-xs ml-1">
                                                {criticalAlerts.length} urgent
                                            </Badge>
                                        )}
                                    </CardTitle>
                                    <Link href="/dashboard/alerts">
                                        <Button variant="ghost" size="sm" className="text-xs gap-1">
                                            View All <ArrowRight className="h-3 w-3" />
                                        </Button>
                                    </Link>
                                </div>
                            </CardHeader>
                            <CardContent>
                                {recentAlerts.length > 0 ? (
                                    <div className="space-y-2">
                                        {recentAlerts.map((alert, i) => (
                                            <motion.div
                                                key={alert.id}
                                                initial={{ opacity: 0, x: -10 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: i * 0.05 }}
                                                className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-muted/30 transition-colors"
                                            >
                                                <Badge className={`text-[10px] px-1.5 py-0.5 mt-0.5 flex-shrink-0 ${severityBadge(alert.severity)}`}>
                                                    {alert.severity}
                                                </Badge>
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-sm font-medium truncate">{alert.title || alert.message}</p>
                                                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{alert.category}</p>
                                                </div>
                                                <span className="text-[10px] text-muted-foreground flex-shrink-0 mt-0.5">
                                                    {alert.created_at ? timeAgo(alert.created_at) : ''}
                                                </span>
                                            </motion.div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center py-8 text-muted-foreground">
                                        <CheckCircle2 className="h-8 w-8 mb-2 text-emerald-400" />
                                        <p className="text-sm font-medium">All clear</p>
                                        <p className="text-xs">No open alerts right now.</p>
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Next Actions */}
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Clock className="h-4 w-4 text-indigo-500" />
                                    Priority Actions
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                {compliance?.next_actions && compliance.next_actions.length > 0 ? (
                                    <div className="space-y-2">
                                        {compliance.next_actions.slice(0, 6).map((action, i) => (
                                            <motion.div
                                                key={i}
                                                initial={{ opacity: 0, x: -10 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: i * 0.05 }}
                                                className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-muted/30 transition-colors"
                                            >
                                                <Badge variant="outline" className={
                                                    action.priority === 'HIGH'
                                                        ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 text-[10px] px-1.5 py-0.5 mt-0.5 flex-shrink-0'
                                                        : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400 text-[10px] px-1.5 py-0.5 mt-0.5 flex-shrink-0'
                                                }>
                                                    {action.priority}
                                                </Badge>
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-sm font-medium">{action.action}</p>
                                                    <p className="text-xs text-muted-foreground mt-0.5">{action.impact}</p>
                                                </div>
                                            </motion.div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center py-8 text-muted-foreground">
                                        <CheckCircle2 className="h-8 w-8 mb-2 text-emerald-400" />
                                        <p className="text-sm font-medium">No pending actions</p>
                                        <p className="text-xs">Your compliance posture is on track.</p>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>

                    {/* Quick Links Footer */}
                    <div className="flex flex-wrap gap-2 justify-center pt-2 pb-4">
                        <Link href="/dashboard">
                            <Button variant="ghost" size="sm" className="text-xs gap-1.5">
                                Full Dashboard <ArrowRight className="h-3 w-3" />
                            </Button>
                        </Link>
                        <Link href="/tools/data-import">
                            <Button variant="ghost" size="sm" className="text-xs gap-1.5">
                                <Upload className="h-3 w-3" /> Import Data
                            </Button>
                        </Link>
                        <Link href="/dashboard/audit-log">
                            <Button variant="ghost" size="sm" className="text-xs gap-1.5">
                                Audit Log <ArrowRight className="h-3 w-3" />
                            </Button>
                        </Link>
                        <Link href="/dashboard/recall-drills">
                            <Button variant="ghost" size="sm" className="text-xs gap-1.5">
                                Mock Drill <ArrowRight className="h-3 w-3" />
                            </Button>
                        </Link>
                    </div>
                </motion.div>
            </PageContainer>
        </div>
    );
}
