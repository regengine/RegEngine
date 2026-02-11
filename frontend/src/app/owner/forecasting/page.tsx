'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    TrendingUp,
    TrendingDown,
    AlertTriangle,
    Heart,
    BarChart3,
    Users,
    Activity,
    Zap,
    Target,
    Eye,
    ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// ── Mock Data ─────────────────────────────────────────────────────

const mockSummary = {
    currentMRR: '$184,250.00',
    arr: '$2,211,000.00',
    mrrGrowth: '+5.4%',
    forecast3mo: '$213,800',
    totalCLV: '$3.8M',
    avgCLV: '$475K',
    atRiskRevenue: '$5,498.00',
    anomalies: 3,
};

const mockForecasts = [
    { month: '2026-03', predicted: '$189,900', lower: '$181,200', upper: '$198,600', confidence: 0.90 },
    { month: '2026-04', predicted: '$196,400', lower: '$184,800', upper: '$208,000', confidence: 0.85 },
    { month: '2026-05', predicted: '$203,100', lower: '$188,700', upper: '$217,500', confidence: 0.80 },
    { month: '2026-06', predicted: '$210,200', lower: '$192,400', upper: '$228,000', confidence: 0.75 },
    { month: '2026-07', predicted: '$217,600', lower: '$196,300', upper: '$238,900', confidence: 0.70 },
    { month: '2026-08', predicted: '$225,300', lower: '$200,500', upper: '$250,100', confidence: 0.65 },
];

const mockChurn = [
    { tenant: 'OldCo Logistics', risk: 'critical', score: 95, action: 'Win-back campaign with 50% discount', trend: 'down' },
    { tenant: 'SafetyFirst Mfg', risk: 'high', score: 72, action: 'Executive intervention required', trend: 'down' },
    { tenant: 'MedSecure Health', risk: 'medium', score: 45, action: 'Customer success call', trend: 'down' },
    { tenant: 'BetaCorp Analytics', risk: 'medium', score: 40, action: 'Convert trial with Enterprise', trend: 'flat' },
    { tenant: 'FreshLeaf Produce', risk: 'low', score: 18, action: 'Offer annual contract', trend: 'up' },
    { tenant: 'NewCo Foods', risk: 'low', score: 15, action: 'Guided onboarding', trend: 'up' },
    { tenant: 'Acme Foods Inc.', risk: 'low', score: 12, action: 'Upsell to Enterprise+', trend: 'up' },
    { tenant: 'GlobalFish Imports', risk: 'low', score: 5, action: 'Strategic review', trend: 'up' },
];

const mockCLV = [
    { tenant: 'GlobalFish Imports', clv: '$479,952', plan: 'enterprise_plus', months: 24 },
    { tenant: 'Acme Foods Inc.', clv: '$269,946', plan: 'enterprise', months: 18 },
    { tenant: 'FreshLeaf Produce', clv: '$74,950', plan: 'professional', months: 10 },
    { tenant: 'MedSecure Health', clv: '$59,960', plan: 'professional', months: 14 },
];

const mockRetention = [
    { cohort: '2025-Q1', rates: [100, 94.2, 88.7, 83.5, 79.1, 75.0, 71.2] },
    { cohort: '2025-Q2', rates: [100, 92.8, 86.3, 80.1, 74.8, 70.2, 66.0] },
    { cohort: '2025-Q3', rates: [100, 95.1, 90.4, 86.0, 82.1, 78.5, 75.2] },
    { cohort: '2025-Q4', rates: [100, 93.5, 87.8, 82.6, 78.0, 73.8] },
    { cohort: '2026-Q1', rates: [100, 91.8, 84.6, 78.3] },
];

const mockAnomalies = [
    { metric: 'Churn Rate', description: '2.1x higher than 6-month average', severity: 'critical', deviation: '+110%' },
    { metric: 'Expansion MRR', description: '35% above forecast — 3 enterprise upgrades', severity: 'info', deviation: '+34.9%' },
    { metric: 'ARPU', description: 'Declining 8% MoM for Starter tier', severity: 'warning', deviation: '-8.1%' },
];

const riskConfig: Record<string, { color: string; bg: string }> = {
    critical: { color: 'text-red-400', bg: 'bg-red-500/15 border-red-500/20' },
    high: { color: 'text-orange-400', bg: 'bg-orange-500/15 border-orange-500/20' },
    medium: { color: 'text-amber-400', bg: 'bg-amber-500/15 border-amber-500/20' },
    low: { color: 'text-emerald-400', bg: 'bg-emerald-500/15 border-emerald-500/20' },
};

