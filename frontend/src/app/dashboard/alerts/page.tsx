'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Bell,
    AlertTriangle,
    ShieldAlert,
    ThermometerSun,
    Clock,
    CheckCircle2,
    Link2,
    TrendingDown,
    Activity,
    Filter,
} from 'lucide-react';

type Severity = 'critical' | 'warning' | 'info' | 'all';

const SAMPLE_ALERTS = [
    {
        id: 'alert-001',
        severity: 'warning' as const,
        category: 'compliance',
        title: 'Missing GLN on Receiving CTE',
        message: 'Receiving event for TLC ROM-0226-A1-001 is missing the ship-from GLN. Required per 21 CFR 1.1345(a)(3).',
        time: '2 hours ago',
        acknowledged: false,
        icon: AlertTriangle,
    },
    {
        id: 'alert-002',
        severity: 'critical' as const,
        category: 'temperature',
        title: 'Temperature Excursion — Atlantic Salmon',
        message: 'IoT sensor detected 8.2°C for SAL-0226-B1-007 (threshold: 5°C). Product may need quarantine.',
        time: '45 min ago',
        acknowledged: false,
        icon: ThermometerSun,
    },
    {
        id: 'alert-003',
        severity: 'warning' as const,
        category: 'compliance',
        title: 'Receiving CTE Overdue — Shipment #SHP-04',
        message: 'Expected Receiving CTE for Roma Tomatoes not recorded. Shipment departed 6 hours ago.',
        time: '1 hour ago',
        acknowledged: false,
        icon: Clock,
    },
    {
        id: 'alert-004',
        severity: 'warning' as const,
        category: 'compliance',
        title: 'Compliance Score Dropped to C',
        message: 'Score dropped from B (82%) to C (71%). Primary factor: KDE completeness decreased.',
        time: '5 hours ago',
        acknowledged: true,
        icon: TrendingDown,
    },
    {
        id: 'alert-005',
        severity: 'info' as const,
        category: 'deadline',
        title: 'Supplier Link Expiring — Valley Fresh Farms',
        message: 'Portal link expires in 36 hours. 3 of 5 pending submissions not yet received.',
        time: '12 hours ago',
        acknowledged: false,
        icon: Link2,
    },
];

const SEVERITY_CONFIG = {
    critical: { color: '#ef4444', bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.2)', label: 'Critical' },
    warning: { color: '#f59e0b', bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.2)', label: 'Warning' },
    info: { color: '#3b82f6', bg: 'rgba(59,130,246,0.08)', border: 'rgba(59,130,246,0.2)', label: 'Info' },
};

export default function AlertsDashboardPage() {
    const [filter, setFilter] = useState<Severity>('all');
    const [alerts, setAlerts] = useState(SAMPLE_ALERTS);

    const filtered = filter === 'all' ? alerts : alerts.filter(a => a.severity === filter);
    const criticalCount = alerts.filter(a => a.severity === 'critical' && !a.acknowledged).length;
    const warningCount = alerts.filter(a => a.severity === 'warning' && !a.acknowledged).length;
    const infoCount = alerts.filter(a => a.severity === 'info' && !a.acknowledged).length;
    const unackCount = alerts.filter(a => !a.acknowledged).length;

    const handleAcknowledge = (alertId: string) => {
        setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, acknowledged: true } : a));
    };

    return (
        <div className="min-h-screen bg-background py-10 px-4 sm:px-6 lg:px-8">
            <div className="max-w-5xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-3">
                            <Bell className="h-6 w-6 text-[var(--re-brand)]" />
                            Alerts & Notifications
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            {unackCount} unacknowledged alert{unackCount !== 1 ? 's' : ''}
                        </p>
                    </div>
                    <Badge variant="outline" className="text-xs py-1.5">
                        <Activity className="h-3 w-3 mr-1" /> Live
                    </Badge>
                </div>

                {/* Summary Cards */}
                <div className="grid grid-cols-3 gap-4">
                    {[
                        { label: 'Critical', count: criticalCount, color: '#ef4444', filter: 'critical' as const },
                        { label: 'Warnings', count: warningCount, color: '#f59e0b', filter: 'warning' as const },
                        { label: 'Info', count: infoCount, color: '#3b82f6', filter: 'info' as const },
                    ].map((item) => (
                        <button
                            key={item.label}
                            onClick={() => setFilter(filter === item.filter ? 'all' : item.filter)}
                            className={`p-4 rounded-xl border transition-all text-left ${filter === item.filter
                                    ? 'border-[var(--re-brand)] bg-[color-mix(in_srgb,var(--re-brand)_5%,transparent)]'
                                    : 'border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] hover:border-[var(--re-brand)]'
                                }`}
                        >
                            <div className="text-2xl font-bold" style={{ color: item.color }}>{item.count}</div>
                            <div className="text-xs text-muted-foreground">{item.label}</div>
                        </button>
                    ))}
                </div>

                {/* Filter Bar */}
                <div className="flex items-center gap-2">
                    <Filter className="h-4 w-4 text-muted-foreground" />
                    {(['all', 'critical', 'warning', 'info'] as const).map((f) => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${filter === f
                                    ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)]'
                                    : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]'
                                }`}
                        >
                            {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
                        </button>
                    ))}
                </div>

                {/* Alert List */}
                <div className="space-y-3">
                    <AnimatePresence>
                        {filtered.map((alert) => {
                            const config = SEVERITY_CONFIG[alert.severity];
                            const Icon = alert.icon;

                            return (
                                <motion.div
                                    key={alert.id}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, height: 0 }}
                                    className={`relative rounded-xl border p-4 transition-all ${alert.acknowledged ? 'opacity-50' : ''
                                        }`}
                                    style={{
                                        borderColor: alert.acknowledged ? 'var(--re-border-default)' : config.border,
                                        background: alert.acknowledged ? 'transparent' : config.bg,
                                    }}
                                >
                                    <div className="flex items-start gap-3">
                                        <div className="mt-0.5" style={{ color: config.color }}>
                                            <Icon className="h-5 w-5" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 mb-1">
                                                <span className="text-sm font-medium">{alert.title}</span>
                                                <Badge
                                                    className="text-[9px] px-1.5 py-0"
                                                    style={{ background: config.bg, color: config.color, border: `1px solid ${config.border}` }}
                                                >
                                                    {config.label}
                                                </Badge>
                                                {alert.acknowledged && (
                                                    <Badge variant="outline" className="text-[9px] px-1.5 py-0">
                                                        <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" /> Acknowledged
                                                    </Badge>
                                                )}
                                            </div>
                                            <p className="text-xs text-muted-foreground">{alert.message}</p>
                                            <span className="text-[10px] text-muted-foreground/60 mt-1 block">{alert.time}</span>
                                        </div>
                                        {!alert.acknowledged && (
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="rounded-xl text-xs flex-shrink-0"
                                                onClick={() => handleAcknowledge(alert.id)}
                                            >
                                                Acknowledge
                                            </Button>
                                        )}
                                    </div>
                                </motion.div>
                            );
                        })}
                    </AnimatePresence>
                </div>

                {filtered.length === 0 && (
                    <div className="text-center py-12 text-muted-foreground">
                        <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-emerald-500" />
                        <div className="font-medium">All clear</div>
                        <div className="text-sm">No {filter === 'all' ? '' : filter} alerts to show</div>
                    </div>
                )}
            </div>
        </div>
    );
}
