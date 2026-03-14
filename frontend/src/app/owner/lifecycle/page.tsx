'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    AlertTriangle,
    ArrowUpRight,
    ArrowDownRight,
    RefreshCw,
    XCircle,
    Clock,
    Zap,
    Crown,
    ChevronRight,
    CheckCircle,
    Play,
    TrendingUp,
    Users,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// ── Mock Data ─────────────────────────────────────────────────────

const mockSummary = {
    totalChanges: 5,
    upgrades: 2,
    downgrades: 1,
    cancellations: 1,
    activeTrials: 2,
    trialConversion: '33.3%',
    netMRR: '$2,833.34',
};

const mockChanges = [
    { id: 'chg_acme_up01', tenant: 'Acme Foods Inc.', type: 'upgrade', from: 'Scale', to: 'Enterprise', proration: '$2,100.00', status: 'applied', date: '12d ago' },
    { id: 'chg_med_up01', tenant: 'MedSecure Health', type: 'upgrade', from: 'Growth', to: 'Scale', proration: '$733.34', status: 'applied', date: '25d ago' },
    { id: 'chg_safety_down', tenant: 'SafetyFirst Mfg', type: 'downgrade', from: 'Enterprise', to: 'Scale', proration: '-$1,750.00', status: 'scheduled', date: 'in 15d' },
    { id: 'chg_fresh_addon', tenant: 'FreshLeaf Produce', type: 'addon', from: 'Scale', to: 'Scale + FDA Export', proration: '—', status: 'applied', date: '8d ago' },
    { id: 'chg_old_cancel', tenant: 'OldCo Logistics', type: 'cancellation', from: 'Growth', to: 'Cancelled', proration: '—', status: 'applied', date: '45d ago' },
];

const mockTrials = [
    { tenant: 'Northstar Analytics', plan: 'Enterprise', daysLeft: 2, started: '12d ago', converted: false },
    { tenant: 'NewCo Foods', plan: 'Scale', daysLeft: 7, started: '7d ago', converted: false },
    { tenant: 'ConvertedInc', plan: 'Growth', daysLeft: 0, started: '20d ago', converted: true },
];

const mockPlans = [
    { name: 'Growth', price: '$1,299/mo', tier: 1, color: 'from-slate-500/20 to-slate-600/20' },
    { name: 'Scale', price: '$2,499/mo', tier: 2, color: 'from-blue-500/20 to-indigo-600/20' },
    { name: 'Enterprise', price: '$4,999/mo', tier: 3, color: 'from-violet-500/20 to-purple-600/20' },
    { name: 'Enterprise+', price: '$9,999/mo', tier: 4, color: 'from-amber-500/20 to-orange-600/20' },
];

const typeConfig: Record<string, { icon: React.ElementType; color: string; bg: string }> = {
    upgrade: { icon: ArrowUpRight, color: 'text-emerald-400', bg: 'bg-emerald-500/15 border-emerald-500/20' },
    downgrade: { icon: ArrowDownRight, color: 'text-red-400', bg: 'bg-red-500/15 border-red-500/20' },
    cancellation: { icon: XCircle, color: 'text-rose-500', bg: 'bg-rose-500/15 border-rose-500/20' },
    addon: { icon: Zap, color: 'text-blue-400', bg: 'bg-blue-500/15 border-blue-500/20' },
    reactivation: { icon: RefreshCw, color: 'text-teal-400', bg: 'bg-teal-500/15 border-teal-500/20' },
};

