'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    AlertTriangle,
    RotateCw,
    ChevronUp,
    DollarSign,
    CheckCircle,
    XCircle,
    Clock,
    Shield,
    TrendingDown,
    ArrowUpRight,
    Ban,
    Zap,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// ── Mock Data ─────────────────────────────────────────────────────

const mockSummary = {
    totalCases: 4,
    activeCases: 2,
    recoveredCases: 1,
    totalAtRisk: '$15,339.39',
    totalRecovered: '$4,862.50',
    totalWrittenOff: '$1,890.00',
    recoveryRate: 25.0,
    totalRetries: 8,
};

const mockCases = [
    { id: 'dun_northstar_01', tenant: 'Northstar Cold Chain', invoice: 'INV-2026-1009', amount: '$12,049.55', stage: 'second_notice', status: 'active', retries: 2, daysPast: 16, lastResult: 'Insufficient funds' },
    { id: 'dun_harvest_01', tenant: 'Harvest Table Foods', invoice: 'INV-2026-1011', amount: '$3,289.84', stage: 'reminder', status: 'active', retries: 1, daysPast: 3, lastResult: 'Card expired' },
    { id: 'dun_freshleaf_01', tenant: 'FreshLeaf Produce', invoice: 'INV-2026-0998', amount: '$4,862.50', stage: 'first_notice', status: 'recovered', retries: 2, daysPast: 9, lastResult: 'Succeeded' },
    { id: 'dun_oldco_01', tenant: 'Legacy Foods Co.', invoice: 'INV-2025-0845', amount: '$1,890.00', stage: 'collections', status: 'written_off', retries: 3, daysPast: 50, lastResult: 'Card declined' },
];

const mockSchedule = [
    { stage: 'Reminder', day: 'Day 1', action: 'Friendly payment reminder email', color: 'text-blue-400' },
    { stage: '1st Notice', day: 'Day 7', action: 'Formal overdue notice', color: 'text-amber-400' },
    { stage: '2nd Notice', day: 'Day 14', action: 'Urgent payment required', color: 'text-orange-400' },
    { stage: 'Final Notice', day: 'Day 21', action: 'Last warning', color: 'text-red-400' },
    { stage: 'Suspension', day: 'Day 30', action: 'Service suspended', color: 'text-red-500' },
    { stage: 'Collections', day: 'Day 45', action: 'External collections', color: 'text-rose-500' },
];

const stageConfig: Record<string, { color: string; bg: string }> = {
    reminder: { color: 'text-blue-400', bg: 'bg-blue-500/15 border-blue-500/20' },
    first_notice: { color: 'text-amber-400', bg: 'bg-amber-500/15 border-amber-500/20' },
    second_notice: { color: 'text-orange-400', bg: 'bg-orange-500/15 border-orange-500/20' },
    final_notice: { color: 'text-red-400', bg: 'bg-red-500/15 border-red-500/20' },
    suspension: { color: 'text-red-500', bg: 'bg-red-600/15 border-red-600/20' },
    collections: { color: 'text-rose-500', bg: 'bg-rose-600/15 border-rose-600/20' },
};

const statusIcons: Record<string, React.ElementType> = {
    active: AlertTriangle,
    recovered: CheckCircle,
    written_off: Ban,
    suspended: XCircle,
};

// ── Main Dashboard ────────────────────────────────────────────────

