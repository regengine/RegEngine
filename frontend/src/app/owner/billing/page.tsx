'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    DollarSign,
    TrendingUp,
    TrendingDown,
    Users,
    BarChart3,
    Target,
    CreditCard,
    Zap,
    AlertTriangle,
    CheckCircle,
    ArrowUpRight,
    ArrowDownRight,
    RefreshCw,
    FileText,
    Activity,
    Database,
    Shield,
    Sparkles,
    ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// ── Mock Data (mirrors analytics engine output) ───────────────────

const mockOverview = {
    mrr: { mrr_cents: 12750000, mrr_display: "$127,500", arr_cents: 153000000, arr_display: "$1,530,000", active_subscriptions: 47, growth_rate_pct: 12.5, avg_deal_size_cents: 271277 },
    key_metrics: { net_dollar_retention: "118%", trial_to_paid_rate: "30.1%", monthly_churn_rate: "1.5%", ltv_cac_ratio: "4.2:1", avg_revenue_per_account_display: "$2,713" },
    health: "excellent",
};

const mockMRRHistory = [
    { month_label: "Mar 2025", mrr_cents: 4860000, new_mrr_cents: 350000, churned_mrr_cents: 97200, expansion_mrr_cents: 145000 },
    { month_label: "Apr 2025", mrr_cents: 5394600, new_mrr_cents: 420000, churned_mrr_cents: 107892, expansion_mrr_cents: 162000 },
    { month_label: "May 2025", mrr_cents: 5880114, new_mrr_cents: 370000, churned_mrr_cents: 117602, expansion_mrr_cents: 176400 },
    { month_label: "Jun 2025", mrr_cents: 6703330, new_mrr_cents: 660000, churned_mrr_cents: 134067, expansion_mrr_cents: 201100 },
    { month_label: "Jul 2025", mrr_cents: 7373663, new_mrr_cents: 520000, churned_mrr_cents: 147473, expansion_mrr_cents: 221210 },
    { month_label: "Aug 2025", mrr_cents: 8258502, new_mrr_cents: 700000, churned_mrr_cents: 165170, expansion_mrr_cents: 247755 },
    { month_label: "Sep 2025", mrr_cents: 9497278, new_mrr_cents: 1000000, churned_mrr_cents: 189946, expansion_mrr_cents: 284918 },
    { month_label: "Oct 2025", mrr_cents: 10731924, new_mrr_cents: 980000, churned_mrr_cents: 214638, expansion_mrr_cents: 321958 },
    { month_label: "Nov 2025", mrr_cents: 11912436, new_mrr_cents: 930000, churned_mrr_cents: 238249, expansion_mrr_cents: 357373 },
    { month_label: "Dec 2025", mrr_cents: 13818426, new_mrr_cents: 1550000, churned_mrr_cents: 276369, expansion_mrr_cents: 414553 },
    { month_label: "Jan 2026", mrr_cents: 15476637, new_mrr_cents: 1300000, churned_mrr_cents: 309533, expansion_mrr_cents: 464299 },
    { month_label: "Feb 2026", mrr_cents: 17488600, new_mrr_cents: 1600000, churned_mrr_cents: 349772, expansion_mrr_cents: 524658 },
];

const mockFunnel = {
    stages: [
        { name: "Website Visitors", count: 12400, rate: 1.0 },
        { name: "Signups", count: 890, rate: 0.0718 },
        { name: "Trial Started", count: 156, rate: 0.1753 },
        { name: "Converted to Paid", count: 47, rate: 0.3013 },
        { name: "Churned", count: 8, rate: 0.1455 },
    ],
    trial_to_paid_rate: 0.3013,
    churn_rate: 0.0145,
    net_retention_rate: 1.18,
};

