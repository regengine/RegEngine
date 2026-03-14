'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    FileSignature,
    Users,
    DollarSign,
    Shield,
    Calendar,
    ArrowRight,
    AlertTriangle,
    CheckCircle,
    Clock,
    ChevronRight,
    TrendingUp,
    RefreshCw,
    Target,
    Award,
    Briefcase,
    Timer,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// ── Mock Data ─────────────────────────────────────────────────────

const mockPipeline = {
    stages: [
        {
            key: 'draft', label: 'Draft', color: 'from-slate-500/30 to-slate-600/30',
            textColor: 'text-slate-300', badgeClass: 'bg-slate-500/15 text-slate-400 border-slate-500/20',
            deals: [
                { id: 'ctr_harvest005', name: 'Harvest Table Foods', tier: 'Enterprise', acv: '$120,000', owner: 'Sarah', daysInStage: 5 },
            ],
        },
        {
            key: 'proposed', label: 'Proposed', color: 'from-blue-500/30 to-blue-600/30',
            textColor: 'text-blue-300', badgeClass: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
            deals: [
                { id: 'ctr_riverbend004', name: 'Riverbend Packers', tier: 'Growth', acv: '$9,588', owner: 'James', daysInStage: 12 },
            ],
        },
        {
            key: 'negotiating', label: 'Negotiating', color: 'from-amber-500/30 to-amber-600/30',
            textColor: 'text-amber-300', badgeClass: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
            deals: [
                { id: 'ctr_freshleaf003', name: 'FreshLeaf Produce', tier: 'Scale', acv: '$60,000', owner: 'Sarah', daysInStage: 18 },
            ],
        },
        {
            key: 'approved', label: 'Approved', color: 'from-emerald-500/30 to-emerald-600/30',
            textColor: 'text-emerald-300', badgeClass: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
            deals: [
                { id: 'ctr_fresh006', name: 'FreshLeaf Produce', tier: 'Scale', acv: '$95,000', owner: 'James', daysInStage: 3 },
            ],
        },
    ],
    total_pipeline_value: '$164,588',
    weighted_value: '$57,606',
};

const mockActiveContracts = [
    { id: 'ctr_acme001', name: 'Acme Foods Inc.', tier: 'Enterprise', acv: '$150,000', tcv: '$450,000', termYears: 3, slaLevel: 'Premium', startDate: 'Aug 2025', renewalDate: 'Jun 2028', daysToRenewal: 885, compliance: 'passing' },
    { id: 'ctr_northstar002', name: 'Northstar Cold Chain', tier: 'Scale', acv: '$180,000', tcv: '$360,000', termYears: 2, slaLevel: 'Enterprise', startDate: 'Nov 2025', renewalDate: 'Sep 2027', daysToRenewal: 610, compliance: 'passing' },
];

const mockSLAStatuses = [
    { contractId: 'ctr_acme001', tenant: 'Acme Foods Inc.', slaLevel: 'Premium', uptimeTarget: 99.99, uptimeActual: 99.97, responseTarget: 1, responseActual: 1.5, resolutionTarget: 4, resolutionActual: 3.2, compliance: 'breached', breaches: [{ metric: 'response_time', target: '1h', actual: '1.5h', severity: 'warning' }] },
    { contractId: 'ctr_northstar002', tenant: 'Northstar Cold Chain', slaLevel: 'Enterprise', uptimeTarget: 99.95, uptimeActual: 99.97, responseTarget: 2, responseActual: 1.5, resolutionTarget: 8, resolutionActual: 3.2, compliance: 'passing', breaches: [] },
];

const mockRenewals = [
    { contractId: 'ctr_northstar002', tenant: 'Northstar Cold Chain', tier: 'Scale', acv: '$180,000', renewalDate: '2027-09-20', daysUntil: 610, urgency: 'upcoming', owner: 'James' },
    { contractId: 'ctr_acme001', tenant: 'Acme Foods Inc.', tier: 'Enterprise', acv: '$150,000', renewalDate: '2028-06-15', daysUntil: 885, urgency: 'upcoming', owner: 'Sarah' },
];

// ── Helper Components ─────────────────────────────────────────────

