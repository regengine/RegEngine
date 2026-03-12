'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    Receipt,
    DollarSign,
    Clock,
    CheckCircle,
    AlertTriangle,
    XCircle,
    CreditCard,
    TrendingUp,
    ArrowUpRight,
    ChevronRight,
    RefreshCw,
    FileText,
    Send,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// ── Mock Data ─────────────────────────────────────────────────────

const mockRevenueSummary = {
    totalCollected: '$54,312.78',
    totalInvoiced: '$72,890.45',
    totalOutstanding: '$18,577.67',
    collectionRate: 72.7,
    invoicesPaid: 8,
    invoicesTotal: 11,
    paymentsCount: 8,
};

const mockAgingBuckets = [
    { label: 'Current', amount: '$0.00', count: 0, color: 'text-emerald-400', bg: 'bg-emerald-500/15' },
    { label: '1-30 days', amount: '$9,288.34', count: 2, color: 'text-blue-400', bg: 'bg-blue-500/15' },
    { label: '31-60 days', amount: '$6,124.50', count: 1, color: 'text-amber-400', bg: 'bg-amber-500/15' },
    { label: '61-90 days', amount: '$3,164.83', count: 1, color: 'text-orange-400', bg: 'bg-orange-500/15' },
    { label: '90+ days', amount: '$0.00', count: 0, color: 'text-red-400', bg: 'bg-red-500/15' },
];

const mockInvoices = [
    { id: 'inv_seed_0005', number: 'INV-2026-1006', tenant: 'Acme Foods Inc.', amount: '$6,528.13', status: 'sent', issueDate: 'Jan 10', dueDate: 'Feb 09', tier: 'Enterprise' },
    { id: 'inv_seed_0008', number: 'INV-2026-1009', tenant: 'Northstar Cold Chain', amount: '$12,049.55', status: 'overdue', issueDate: 'Dec 11', dueDate: 'Jan 10', tier: 'Scale' },
    { id: 'inv_seed_0010', number: 'INV-2026-1011', tenant: 'Harvest Table Foods', amount: '$3,289.84', status: 'sent', issueDate: 'Jan 10', dueDate: 'Feb 09', tier: 'Growth' },
    { id: 'inv_seed_0004', number: 'INV-2026-1005', tenant: 'Acme Foods Inc.', amount: '$7,612.50', status: 'paid', issueDate: 'Dec 11', dueDate: 'Jan 10', paidDate: 'Dec 23', tier: 'Enterprise' },
    { id: 'inv_seed_0007', number: 'INV-2026-1008', tenant: 'Northstar Cold Chain', amount: '$10,478.25', status: 'paid', issueDate: 'Nov 11', dueDate: 'Dec 11', paidDate: 'Nov 23', tier: 'Scale' },
    { id: 'inv_seed_0003', number: 'INV-2026-1004', tenant: 'Acme Foods Inc.', amount: '$8,415.00', status: 'paid', issueDate: 'Nov 11', dueDate: 'Dec 11', paidDate: 'Nov 23', tier: 'Enterprise' },
];

const mockPayments = [
    { id: 'pay_seed_0004', invoice: 'INV-2026-1005', tenant: 'Acme Foods Inc.', amount: '$7,612.50', method: 'Visa •4242', date: 'Dec 23, 2025', status: 'succeeded' },
    { id: 'pay_seed_0007', invoice: 'INV-2026-1008', tenant: 'Northstar Cold Chain', amount: '$10,478.25', method: 'MC •8888', date: 'Nov 23, 2025', status: 'succeeded' },
    { id: 'pay_seed_0003', invoice: 'INV-2026-1004', tenant: 'Acme Foods Inc.', amount: '$8,415.00', method: 'Amex •3782', date: 'Nov 23, 2025', status: 'succeeded' },
    { id: 'pay_seed_0006', invoice: 'INV-2026-1007', tenant: 'Northstar Cold Chain', amount: '$5,812.50', method: 'Visa •4242', date: 'Oct 23, 2025', status: 'succeeded' },
];

const statusConfig: Record<string, { color: string; bg: string; icon: React.ElementType }> = {
    paid: { color: 'text-emerald-400', bg: 'bg-emerald-500/15 border-emerald-500/20', icon: CheckCircle },
    sent: { color: 'text-blue-400', bg: 'bg-blue-500/15 border-blue-500/20', icon: Send },
    overdue: { color: 'text-red-400', bg: 'bg-red-500/15 border-red-500/20', icon: AlertTriangle },
    draft: { color: 'text-slate-400', bg: 'bg-slate-500/15 border-slate-500/20', icon: FileText },
    void: { color: 'text-slate-500', bg: 'bg-slate-600/15 border-slate-600/20', icon: XCircle },
};

// ── Main Dashboard ────────────────────────────────────────────────

