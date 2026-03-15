'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    AlertTriangle,
    Calculator,
    Globe,
    Shield,
    FileCheck,
    MapPin,
    DollarSign,
    TrendingUp,
    CheckCircle,
    Clock,
    ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// ── Mock Data ─────────────────────────────────────────────────────

const mockReport = {
    totalTax: '$3,245.62',
    totalTaxable: '$31,000.00',
    effectiveRate: '10.47%',
    exemptionsActive: 3,
};

const mockJurisdictions = [
    { id: 'us_ca', name: 'California', country: 'US', type: 'Sales Tax', rate: '8.75%', taxCollected: '$1,531.25', transactions: 4 },
    { id: 'us_ny', name: 'New York', country: 'US', type: 'Sales Tax', rate: '8.00%', taxCollected: '$576.00', transactions: 4 },
    { id: 'us_tx', name: 'Texas', country: 'US', type: 'Sales Tax', rate: '6.25%', taxCollected: '$237.50', transactions: 4 },
    { id: 'gb', name: 'United Kingdom', country: 'GB', type: 'VAT', rate: '20.00%', taxCollected: '$0.00', transactions: 0 },
    { id: 'ca_on', name: 'Ontario', country: 'CA', type: 'HST', rate: '13.00%', taxCollected: '$0.00', transactions: 0 },
    { id: 'de', name: 'Germany', country: 'DE', type: 'VAT', rate: '19.00%', taxCollected: '$0.00', transactions: 0 },
];

const mockExemptions = [
    { id: 'txe_acme_01', tenant: 'Acme Foods Inc.', jurisdiction: 'Oregon', reason: 'Reseller', cert: 'OR-RES-2025-4477', verified: true, expires: 'Aug 2026' },
    { id: 'txe_fresh_01', tenant: 'FreshLeaf Produce', jurisdiction: 'California', reason: 'Reseller', cert: 'CA-RES-2025-8891', verified: true, expires: 'Nov 2026' },
    { id: 'txe_gov_01', tenant: 'USDA Inspection Unit', jurisdiction: 'New York', reason: 'Government', cert: 'FED-GOV-0001', verified: true, expires: 'N/A' },
];

const taxTypeColors: Record<string, string> = {
    'Sales Tax': 'text-blue-400 bg-blue-500/15 border-blue-500/20',
    'VAT': 'text-violet-400 bg-violet-500/15 border-violet-500/20',
    'GST': 'text-emerald-400 bg-emerald-500/15 border-emerald-500/20',
    'HST': 'text-amber-400 bg-amber-500/15 border-amber-500/20',
};

// ── Main Dashboard ────────────────────────────────────────────────

export default function TaxDashboard() {
    const [tab, setTab] = useState<'jurisdictions' | 'exemptions'>('jurisdictions');

    return (
        <div className="p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto">
            {/* Header */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500/20 to-purple-600/20">
                            <Calculator className="h-7 w-7 text-indigo-400" />
                        </div>
                        Tax Management
                    </h1>
                    <p className="text-white/50 mt-1 ml-14">Multi-jurisdiction tax calculation, exemptions & reporting</p>
                </div>
                <Badge className="bg-indigo-500/20 text-indigo-400 border-indigo-500/30 border px-3 py-1">
                    <Globe className="h-3.5 w-3.5 mr-1.5" />
                    12 Jurisdictions
                </Badge>
            </motion.div>

            <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Demo Data — This page shows simulated data. Connect your backend to see live metrics.</span>
            </div>

            {/* KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                {[
                    { title: 'Tax Collected', value: mockReport.totalTax, sub: 'Current period', icon: DollarSign, gradient: 'from-emerald-500/20 to-teal-600/20', iconColor: 'text-emerald-400' },
                    { title: 'Taxable Revenue', value: mockReport.totalTaxable, sub: 'All jurisdictions', icon: TrendingUp, gradient: 'from-blue-500/20 to-indigo-600/20', iconColor: 'text-blue-400' },
                    { title: 'Effective Rate', value: mockReport.effectiveRate, sub: 'Weighted average', icon: Calculator, gradient: 'from-violet-500/20 to-purple-600/20', iconColor: 'text-violet-400' },
                    { title: 'Active Exemptions', value: String(mockReport.exemptionsActive), sub: 'Verified certificates', icon: Shield, gradient: 'from-amber-500/20 to-orange-600/20', iconColor: 'text-amber-400' },
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

            {/* Tabs: Jurisdictions / Exemptions */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader className="border-b border-white/10 pb-0">
                        <div className="flex gap-0">
                            {(['jurisdictions', 'exemptions'] as const).map((t) => (
                                <button
                                    key={t}
                                    onClick={() => setTab(t)}
                                    className={cn(
                                        'px-6 py-3 text-sm font-medium border-b-2 transition-all capitalize',
                                        tab === t
                                            ? 'text-white border-indigo-400'
                                            : 'text-white/40 border-transparent hover:text-white/60'
                                    )}
                                >
                                    {t}
                                </button>
                            ))}
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        {tab === 'jurisdictions' ? (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1.5fr_0.8fr_1fr_0.8fr_1fr_0.8fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Jurisdiction</span><span>Country</span><span>Tax Type</span><span>Rate</span><span>Tax Collected</span><span>Transactions</span>
                                </div>
                                {mockJurisdictions.map((j) => {
                                    const typeColor = taxTypeColors[j.type] || taxTypeColors['Sales Tax'];
                                    return (
                                        <div key={j.id} className="grid grid-cols-[1.5fr_0.8fr_1fr_0.8fr_1fr_0.8fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                            <div className="flex items-center gap-2">
                                                <MapPin className="h-3.5 w-3.5 text-white/30" />
                                                <span className="text-sm font-semibold text-white">{j.name}</span>
                                            </div>
                                            <p className="text-xs text-white/50">{j.country}</p>
                                            <Badge className={cn('border text-xs w-fit', typeColor)}>
                                                {j.type}
                                            </Badge>
                                            <p className="text-sm font-semibold text-white">{j.rate}</p>
                                            <p className={cn('text-sm', j.transactions > 0 ? 'text-emerald-400 font-semibold' : 'text-white/30')}>
                                                {j.taxCollected}
                                            </p>
                                            <p className="text-xs text-white/50">{j.transactions}</p>
                                        </div>
                                    );
                                })}
                            </div>
                        ) : (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1.5fr_1fr_1fr_1.2fr_0.8fr_0.8fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Tenant</span><span>Jurisdiction</span><span>Reason</span><span>Certificate</span><span>Verified</span><span>Expires</span>
                                </div>
                                {mockExemptions.map((ex) => (
                                    <div key={ex.id} className="grid grid-cols-[1.5fr_1fr_1fr_1.2fr_0.8fr_0.8fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                        <p className="text-sm font-semibold text-white">{ex.tenant}</p>
                                        <p className="text-sm text-white/60">{ex.jurisdiction}</p>
                                        <Badge className="bg-white/5 text-white/60 border-white/10 border text-xs w-fit capitalize">{ex.reason}</Badge>
                                        <p className="text-xs text-white/40 font-mono">{ex.cert}</p>
                                        <div className="flex items-center gap-1.5">
                                            {ex.verified ? (
                                                <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
                                            ) : (
                                                <Clock className="h-3.5 w-3.5 text-amber-400" />
                                            )}
                                            <span className={cn('text-xs', ex.verified ? 'text-emerald-400' : 'text-amber-400')}>
                                                {ex.verified ? 'Verified' : 'Pending'}
                                            </span>
                                        </div>
                                        <p className="text-xs text-white/50">{ex.expires}</p>
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
