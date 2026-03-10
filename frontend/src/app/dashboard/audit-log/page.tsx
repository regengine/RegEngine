'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
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
    RefreshCw,
    ChevronLeft,
    ChevronRight,
} from 'lucide-react';

import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';

/* ── Types matching AuditLogResponse ── */

interface AuditEntry {
    id: string;
    timestamp: string;
    event_type: string;
    category: string;
    actor: string;
    action: string;
    resource: string;
    details: Record<string, unknown>;
    ip_address: string;
    hash: string;
}

interface AuditLogResponse {
    tenant_id: string;
    total: number;
    page: number;
    page_size: number;
    entries: AuditEntry[];
}

const EVENT_CONFIG: Record<string, { color: string; icon: React.ElementType; label: string }> = {
    cte_recorded: { color: '#10b981', icon: Database, label: 'CTE Recorded' },
    api_call: { color: '#3b82f6', icon: Webhook, label: 'API Call' },
    compliance_change: { color: '#f59e0b', icon: AlertTriangle, label: 'Compliance' },
    export: { color: '#8b5cf6', icon: Upload, label: 'Export' },
    user_login: { color: '#6366f1', icon: User, label: 'Auth' },
    alert: { color: '#ef4444', icon: AlertTriangle, label: 'Alert' },
};

type EventFilter = 'all' | 'cte_recorded' | 'api_call' | 'compliance_change' | 'export' | 'user_login' | 'alert';

function formatTimeAgo(iso: string): string {
    try {
        const diff = Date.now() - new Date(iso).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 60) return `${mins} min ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        return `${days}d ago`;
    } catch {
        return iso;
    }
}

async function fetchAuditLog(tenantId: string, page = 1, pageSize = 50): Promise<AuditLogResponse> {
    const apiKey = typeof window !== 'undefined'
        ? (
            localStorage.getItem('regengine_api_key') ||
            localStorage.getItem('re-api-key') ||
            process.env.NEXT_PUBLIC_API_KEY ||
            ''
        )
        : (process.env.NEXT_PUBLIC_API_KEY || '');
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetch(`${base}/api/v1/audit-log/${tenantId}?page=${page}&page_size=${pageSize}`, {
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
}

export default function AuditLogPage() {
    const { apiKey } = useAuth();
    const { tenantId } = useTenant();
    const isLoggedIn = Boolean(apiKey);

    const [filter, setFilter] = useState<EventFilter>('all');
    const [entries, setEntries] = useState<AuditEntry[]>([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [pageSize] = useState(50);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const loadLog = useCallback(async () => {
        if (!isLoggedIn || !tenantId) return;
        setLoading(true);
        setError(null);
        try {
            const data = await fetchAuditLog(tenantId, page, pageSize);
            setEntries(data.entries || []);
            setTotal(data.total || 0);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load audit log');
        } finally {
            setLoading(false);
        }
    }, [isLoggedIn, tenantId, page, pageSize]);

    useEffect(() => { loadLog(); }, [loadLog]);

    const filtered = filter === 'all' ? entries : entries.filter(e => e.event_type === filter);
    const totalPages = Math.ceil(total / pageSize);

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
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" className="rounded-xl" onClick={loadLog} disabled={loading}>
                            <RefreshCw className={`h-3 w-3 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
                        </Button>
                        <Badge variant="outline" className="text-xs py-1.5">
                            <ShieldCheck className="h-3 w-3 mr-1 text-[var(--re-brand)]" /> Tamper-proof
                        </Badge>
                    </div>
                </div>

                {/* Auth gate */}
                {!isLoggedIn && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-6 text-center text-sm text-muted-foreground">
                            Sign in to view the audit log.
                        </CardContent>
                    </Card>
                )}

                {loading && entries.length === 0 && (
                    <div className="flex justify-center py-16"><Spinner size="lg" /></div>
                )}

                {error && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-4">
                            <div className="flex items-center gap-3 text-orange-600 dark:text-orange-400">
                                <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                                <p className="text-sm">{error}</p>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {isLoggedIn && entries.length > 0 && (
                    <>
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
                                    className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                                        filter === f.id
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
                                                <Clock className="h-3 w-3" /> {formatTimeAgo(entry.timestamp)}
                                            </div>
                                            {entry.hash && (
                                                <div className="text-[9px] font-mono text-muted-foreground/50 mt-0.5">
                                                    {entry.hash.slice(0, 10)}...
                                                </div>
                                            )}
                                        </div>
                                    </motion.div>
                                );
                            })}
                        </div>

                        {/* Pagination */}
                        {totalPages > 1 && (
                            <div className="flex items-center justify-between pt-2">
                                <span className="text-xs text-muted-foreground">
                                    Page {page} of {totalPages} ({total} entries)
                                </span>
                                <div className="flex gap-2">
                                    <Button variant="outline" size="sm" className="rounded-xl" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                                        <ChevronLeft className="h-3 w-3" />
                                    </Button>
                                    <Button variant="outline" size="sm" className="rounded-xl" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                                        <ChevronRight className="h-3 w-3" />
                                    </Button>
                                </div>
                            </div>
                        )}
                    </>
                )}

                {isLoggedIn && !loading && entries.length === 0 && !error && (
                    <div className="text-center py-12 text-muted-foreground">
                        <ScrollText className="h-10 w-10 mx-auto mb-3 opacity-30" />
                        <div className="font-medium">No audit entries</div>
                        <div className="text-sm">Events will appear here as they are recorded</div>
                    </div>
                )}
            </div>
        </div>
    );
}