export default function LifecycleDashboard() {
    const [tab, setTab] = useState<'changes' | 'trials' | 'plans'>('changes');

    return (
        <div className="p-8 max-w-[1600px] mx-auto">
            {/* Header */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-gradient-to-br from-violet-500/20 to-purple-600/20">
                            <RefreshCw className="h-7 w-7 text-violet-400" />
                        </div>
                        Subscription Lifecycle
                    </h1>
                    <p className="text-white/50 mt-1 ml-14">Upgrades, downgrades, proration & trial management</p>
                </div>
                <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 border px-3 py-1">
                    <TrendingUp className="h-3.5 w-3.5 mr-1.5" />
                    Net MRR: {mockSummary.netMRR}
                </Badge>
            </motion.div>

            <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Demo Data — This page shows simulated data. Connect your backend to see live metrics.</span>
            </div>

            {/* KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                {[
                    { title: 'Upgrades', value: String(mockSummary.upgrades), sub: 'Plan upgrades', icon: ArrowUpRight, gradient: 'from-emerald-500/20 to-teal-600/20', iconColor: 'text-emerald-400' },
                    { title: 'Downgrades', value: String(mockSummary.downgrades), sub: '1 scheduled', icon: ArrowDownRight, gradient: 'from-red-500/20 to-orange-600/20', iconColor: 'text-red-400' },
                    { title: 'Active Trials', value: String(mockSummary.activeTrials), sub: '1 expiring soon', icon: Play, gradient: 'from-blue-500/20 to-indigo-600/20', iconColor: 'text-blue-400' },
                    { title: 'Trial Conversion', value: mockSummary.trialConversion, sub: '1 of 3 converted', icon: Users, gradient: 'from-violet-500/20 to-purple-600/20', iconColor: 'text-violet-400' },
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
                            {(['changes', 'trials', 'plans'] as const).map((t) => (
                                <button key={t} onClick={() => setTab(t)}
                                    className={cn('px-6 py-3 text-sm font-medium border-b-2 transition-all capitalize',
                                        tab === t ? 'text-white border-violet-400' : 'text-white/40 border-transparent hover:text-white/60')}>
                                    {t === 'changes' ? 'Plan Changes' : t}
                                </button>
                            ))}
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        {tab === 'changes' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1.5fr_0.8fr_1fr_1fr_1fr_0.8fr_0.8fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Customer</span><span>Type</span><span>From</span><span>To</span><span>Proration</span><span>Status</span><span>When</span>
                                </div>
                                {mockChanges.map((c) => {
                                    const cfg = typeConfig[c.type] || typeConfig.addon;
                                    const Icon = cfg.icon;
                                    return (
                                        <div key={c.id} className="grid grid-cols-[1.5fr_0.8fr_1fr_1fr_1fr_0.8fr_0.8fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                            <p className="text-sm font-semibold text-white">{c.tenant}</p>
                                            <Badge className={cn('border text-xs w-fit', cfg.bg)}>
                                                <Icon className={cn('h-3 w-3 mr-1', cfg.color)} />
                                                <span className={cfg.color}>{c.type}</span>
                                            </Badge>
                                            <p className="text-xs text-white/50">{c.from}</p>
                                            <p className="text-sm font-semibold text-white">{c.to}</p>
                                            <p className={cn('text-sm font-semibold', c.proration.startsWith('-') ? 'text-red-400' : c.proration === '—' ? 'text-white/30' : 'text-emerald-400')}>{c.proration}</p>
                                            <Badge className={cn('text-xs w-fit border', c.status === 'applied' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20' : 'bg-amber-500/15 text-amber-400 border-amber-500/20')}>
                                                {c.status}
                                            </Badge>
                                            <p className="text-xs text-white/40">{c.date}</p>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {tab === 'trials' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1.5fr_1fr_1fr_1fr_1fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Tenant</span><span>Plan</span><span>Started</span><span>Days Left</span><span>Status</span>
                                </div>
                                {mockTrials.map((t, i) => (
                                    <div key={i} className="grid grid-cols-[1.5fr_1fr_1fr_1fr_1fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                        <p className="text-sm font-semibold text-white">{t.tenant}</p>
                                        <p className="text-sm text-white/60">{t.plan}</p>
                                        <p className="text-xs text-white/40">{t.started}</p>
                                        <p className={cn('text-sm font-bold', t.daysLeft <= 3 ? 'text-red-400' : 'text-blue-400')}>
                                            {t.daysLeft > 0 ? `${t.daysLeft}d` : 'Ended'}
                                        </p>
                                        <div className="flex items-center gap-1.5">
                                            {t.converted ? (
                                                <><CheckCircle className="h-3.5 w-3.5 text-emerald-400" /><span className="text-xs text-emerald-400">Converted</span></>
                                            ) : t.daysLeft > 0 ? (
                                                <><Clock className="h-3.5 w-3.5 text-blue-400" /><span className="text-xs text-blue-400">Active</span></>
                                            ) : (
                                                <><XCircle className="h-3.5 w-3.5 text-red-400" /><span className="text-xs text-red-400">Expired</span></>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {tab === 'plans' && (
                            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-4">
                                {mockPlans.map((p, i) => (
                                    <motion.div key={p.name} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.05 }}>
                                        <div className={cn('p-5 rounded-xl bg-gradient-to-br border border-white/10 text-center', p.color)}>
                                            <Crown className="h-6 w-6 mx-auto text-white/60 mb-2" />
                                            <p className="text-lg font-bold text-white">{p.name}</p>
                                            <p className="text-2xl font-bold text-white mt-1">{p.price}</p>
                                            <p className="text-xs text-white/40 mt-1">Tier {p.tier}</p>
                                        </div>
                                    </motion.div>
                                ))}
                            </div>
                        )}
                    </CardContent>
                </Card>
            </motion.div>
        </div>
    );
}