export default function DunningDashboard() {
    return (
        <div className="p-8 max-w-[1600px] mx-auto">
            {/* Header */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-gradient-to-br from-red-500/20 to-orange-600/20">
                            <Shield className="h-7 w-7 text-red-400" />
                        </div>
                        Collections
                    </h1>
                    <p className="text-white/50 mt-1 ml-14">Dunning automation, payment recovery & escalation</p>
                </div>
                <Badge className="bg-red-500/20 text-red-400 border-red-500/30 border px-3 py-1">
                    <AlertTriangle className="h-3.5 w-3.5 mr-1.5" />
                    {mockSummary.activeCases} Active Cases
                </Badge>
            </motion.div>

            <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Demo Data — This page shows simulated data. Connect your backend to see live metrics.</span>
            </div>

            {/* KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                {[
                    { title: 'At Risk', value: mockSummary.totalAtRisk, sub: `${mockSummary.activeCases} active cases`, icon: AlertTriangle, gradient: 'from-red-500/20 to-orange-600/20', iconColor: 'text-red-400' },
                    { title: 'Recovered', value: mockSummary.totalRecovered, sub: `${mockSummary.recoveredCases} case(s)`, icon: CheckCircle, gradient: 'from-emerald-500/20 to-teal-600/20', iconColor: 'text-emerald-400' },
                    { title: 'Written Off', value: mockSummary.totalWrittenOff, sub: 'Uncollectible', icon: TrendingDown, gradient: 'from-slate-500/20 to-slate-600/20', iconColor: 'text-slate-400' },
                    { title: 'Recovery Rate', value: `${mockSummary.recoveryRate}%`, sub: `${mockSummary.totalRetries} retry attempts`, icon: RotateCw, gradient: 'from-blue-500/20 to-indigo-600/20', iconColor: 'text-blue-400' },
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

            {/* Escalation Schedule */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="mb-6">
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader className="border-b border-white/10 pb-4">
                        <CardTitle className="text-white flex items-center gap-2">
                            <ChevronUp className="h-4 w-4 text-orange-400" />
                            Escalation Schedule
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-4">
                        <div className="flex gap-2">
                            {mockSchedule.map((step, i) => (
                                <div key={step.stage} className="flex-1 relative">
                                    <div className="p-3 rounded-lg bg-white/5 border border-white/10 text-center">
                                        <p className={cn('text-xs font-bold', step.color)}>{step.stage}</p>
                                        <p className="text-[10px] text-white/40 mt-1">{step.day}</p>
                                        <p className="text-[9px] text-white/30 mt-0.5">{step.action}</p>
                                    </div>
                                    {i < mockSchedule.length - 1 && (
                                        <div className="absolute top-1/2 -right-2 text-white/20 text-xs">→</div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* Active Cases */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}>
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader className="border-b border-white/10 pb-4">
                        <CardTitle className="text-white flex items-center gap-2">
                            <Zap className="h-4 w-4 text-amber-400" />
                            Dunning Cases
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                        <div className="divide-y divide-white/5">
                            {/* Header */}
                            <div className="grid grid-cols-[1.5fr_1fr_1fr_1fr_0.8fr_0.8fr_1fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                <span>Customer</span><span>Invoice</span><span>Amount</span><span>Stage</span><span>Status</span><span>Retries</span><span>Last Result</span>
                            </div>
                            {mockCases.map((c) => {
                                const stage = stageConfig[c.stage] || stageConfig.reminder;
                                const StatusIcon = statusIcons[c.status] || AlertTriangle;
                                return (
                                    <div key={c.id} className="grid grid-cols-[1.5fr_1fr_1fr_1fr_0.8fr_0.8fr_1fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                        <div>
                                            <p className="text-sm font-semibold text-white">{c.tenant}</p>
                                            <p className="text-[10px] text-white/30">{c.daysPast}d overdue</p>
                                        </div>
                                        <p className="text-xs text-white/60">{c.invoice}</p>
                                        <p className="text-sm font-bold text-white">{c.amount}</p>
                                        <Badge className={cn('border text-xs w-fit', stage.bg)}>
                                            <span className={stage.color}>{c.stage.replace('_', ' ')}</span>
                                        </Badge>
                                        <div className="flex items-center gap-1.5">
                                            <StatusIcon className={cn('h-3.5 w-3.5',
                                                c.status === 'recovered' ? 'text-emerald-400'
                                                    : c.status === 'written_off' ? 'text-slate-500'
                                                        : 'text-red-400'
                                            )} />
                                            <span className="text-xs text-white/50 capitalize">{c.status.replace('_', ' ')}</span>
                                        </div>
                                        <p className="text-xs text-white/50">{c.retries} / 4</p>
                                        <p className={cn('text-xs',
                                            c.lastResult === 'Succeeded' ? 'text-emerald-400' : 'text-red-400/70'
                                        )}>{c.lastResult}</p>
                                    </div>
                                );
                            })}
                        </div>
                    </CardContent>
                </Card>
            </motion.div>
        </div>
    );
}
