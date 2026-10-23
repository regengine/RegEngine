'use client';

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { ErrorState } from '@/components/ui/error-state';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { StatTile } from '@/components/ui/stat-tile';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';
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
    Shield,
} from 'lucide-react';

import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
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

/* ── Config ──
   Event type is expressed as an icon + label badge in a semantic tone, never
   as a hard-coded hex piped through an inline style. */

const EVENT_CONFIG: Record<string, { tone: BadgeTone; icon: React.ElementType; label: string }> = {
    cte_recorded: { tone: 'success', icon: Database, label: 'CTE Recorded' },
    api_call: { tone: 'info', icon: Webhook, label: 'API Call' },
    compliance_change: { tone: 'warning', icon: AlertTriangle, label: 'Compliance' },
    export: { tone: 'neutral', icon: Upload, label: 'Export' },
    user_login: { tone: 'neutral', icon: User, label: 'Auth' },
    alert: { tone: 'danger', icon: AlertTriangle, label: 'Alert' },
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
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetchWithCsrf(`${base}/api/v1/audit-log/${tenantId}?page=${page}&page_size=${pageSize}`, {
        credentials: 'include',
        signal: AbortSignal.timeout(8000),
        headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
        console.error(`Audit log fetch failed: ${res.status} ${res.statusText}`);
        throw new Error("Couldn't load the audit log.");
    }
    return res.json();
}

/* ── Page ── */

export default function AuditLogPage() {
    const { isAuthenticated } = useAuth();
    const { tenantId } = useTenant();

    const isLoggedIn = isAuthenticated;
    const effectiveTenantId = tenantId;

    const [filter, setFilter] = useState<EventFilter>('all');
    const [searchQuery, setSearchQuery] = useState('');
    const [page, setPage] = useState(1);
    const [pageSize] = useState(50);
    const [expandedId, setExpandedId] = useState<string | null>(null);

    const { data: auditData, isLoading: loading, error: auditError, refetch: loadLog, dataUpdatedAt } = useQuery({
        queryKey: ['audit-log', effectiveTenantId, page, pageSize],
        queryFn: async () => {
            const data = await fetchAuditLog(effectiveTenantId!, page, pageSize);
            return { entries: data.entries || [], total: data.total || 0 };
        },
        enabled: isLoggedIn && !!effectiveTenantId,
        retry: false,
    });

    const entries = useMemo(() => auditData?.entries ?? [], [auditData?.entries]);
    const total = auditData?.total ?? 0;
    const error = auditError;
    const lastFetched = dataUpdatedAt ? new Date(dataUpdatedAt) : null;

    // Re-fetch when data changes elsewhere (upload, bulk import, tab refocus)
    useDashboardRefresh(() => { loadLog(); });

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
        const now = dataUpdatedAt || 0;
        const today = entries.filter(e => now - new Date(e.timestamp).getTime() < 86400000).length;
        const typeCounts: Record<string, number> = {};
        entries.forEach(e => { typeCounts[e.event_type] = (typeCounts[e.event_type] || 0) + 1; });
        return { today, typeCounts };
    }, [entries, dataUpdatedAt]);

    return (
        <PageContainer>
            <PageHeader
                title="Audit Log"
                description={auditData && !error ? "Immutable, SHA-256 verified record of all system events" : "System event history"}
                meta={
                    <>
                        {lastFetched && !error && <span>Updated {lastFetched.toLocaleTimeString()}</span>}
                        {auditData && !error && <Badge tone="neutral" size="sm" className="hidden sm:inline-flex">
                            <Shield className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                            Hash-chained
                        </Badge>}
                    </>
                }
                secondaryActions={
                    <>
                        <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Refresh audit log"
                            onClick={() => loadLog()}
                            disabled={loading}
                        >
                            <RefreshCw
                                className={loading ? 'animate-spin motion-reduce:animate-none' : undefined}
                                strokeWidth={1.75}
                                aria-hidden="true"
                            />
                        </Button>
                        {auditData && !error && <Button variant="secondary" size="sm" asChild>
                            <Link href="/dashboard/export-jobs">
                                <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                Export
                            </Link>
                        </Button>}
                    </>
                }
            />

            <div className="space-y-6">
                {/* Auth gate */}
                {!isLoggedIn && (
                    <Callout tone="warning" icon={Shield}>
                        Sign in to view the audit log.
                    </Callout>
                )}

                {/* Summary */}
                {isLoggedIn && !error && entries.length > 0 && (
                    <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
                        <StatTile label="Total Events" value={total.toLocaleString()} />
                        <StatTile label="Today" value={stats.today} />
                        <StatTile label="Event Types" value={Object.keys(stats.typeCounts).length} />
                    </div>
                )}

                {/* Loading */}
                {loading && entries.length === 0 && (
                    <div className="flex flex-col items-center justify-center gap-3 py-16">
                        <Spinner size="lg" />
                        <p className="text-ui text-re-text-tertiary">Loading audit trail...</p>
                    </div>
                )}

                {/* Error */}
                {error && <ErrorState message="We could not load this page." onRetry={() => loadLog()} />}

                {/* Event list shell: toolbar, rows, pagination */}
                {isLoggedIn && !error && entries.length > 0 && (
                    <div className="rounded-lg border border-re-border bg-re-surface-card">
                        {/* Toolbar */}
                        <div className="space-y-3 border-b border-re-border-subtle px-4 py-3">
                            <div className="w-full sm:max-w-sm">
                                <label htmlFor="audit-log-search" className="sr-only">
                                    Search actions, actors, resources
                                </label>
                                <Input
                                    id="audit-log-search"
                                    type="search"
                                    placeholder="Search actions, actors, resources..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    leadingIcon={<Search strokeWidth={1.75} />}
                                />
                            </div>

                            <div className="no-scrollbar flex items-center gap-1.5 overflow-x-auto pb-1">
                                <Filter
                                    className="h-4 w-4 shrink-0 text-re-text-muted"
                                    strokeWidth={1.75}
                                    aria-hidden="true"
                                />
                                {FILTER_OPTIONS.map((f) => {
                                    const count = f.id === 'all' ? entries.length : (stats.typeCounts[f.id] || 0);
                                    const active = filter === f.id;
                                    return (
                                        <button
                                            key={f.id}
                                            type="button"
                                            aria-pressed={active}
                                            onClick={() => setFilter(f.id)}
                                            className={cn(
                                                'flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 text-[0.8125rem] font-medium transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-card motion-reduce:transition-none',
                                                active
                                                    ? 'border-re-border-strong bg-re-surface-inset text-re-text-primary'
                                                    : 'border-re-border bg-re-surface-card text-re-text-secondary hover:bg-re-surface-inset hover:text-re-text-primary'
                                            )}
                                        >
                                            {f.label}
                                            {count > 0 && (
                                                <span className="font-mono text-label tabular-nums text-re-text-tertiary">
                                                    {count}
                                                </span>
                                            )}
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Rows */}
                        {filtered.length > 0 ? (
                            <ul className="divide-y divide-re-border-subtle">
                                {filtered.map((entry) => {
                                    const config = EVENT_CONFIG[entry.event_type] || EVENT_CONFIG.cte_recorded;
                                    const Icon = config.icon;
                                    const isExpanded = expandedId === entry.id;

                                    return (
                                        <li key={entry.id}>
                                            <button
                                                type="button"
                                                aria-expanded={isExpanded}
                                                onClick={() => setExpandedId(isExpanded ? null : entry.id)}
                                                className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors duration-120 hover:bg-re-surface-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none sm:items-center"
                                            >
                                                <div className="min-w-0 flex-1">
                                                    <div className="flex flex-wrap items-center gap-2">
                                                        <span className="text-ui font-medium text-re-text-primary">
                                                            {entry.action}
                                                        </span>
                                                        <Badge tone={config.tone} size="sm">
                                                            <Icon
                                                                className="h-3.5 w-3.5 shrink-0"
                                                                strokeWidth={1.75}
                                                                aria-hidden="true"
                                                            />
                                                            {config.label}
                                                        </Badge>
                                                    </div>
                                                    <div className="mt-0.5 flex items-center gap-1.5 text-small text-re-text-tertiary">
                                                        <span className="truncate">{entry.actor}</span>
                                                        <span className="hidden sm:inline" aria-hidden="true">→</span>
                                                        <span className="hidden truncate sm:inline">{entry.resource}</span>
                                                    </div>
                                                </div>
                                                <div className="flex shrink-0 items-center gap-2 text-right">
                                                    <div>
                                                        <div className="flex items-center justify-end gap-1 text-small text-re-text-tertiary">
                                                            <Clock
                                                                className="h-3 w-3"
                                                                strokeWidth={1.75}
                                                                aria-hidden="true"
                                                            />
                                                            {formatTimeAgo(entry.timestamp)}
                                                        </div>
                                                        {entry.hash && (
                                                            <div className="mt-0.5 hidden items-center justify-end gap-1 font-mono text-label text-re-text-muted sm:flex">
                                                                <Hash
                                                                    className="h-3 w-3"
                                                                    strokeWidth={1.75}
                                                                    aria-hidden="true"
                                                                />
                                                                {entry.hash.slice(0, 10)}
                                                            </div>
                                                        )}
                                                    </div>
                                                    <ChevronDown
                                                        className={cn(
                                                            'h-4 w-4 text-re-text-muted transition-transform duration-120 motion-reduce:transition-none',
                                                            isExpanded && 'rotate-180'
                                                        )}
                                                        strokeWidth={1.75}
                                                        aria-hidden="true"
                                                    />
                                                </div>
                                            </button>

                                            {isExpanded && (
                                                <dl className="grid grid-cols-1 gap-2 border-t border-re-border-subtle bg-re-surface-inset px-4 py-3 text-small sm:grid-cols-2">
                                                    <div>
                                                        <dt className="inline text-re-text-tertiary">Timestamp:</dt>{' '}
                                                        <dd className="inline font-mono text-re-text-secondary">
                                                            {new Date(entry.timestamp).toLocaleString()}
                                                        </dd>
                                                    </div>
                                                    <div>
                                                        <dt className="inline text-re-text-tertiary">Category:</dt>{' '}
                                                        <dd className="inline capitalize text-re-text-secondary">
                                                            {entry.category}
                                                        </dd>
                                                    </div>
                                                    <div>
                                                        <dt className="inline text-re-text-tertiary">Actor:</dt>{' '}
                                                        <dd className="inline text-re-text-secondary">{entry.actor}</dd>
                                                    </div>
                                                    <div className="min-w-0">
                                                        <dt className="inline text-re-text-tertiary">Resource:</dt>{' '}
                                                        <dd className="inline break-all font-mono text-re-text-secondary">
                                                            {entry.resource}
                                                        </dd>
                                                    </div>
                                                    {entry.ip_address && (
                                                        <div>
                                                            <dt className="inline text-re-text-tertiary">IP:</dt>{' '}
                                                            <dd className="inline font-mono text-re-text-secondary">
                                                                {entry.ip_address}
                                                            </dd>
                                                        </div>
                                                    )}
                                                    {entry.hash && (
                                                        <div className="sm:col-span-2">
                                                            <dt className="inline text-re-text-tertiary">SHA-256:</dt>{' '}
                                                            <dd className="inline break-all font-mono text-re-text-secondary">
                                                                {entry.hash}
                                                            </dd>
                                                        </div>
                                                    )}
                                                    {entry.details && Object.keys(entry.details).length > 0 && (
                                                        <div className="sm:col-span-2">
                                                            <dt className="text-re-text-tertiary">Metadata:</dt>
                                                            <dd>
                                                                <pre className="mt-1 overflow-x-auto rounded-md bg-re-surface-card p-2 font-mono text-label leading-4 text-re-text-secondary">
                                                                    {JSON.stringify(entry.details, null, 2)}
                                                                </pre>
                                                            </dd>
                                                        </div>
                                                    )}
                                                </dl>
                                            )}
                                        </li>
                                    );
                                })}
                            </ul>
                        ) : (
                            <EmptyState
                                bare
                                size="sm"
                                icon={Search}
                                title="No matching events"
                                description="No audit entries on this page match the current search and filter."
                            />
                        )}

                        {/* Pagination */}
                        {totalPages > 1 && (
                            <div className="flex items-center justify-between border-t border-re-border-subtle px-4 py-2">
                                <span className="text-small text-re-text-tertiary">
                                    Page {page} of {totalPages} ({total.toLocaleString()} entries)
                                </span>
                                <div className="flex gap-2">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        aria-label="Previous page"
                                        disabled={page <= 1}
                                        onClick={() => setPage(p => p - 1)}
                                    >
                                        <ChevronLeft strokeWidth={1.75} aria-hidden="true" />
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        aria-label="Next page"
                                        disabled={page >= totalPages}
                                        onClick={() => setPage(p => p + 1)}
                                    >
                                        <ChevronRight strokeWidth={1.75} aria-hidden="true" />
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* Empty state */}
                {isLoggedIn && !loading && entries.length === 0 && !error && (
                    <EmptyState
                        icon={ScrollText}
                        title="No Audit Entries Yet"
                        titleAs="h2"
                        description="Events will appear here as your team scans labels, imports data, and generates reports. Every action is SHA-256 hash-chained and protected from modification by append-only database triggers."
                        action={
                            <Badge tone="success">
                                <ShieldCheck className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                SHA-256 hash chain ready
                            </Badge>
                        }
                    />
                )}

                {/* Chain integrity footer */}
                {isLoggedIn && !error && entries.length > 0 && (
                    <Card variant="inset">
                        <CardContent className="p-4 text-ui text-re-text-secondary">
                            <span className="font-medium text-re-text-primary">Tamper-evident audit trail: </span>
                            Every entry is cryptographically chained using SHA-256. Database triggers prevent modification or deletion.
                            Designed to support 21 CFR Part 11-style record controls and long-term retention.
                        </CardContent>
                    </Card>
                )}
            </div>
        </PageContainer>
    );
}
