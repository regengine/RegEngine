'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    AlertTriangle,
    Handshake,
    Users,
    DollarSign,
    Award,
    TrendingUp,
    ArrowUpRight,
    ChevronRight,
    Star,
    Clock,
    CheckCircle,
    Send,
    UserPlus,
    Gem,
    Crown,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// ── Mock Data ─────────────────────────────────────────────────────

const mockSummary = {
    totalPartners: 4,
    activePartners: 4,
    totalReferrals: 37,
    activeReferrals: 29,
    totalEarned: '$14,430.00',
    totalPaid: '$12,060.00',
    pendingPayouts: '$2,370.00',
    partnerSourcedRevenue: '$9,100.00',
};

const mockPartners = [
    { id: 'ptr_compliance01', name: 'Jordan Mitchell', company: 'CompliancePro Consulting', tier: 'platinum', referrals: 18, active: 14, earned: '$8,640.00', pending: '$1,440.00', rate: '20%', code: 'COMPRO20', lastReferral: '8d ago' },
    { id: 'ptr_foodsafe02', name: 'Emily Chen', company: 'FoodSafe Solutions', tier: 'gold', referrals: 9, active: 7, earned: '$3,150.00', pending: '$450.00', rate: '15%', code: 'FSAFE15', lastReferral: '22d ago' },
    { id: 'ptr_regadv04', name: 'Sarah Park', company: 'RegAdvisory Group', tier: 'gold', referrals: 7, active: 5, earned: '$2,100.00', pending: '$300.00', rate: '15%', code: 'REGADV15', lastReferral: '15d ago' },
    { id: 'ptr_techint03', name: 'Marcus Williams', company: 'TechIntegrations LLC', tier: 'silver', referrals: 3, active: 3, earned: '$540.00', pending: '$180.00', rate: '10%', code: 'TECH10', lastReferral: '45d ago' },
];

const mockReferrals = [
    { partner: 'CompliancePro', tenant: 'Acme Foods Inc.', tier: 'Enterprise', monthly: '$5,000', commission: '$1,000', date: 'Aug 2025' },
    { partner: 'CompliancePro', tenant: 'FreshLeaf Produce', tier: 'Scale', monthly: '$1,500', commission: '$300', date: 'Nov 2025' },
    { partner: 'FoodSafe Solutions', tenant: 'MedSecure Health', tier: 'Scale', monthly: '$1,800', commission: '$270', date: 'Oct 2025' },
    { partner: 'TechIntegrations', tenant: 'EnergyFlow Corp', tier: 'Growth', monthly: '$800', commission: '$80', date: 'Dec 2025' },
];

const mockPayouts = [
    { id: 'po_001', partner: 'CompliancePro Consulting', amount: '$2,400.00', status: 'paid', period: 'Dec 2025', paidDate: 'Jan 5' },
    { id: 'po_002', partner: 'FoodSafe Solutions', amount: '$900.00', status: 'paid', period: 'Dec 2025', paidDate: 'Jan 5' },
    { id: 'po_003', partner: 'CompliancePro Consulting', amount: '$1,440.00', status: 'pending', period: 'Jan 2026', paidDate: '' },
];

const tierConfig: Record<string, { icon: React.ElementType; color: string; bg: string; gradient: string }> = {
    platinum: { icon: Crown, color: 'text-violet-400', bg: 'bg-violet-500/15 border-violet-500/20', gradient: 'from-violet-500/20 to-purple-600/20' },
    gold: { icon: Gem, color: 'text-amber-400', bg: 'bg-amber-500/15 border-amber-500/20', gradient: 'from-amber-500/20 to-orange-600/20' },
    silver: { icon: Star, color: 'text-slate-400', bg: 'bg-slate-500/15 border-slate-500/20', gradient: 'from-slate-400/20 to-slate-500/20' },
};

// ── Main Dashboard ────────────────────────────────────────────────