const mockCohorts = [
    { label: "Sep 2025", initial_tenants: 8, retention_rates: [1.0, 0.85, 0.78, 0.74, 0.71, 0.69] },
    { label: "Oct 2025", initial_tenants: 11, retention_rates: [1.0, 0.88, 0.82, 0.77, 0.74, 0.72] },
    { label: "Nov 2025", initial_tenants: 14, retention_rates: [1.0, 0.82, 0.75, 0.70, 0.67] },
    { label: "Dec 2025", initial_tenants: 17, retention_rates: [1.0, 0.90, 0.84, 0.80] },
    { label: "Jan 2026", initial_tenants: 20, retention_rates: [1.0, 0.87, 0.81] },
    { label: "Feb 2026", initial_tenants: 23, retention_rates: [1.0, 0.91] },
];

const mockCreditPrograms = [
    { code: "EARLY2026", type: "early_adopter", amount_display: "$120", total_redemptions: 23, utilization_rate: 0.046, roi: 2.0, abuse_risk: "low" },
    { code: "REFER500", type: "referral", amount_display: "$500", total_redemptions: 8, utilization_rate: 0.0, roi: 2.0, abuse_risk: "low" },
    { code: "PARTNER100", type: "partner", amount_display: "$100", total_redemptions: 15, utilization_rate: 0.015, roi: 2.0, abuse_risk: "low" },
    { code: "LAUNCH50", type: "promo", amount_display: "$50", total_redemptions: 42, utilization_rate: 0.21, roi: 2.0, abuse_risk: "low" },
];

const mockOverageAlerts = [
    { tenant_id: "medsecure", resource: "document_processing", used: 15600, included: 10000, usage_pct: 156, severity: "critical" },
    { tenant_id: "acme_foods", resource: "document_processing", used: 8420, included: 10000, usage_pct: 84.2, severity: "warning" },
    { tenant_id: "medsecure", resource: "api_calls", used: 67300, included: 50000, usage_pct: 134.6, severity: "critical" },
    { tenant_id: "safetyfirst", resource: "storage_gb", used: 38, included: 100, usage_pct: 88.0, severity: "warning" },
];

const mockForecasts = [
    { month_label: "Mar 2026", projected_mrr_display: "$148,200", projected_arr_display: "$1,778,400" },
    { month_label: "Apr 2026", projected_mrr_display: "$165,400", projected_arr_display: "$1,984,800" },
    { month_label: "May 2026", projected_mrr_display: "$184,600", projected_arr_display: "$2,215,200" },
    { month_label: "Jun 2026", projected_mrr_display: "$206,100", projected_arr_display: "$2,473,200" },
    { month_label: "Jul 2026", projected_mrr_display: "$230,000", projected_arr_display: "$2,760,000" },
    { month_label: "Aug 2026", projected_mrr_display: "$256,700", projected_arr_display: "$3,080,400" },
];

// ── Helper Components ─────────────────────────────────────────────

function formatCurrency(cents: number): string {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(cents / 100);
}

function MetricCard({
    title, value, subtitle, icon: Icon, trend, trendValue, delay = 0,
    gradient = 'from-amber-500/20 to-orange-600/20',
    iconColor = 'text-amber-400',
}: {
    title: string; value: string; subtitle?: string; icon: React.ElementType;
    trend?: 'up' | 'down'; trendValue?: string; delay?: number;
    gradient?: string; iconColor?: string;
}) {
    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.4 }}>
            <Card className="bg-white/5 backdrop-blur-xl border-white/10 hover:bg-white/8 transition-all duration-300 group">
                <CardContent className="p-5">
                    <div className="flex items-start justify-between">
                        <div className="space-y-1">
                            <p className="text-xs font-medium text-white/50 uppercase tracking-wider">{title}</p>
                            <p className="text-2xl font-bold text-white">{value}</p>
                            {(trend || subtitle) && (
                                <div className="flex items-center gap-1.5 pt-0.5">
                                    {trend && (
                                        <>
                                            {trend === 'up'
                                                ? <ArrowUpRight className="h-3.5 w-3.5 text-emerald-400" />
                                                : <ArrowDownRight className="h-3.5 w-3.5 text-red-400" />}
                                            <span className={cn('text-xs font-semibold', trend === 'up' ? 'text-emerald-400' : 'text-red-400')}>
                                                {trendValue}
                                            </span>
                                        </>
                                    )}
                                    {subtitle && <span className="text-xs text-white/40">{subtitle}</span>}
                                </div>
                            )}
                        </div>
                        <div className={cn('p-2.5 rounded-xl bg-gradient-to-br', gradient, 'group-hover:scale-110 transition-transform duration-300')}>
                            <Icon className={cn('h-5 w-5', iconColor)} />
                        </div>
                    </div>
                </CardContent>
            </Card>
        </motion.div>
    );
}

