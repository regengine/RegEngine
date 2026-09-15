'use client';

import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/layout/page-header';
import { Skeleton } from '@/components/ui/skeleton';
import { StatTile } from '@/components/ui/stat-tile';
import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';

interface UsageRow {
    endpoint: string;
    method: string;
    status_code: number;
    response_time_ms: number | null;
    created_at: string;
}

interface EndpointSummary {
    endpoint: string;
    method: string;
    count: number;
    avgLatency: number;
    errorRate: number;
}

/** Segmented range control — the one place this page spends a tint. */
function rangeButtonClass(active: boolean) {
    return cn(
        'rounded-sm px-3 py-1 text-[0.8125rem] transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none',
        active
            ? 'bg-re-surface-inset font-medium text-re-text-primary'
            : 'text-re-text-secondary hover:text-re-text-primary',
    );
}

export default function UsagePage() {
    const { user: authUser } = useAuth();
    const [usage, setUsage] = useState<UsageRow[]>([]);
    // `isLoading` covers the very first paint only. Range switches use `isRefreshing`
    // so the header and the range toggle stay mounted instead of being replaced by a
    // full-page spinner under the pointer that just clicked them.
    const [isLoading, setIsLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [loadFailed, setLoadFailed] = useState(false);
    const [timeRange, setTimeRange] = useState<'24h' | '7d' | '30d'>('7d');

    const loadUsage = useCallback(async () => {
        if (!authUser) {
            setIsLoading(false);
            return;
        }

        setIsRefreshing(true);
        setLoadFailed(false);
        try {
            const response = await fetch(`/api/developer/portal/usage?range=${timeRange}`, {
                credentials: 'include',
            });
            if (!response.ok) {
                setUsage([]);
                setLoadFailed(true);
                return;
            }
            const data = await response.json();
            setUsage(data.usage || []);
        } catch {
            setUsage([]);
            setLoadFailed(true);
        } finally {
            setIsRefreshing(false);
            setIsLoading(false);
        }
    }, [authUser, timeRange]);

    useEffect(() => { loadUsage(); }, [loadUsage]);

    // Compute summary stats
    const totalRequests = usage.length;
    const errorCount = usage.filter(r => r.status_code >= 400).length;
    const errorRate = totalRequests > 0 ? ((errorCount / totalRequests) * 100).toFixed(1) : '0';
    const avgLatency = totalRequests > 0
        ? Math.round(usage.reduce((sum, r) => sum + (r.response_time_ms || 0), 0) / totalRequests)
        : 0;

    // Group by endpoint
    const endpointMap = new Map<string, UsageRow[]>();
    usage.forEach(row => {
        const key = `${row.method} ${row.endpoint}`;
        if (!endpointMap.has(key)) endpointMap.set(key, []);
        endpointMap.get(key)!.push(row);
    });

    const endpoints: EndpointSummary[] = Array.from(endpointMap.entries())
        .map(([, rows]) => ({
            endpoint: rows[0].endpoint,
            method: rows[0].method,
            count: rows.length,
            avgLatency: Math.round(rows.reduce((s, r) => s + (r.response_time_ms || 0), 0) / rows.length),
            errorRate: (rows.filter(r => r.status_code >= 400).length / rows.length) * 100,
        }))
        .sort((a, b) => b.count - a.count);

    if (isLoading) {
        return (
            <div className="space-y-6">
                <div className="space-y-2 border-b border-re-border-subtle pb-5">
                    <Skeleton className="h-8 w-48" />
                    <Skeleton className="h-4 w-80" />
                </div>
                <Skeleton className="h-16 w-full rounded-md" />
                <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                    {Array.from({ length: 4 }).map((_, i) => (
                        <Skeleton key={i} className="h-24 w-full rounded-lg" />
                    ))}
                </div>
                <Skeleton className="h-48 w-full rounded-lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <PageHeader
                title="API Usage"
                description="Monitor your API request volume, latency, and error rates."
                meta={isRefreshing ? (
                    <Loader2
                        className="h-3.5 w-3.5 animate-spin text-re-text-muted motion-reduce:animate-none"
                        strokeWidth={1.75}
                        aria-label="Refreshing usage"
                    />
                ) : undefined}
                secondaryActions={
                    <div className="flex gap-1 rounded-md border border-re-border bg-re-surface-card p-1">
                        {(['24h', '7d', '30d'] as const).map(range => (
                            <button
                                key={range}
                                type="button"
                                onClick={() => setTimeRange(range)}
                                aria-pressed={timeRange === range}
                                className={rangeButtonClass(timeRange === range)}
                            >
                                {range}
                            </button>
                        ))}
                    </div>
                }
                className="mb-0"
            />

            {/* Telemetry honesty: sandbox keys don't record traffic, so this page
                can only ever show live-integration data — which is provisioned
                during onboarding. Zeros here are expected, not a failure. */}
            <Callout tone="info">
                Sandbox keys don&apos;t record request telemetry yet. Usage data appears here once a
                live <code className="font-mono text-[0.8125rem]">rge_live_</code> integration is enabled for your
                workspace during onboarding.
            </Callout>

            {loadFailed && (
                <Callout tone="danger" role="alert">
                    Couldn&apos;t load usage for the selected range. Pick a range again to retry.
                </Callout>
            )}

            {/* Summary tiles */}
            <div
                className={cn(
                    'grid grid-cols-2 gap-4 transition-opacity duration-180 motion-reduce:transition-none lg:grid-cols-4',
                    isRefreshing && 'opacity-50',
                )}
            >
                <StatTile label="Requests" value={totalRequests.toLocaleString()} />
                <StatTile label="Avg Latency" value={`${avgLatency}ms`} />
                <StatTile label="Error Rate" value={`${errorRate}%`} />
                <StatTile label="Endpoints Hit" value={endpoints.length} />
            </div>

            {/* Endpoint breakdown */}
            <Card
                className={cn(
                    'transition-opacity duration-180 motion-reduce:transition-none',
                    isRefreshing && 'opacity-50',
                )}
            >
                <CardHeader>
                    <CardTitle>Endpoint Breakdown</CardTitle>
                </CardHeader>
                {endpoints.length === 0 ? (
                    <CardContent>
                        <p className="py-8 text-center text-ui text-re-text-tertiary">
                            No recorded requests in this time period.
                        </p>
                    </CardContent>
                ) : (
                    <ul className="divide-y divide-re-border-subtle">
                        {endpoints.map((ep, i) => (
                            <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-2.5">
                                <Badge tone="neutral" size="sm" mono className="w-14 shrink-0 justify-center">
                                    {ep.method}
                                </Badge>
                                <code className="min-w-0 flex-1 truncate font-mono text-[0.8125rem] text-re-text-primary">{ep.endpoint}</code>
                                <span className="text-small tabular-nums text-re-text-secondary">{ep.count.toLocaleString()} req</span>
                                <span className="w-16 text-right text-small tabular-nums text-re-text-tertiary">{ep.avgLatency}ms</span>
                                <span className="w-12 text-right text-small tabular-nums text-re-text-tertiary">
                                    {ep.errorRate.toFixed(1)}%
                                </span>
                            </li>
                        ))}
                    </ul>
                )}
            </Card>
        </div>
    );
}
