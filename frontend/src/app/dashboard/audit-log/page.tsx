'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
    ScrollText,
    Database,
    ShieldCheck,
    Upload,
    User,
    Webhook,
    AlertTriangle,
    Filter,
    Clock,
} from 'lucide-react';

const EVENT_CONFIG: Record<string, { color: string; icon: typeof ScrollText; label: string }> = {
    cte_recorded: { color: '#10b981', icon: Database, label: 'CTE Recorded' },
    api_call: { color: '#3b82f6', icon: Webhook, label: 'API Call' },
    compliance_change: { color: '#f59e0b', icon: AlertTriangle, label: 'Compliance' },
    export: { color: '#8b5cf6', icon: Upload, label: 'Export' },
    user_login: { color: '#6366f1', icon: User, label: 'Auth' },
    alert: { color: '#ef4444', icon: AlertTriangle, label: 'Alert' },
};

const SAMPLE_LOG = [
    { id: '001', timestamp: '5 min ago', event_type: 'cte_recorded', actor: 'ops@valleyfresh.com', action: 'Recorded Shipping CTE', resource: 'TLC ROM-0226-A1-001', hash: 'a3f8c1d2...' },
    { id: '002', timestamp: '15 min ago', event_type: 'api_call', actor: 'rge_key_prod_001', action: 'POST /api/v1/webhooks/ingest', resource: 'Webhook Ingestion', hash: 'b4c9d3e5...' },
    { id: '003', timestamp: '30 min ago', event_type: 'compliance_change', actor: 'system', action: 'Compliance score updated', resource: 'Tenant Score (B → C)', hash: 'c5dae4f6...' },
    { id: '004', timestamp: '1 hour ago', event_type: 'export', actor: 'jsmith@example.com', action: 'Exported EPCIS 2.0 JSON-LD', resource: '47 events → Walmart', hash: 'd6ebf5a7...' },
    { id: '005', timestamp: '2 hours ago', event_type: 'user_login', actor: 'jsmith@example.com', action: 'User logged in via SSO', resource: 'Session (Okta)', hash: 'e7fca6b8...' },
    { id: '006', timestamp: '3 hours ago', event_type: 'cte_recorded', actor: 'portal-vff-001', action: 'Supplier submitted Receiving CTE', resource: 'TLC SAL-0226-B1-007', hash: 'f8adb7c9...' },
    { id: '007', timestamp: '4 hours ago', event_type: 'alert', actor: 'system', action: 'Temperature excursion triggered', resource: '8.2°C (threshold: 5°C)', hash: 'a9bec8d0...' },
    { id: '008', timestamp: '6 hours ago', event_type: 'api_call', actor: 'rge_key_prod_001', action: 'POST /api/v1/ingest/csv', resource: 'shipping_feb_26.csv (15 rows)', hash: 'bacfd9e1...' },
];

type EventFilter = 'all' | 'cte_recorded' | 'api_call' | 'compliance_change' | 'export' | 'user_login' | 'alert';

export default function AuditLogPage() {
    const [filter, setFilter] = useState<EventFilter>('all');
    const filtered = filter === 'all' ? SAMPLE_LOG : SAMPLE_LOG.filter(e => e.event_type === filter);

    return (
        <div className="min-h-screen bg-background py-10 px-4">
            <div className="max-w-5xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-3">
                            <ScrollText className="h-6 w-6 text-[var(--re-brand)]" />
                            Audit Log
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Immutable record of all system events · SHA-256 verified
                        </p>
                    </div>
                    <Badge variant="outline" className="text-xs py-1.5">
                        <ShieldCheck className="h-3 w-3 mr-1 text-[var(--re-brand)]" /> Tamper-proof
                    </Badge>
                </div>

                {/* Filter Bar */}
                <div className="flex items-center gap-2 flex-wrap">
                    <Filter className="h-4 w-4 text-muted-foreground" />
                    {[
                        { id: 'all' as const, label: 'All' },
                        { id: 'cte_recorded' as const, label: 'CTEs' },
                        { id: 'api_call' as const, label: 'API' },
                        { id: 'compliance_change' as const, label: 'Compliance' },
                        { id: 'export' as const, label: 'Exports' },
                        { id: 'user_login' as const, label: 'Auth' },
                        { id: 'alert' as const, label: 'Alerts' },
                    ].map((f) => (
                        <button
                            key={f.id}
                            onClick={() => setFilter(f.id)}
                            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${filter === f.id
                                    ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)]'
                                    : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]'
                                }`}
                        >
                            {f.label}
                        </button>
                    ))}
                </div>

                {/* Event List */}
                <div className="space-y-2">
                    {filtered.map((entry, i) => {
                        const config = EVENT_CONFIG[entry.event_type] || EVENT_CONFIG.cte_recorded;
                        const Icon = config.icon;
                        return (
                            <motion.div
                                key={entry.id}
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: i * 0.03 }}
                                className="flex items-center gap-3 p-3 rounded-xl border border-[var(--re-border-default)] hover:border-[var(--re-brand)] transition-all"
                            >
                                <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                                    style={{ background: `${config.color}10` }}>
                                    <Icon className="h-4 w-4" style={{ color: config.color }} />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="text-sm font-medium">{entry.action}</span>
                                        <Badge className="text-[9px] px-1.5 py-0"
                                            style={{ background: `${config.color}10`, color: config.color }}>
                                            {config.label}
                                        </Badge>
                                    </div>
                                    <div className="text-xs text-muted-foreground flex items-center gap-3 mt-0.5">
                                        <span>{entry.actor}</span>
                                        <span>→ {entry.resource}</span>
                                    </div>
                                </div>
                                <div className="text-right flex-shrink-0">
                                    <div className="text-xs text-muted-foreground flex items-center gap-1">
                                        <Clock className="h-3 w-3" /> {entry.timestamp}
                                    </div>
                                    <div className="text-[9px] font-mono text-muted-foreground/50 mt-0.5">
                                        {entry.hash}
                                    </div>
                                </div>
                            </motion.div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
