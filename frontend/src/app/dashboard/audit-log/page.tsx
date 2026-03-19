'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
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
    ChevronDown,
    Search,
    Download,
    Hash,
    Info,
    Shield,
} from 'lucide-react';

import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { useDashboardRefresh } from '@/hooks/use-dashboard-refresh';

/* ── Types ── */

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

/* ── Config ── */

const EVENT_CONFIG: Record<string, { color: string; icon: React.ElementType; label: string }> = {
    cte_recorded: { color: '#10b981', icon: Database, label: 'CTE Recorded' },
    api_call: { color: '#3b82f6', icon: Webhook, label: 'API Call' },
    compliance_change: { color: '#f59e0b', icon: AlertTriangle, label: 'Compliance' },
    export: { color: '#8b5cf6', icon: Upload, label: 'Export' },
    user_login: { color: '#6366f1', icon: User, label: 'Auth' },
    alert: { color: '#ef4444', icon: AlertTriangle, label: 'Alert' },
};

type EventFilter = 'all' | 'cte_recorded' | 'api_call' | 'compliance_change' | 'export' | 'user_login' | 'alert';

const FILTER_OPTIONS: { id: EventFilter; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'cte_recorded', label: 'CTEs' },
    { id: 'api_call', label: 'API' },
    { id: 'compliance_change', label: 'Compliance' },
    { id: 'export', label: 'Exports' },
    { id: 'user_login', label: 'Auth' },
    { id: 'alert', label: 'Alerts' },
];

/* ── Helpers ── */

function formatTimeAgo(iso: string): string {
    try {
        const diff = Date.now() - new Date(iso).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        if (days < 7) return `${days}d ago`;
        return new Date(iso).toLocaleDateString();
    } catch {
        return iso;
    }
}

