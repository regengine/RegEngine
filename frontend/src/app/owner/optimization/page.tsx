'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    Sparkles,
    DollarSign,
    Target,
    Heart,
    Users,
    TrendingUp,
    ArrowUpRight,
    Gift,
    BarChart3,
    Megaphone,
    Shield,
    ArrowRight,
    CheckCircle,
    Clock,
    XCircle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// ── Mock Data ─────────────────────────────────────────────────────

const mockPipeline = {
    pipelineValue: '$8,896.00',
    weightedPipeline: '$5,234.50',
    wonRevenue: '$1,500.00',
    activeOpps: 4,
    winBackRecovered: '$31,690.00',
    nrr: '118.4%',
};

const mockPricingRecs = [
    { plan: 'Starter', current: '$499', recommended: '$599', change: '+20%', confidence: '82%', impact: '+$8.4K MRR', rationale: 'Price anchoring drives Pro conversions' },
    { plan: 'Enterprise', current: '$4,999', recommended: '$5,499', change: '+10%', confidence: '75%', impact: '+$15K MRR', rationale: '94% retention, competitors avg $6,200' },
    { plan: 'FDA Export', current: '$299', recommended: '$399', change: '+33%', confidence: '88%', impact: '+$4.2K MRR', rationale: '98% attachment, no alternatives' },
];

const mockOpportunities = [
    { tenant: 'Acme Foods', type: 'upsell', title: 'Enterprise+ Upgrade', value: '$5,000', probability: '72%', status: 'identified', action: 'Demo E+ features with CTO' },
    { tenant: 'MedSecure Health', type: 'expansion', title: 'Multi-Dept Expansion', value: '$2,997', probability: '55%', status: 'in_progress', action: 'Multi-dept pricing review' },
    { tenant: 'GlobalFish', type: 'expansion', title: '15 Seat Expansion', value: '$1,500', probability: '100%', status: 'won', action: 'Deploy & onboard' },
    { tenant: 'FreshLeaf', type: 'cross_sell', title: 'FDA Export Module', value: '$399', probability: '85%', status: 'contacted', action: 'Share ROI calculator' },
    { tenant: 'OldCo Logistics', type: 'win_back', title: 'Win-Back Offer', value: '$499', probability: '30%', status: 'identified', action: '3 months at 50% off' },
];

const mockHealth = [
    { tenant: 'GlobalFish Imports', grade: 'A', score: 96, usage: 98, engagement: 95, payment: 100 },
    { tenant: 'Acme Foods Inc.', grade: 'A', score: 92, usage: 95, engagement: 88, payment: 100 },
    { tenant: 'FreshLeaf Produce', grade: 'B', score: 78, usage: 82, engagement: 75, payment: 100 },
    { tenant: 'MedSecure Health', grade: 'C', score: 55, usage: 45, engagement: 50, payment: 65 },
    { tenant: 'SafetyFirst Mfg', grade: 'D', score: 32, usage: 30, engagement: 25, payment: 45 },
    { tenant: 'OldCo Logistics', grade: 'F', score: 8, usage: 0, engagement: 0, payment: 0 },
];

const mockCampaigns = [
    { name: 'Q1 Save & Recover', status: 'active', segment: 'Churned < 90d', offer: '50% off 3mo', contacted: 8, converted: 2, recovered: '$1,498.00' },
    { name: 'Enterprise Retention', status: 'active', segment: 'Enterprise declining', offer: 'Free E+ trial', contacted: 3, converted: 1, recovered: '$4,999.00' },
    { name: 'Annual Commitment', status: 'completed', segment: 'Monthly > 6mo', offer: '20% annual discount', contacted: 18, converted: 7, recovered: '$25,193.00' },
];

const typeColors: Record<string, { color: string; bg: string }> = {
    upsell: { color: 'text-emerald-400', bg: 'bg-emerald-500/15 border-emerald-500/20' },
    cross_sell: { color: 'text-blue-400', bg: 'bg-blue-500/15 border-blue-500/20' },
    expansion: { color: 'text-violet-400', bg: 'bg-violet-500/15 border-violet-500/20' },
    win_back: { color: 'text-amber-400', bg: 'bg-amber-500/15 border-amber-500/20' },
};