export default function ForecastingDashboard() {
    const [tab, setTab] = useState<'forecast' | 'churn' | 'clv' | 'cohorts' | 'anomalies'>('forecast');

    return (
        <div className="p-8 max-w-[1600px] mx-auto">
            {/* Header */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-600/20">
                            <Activity className="h-7 w-7 text-cyan-400" />
                        </div>
                        Predictive Analytics
                    </h1>
                    <p className="text-white/50 mt-1 ml-14">MRR forecasting, churn prediction, CLV & cohort analysis</p>
                </div>
                <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/30 border px-3 py-1">
                    <TrendingUp className="h-3.5 w-3.5 mr-1.5" />
                    ARR: {mockSummary.arr}
                </Badge>
            </motion.div>

            {/* KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                {[
                    { title: 'Current MRR', value: mockSummary.currentMRR, sub: mockSummary.mrrGrowth + ' growth', icon: TrendingUp, gradient: 'from-emerald-500/20 to-teal-600/20', iconColor: 'text-emerald-400' },
                    { title: '3-Month Forecast', value: mockSummary.forecast3mo, sub: '75% confidence', icon: Target, gradient: 'from-cyan-500/20 to-blue-600/20', iconColor: 'text-cyan-400' },
                    { title: 'Total CLV', value: mockSummary.totalCLV, sub: `Avg ${mockSummary.avgCLV}`, icon: Heart, gradient: 'from-violet-500/20 to-purple-600/20', iconColor: 'text-violet-400' },
                    { title: 'At-Risk Revenue', value: mockSummary.atRiskRevenue, sub: '2 high-risk tenants', icon: AlertTriangle, gradient: 'from-red-500/20 to-rose-600/20', iconColor: 'text-red-400' },
                ].map((kpi, i) => (
                    <motion.div key={kpi.title} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                        <Card className="bg-white/5 backdrop-blur-xl border-white/10 hover:bg-white/8 transition-all group">
                            <CardContent className="p-5">
                                <div className="flex items-start justify-between">
                                    <div className="space-y-1">
                                        <p className="text-xs font-medium text-white/50 uppercase tracking-wider">{kpi.title}</p>
                                        <p className="text-2xl font-bold text-white">{kpi.value}</p>
                                        <p className="text-xs text-white/40">{kpi.sub}</p>
                                    </div>
                                    <div className={cn('p-2.5 rounded-xl bg-gradient-to-br', kpi.gradient, 'group-hover:scale-110 transition-transform')}>
                                        <kpi.icon className={cn('h-5 w-5', kpi.iconColor)} />
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                ))}
            </div>

            {/* Tabbed Content */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader className="border-b border-white/10 pb-0">
                        <div className="flex gap-0 overflow-x-auto">
                            {([
                                { key: 'forecast', label: 'MRR Forecast' },
                                { key: 'churn', label: 'Churn Risk' },
                                { key: 'clv', label: 'Lifetime Value' },
                                { key: 'cohorts', label: 'Retention' },
                                { key: 'anomalies', label: 'Anomalies' },
                            ] as const).map((t) => (
                                <button key={t.key} onClick={() => setTab(t.key)}
                                    className={cn('px-5 py-3 text-sm font-medium border-b-2 transition-all whitespace-nowrap',
                                        tab === t.key ? 'text-white border-cyan-400' : 'text-white/40 border-transparent hover:text-white/60')}>
                                    {t.label}
                                </button>
                            ))}
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        {tab === 'forecast' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1fr_1fr_1fr_1fr_0.8fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Month</span><span>Predicted MRR</span><span>Lower Bound</span><span>Upper Bound</span><span>Confidence</span>
                                </div>
                                {mockForecasts.map((f) => (
                                    <div key={f.month} className="grid grid-cols-[1fr_1fr_1fr_1fr_0.8fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                        <p className="text-sm font-semibold text-white">{f.month}</p>
                                        <p className="text-sm font-bold text-emerald-400">{f.predicted}</p>
                                        <p className="text-xs text-white/40">{f.lower}</p>
                                        <p className="text-xs text-white/40">{f.upper}</p>
                                        <div className="flex items-center gap-2">
                                            <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden">
                                                <div className="h-full bg-cyan-400/60 rounded-full" style={{ width: `${f.confidence * 100}%` }} />
                                            </div>
                                            <span className="text-xs text-white/50">{Math.round(f.confidence * 100)}%</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {tab === 'churn' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1.5fr_0.8fr_0.6fr_2fr_0.5fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Tenant</span><span>Risk</span><span>Score</span><span>Recommended Action</span><span>Trend</span>
                                </div>
                                {mockChurn.map((c) => {
                                    const cfg = riskConfig[c.risk] || riskConfig.low;
                                    return (
                                        <div key={c.tenant} className="grid grid-cols-[1.5fr_0.8fr_0.6fr_2fr_0.5fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                            <p className="text-sm font-semibold text-white">{c.tenant}</p>
                                            <Badge className={cn('border text-xs w-fit', cfg.bg)}>
                                                <span className={cfg.color}>{c.risk}</span>
                                            </Badge>
                                            <div className="flex items-center gap-2">
                                                <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden">
                                                    <div className={cn('h-full rounded-full', c.score > 70 ? 'bg-red-400' : c.score > 30 ? 'bg-amber-400' : 'bg-emerald-400')}
                                                        style={{ width: `${c.score}%` }} />
                                                </div>
                                                <span className="text-xs text-white/40 w-6">{c.score}</span>
                                            </div>
                                            <p className="text-xs text-white/50">{c.action}</p>
                                            <div>
                                                {c.trend === 'up' ? <TrendingUp className="h-4 w-4 text-emerald-400" /> :
                                                    c.trend === 'down' ? <TrendingDown className="h-4 w-4 text-red-400" /> :
                                                        <ChevronRight className="h-4 w-4 text-amber-400" />}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {tab === 'clv' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1.5fr_1fr_1fr_1fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Customer</span><span>Lifetime Value</span><span>Plan</span><span>Tenure</span>
                                </div>
                                {mockCLV.map((c) => (
                                    <div key={c.tenant} className="grid grid-cols-[1.5fr_1fr_1fr_1fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                        <p className="text-sm font-semibold text-white">{c.tenant}</p>
                                        <p className="text-lg font-bold text-violet-400">{c.clv}</p>
                                        <Badge className="bg-white/5 text-white/60 border-white/10 border text-xs w-fit">{c.plan}</Badge>
                                        <p className="text-sm text-white/50">{c.months} months</p>
                                    </div>
                                ))}
                            </div>
                        )}

                        {tab === 'cohorts' && (
                            <div className="p-4 overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                            <th className="text-left py-2 px-2">Cohort</th>
                                            {['M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6'].map(m => (
                                                <th key={m} className="text-center py-2 px-2">{m}</th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {mockRetention.map((c) => (
                                            <tr key={c.cohort} className="border-t border-white/5 hover:bg-white/5 transition-colors">
                                                <td className="py-2 px-2 font-semibold text-white text-xs">{c.cohort}</td>
                                                {c.rates.map((r, i) => (
                                                    <td key={i} className="text-center py-2 px-2">
                                                        <span className={cn('text-xs font-mono px-2 py-1 rounded',
                                                            r >= 90 ? 'bg-emerald-500/20 text-emerald-400' :
                                                                r >= 75 ? 'bg-cyan-500/20 text-cyan-400' :
                                                                    r >= 60 ? 'bg-amber-500/20 text-amber-400' :
                                                                        'bg-red-500/20 text-red-400')}>
                                                            {r}%
                                                        </span>
                                                    </td>
                                                ))}
                                                {Array.from({ length: 7 - c.rates.length }).map((_, i) => (
                                                    <td key={`empty-${i}`} className="text-center py-2 px-2">
                                                        <span className="text-xs text-white/10">—</span>
                                                    </td>
                                                ))}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}

                        {tab === 'anomalies' && (
                            <div className="divide-y divide-white/5">
                                {mockAnomalies.map((a, i) => {
                                    const sev = a.severity === 'critical' ? 'bg-red-500/15 border-red-500/20 text-red-400' :
                                        a.severity === 'warning' ? 'bg-amber-500/15 border-amber-500/20 text-amber-400' :
                                            'bg-blue-500/15 border-blue-500/20 text-blue-400';
                                    return (
                                        <div key={i} className="flex items-center gap-4 px-4 py-4 hover:bg-white/5 transition-colors">
                                            <div className={cn('p-2 rounded-lg', a.severity === 'critical' ? 'bg-red-500/15' : a.severity === 'warning' ? 'bg-amber-500/15' : 'bg-blue-500/15')}>
                                                {a.severity === 'critical' ? <AlertTriangle className="h-5 w-5 text-red-400" /> :
                                                    a.severity === 'warning' ? <Eye className="h-5 w-5 text-amber-400" /> :
                                                        <Zap className="h-5 w-5 text-blue-400" />}
                                            </div>
                                            <div className="flex-1">
                                                <p className="text-sm font-semibold text-white">{a.metric}</p>
                                                <p className="text-xs text-white/40 mt-0.5">{a.description}</p>
                                            </div>
                                            <Badge className={cn('border text-xs', sev)}>{a.severity}</Badge>
                                            <span className={cn('text-sm font-bold', a.deviation.startsWith('+') ? 'text-emerald-400' : 'text-red-400')}>{a.deviation}</span>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </CardContent>
                </Card>
            </motion.div>
        </div>
    );
}