export default function InvoicesDashboard() {
    const [tab, setTab] = useState<'invoices' | 'payments'>('invoices');

    return (
        <div className="p-8 max-w-[1600px] mx-auto">
            {/* Header */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-gradient-to-br from-teal-500/20 to-cyan-600/20">
                            <Receipt className="h-7 w-7 text-teal-400" />
                        </div>
                        Billing & Payments
                    </h1>
                    <p className="text-white/50 mt-1 ml-14">Invoices, payment history, and accounts receivable</p>
                </div>
                <Badge className="bg-teal-500/20 text-teal-400 border-teal-500/30 border px-3 py-1">
                    <CreditCard className="h-3.5 w-3.5 mr-1.5" />
                    11 Total Invoices
                </Badge>
            </motion.div>

            <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Demo Data — This page shows simulated data. Connect your backend to see live metrics.</span>
            </div>

            {/* Revenue KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                {[
                    { title: 'Collected', value: mockRevenueSummary.totalCollected, sub: `${mockRevenueSummary.paymentsCount} payments`, icon: DollarSign, gradient: 'from-emerald-500/20 to-teal-600/20', iconColor: 'text-emerald-400' },
                    { title: 'Total Invoiced', value: mockRevenueSummary.totalInvoiced, sub: `${mockRevenueSummary.invoicesTotal} invoices`, icon: FileText, gradient: 'from-blue-500/20 to-indigo-600/20', iconColor: 'text-blue-400' },
                    { title: 'Outstanding', value: mockRevenueSummary.totalOutstanding, sub: '3 unpaid invoices', icon: Clock, gradient: 'from-amber-500/20 to-orange-600/20', iconColor: 'text-amber-400' },
                    { title: 'Collection Rate', value: `${mockRevenueSummary.collectionRate}%`, sub: `${mockRevenueSummary.invoicesPaid}/${mockRevenueSummary.invoicesTotal} paid`, icon: TrendingUp, gradient: 'from-violet-500/20 to-purple-600/20', iconColor: 'text-violet-400' },
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

            {/* Accounts Receivable Aging */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="mb-6">
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader className="border-b border-white/10 pb-4">
                        <CardTitle className="text-white flex items-center gap-2">
                            <Clock className="h-4 w-4 text-amber-400" />
                            Accounts Receivable Aging
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-4">
                        <div className="grid grid-cols-5 gap-3">
                            {mockAgingBuckets.map((bucket) => (
                                <div key={bucket.label} className={cn('p-4 rounded-lg border border-white/10 text-center', bucket.bg)}>
                                    <p className="text-xs text-white/50 mb-1">{bucket.label}</p>
                                    <p className={cn('text-lg font-bold', bucket.color)}>{bucket.amount}</p>
                                    <p className="text-[10px] text-white/30 mt-1">{bucket.count} invoice{bucket.count !== 1 ? 's' : ''}</p>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* Tabs: Invoices / Payments */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}>
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader className="border-b border-white/10 pb-0">
                        <div className="flex gap-0">
                            {(['invoices', 'payments'] as const).map((t) => (
                                <button
                                    key={t}
                                    onClick={() => setTab(t)}
                                    className={cn(
                                        'px-6 py-3 text-sm font-medium border-b-2 transition-all capitalize',
                                        tab === t
                                            ? 'text-white border-teal-400'
                                            : 'text-white/40 border-transparent hover:text-white/60'
                                    )}
                                >
                                    {t}
                                </button>
                            ))}
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        {tab === 'invoices' ? (
                            <div className="divide-y divide-white/5">
                                {/* Header */}
                                <div className="grid grid-cols-[2fr_1.5fr_1fr_1fr_1fr_0.5fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Invoice</span><span>Customer</span><span>Amount</span><span>Status</span><span>Due Date</span><span></span>
                                </div>
                                {mockInvoices.map((inv) => {
                                    const cfg = statusConfig[inv.status] || statusConfig.draft;
                                    const StatusIcon = cfg.icon;
                                    return (
                                        <div key={inv.id} className="grid grid-cols-[2fr_1.5fr_1fr_1fr_1fr_0.5fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                            <div>
                                                <p className="text-sm font-semibold text-white">{inv.number}</p>
                                                <p className="text-[10px] text-white/30">{inv.issueDate}</p>
                                            </div>
                                            <div>
                                                <p className="text-sm text-white/80">{inv.tenant}</p>
                                                <p className="text-[10px] text-white/30">{inv.tier}</p>
                                            </div>
                                            <p className="text-sm font-semibold text-white">{inv.amount}</p>
                                            <Badge className={cn('border text-xs w-fit', cfg.bg)}>
                                                <StatusIcon className={cn('h-3 w-3 mr-1', cfg.color)} />
                                                <span className={cfg.color}>{inv.status}</span>
                                            </Badge>
                                            <p className="text-xs text-white/50">{inv.dueDate}</p>
                                            <Button variant="ghost" size="sm" className="text-white/30 hover:text-white p-0">
                                                <ChevronRight className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    );
                                })}
                            </div>
                        ) : (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1.5fr_1.5fr_1fr_1.2fr_1fr_0.5fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Payment</span><span>Customer</span><span>Amount</span><span>Method</span><span>Date</span><span>Status</span>
                                </div>
                                {mockPayments.map((pay) => (
                                    <div key={pay.id} className="grid grid-cols-[1.5fr_1.5fr_1fr_1.2fr_1fr_0.5fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                        <div>
                                            <p className="text-sm font-semibold text-white">{pay.id.slice(0, 16)}</p>
                                            <p className="text-[10px] text-white/30">{pay.invoice}</p>
                                        </div>
                                        <p className="text-sm text-white/80">{pay.tenant}</p>
                                        <p className="text-sm font-semibold text-white">{pay.amount}</p>
                                        <div className="flex items-center gap-2">
                                            <CreditCard className="h-3.5 w-3.5 text-white/40" />
                                            <span className="text-xs text-white/60">{pay.method}</span>
                                        </div>
                                        <p className="text-xs text-white/50">{pay.date}</p>
                                        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/20 border text-xs w-fit">
                                            <CheckCircle className="h-3 w-3 mr-1" />
                                            ✓
                                        </Badge>
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
