'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    Bell,
    Mail,
    Webhook,
    MessageSquare,
    Shield,
    AlertTriangle,
    CheckCircle,
    XCircle,
    Clock,
    Eye,
    Zap,
    ToggleLeft,
    ToggleRight,
    Globe,
    Info,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// ── Mock Data ─────────────────────────────────────────────────────

const mockSummary = {
    totalEvents: 5,
    unacknowledged: 4,
    criticalUnacked: 1,
    totalRules: 6,
    enabledRules: 6,
    webhookSuccess: '66.7%',
};

const mockRules = [
    { id: 'rule_pay_fail', name: 'Payment Failed', type: 'payment_failed', severity: 'critical', channels: ['email', 'slack', 'in_app'], enabled: true },
    { id: 'rule_usage_80', name: 'Usage at 80%', type: 'usage_threshold', severity: 'warning', channels: ['email', 'in_app'], enabled: true },
    { id: 'rule_trial_exp', name: 'Trial Expiring (3 days)', type: 'trial_expiring', severity: 'info', channels: ['email'], enabled: true },
    { id: 'rule_contract_exp', name: 'Contract Renewal Due', type: 'contract_expiring', severity: 'warning', channels: ['email', 'slack'], enabled: true },
    { id: 'rule_credit_low', name: 'Credits Below $100', type: 'credit_low', severity: 'warning', channels: ['in_app'], enabled: true },
    { id: 'rule_dunning_esc', name: 'Dunning Escalated', type: 'dunning_escalated', severity: 'critical', channels: ['email', 'slack'], enabled: true },
];

const mockEvents = [
    { id: 'evt_pay', title: 'Payment Failed — MedSecure', message: 'Retry #2 declined for INV-2026-1009', severity: 'critical', channels: ['email', 'slack'], acknowledged: false, time: '6h ago' },
    { id: 'evt_usage', title: 'API Usage at 85% — Acme Foods', message: '42,500 of 50,000 API calls used', severity: 'warning', channels: ['in_app'], acknowledged: false, time: '18h ago' },
    { id: 'evt_trial', title: 'Trial Expiring — BetaCorp', message: 'Enterprise trial expires in 2 days', severity: 'info', channels: ['email'], acknowledged: false, time: '1d ago' },
    { id: 'evt_contract', title: 'Contract Renewal — FreshLeaf', message: 'RE-2026-002 expires in 28 days', severity: 'warning', channels: ['email', 'slack'], acknowledged: false, time: '2d ago' },
    { id: 'evt_plan', title: 'Upgrade — Acme Foods', message: 'Pro → Enterprise, proration $2,100', severity: 'info', channels: ['in_app'], acknowledged: true, time: '12d ago' },
];

const mockWebhooks = [
    { id: 'whk_01', event: 'payment.failed', url: 'hooks.slack.com/billing', status: 'delivered', code: 200, time: '6h ago' },
    { id: 'whk_02', event: 'subscription.changed', url: 'hooks.slack.com/billing', status: 'delivered', code: 200, time: '12d ago' },
    { id: 'whk_03', event: 'invoice.overdue', url: 'api.partner.com/hooks/billing', status: 'failed', code: 500, time: '1d ago' },
];

const severityConfig: Record<string, { color: string; bg: string; icon: React.ElementType }> = {
    critical: { color: 'text-red-400', bg: 'bg-red-500/15 border-red-500/20', icon: AlertTriangle },
    warning: { color: 'text-amber-400', bg: 'bg-amber-500/15 border-amber-500/20', icon: Shield },
    info: { color: 'text-blue-400', bg: 'bg-blue-500/15 border-blue-500/20', icon: Info },
};

const channelIcons: Record<string, React.ElementType> = {
    email: Mail,
    webhook: Webhook,
    slack: MessageSquare,
    in_app: Bell,
};