// ── MRR Sparkline Chart ───────────────────────────────────────────

function MRRSparkline({ data }: { data: typeof mockMRRHistory }) {
    const maxMRR = Math.max(...data.map(d => d.mrr_cents));
    const width = 100;
    const height = 40;
    const points = data.map((d, i) => ({
        x: (i / (data.length - 1)) * width,
        y: height - (d.mrr_cents / maxMRR) * height * 0.85,
    }));
    const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
    const areaD = `${pathD} L ${width} ${height} L 0 ${height} Z`;

    return (
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-24" preserveAspectRatio="none">
            <defs>
                <linearGradient id="mrrGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.3" />
                    <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.02" />
                </linearGradient>
            </defs>
            <path d={areaD} fill="url(#mrrGradient)" />
            <path d={pathD} fill="none" stroke="#f59e0b" strokeWidth="1" strokeLinecap="round" />
            {points.length > 0 && (
                <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="2" fill="#f59e0b" />
            )}
        </svg>
    );
}

// ── Cohort Heatmap ────────────────────────────────────────────────

function CohortHeatmap({ cohorts }: { cohorts: typeof mockCohorts }) {
    const getColor = (rate: number) => {
        if (rate >= 0.9) return 'bg-emerald-500/40 text-emerald-300';
        if (rate >= 0.8) return 'bg-emerald-500/25 text-emerald-300';
        if (rate >= 0.7) return 'bg-amber-500/25 text-amber-300';
        if (rate >= 0.6) return 'bg-orange-500/25 text-orange-300';
        return 'bg-red-500/25 text-red-300';
    };

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-xs">
                <thead>
                    <tr>
                        <th className="text-left text-white/40 font-medium p-2">Cohort</th>
                        <th className="text-center text-white/40 font-medium p-2">Size</th>
                        {Array.from({ length: 6 }, (_, i) => (
                            <th key={i} className="text-center text-white/40 font-medium p-2">M{i}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {cohorts.map((cohort) => (
                        <tr key={cohort.label}>
                            <td className="text-white/70 font-medium p-2 whitespace-nowrap">{cohort.label}</td>
                            <td className="text-center text-white/60 p-2">{cohort.initial_tenants}</td>
                            {Array.from({ length: 6 }, (_, i) => (
                                <td key={i} className="p-1">
                                    {cohort.retention_rates[i] !== undefined ? (
                                        <div className={cn('rounded px-2 py-1 text-center font-mono font-medium', getColor(cohort.retention_rates[i]))}>
                                            {(cohort.retention_rates[i] * 100).toFixed(0)}%
                                        </div>
                                    ) : (
                                        <div className="text-center text-white/10">—</div>
                                    )}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

// ── Conversion Funnel ─────────────────────────────────────────────

function FunnelVisualization({ stages }: { stages: typeof mockFunnel.stages }) {
    const maxCount = stages[0].count;
    const colors = [
        'from-blue-500/30 to-blue-600/30',
        'from-cyan-500/30 to-cyan-600/30',
        'from-amber-500/30 to-amber-600/30',
        'from-emerald-500/30 to-emerald-600/30',
        'from-red-500/30 to-red-600/30',
    ];

    return (
        <div className="space-y-2">
            {stages.map((stage, i) => {
                const widthPct = Math.max(15, (stage.count / maxCount) * 100);
                return (
                    <div key={stage.name} className="flex items-center gap-3">
                        <div className="w-28 text-xs text-white/60 text-right shrink-0">{stage.name}</div>
                        <div className="flex-1 relative h-7">
                            <motion.div
                                initial={{ width: 0 }}
                                animate={{ width: `${widthPct}%` }}
                                transition={{ delay: i * 0.1, duration: 0.6 }}
                                className={cn('absolute inset-y-0 left-0 rounded-md bg-gradient-to-r flex items-center px-3', colors[i])}
                            >
                                <span className="text-xs font-semibold text-white whitespace-nowrap">
                                    {stage.count.toLocaleString()}
                                </span>
                            </motion.div>
                        </div>
                        <div className="w-12 text-xs text-white/40 text-right shrink-0">
                            {(stage.rate * 100).toFixed(1)}%
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

// ── Main Dashboard ────────────────────────────────────────────────

export default function RevenueDashboard() {
    const [isRefreshing, setIsRefreshing] = useState(false);

    const handleRefresh = () => {
        setIsRefreshing(true);
        setTimeout(() => setIsRefreshing(false), 1500);
    };

    return (
        <div className="p-8 max-w-[1600px] mx-auto">
            {/* Header */}
            <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center justify-between mb-8"
            >
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-600/20">
                            <BarChart3 className="h-7 w-7 text-amber-400" />
                        </div>
                        Revenue Command Center
                    </h1>
                    <p className="text-white/50 mt-1 ml-14">Real-time revenue analytics, usage metering & growth forecasting</p>
                </div>
                <div className="flex items-center gap-3">
                    <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 border px-3 py-1">
                        <CheckCircle className="h-3.5 w-3.5 mr-1.5" />
                        All Systems Healthy
                    </Badge>
                    <Button
                        onClick={handleRefresh}
                        variant="outline"
                        size="sm"
                        className="bg-white/5 border-white/10 text-white hover:bg-white/10"
                    >
                        <RefreshCw className={cn('h-4 w-4 mr-2', isRefreshing && 'animate-spin')} />
                        Refresh
                    </Button>
                </div>
            </motion.div>

            {/* KPI Cards — Row 1 */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
                <MetricCard
                    title="MRR" value={mockOverview.mrr.mrr_display}
                    icon={DollarSign} trend="up" trendValue="+12.5%"
                    subtitle="vs last month" delay={0}
                />
                <MetricCard
                    title="ARR" value={mockOverview.mrr.arr_display}
                    icon={TrendingUp} trend="up" trendValue="+$180K"
                    subtitle="run rate" delay={0.05}
                    gradient="from-emerald-500/20 to-teal-600/20" iconColor="text-emerald-400"
                />
                <MetricCard
                    title="Active Subscribers" value="47"
                    icon={Users} trend="up" trendValue="+8"
                    subtitle="this month" delay={0.1}
                    gradient="from-blue-500/20 to-indigo-600/20" iconColor="text-blue-400"
                />
                <MetricCard
                    title="Net Revenue Retention" value={mockOverview.key_metrics.net_dollar_retention}
                    icon={Target}
                    subtitle="expansion > churn" delay={0.15}
                    gradient="from-purple-500/20 to-violet-600/20" iconColor="text-purple-400"
                />
                <MetricCard
                    title="LTV:CAC Ratio" value={mockOverview.key_metrics.ltv_cac_ratio}
                    icon={Sparkles}
                    subtitle="target: 3:1" delay={0.2}
                    gradient="from-pink-500/20 to-rose-600/20" iconColor="text-pink-400"
                />
            </div>

            {/* MRR Chart + Forecasts */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.25 }}
                    className="lg:col-span-2"
                >
                    <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                        <CardHeader className="border-b border-white/10 pb-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="text-white">MRR Growth Trajectory</CardTitle>
                                    <CardDescription className="text-white/50">12-month trend with net-new breakdown</CardDescription>
                                </div>
                                <div className="flex items-center gap-4 text-xs">
                                    <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-emerald-400" /> New</span>
                                    <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-blue-400" /> Expansion</span>
                                    <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-red-400" /> Churned</span>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="p-6">
                            <MRRSparkline data={mockMRRHistory} />
                            <div className="grid grid-cols-6 gap-2 mt-4">
                                {mockMRRHistory.slice(-6).map((m) => (
                                    <div key={m.month_label} className="text-center">
                                        <p className="text-[10px] text-white/40">{m.month_label}</p>
                                        <p className="text-xs font-semibold text-white">{formatCurrency(m.mrr_cents)}</p>
                                        <div className="flex items-center justify-center gap-0.5 mt-0.5">
                                            <span className="text-[9px] text-emerald-400">+{formatCurrency(m.new_mrr_cents)}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Revenue Forecast */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                >
                    <Card className="bg-white/5 backdrop-blur-xl border-white/10 h-full">
                        <CardHeader className="border-b border-white/10 pb-4">
                            <CardTitle className="text-white flex items-center gap-2">
                                <Sparkles className="h-4 w-4 text-purple-400" />
                                Revenue Forecast
                            </CardTitle>
                            <CardDescription className="text-white/50">6-month projection</CardDescription>
                        </CardHeader>
                        <CardContent className="p-4">
                            <div className="space-y-2.5">
                                {mockForecasts.map((f, i) => (
                                    <div key={f.month_label} className="flex items-center justify-between py-1.5 border-b border-white/5 last:border-0">
                                        <span className="text-xs text-white/60">{f.month_label}</span>
                                        <div className="text-right">
                                            <p className="text-sm font-semibold text-white">{f.projected_mrr_display}</p>
                                            <p className="text-[10px] text-white/40">{f.projected_arr_display} ARR</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <div className="mt-4 p-3 rounded-lg bg-purple-500/10 border border-purple-500/20">
                                <p className="text-xs text-purple-300 font-medium">Projected by Aug 2026</p>
                                <p className="text-lg font-bold text-purple-200 mt-0.5">$3.08M ARR</p>
                                <p className="text-[10px] text-purple-400 mt-0.5">Based on 11.8% avg monthly growth</p>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            </div>

            {/* Funnel + Cohorts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                {/* Conversion Funnel */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
                    <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                        <CardHeader className="border-b border-white/10 pb-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="text-white">Conversion Funnel</CardTitle>
                                    <CardDescription className="text-white/50">Visitor → Subscriber pipeline</CardDescription>
                                </div>
                                <div className="flex gap-2">
                                    <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/20 border text-xs">
                                        30.1% trial→paid
                                    </Badge>
                                    <Badge className="bg-blue-500/15 text-blue-400 border-blue-500/20 border text-xs">
                                        1.5% churn
                                    </Badge>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="p-6">
                            <FunnelVisualization stages={mockFunnel.stages} />
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Cohort Retention */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
                    <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                        <CardHeader className="border-b border-white/10 pb-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="text-white">Cohort Retention</CardTitle>
                                    <CardDescription className="text-white/50">Monthly retention by signup cohort</CardDescription>
                                </div>
                                <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/20 border text-xs">
                                    92% avg retention
                                </Badge>
                            </div>
                        </CardHeader>
                        <CardContent className="p-4">
                            <CohortHeatmap cohorts={mockCohorts} />
                        </CardContent>
                    </Card>
                </motion.div>
            </div>

            {/* Credits ROI + Overage Alerts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Credit Program Performance */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }}>
                    <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                        <CardHeader className="border-b border-white/10 pb-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="text-white flex items-center gap-2">
                                        <CreditCard className="h-4 w-4 text-amber-400" />
                                        Credit Program ROI
                                    </CardTitle>
                                    <CardDescription className="text-white/50">Performance & abuse monitoring</CardDescription>
                                </div>
                                <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/20 border text-xs">
                                    4 active programs
                                </Badge>
                            </div>
                        </CardHeader>
                        <CardContent className="p-0">
                            <div className="divide-y divide-white/5">
                                {mockCreditPrograms.map((prog) => (
                                    <div key={prog.code} className="p-4 flex items-center justify-between hover:bg-white/5 transition-colors">
                                        <div className="flex items-center gap-3">
                                            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-500/20 to-orange-600/20 flex items-center justify-center">
                                                <Zap className="h-4 w-4 text-amber-400" />
                                            </div>
                                            <div>
                                                <p className="text-sm font-semibold text-white font-mono">{prog.code}</p>
                                                <p className="text-xs text-white/40">{prog.type} · {prog.amount_display}</p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-4">
                                            <div className="text-right">
                                                <p className="text-sm font-medium text-white">{prog.total_redemptions} uses</p>
                                                <p className="text-[10px] text-white/40">{(prog.utilization_rate * 100).toFixed(1)}% utilized</p>
                                            </div>
                                            <Badge className={cn(
                                                'border text-xs',
                                                prog.abuse_risk === 'low'
                                                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
                                                    : prog.abuse_risk === 'medium'
                                                        ? 'bg-amber-500/15 text-amber-400 border-amber-500/20'
                                                        : 'bg-red-500/15 text-red-400 border-red-500/20'
                                            )}>
                                                {prog.abuse_risk}
                                            </Badge>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Usage & Overage Alerts */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}>
                    <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                        <CardHeader className="border-b border-white/10 pb-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="text-white flex items-center gap-2">
                                        <Activity className="h-4 w-4 text-blue-400" />
                                        Usage & Overage Alerts
                                    </CardTitle>
                                    <CardDescription className="text-white/50">Tenants approaching or exceeding limits</CardDescription>
                                </div>
                                <div className="flex gap-2">
                                    <Badge className="bg-red-500/15 text-red-400 border-red-500/20 border text-xs">
                                        2 critical
                                    </Badge>
                                    <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/20 border text-xs">
                                        2 warnings
                                    </Badge>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="p-0">
                            <div className="divide-y divide-white/5">
                                {mockOverageAlerts.map((alert, i) => {
                                    const resourceIcons: Record<string, React.ElementType> = {
                                        document_processing: FileText,
                                        api_calls: Zap,
                                        storage_gb: Database,
                                    };
                                    const ResourceIcon = resourceIcons[alert.resource] || Activity;
                                    const resourceLabels: Record<string, string> = {
                                        document_processing: 'Documents',
                                        api_calls: 'API Calls',
                                        storage_gb: 'Storage',
                                    };

                                    return (
                                        <div key={i} className="p-4 flex items-center justify-between hover:bg-white/5 transition-colors">
                                            <div className="flex items-center gap-3">
                                                <div className={cn(
                                                    'w-9 h-9 rounded-lg flex items-center justify-center',
                                                    alert.severity === 'critical'
                                                        ? 'bg-red-500/20'
                                                        : 'bg-amber-500/20'
                                                )}>
                                                    {alert.severity === 'critical'
                                                        ? <AlertTriangle className="h-4 w-4 text-red-400" />
                                                        : <ResourceIcon className="h-4 w-4 text-amber-400" />}
                                                </div>
                                                <div>
                                                    <p className="text-sm font-medium text-white">{alert.tenant_id}</p>
                                                    <p className="text-xs text-white/40">{resourceLabels[alert.resource]}</p>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-3">
                                                <div className="text-right">
                                                    <p className="text-sm font-medium text-white">
                                                        {alert.used.toLocaleString()} / {alert.included.toLocaleString()}
                                                    </p>
                                                    <div className="w-24 h-1.5 bg-white/10 rounded-full mt-1 overflow-hidden">
                                                        <div
                                                            className={cn(
                                                                'h-full rounded-full transition-all',
                                                                alert.severity === 'critical' ? 'bg-red-400' : 'bg-amber-400'
                                                            )}
                                                            style={{ width: `${Math.min(alert.usage_pct, 100)}%` }}
                                                        />
                                                    </div>
                                                </div>
                                                <Badge className={cn(
                                                    'border text-xs font-mono',
                                                    alert.severity === 'critical'
                                                        ? 'bg-red-500/15 text-red-400 border-red-500/20'
                                                        : 'bg-amber-500/15 text-amber-400 border-amber-500/20'
                                                )}>
                                                    {alert.usage_pct.toFixed(0)}%
                                                </Badge>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            </div>
        </div>
    );
}