const gradeColors: Record<string, string> = {
    A: 'text-emerald-400 bg-emerald-500/15',
    B: 'text-cyan-400 bg-cyan-500/15',
    C: 'text-amber-400 bg-amber-500/15',
    D: 'text-orange-400 bg-orange-500/15',
    F: 'text-red-400 bg-red-500/15',
};

export default function OptimizationDashboard() {
    const [tab, setTab] = useState<'pipeline' | 'pricing' | 'health' | 'campaigns'>('pipeline');

    return (
        <div className="p-8 max-w-[1600px] mx-auto">
            {/* Header */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-gradient-to-br from-amber-500/20 to-yellow-600/20">
                            <Sparkles className="h-7 w-7 text-amber-400" />
                        </div>
                        Revenue Intelligence
                    </h1>
                    <p className="text-white/50 mt-1 ml-14">Pricing optimization, pipeline, health scoring & win-back campaigns</p>
                </div>
                <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 border px-3 py-1">
                    <TrendingUp className="h-3.5 w-3.5 mr-1.5" />
                    NRR: {mockPipeline.nrr}
                </Badge>
            </motion.div>

            {/* KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                {[
                    { title: 'Pipeline Value', value: mockPipeline.pipelineValue, sub: `Weighted: ${mockPipeline.weightedPipeline}`, icon: Target, gradient: 'from-violet-500/20 to-purple-600/20', iconColor: 'text-violet-400' },
                    { title: 'Active Opportunities', value: String(mockPipeline.activeOpps), sub: '1 won, 4 in pipeline', icon: ArrowUpRight, gradient: 'from-emerald-500/20 to-teal-600/20', iconColor: 'text-emerald-400' },
                    { title: 'Win-Back Recovered', value: mockPipeline.winBackRecovered, sub: '10 conversions total', icon: Gift, gradient: 'from-amber-500/20 to-orange-600/20', iconColor: 'text-amber-400' },
                    { title: 'NRR', value: mockPipeline.nrr, sub: 'Expansion > churn', icon: TrendingUp, gradient: 'from-cyan-500/20 to-blue-600/20', iconColor: 'text-cyan-400' },
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
                        <div className="flex gap-0">
                            {([
                                { key: 'pipeline', label: 'Opportunity Pipeline' },
                                { key: 'pricing', label: 'Pricing Intelligence' },
                                { key: 'health', label: 'Customer Health' },
                                { key: 'campaigns', label: 'Win-Back Campaigns' },
                            ] as const).map((t) => (
                                <button key={t.key} onClick={() => setTab(t.key)}
                                    className={cn('px-5 py-3 text-sm font-medium border-b-2 transition-all whitespace-nowrap',
                                        tab === t.key ? 'text-white border-amber-400' : 'text-white/40 border-transparent hover:text-white/60')}>
                                    {t.label}
                                </button>
                            ))}
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        {tab === 'pipeline' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1.2fr_0.7fr_1.2fr_0.8fr_0.7fr_0.7fr_1.5fr] gap-3 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Tenant</span><span>Type</span><span>Opportunity</span><span>Value</span><span>Probability</span><span>Status</span><span>Action</span>
                                </div>
                                {mockOpportunities.map((o, i) => {
                                    const tc = typeColors[o.type] || typeColors.upsell;
                                    const statusIcon = o.status === 'won' ? <CheckCircle className="h-3 w-3 text-emerald-400" /> :
                                        o.status === 'in_progress' ? <Clock className="h-3 w-3 text-blue-400" /> :
                                            <Target className="h-3 w-3 text-white/30" />;
                                    return (
                                        <div key={i} className="grid grid-cols-[1.2fr_0.7fr_1.2fr_0.8fr_0.7fr_0.7fr_1.5fr] gap-3 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                            <p className="text-sm font-semibold text-white">{o.tenant}</p>
                                            <Badge className={cn('border text-[10px] w-fit', tc.bg)}>
                                                <span className={tc.color}>{o.type.replace('_', ' ')}</span>
                                            </Badge>
                                            <p className="text-xs text-white/60">{o.title}</p>
                                            <p className="text-sm font-bold text-emerald-400">{o.value}</p>
                                            <p className="text-xs text-white/50">{o.probability}</p>
                                            <div className="flex items-center gap-1">{statusIcon}<span className="text-[10px] text-white/40">{o.status}</span></div>
                                            <p className="text-[11px] text-white/40">{o.action}</p>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {tab === 'pricing' && (
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4">
                                {mockPricingRecs.map((r, i) => (
                                    <motion.div key={r.plan} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.05 }}>
                                        <div className="p-5 rounded-xl bg-white/5 border border-white/10 space-y-4">
                                            <div className="flex items-center justify-between">
                                                <p className="text-lg font-bold text-white">{r.plan}</p>
                                                <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/20 border text-xs">{r.change}</Badge>
                                            </div>
                                            <div className="flex items-center gap-3">
                                                <span className="text-white/30 line-through">{r.current}</span>
                                                <ArrowRight className="h-4 w-4 text-white/20" />
                                                <span className="text-xl font-bold text-emerald-400">{r.recommended}</span>
                                            </div>
                                            <p className="text-xs text-white/40">{r.rationale}</p>
                                            <div className="flex items-center justify-between pt-2 border-t border-white/5">
                                                <div className="flex items-center gap-1.5">
                                                    <Shield className="h-3.5 w-3.5 text-cyan-400" />
                                                    <span className="text-xs text-white/50">Confidence: {r.confidence}</span>
                                                </div>
                                                <span className="text-sm font-bold text-violet-400">{r.impact}</span>
                                            </div>
                                        </div>
                                    </motion.div>
                                ))}
                            </div>
                        )}

                        {tab === 'health' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1.5fr_0.5fr_0.6fr_0.8fr_0.8fr_0.8fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Customer</span><span>Grade</span><span>Score</span><span>Usage</span><span>Engagement</span><span>Payment</span>
                                </div>
                                {mockHealth.map((h) => (
                                    <div key={h.tenant} className="grid grid-cols-[1.5fr_0.5fr_0.6fr_0.8fr_0.8fr_0.8fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                        <p className="text-sm font-semibold text-white">{h.tenant}</p>
                                        <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm', gradeColors[h.grade])}>
                                            {h.grade}
                                        </div>
                                        <p className="text-sm font-bold text-white">{h.score}</p>
                                        {[h.usage, h.engagement, h.payment].map((v, i) => (
                                            <div key={i} className="flex items-center gap-2">
                                                <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden">
                                                    <div className={cn('h-full rounded-full', v >= 80 ? 'bg-emerald-400' : v >= 50 ? 'bg-amber-400' : 'bg-red-400')}
                                                        style={{ width: `${v}%` }} />
                                                </div>
                                                <span className="text-xs text-white/40 w-6">{v}</span>
                                            </div>
                                        ))}
                                    </div>
                                ))}
                            </div>
                        )}

                        {tab === 'campaigns' && (
                            <div className="divide-y divide-white/5">
                                {mockCampaigns.map((c, i) => (
                                    <div key={i} className="p-4 hover:bg-white/5 transition-colors">
                                        <div className="flex items-center justify-between mb-3">
                                            <div className="flex items-center gap-3">
                                                <Megaphone className="h-5 w-5 text-amber-400" />
                                                <p className="text-sm font-bold text-white">{c.name}</p>
                                                <Badge className={cn('border text-xs', c.status === 'active' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20' : 'bg-white/5 text-white/40 border-white/10')}>
                                                    {c.status}
                                                </Badge>
                                            </div>
                                            <p className="text-lg font-bold text-emerald-400">{c.recovered}</p>
                                        </div>
                                        <div className="grid grid-cols-4 gap-4 text-xs">
                                            <div><span className="text-white/40">Segment:</span> <span className="text-white/70 ml-1">{c.segment}</span></div>
                                            <div><span className="text-white/40">Offer:</span> <span className="text-white/70 ml-1">{c.offer}</span></div>
                                            <div><span className="text-white/40">Contacted:</span> <span className="text-white/70 ml-1">{c.contacted}</span></div>
                                            <div><span className="text-white/40">Converted:</span> <span className="text-emerald-400 font-bold ml-1">{c.converted}</span></div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </CardContent>
                </Card>
            </motion.div>
        </div>
    );
}