export default function AlertsDashboard() {
    const [tab, setTab] = useState<'events' | 'rules' | 'webhooks'>('events');

    return (
        <div className="p-8 max-w-[1600px] mx-auto">
            {/* Header */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-600/20">
                            <Bell className="h-7 w-7 text-amber-400" />
                        </div>
                        Billing Alerts
                    </h1>
                    <p className="text-white/50 mt-1 ml-14">Notification rules, event log & webhook monitoring</p>
                </div>
                {mockSummary.criticalUnacked > 0 && (
                    <Badge className="bg-red-500/20 text-red-400 border-red-500/30 border px-3 py-1 animate-pulse">
                        <AlertTriangle className="h-3.5 w-3.5 mr-1.5" />
                        {mockSummary.criticalUnacked} Critical
                    </Badge>
                )}
            </motion.div>

            <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Demo Data — This page shows simulated data. Connect your backend to see live metrics.</span>
            </div>

            {/* KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                {[
                    { title: 'Unacknowledged', value: String(mockSummary.unacknowledged), sub: 'Pending review', icon: Eye, gradient: 'from-amber-500/20 to-orange-600/20', iconColor: 'text-amber-400' },
                    { title: 'Critical', value: String(mockSummary.criticalUnacked), sub: 'Immediate attention', icon: AlertTriangle, gradient: 'from-red-500/20 to-rose-600/20', iconColor: 'text-red-400' },
                    { title: 'Active Rules', value: `${mockSummary.enabledRules}/${mockSummary.totalRules}`, sub: 'All enabled', icon: Zap, gradient: 'from-blue-500/20 to-indigo-600/20', iconColor: 'text-blue-400' },
                    { title: 'Webhook Rate', value: mockSummary.webhookSuccess, sub: '2 of 3 delivered', icon: Globe, gradient: 'from-emerald-500/20 to-teal-600/20', iconColor: 'text-emerald-400' },
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
                            {(['events', 'rules', 'webhooks'] as const).map((t) => (
                                <button key={t} onClick={() => setTab(t)}
                                    className={cn('px-6 py-3 text-sm font-medium border-b-2 transition-all capitalize',
                                        tab === t ? 'text-white border-amber-400' : 'text-white/40 border-transparent hover:text-white/60')}>
                                    {t}
                                </button>
                            ))}
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        {tab === 'events' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[2fr_1fr_1fr_0.8fr_0.6fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Alert</span><span>Severity</span><span>Channels</span><span>Status</span><span>Time</span>
                                </div>
                                {mockEvents.map((e) => {
                                    const sev = severityConfig[e.severity] || severityConfig.info;
                                    const SevIcon = sev.icon;
                                    return (
                                        <div key={e.id} className="grid grid-cols-[2fr_1fr_1fr_0.8fr_0.6fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                            <div>
                                                <p className="text-sm font-semibold text-white">{e.title}</p>
                                                <p className="text-[11px] text-white/30 mt-0.5">{e.message}</p>
                                            </div>
                                            <Badge className={cn('border text-xs w-fit', sev.bg)}>
                                                <SevIcon className={cn('h-3 w-3 mr-1', sev.color)} />
                                                <span className={sev.color}>{e.severity}</span>
                                            </Badge>
                                            <div className="flex gap-1.5">
                                                {e.channels.map((ch) => {
                                                    const ChIcon = channelIcons[ch] || Bell;
                                                    return <ChIcon key={ch} className="h-3.5 w-3.5 text-white/30" title={ch} />;
                                                })}
                                            </div>
                                            <div className="flex items-center gap-1.5">
                                                {e.acknowledged ? (
                                                    <><CheckCircle className="h-3.5 w-3.5 text-emerald-400" /><span className="text-xs text-emerald-400">Acked</span></>
                                                ) : (
                                                    <><Clock className="h-3.5 w-3.5 text-amber-400" /><span className="text-xs text-amber-400">Pending</span></>
                                                )}
                                            </div>
                                            <p className="text-xs text-white/40">{e.time}</p>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {tab === 'rules' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1.5fr_1.2fr_0.8fr_1.2fr_0.6fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Rule</span><span>Trigger</span><span>Severity</span><span>Channels</span><span>Enabled</span>
                                </div>
                                {mockRules.map((r) => {
                                    const sev = severityConfig[r.severity] || severityConfig.info;
                                    return (
                                        <div key={r.id} className="grid grid-cols-[1.5fr_1.2fr_0.8fr_1.2fr_0.6fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                            <p className="text-sm font-semibold text-white">{r.name}</p>
                                            <p className="text-xs text-white/50 font-mono">{r.type}</p>
                                            <Badge className={cn('border text-xs w-fit', sev.bg)}>
                                                <span className={sev.color}>{r.severity}</span>
                                            </Badge>
                                            <div className="flex gap-1.5">
                                                {r.channels.map((ch) => {
                                                    const ChIcon = channelIcons[ch] || Bell;
                                                    return (
                                                        <Badge key={ch} className="bg-white/5 text-white/50 border-white/10 border text-[10px] gap-1">
                                                            <ChIcon className="h-3 w-3" />{ch}
                                                        </Badge>
                                                    );
                                                })}
                                            </div>
                                            <div>
                                                {r.enabled ? (
                                                    <ToggleRight className="h-5 w-5 text-emerald-400" />
                                                ) : (
                                                    <ToggleLeft className="h-5 w-5 text-white/20" />
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {tab === 'webhooks' && (
                            <div className="divide-y divide-white/5">
                                <div className="grid grid-cols-[1fr_1.5fr_0.8fr_0.6fr_0.6fr] gap-4 px-4 py-3 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                                    <span>Event</span><span>URL</span><span>Status</span><span>Code</span><span>Time</span>
                                </div>
                                {mockWebhooks.map((w) => (
                                    <div key={w.id} className="grid grid-cols-[1fr_1.5fr_0.8fr_0.6fr_0.6fr] gap-4 px-4 py-3 items-center hover:bg-white/5 transition-colors">
                                        <p className="text-sm font-semibold text-white">{w.event}</p>
                                        <p className="text-xs text-white/40 font-mono truncate">{w.url}</p>
                                        <Badge className={cn('border text-xs w-fit', w.status === 'delivered' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20' : 'bg-red-500/15 text-red-400 border-red-500/20')}>
                                            {w.status}
                                        </Badge>
                                        <p className={cn('text-xs font-mono', w.code === 200 ? 'text-emerald-400' : 'text-red-400')}>{w.code}</p>
                                        <p className="text-xs text-white/40">{w.time}</p>
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