function StatCard({ title, value, subtitle, icon: Icon, delay = 0, gradient, iconColor }: {
    title: string; value: string; subtitle?: string; icon: React.ElementType;
    delay?: number; gradient: string; iconColor: string;
}) {
    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.4 }}>
            <Card className="bg-white/5 backdrop-blur-xl border-white/10 hover:bg-white/8 transition-all group">
                <CardContent className="p-5">
                    <div className="flex items-start justify-between">
                        <div className="space-y-1">
                            <p className="text-xs font-medium text-white/50 uppercase tracking-wider">{title}</p>
                            <p className="text-2xl font-bold text-white">{value}</p>
                            {subtitle && <p className="text-xs text-white/40">{subtitle}</p>}
                        </div>
                        <div className={cn('p-2.5 rounded-xl bg-gradient-to-br', gradient, 'group-hover:scale-110 transition-transform')}>
                            <Icon className={cn('h-5 w-5', iconColor)} />
                        </div>
                    </div>
                </CardContent>
            </Card>
        </motion.div>
    );
}

interface Deal {
    id: string;
    name: string;
    tier: string;
    acv: string;
    owner: string;
    daysInStage: number;
}

function DealCard({ deal, stageColor }: { deal: Deal; stageColor: string }) {
    return (
        <div className="p-3 rounded-lg bg-white/5 border border-white/10 hover:bg-white/8 transition-all group cursor-pointer">
            <div className="flex items-start justify-between mb-2">
                <p className="text-sm font-semibold text-white truncate">{deal.name}</p>
                <Badge className="bg-white/10 text-white/70 border-white/10 border text-[10px] shrink-0 ml-2">
                    {deal.tier}
                </Badge>
            </div>
            <div className="flex items-center justify-between">
                <span className="text-lg font-bold text-white">{deal.acv}</span>
                <span className="text-[10px] text-white/40">{deal.owner} · {deal.daysInStage}d</span>
            </div>
        </div>
    );
}


// ── Main Dashboard ────────────────────────────────────────────────