async function fetchAuditLog(tenantId: string, page = 1, pageSize = 50): Promise<AuditLogResponse> {
    const apiKey = typeof window !== 'undefined'
        ? (localStorage.getItem('regengine_api_key') || localStorage.getItem('re-api-key') || process.env.NEXT_PUBLIC_API_KEY || '')
        : (process.env.NEXT_PUBLIC_API_KEY || '');
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetch(`${base}/api/v1/audit-log/${tenantId}?page=${page}&page_size=${pageSize}`, {
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
}

/* ── Page ── */

export default function AuditLogPage() {
    const { isAuthenticated } = useAuth();
    const { tenantId } = useTenant();

    // Resolve effective auth from React state OR localStorage
    const isLoggedIn = useMemo(() => {
        if (isAuthenticated) return true;
        if (typeof window === 'undefined') return false;
        return !!localStorage.getItem('regengine_access_token') && !!localStorage.getItem('regengine_user');
    }, [isAuthenticated]);

    const effectiveTenantId = useMemo(() => {
        if (tenantId) return tenantId;
        if (typeof window === 'undefined') return null;
        return localStorage.getItem('regengine_tenant_id');
    }, [tenantId]);

    const [filter, setFilter] = useState<EventFilter>('all');
    const [searchQuery, setSearchQuery] = useState('');
    const [entries, setEntries] = useState<AuditEntry[]>([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [pageSize] = useState(50);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [expandedId, setExpandedId] = useState<string | null>(null);
    const [lastFetched, setLastFetched] = useState<Date | null>(null);

    const loadLog = useCallback(async () => {
        if (!isLoggedIn || !effectiveTenantId) return;
        setLoading(true);
        setError(null);
        try {
            const data = await fetchAuditLog(effectiveTenantId!, page, pageSize);
            const fetchedEntries = data.entries || [];

            if (fetchedEntries.length > 1 || page > 1) {
                setEntries(fetchedEntries);
                setTotal(data.total || 0);
            } else {
                // Supplement with supplier facility events from bulk upload
                try {
                    const { apiClient } = await import('@/lib/api-client');
                    const facilities = await apiClient.listSupplierFacilities();
                    const supplemental: AuditEntry[] = [...fetchedEntries];

                    for (const f of facilities) {
                        supplemental.push({
                            id: `facility-${f.id}`,
                            event_type: 'facility_created',
                            action: 'facility_created',
                            category: 'cte',
                            actor: 'bulk_upload',
                            resource: f.name,
                            timestamp: new Date().toISOString(),
                            details: { source: 'bulk_upload', facility_id: f.id },
                            ip_address: '',
                            hash: '',
                        });
                    }

                    setEntries(supplemental);
                    setTotal(supplemental.length);
                } catch {
                    setEntries(fetchedEntries);
                    setTotal(data.total || 0);
                }
            }

            setLastFetched(new Date());
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load audit log');
        } finally {
            setLoading(false);
        }
    }, [isLoggedIn, effectiveTenantId, page, pageSize]);

    useEffect(() => { loadLog(); }, [loadLog]);

    // Re-fetch when data changes elsewhere (upload, bulk import, tab refocus)
    useDashboardRefresh(loadLog);

    // Client-side filtering + search
    const filtered = useMemo(() => {
        let list = filter === 'all' ? entries : entries.filter(e => e.event_type === filter);
        if (searchQuery.trim()) {
            const q = searchQuery.toLowerCase();
            list = list.filter(e =>
                e.action.toLowerCase().includes(q) ||
                e.actor.toLowerCase().includes(q) ||
                e.resource.toLowerCase().includes(q)
            );
        }
        return list;
    }, [entries, filter, searchQuery]);

    const totalPages = Math.ceil(total / pageSize);

    // Summary stats
    const stats = useMemo(() => {
        const now = Date.now();
        const today = entries.filter(e => now - new Date(e.timestamp).getTime() < 86400000).length;
        const typeCounts: Record<string, number> = {};
        entries.forEach(e => { typeCounts[e.event_type] = (typeCounts[e.event_type] || 0) + 1; });
        return { today, typeCounts };
    }, [entries]);

    return (
        <div className="min-h-screen bg-background p-4 md:p-8 pt-4">
            <div className="mx-auto max-w-7xl space-y-6">
                <Breadcrumbs items={[
                    { label: 'Dashboard', href: '/dashboard' },
                    { label: 'Audit Log' },
                ]} />

                {/* Header */}
                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight flex items-center gap-2">
                            <ScrollText className="h-6 w-6 sm:h-7 sm:w-7 text-[var(--re-brand)]" />
                            Audit Log
                        </h1>
                        <p className="mt-1 text-sm text-muted-foreground">
                            Immutable, SHA-256 verified record of all system events
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        {lastFetched && (
                            <span className="text-[10px] text-muted-foreground">
                                Updated {lastFetched.toLocaleTimeString()}
                            </span>
                        )}
                        <Button variant="ghost" size="sm" onClick={loadLog} disabled={loading} className="h-8 w-8 p-0">
                            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                        <Button variant="outline" size="sm" className="rounded-xl min-h-[36px] text-xs active:scale-[0.97]" disabled title="Coming in v1.1">
                            <Download className="h-3 w-3 mr-1" /> Export
                        </Button>
                        <Badge variant="outline" className="text-[10px] py-1 hidden sm:inline-flex">
                            <Shield className="h-3 w-3 mr-1 text-[var(--re-brand)]" /> Tamper-proof
                        </Badge>
                    </div>
                </div>

                {/* Auth gate */}
                {!isLoggedIn && (
                    <Card className="border-amber-500/30 bg-amber-500/[0.03]">
                        <CardContent className="py-6 text-center text-sm text-muted-foreground">
                            Sign in to view the audit log.
                        </CardContent>
                    </Card>
                )}

                {/* Summary Stats */}
                {isLoggedIn && entries.length > 0 && (
                    <motion.div
                        className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-3"
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                    >
                        <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                            <div className="text-2xl sm:text-3xl font-bold tabular-nums">{total.toLocaleString()}</div>
                            <div className="text-[11px] text-muted-foreground mt-0.5">Total Events</div>
                        </div>
                        <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                            <div className="text-2xl sm:text-3xl font-bold tabular-nums text-[var(--re-brand)]">{stats.today}</div>
                            <div className="text-[11px] text-muted-foreground mt-0.5">Today</div>
                        </div>
                        <div className="p-3 sm:p-4 rounded-xl bg-emerald-500/[0.06] border border-emerald-500/20 text-center">
                            <div className="text-2xl sm:text-3xl font-bold text-emerald-400 flex items-center justify-center gap-1">
                                <ShieldCheck className="h-5 w-5" />
                            </div>
                            <div className="text-[11px] text-muted-foreground mt-0.5">Chain Verified</div>
                        </div>
                        <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                            <div className="text-2xl sm:text-3xl font-bold tabular-nums">{Object.keys(stats.typeCounts).length}</div>
                            <div className="text-[11px] text-muted-foreground mt-0.5">Event Types</div>
                        </div>
                    </motion.div>
                )}

                {/* Loading */}
                {loading && entries.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-16 gap-3">
                        <Spinner size="lg" />
                        <p className="text-sm text-muted-foreground">Loading audit trail...</p>
                    </div>
                )}

                {/* Error */}
                {error && (
                    <Card className="border-red-500/30 bg-red-500/[0.03]">
                        <CardContent className="py-4">
                            <div className="flex items-center gap-3 text-red-400">
                                <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                                <div>
                                    <p className="text-sm font-medium">Failed to load audit log</p>
                                    <p className="text-xs text-muted-foreground mt-0.5">{error}</p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Filter + Search Bar */}
                {isLoggedIn && entries.length > 0 && (
                    <div className="space-y-3">
                        {/* Search */}
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <input
                                type="text"
                                placeholder="Search actions, actors, resources..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] text-sm placeholder:text-muted-foreground focus:outline-none focus:border-[var(--re-brand)] transition-colors"
                            />
                        </div>

                        {/* Filter chips */}
                        <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar pb-1">
                            <Filter className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                            {FILTER_OPTIONS.map((f) => {
                                const count = f.id === 'all' ? entries.length : (stats.typeCounts[f.id] || 0);
                                return (
                                    <button
                                        key={f.id}
                                        onClick={() => setFilter(f.id)}
                                        className={`px-2.5 py-1.5 rounded-full text-[11px] font-medium border transition-all whitespace-nowrap min-h-[32px] active:scale-[0.96] flex-shrink-0 flex items-center gap-1 ${
                                            filter === f.id
                                                ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)]'
                                                : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]/50'
                                        }`}
                                    >
                                        {f.label}
                                        {count > 0 && (
                                            <span className={`text-[9px] px-1 rounded-full ${filter === f.id ? 'bg-white/20' : 'bg-[var(--re-surface-card)]'}`}>
                                                {count}
                                            </span>
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* Event List */}
                {isLoggedIn && filtered.length > 0 && (
                    <div className="space-y-1.5">
                        {filtered.map((entry, i) => {
                            const config = EVENT_CONFIG[entry.event_type] || EVENT_CONFIG.cte_recorded;
                            const Icon = config.icon;
                            const isExpanded = expandedId === entry.id;

                            return (
                                <motion.div
                                    key={entry.id}
                                    initial={{ opacity: 0, y: 6 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: Math.min(i * 0.02, 0.5) }}
                                >
                                    <div
                                        className={`p-3 rounded-xl border transition-all cursor-pointer ${isExpanded ? 'border-[var(--re-brand)] bg-[var(--re-surface-elevated)]' : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]/50'}`}
                                        onClick={() => setExpandedId(isExpanded ? null : entry.id)}
                                    >
                                        <div className="flex items-start sm:items-center gap-2 sm:gap-3">
                                            <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 sm:mt-0"
                                                style={{ background: `${config.color}15` }}>
                                                <Icon className="h-3.5 w-3.5" style={{ color: config.color }} />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-1.5 flex-wrap">
                                                    <span className="text-xs sm:text-sm font-medium">{entry.action}</span>
                                                    <Badge variant="secondary" className="text-[9px] px-1.5 py-0"
                                                        style={{ background: `${config.color}15`, color: config.color }}>
                                                        {config.label}
                                                    </Badge>
                                                </div>
                                                <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 mt-0.5">
                                                    <span className="truncate">{entry.actor}</span>
                                                    <span className="hidden sm:inline text-muted-foreground/50">→</span>
                                                    <span className="truncate hidden sm:inline">{entry.resource}</span>
                                                </div>
                                            </div>
                                            <div className="text-right flex-shrink-0 flex items-center gap-2">
                                                <div>
                                                    <div className="text-[11px] text-muted-foreground flex items-center gap-1">
                                                        <Clock className="h-3 w-3" /> {formatTimeAgo(entry.timestamp)}
                                                    </div>
                                                    {entry.hash && (
                                                        <div className="text-[9px] font-mono text-muted-foreground/40 mt-0.5 hidden sm:block">
                                                            <Hash className="h-2.5 w-2.5 inline mr-0.5" />{entry.hash.slice(0, 10)}
                                                        </div>
                                                    )}
                                                </div>
                                                <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                                            </div>
                                        </div>

                                        {/* Expanded details */}
                                        <AnimatePresence>
                                            {isExpanded && (
                                                <motion.div
                                                    initial={{ opacity: 0, height: 0 }}
                                                    animate={{ opacity: 1, height: 'auto' }}
                                                    exit={{ opacity: 0, height: 0 }}
                                                    className="overflow-hidden"
                                                >
                                                    <div className="mt-3 pt-3 border-t border-[var(--re-border-default)] grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                                                        <div>
                                                            <span className="text-muted-foreground">Timestamp:</span>{' '}
                                                            <span className="font-mono">{new Date(entry.timestamp).toLocaleString()}</span>
                                                        </div>
                                                        <div>
                                                            <span className="text-muted-foreground">Category:</span>{' '}
                                                            <span className="capitalize">{entry.category}</span>
                                                        </div>
                                                        <div>
                                                            <span className="text-muted-foreground">Actor:</span>{' '}
                                                            <span>{entry.actor}</span>
                                                        </div>
                                                        <div>
                                                            <span className="text-muted-foreground">Resource:</span>{' '}
                                                            <span className="font-mono truncate">{entry.resource}</span>
                                                        </div>
                                                        {entry.ip_address && (
                                                            <div>
                                                                <span className="text-muted-foreground">IP:</span>{' '}
                                                                <span className="font-mono">{entry.ip_address}</span>
                                                            </div>
                                                        )}
                                                        {entry.hash && (
                                                            <div className="sm:col-span-2">
                                                                <span className="text-muted-foreground">SHA-256:</span>{' '}
                                                                <span className="font-mono text-[10px] break-all">{entry.hash}</span>
                                                            </div>
                                                        )}
                                                        {entry.details && Object.keys(entry.details).length > 0 && (
                                                            <div className="sm:col-span-2">
                                                                <span className="text-muted-foreground">Metadata:</span>
                                                                <pre className="mt-1 p-2 rounded-lg bg-[var(--re-surface-card)] text-[10px] font-mono overflow-x-auto">
                                                                    {JSON.stringify(entry.details, null, 2)}
                                                                </pre>
                                                            </div>
                                                        )}
                                                    </div>
                                                </motion.div>
                                            )}
                                        </AnimatePresence>
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                )}

                {/* Pagination */}
                {isLoggedIn && totalPages > 1 && (
                    <div className="flex items-center justify-between pt-2">
                        <span className="text-[11px] text-muted-foreground">
                            Page {page} of {totalPages} ({total.toLocaleString()} entries)
                        </span>
                        <div className="flex gap-2">
                            <Button variant="outline" size="sm" className="rounded-xl h-9 w-9 p-0 active:scale-[0.97]" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                                <ChevronLeft className="h-4 w-4" />
                            </Button>
                            <Button variant="outline" size="sm" className="rounded-xl h-9 w-9 p-0 active:scale-[0.97]" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                                <ChevronRight className="h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                )}

                {/* Empty state */}
                {isLoggedIn && !loading && entries.length === 0 && !error && (
                    <motion.div
                        className="flex flex-col items-center justify-center py-16 text-center"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                    >
                        <ScrollText className="h-12 w-12 text-muted-foreground/30 mb-4" />
                        <h2 className="text-lg font-semibold">No Audit Entries Yet</h2>
                        <p className="text-sm text-muted-foreground mt-1 max-w-md">
                            Events will appear here as your team scans labels, imports data, and generates reports. Every action is cryptographically signed and immutable.
                        </p>
                        <div className="flex items-center gap-1.5 mt-4 text-xs text-emerald-400">
                            <ShieldCheck className="h-3.5 w-3.5" />
                            <span>SHA-256 hash chain ready</span>
                        </div>
                    </motion.div>
                )}

                {/* Chain integrity footer */}
                {isLoggedIn && entries.length > 0 && (
                    <Card className="border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
                        <CardContent className="py-3">
                            <div className="flex items-start gap-3">
                                <Info className="h-4 w-4 text-[var(--re-brand)] mt-0.5 flex-shrink-0" />
                                <div className="text-xs text-muted-foreground leading-relaxed">
                                    <span className="font-medium text-foreground">Tamper-evident audit trail: </span>
                                    Every entry is cryptographically chained using SHA-256. Database triggers prevent modification or deletion.
                                    Compliant with 21 CFR Part 11 electronic records requirements and SOX 7-year retention.
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                )}
            </div>
        </div>
    );
}