export default function PartnersDashboard() {
    const [tab, setTab] = useState<'partners' | 'referrals' | 'payouts'>('partners');

    return (
        <div className="p-8 max-w-[1600px] mx-auto">
            {/* Header */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-gradient-to-br from-rose-500/20 to-pink-600/20">
                            <Handshake className="h-7 w-7 text-rose-400" />
                        </div>
                        Partner Portal
                    </h1>
                    <p className="text-white/50 mt-1 ml-14">Channel partners, referrals, commissions & payouts</p>
                </div>
                <Button variant="outline" size="sm" className="bg-rose-500/10 border-rose-500/30 text-rose-400 hover:bg-rose-500/20">
                    <UserPlus className="h-4 w-4 mr-2" />
                    Invite Partner
                </Button>
            </motion.div>

            <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Demo Data — This page shows simulated data. Connect your backend to see live metrics.</span>
            </div>

            {/* KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                {[
                    { title: 'Active Partners', value: String(mockSummary.activePartners), sub: `${mockSummary.totalReferrals} total referrals`, icon: Users, gradient: 'from-rose-500/20 to-pink-600/20', iconColor: 'text-rose-400' },
                    { title: 'Partner Revenue', value: mockSummary.partnerSourcedRevenue, sub: `${mockSummary.activeReferrals} active accounts`, icon: TrendingUp, gradient: 'from-emerald-500/20 to-teal-600/20', iconColor: 'text-emerald-400' },
                    { title: 'Commissions Paid', value: mockSummary.totalPaid, sub: mockSummary.totalEarned + ' total earned', icon: DollarSign, gradient: 'from-blue-500/20 to-indigo-600/20', iconColor: 'text-blue-400' },
                    { title: 'Pending Payouts', value: mockSummary.pendingPayouts, sub: 'Next cycle: Feb 1', icon: Clock, gradient: 'from-amber-500/20 to-orange-600/20', iconColor: 'text-amber-400' },
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

            {/* Commission Tiers */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="mb-6">
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader className="border-b border-white/10 pb-4">
                        <CardTitle className="text-white flex items-center gap-2">
                            <Award className="h-4 w-4 text-amber-400" />
                            Commission Tiers
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-4">
                        <div className="grid grid-cols-3 gap-4">
                            {[
                                { tier: 'Silver', rate: '10%', min: '0+', bonus: '—', partners: 1, color: 'text-slate-400', gradient: 'from-slate-400/10 to-slate-500/10', border: 'border-slate-500/20' },
                                { tier: 'Gold', rate: '15%', min: '5+', bonus: '+2% bonus', partners: 2, color: 'text-amber-400', gradient: 'from-amber-400/10 to-amber-500/10', border: 'border-amber-500/20' },
                                { tier: 'Platinum', rate: '20%', min: '15+', bonus: '+5% bonus', partners: 1, color: 'text-violet-400', gradient: 'from-violet-400/10 to-violet-500/10', border: 'border-violet-500/20' },
                            ].map((t) => (
                                <div key={t.tier} className={cn('p-4 rounded-lg border bg-gradient-to-br', t.gradient, t.border)}>
                                    <div className="flex items-center justify-between mb-2">
                                        <span className={cn('text-sm font-bold', t.color)}>{t.tier}</span>
                                        <span className={cn('text-xl font-bold', t.color)}>{t.rate}</span>
                                    </div>
                                    <p className="text-xs text-white/40">Min {t.min} referrals · {t.bonus}</p>
                                    <p className="text-[10px] text-white/30 mt-1">{t.partners} partner{t.partners !== 1 ? 's' : ''}</p>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* Tabs: Partners / Referrals / Payouts */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}>
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader className="border-b border-white/10 pb-0">
                        <div className="flex gap-0">
                            {(['partners', 'referrals', 'payouts'] as const).map((t) => (
                                <button
                                    key={t}
                                    onClick={() => setTab(t)}
                                    className={cn(
                                        'px-6 py-3 text-sm font-medium border-b-2 transition-all capitalize',
                                        tab === t
                                            ? 'text-white border-rose-400'
                                            : 'text-white/40 border-transparent hover:text-white/60'
                                    )}
                                >
                                    {t}
                                </button>
                            ))}
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        {tab === 'partners' && (
                            <div className="divide-y divide-white/5">
                                {mockPartners.map((partner) => {
                                    const cfg = tierConfig[partner.tier] || tierConfig.silver;
                                    const TierIcon = cfg.icon;
                                    return (
                                        <div key={partner.id} className="p-4 hover:bg-white/5 transition-colors">
                                            <div className="flex items-start justify-between mb-3">
                                                <div className="flex items-center gap-3">
                                                    <div className={cn('p-2 rounded-lg bg-gradient-to-br', cfg.gradient)}>
                                                        <TierIcon className={cn('h-4 w-4', cfg.color)} />
                                                    </div>
                                                    <div>
                                                        <p className="text-sm font-semibold text-white">{partner.name}</p>
                                                        <p className="text-xs text-white/40">{partner.company}</p>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <Badge className={cn('border text-xs', cfg.bg)}>
                                                        <span className={cfg.color}>{partner.tier} · {partner.rate}</span>
                                                    </Badge>
                                                    <Badge className="bg-white/5 text-white/50 border-white/10 border text-[10px]">
                                                        {partner.code}
                                                    </Badge>
                                                </div>
                                            </div>
                                            <div className="grid grid-cols-5 gap-4 ml-11">
                                                <div><p className="text-[10px] text-white/40">Referrals</p><p className="text-sm font-semibold text-white">{partner.active}/{partner.referrals}</p></div>
                                                <div><p className="text-[10px] text-white/40">Earned</p><p className="text-sm font-semibold text-white">{partner.earned}</p></div>
                                                <div><p className="text-[10px] text-white/40">Pending</p><p className="text-sm font-semibold text-amber-400">{partner.pending}</p></div>
                                                <div><p className="text-[10px] text-white/40">Last Referral</p><p className="text-sm text-white/60">{partner.lastReferral}</p></div>
                                                <div className="flex items-end justify-end">
                                                    <Button variant="ghost" size="sm" className="text-white/30 hover:text-white">
                                                        <ChevronRight className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {tab === 'referrals' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1.5fr_1.5fr_1fr_1fr_1fr_0.8fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Partner</span><span>Referred Customer</span><span>Tier</span><span>Monthly</span><span>Commission</span><span>Date</span>
                                </div>
                                {mockReferrals.map((ref, i) => (
                                    <div key={i} className="grid grid-cols-[1.5fr_1.5fr_1fr_1fr_1fr_0.8fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                        <p className="text-sm text-white/80">{ref.partner}</p>
                                        <p className="text-sm font-semibold text-white">{ref.tenant}</p>
                                        <Badge className="bg-white/5 text-white/60 border-white/10 border text-xs w-fit">{ref.tier}</Badge>
                                        <p className="text-sm text-white/60">{ref.monthly}/mo</p>
                                        <p className="text-sm font-semibold text-emerald-400">{ref.commission}/mo</p>
                                        <p className="text-xs text-white/40">{ref.date}</p>
                                    </div>
                                ))}
                            </div>
                        )}

                        {tab === 'payouts' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Partner</span><span>Amount</span><span>Period</span><span>Status</span><span>Paid Date</span>
                                </div>
                                {mockPayouts.map((po) => (
                                    <div key={po.id} className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                        <p className="text-sm font-semibold text-white">{po.partner}</p>
                                        <p className="text-sm font-semibold text-white">{po.amount}</p>
                                        <p className="text-xs text-white/50">{po.period}</p>
                                        <Badge className={cn('border text-xs w-fit',
                                            po.status === 'paid'
                                                ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
                                                : 'bg-amber-500/15 text-amber-400 border-amber-500/20'
                                        )}>
                                            {po.status === 'paid' ? <CheckCircle className="h-3 w-3 mr-1" /> : <Clock className="h-3 w-3 mr-1" />}
                                            {po.status}
                                        </Badge>
                                        <p className="text-xs text-white/50">{po.paidDate || '—'}</p>
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