export default function ContractsDashboard() {
    const [isRefreshing, setIsRefreshing] = useState(false);

    const handleRefresh = () => {
        setIsRefreshing(true);
        setTimeout(() => setIsRefreshing(false), 1500);
    };

    return (
        <div className="p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto">
            {/* Header */}
            <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8"
            >
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500/20 to-purple-600/20">
                            <FileSignature className="h-7 w-7 text-indigo-400" />
                        </div>
                        Enterprise Deals
                    </h1>
                    <p className="text-white/50 mt-1 ml-14">Contract lifecycle, pipeline, SLA tracking & renewals</p>
                </div>
                <div className="flex items-center gap-3">
                    <Badge className="bg-indigo-500/20 text-indigo-400 border-indigo-500/30 border px-3 py-1">
                        <Briefcase className="h-3.5 w-3.5 mr-1.5" />
                        6 Active Deals
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

            <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Demo Data — This page shows simulated data. Connect your backend to see live metrics.</span>
            </div>

            {/* KPI Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <StatCard
                    title="Pipeline Value" value={mockPipeline.total_pipeline_value}
                    subtitle="4 deals in pipeline" icon={Target} delay={0}
                    gradient="from-indigo-500/20 to-purple-600/20" iconColor="text-indigo-400"
                />
                <StatCard
                    title="Weighted Pipeline" value={mockPipeline.weighted_value}
                    subtitle="35% weighted avg" icon={TrendingUp} delay={0.05}
                    gradient="from-emerald-500/20 to-teal-600/20" iconColor="text-emerald-400"
                />
                <StatCard
                    title="Active ACV" value="$330,000"
                    subtitle="2 active contracts" icon={DollarSign} delay={0.1}
                    gradient="from-amber-500/20 to-orange-600/20" iconColor="text-amber-400"
                />
                <StatCard
                    title="SLA Compliance" value="50%"
                    subtitle="1 breach detected" icon={Shield} delay={0.15}
                    gradient="from-red-500/20 to-rose-600/20" iconColor="text-red-400"
                />
            </div>

            {/* Deal Pipeline */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="mb-6"
            >
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader className="border-b border-white/10 pb-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-white">Deal Pipeline</CardTitle>
                                <CardDescription className="text-white/50">Drag deals through stages — Draft → Proposed → Negotiating → Approved</CardDescription>
                            </div>
                            <div className="flex gap-2">
                                {mockPipeline.stages.map((stage) => (
                                    <Badge key={stage.key} className={cn('border text-xs', stage.badgeClass)}>
                                        {stage.deals.length}
                                    </Badge>
                                ))}
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent className="p-4">
                        <div className="grid grid-cols-4 gap-4">
                            {mockPipeline.stages.map((stage) => (
                                <div key={stage.key} className="space-y-3">
                                    {/* Stage Header */}
                                    <div className={cn('flex items-center gap-2 p-2 rounded-lg bg-gradient-to-r', stage.color)}>
                                        <span className={cn('text-xs font-semibold uppercase tracking-wider', stage.textColor)}>
                                            {stage.label}
                                        </span>
                                        <Badge className={cn('border text-[10px] ml-auto', stage.badgeClass)}>
                                            {stage.deals.length}
                                        </Badge>
                                    </div>
                                    {/* Deal Cards */}
                                    {stage.deals.map((deal) => (
                                        <DealCard key={deal.id} deal={deal} stageColor={stage.color} />
                                    ))}
                                    {stage.deals.length === 0 && (
                                        <div className="p-4 text-center text-xs text-white/20 border border-dashed border-white/10 rounded-lg">
                                            No deals
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* Active Contracts + SLA Monitor */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                {/* Active Contracts */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
                    <Card className="bg-white/5 backdrop-blur-xl border-white/10 h-full">
                        <CardHeader className="border-b border-white/10 pb-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="text-white flex items-center gap-2">
                                        <Award className="h-4 w-4 text-amber-400" />
                                        Active Contracts
                                    </CardTitle>
                                    <CardDescription className="text-white/50">Enterprise agreements in force</CardDescription>
                                </div>
                                <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/20 border text-xs">
                                    {mockActiveContracts.length} active
                                </Badge>
                            </div>
                        </CardHeader>
                        <CardContent className="p-0">
                            <div className="divide-y divide-white/5">
                                {mockActiveContracts.map((contract) => (
                                    <div key={contract.id} className="p-4 hover:bg-white/5 transition-colors">
                                        <div className="flex items-start justify-between mb-2">
                                            <div>
                                                <p className="text-sm font-semibold text-white">{contract.name}</p>
                                                <p className="text-xs text-white/40">{contract.tier} · {contract.termYears}-year term</p>
                                            </div>
                                            <Badge className={cn(
                                                'border text-[10px]',
                                                contract.compliance === 'passing'
                                                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
                                                    : 'bg-red-500/15 text-red-400 border-red-500/20'
                                            )}>
                                                {contract.slaLevel} SLA
                                            </Badge>
                                        </div>
                                        <div className="grid grid-cols-3 gap-3 mt-3">
                                            <div>
                                                <p className="text-[10px] text-white/40 uppercase">ACV</p>
                                                <p className="text-sm font-semibold text-white">{contract.acv}</p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] text-white/40 uppercase">TCV</p>
                                                <p className="text-sm font-semibold text-white">{contract.tcv}</p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] text-white/40 uppercase">Renewal</p>
                                                <p className="text-sm font-semibold text-white">{contract.renewalDate}</p>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* SLA Monitor */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
                    <Card className="bg-white/5 backdrop-blur-xl border-white/10 h-full">
                        <CardHeader className="border-b border-white/10 pb-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="text-white flex items-center gap-2">
                                        <Shield className="h-4 w-4 text-blue-400" />
                                        SLA Compliance
                                    </CardTitle>
                                    <CardDescription className="text-white/50">Real-time SLA monitoring for active contracts</CardDescription>
                                </div>
                                <div className="flex gap-2">
                                    <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/20 border text-xs">
                                        1 passing
                                    </Badge>
                                    <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/20 border text-xs">
                                        1 warning
                                    </Badge>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="p-0">
                            <div className="divide-y divide-white/5">
                                {mockSLAStatuses.map((sla) => (
                                    <div key={sla.contractId} className="p-4 hover:bg-white/5 transition-colors">
                                        <div className="flex items-center justify-between mb-3">
                                            <div>
                                                <p className="text-sm font-semibold text-white">{sla.tenant}</p>
                                                <p className="text-xs text-white/40">{sla.slaLevel} SLA</p>
                                            </div>
                                            <Badge className={cn(
                                                'border text-xs',
                                                sla.compliance === 'passing'
                                                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
                                                    : 'bg-amber-500/15 text-amber-400 border-amber-500/20'
                                            )}>
                                                {sla.compliance === 'passing' ? (
                                                    <><CheckCircle className="h-3 w-3 mr-1" /> Passing</>
                                                ) : (
                                                    <><AlertTriangle className="h-3 w-3 mr-1" /> Warning</>
                                                )}
                                            </Badge>
                                        </div>
                                        <div className="grid grid-cols-3 gap-3">
                                            {/* Uptime */}
                                            <div className="p-2 rounded-lg bg-white/5">
                                                <p className="text-[10px] text-white/40 mb-1">Uptime</p>
                                                <p className={cn('text-sm font-mono font-semibold',
                                                    sla.uptimeActual >= sla.uptimeTarget ? 'text-emerald-400' : 'text-red-400'
                                                )}>
                                                    {sla.uptimeActual}%
                                                </p>
                                                <p className="text-[9px] text-white/30">target: {sla.uptimeTarget}%</p>
                                            </div>
                                            {/* Response Time */}
                                            <div className="p-2 rounded-lg bg-white/5">
                                                <p className="text-[10px] text-white/40 mb-1">Response</p>
                                                <p className={cn('text-sm font-mono font-semibold',
                                                    sla.responseActual <= sla.responseTarget ? 'text-emerald-400' : 'text-amber-400'
                                                )}>
                                                    {sla.responseActual}h
                                                </p>
                                                <p className="text-[9px] text-white/30">target: {sla.responseTarget}h</p>
                                            </div>
                                            {/* Resolution Time */}
                                            <div className="p-2 rounded-lg bg-white/5">
                                                <p className="text-[10px] text-white/40 mb-1">Resolution</p>
                                                <p className={cn('text-sm font-mono font-semibold',
                                                    sla.resolutionActual <= sla.resolutionTarget ? 'text-emerald-400' : 'text-red-400'
                                                )}>
                                                    {sla.resolutionActual}h
                                                </p>
                                                <p className="text-[9px] text-white/30">target: {sla.resolutionTarget}h</p>
                                            </div>
                                        </div>
                                        {sla.breaches.length > 0 && (
                                            <div className="mt-2 p-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
                                                <p className="text-[10px] text-amber-400 font-medium">
                                                    ⚠ {sla.breaches[0].metric}: {sla.breaches[0].actual} (target: {sla.breaches[0].target})
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            </div>

            {/* Renewal Calendar */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader className="border-b border-white/10 pb-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-white flex items-center gap-2">
                                    <Calendar className="h-4 w-4 text-purple-400" />
                                    Renewal Calendar
                                </CardTitle>
                                <CardDescription className="text-white/50">Contracts approaching renewal — plan retention strategy</CardDescription>
                            </div>
                            <Badge className="bg-purple-500/15 text-purple-400 border-purple-500/20 border text-xs">
                                $330,000 ACV at stake
                            </Badge>
                        </div>
                    </CardHeader>
                    <CardContent className="p-4">
                        <div className="space-y-3">
                            {mockRenewals.map((renewal) => {
                                const urgencyColors: Record<string, { bg: string; text: string; badge: string }> = {
                                    critical: { bg: 'bg-red-500/10', text: 'text-red-400', badge: 'bg-red-500/15 text-red-400 border-red-500/20' },
                                    warning: { bg: 'bg-amber-500/10', text: 'text-amber-400', badge: 'bg-amber-500/15 text-amber-400 border-amber-500/20' },
                                    upcoming: { bg: 'bg-blue-500/10', text: 'text-blue-400', badge: 'bg-blue-500/15 text-blue-400 border-blue-500/20' },
                                };
                                const colors = urgencyColors[renewal.urgency] || urgencyColors.upcoming;

                                return (
                                    <div key={renewal.contractId} className={cn('p-4 rounded-lg border border-white/10 flex items-center justify-between hover:bg-white/5 transition-colors', colors.bg)}>
                                        <div className="flex items-center gap-4">
                                            <div className="p-2 rounded-lg bg-white/5">
                                                <Timer className={cn('h-5 w-5', colors.text)} />
                                            </div>
                                            <div>
                                                <p className="text-sm font-semibold text-white">{renewal.tenant}</p>
                                                <p className="text-xs text-white/40">{renewal.tier} · {renewal.owner} · Renews {renewal.renewalDate}</p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-4">
                                            <div className="text-right">
                                                <p className="text-lg font-bold text-white">{renewal.acv}</p>
                                                <p className="text-[10px] text-white/40">annual value</p>
                                            </div>
                                            <div className="text-right min-w-[60px]">
                                                <Badge className={cn('border text-xs', colors.badge)}>
                                                    {renewal.daysUntil}d
                                                </Badge>
                                            </div>
                                            <Button variant="ghost" size="sm" className="text-white/50 hover:text-white">
                                                <ChevronRight className="h-4 w-4" />
                                            </Button>
                                        </div>
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
