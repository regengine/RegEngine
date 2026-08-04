'use client';

import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, TrendingUp, Clock, AlertCircle, Activity } from 'lucide-react';

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
        return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-[var(--re-text-muted)]" /></div>;
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-[var(--re-text-primary)]">API Usage</h1>
                    <p className="text-sm mt-1 text-[var(--re-text-muted)]">
                        Monitor your API request volume, latency, and error rates.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {isRefreshing && (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--re-text-muted)]" aria-label="Refreshing usage" />
                    )}
                    <div className="flex gap-1 p-1 rounded-md bg-white/[0.03] border border-white/[0.06]">
                        {(['24h', '7d', '30d'] as const).map(range => (
                            <button
                                key={range}
                                type="button"
                                onClick={() => setTimeRange(range)}
                                aria-pressed={timeRange === range}
                                className="px-3 py-1 text-xs font-medium rounded transition-colors"
                                style={{
                                    background: timeRange === range ? 'rgba(16,185,129,0.15)' : 'transparent',
                                    color: timeRange === range ? 'var(--re-brand)' : 'var(--re-text-muted)',
                                }}
                            >
                                {range}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {loadFailed && (
                <p className="text-sm text-re-danger">
                    Couldn&apos;t load usage for the selected range. Pick a range again to retry.
                </p>
            )}

            {/* Summary cards */}
            <div
                className="grid grid-cols-1 md:grid-cols-4 gap-4 transition-opacity"
                style={{ opacity: isRefreshing ? 0.5 : 1 }}
            >
                <Card className="bg-white/[0.02] border-white/[0.06]">
                    <CardContent className="py-4">
                        <div className="flex items-center gap-2 mb-1">
                            <Activity className="w-4 h-4 text-[var(--re-brand)]" />
                            <span className="text-xs font-medium text-[var(--re-text-muted)]">Requests</span>
                        </div>
                        <p className="text-2xl font-bold text-[var(--re-text-primary)]">{totalRequests.toLocaleString()}</p>
                    </CardContent>
                </Card>
                <Card className="bg-white/[0.02] border-white/[0.06]">
                    <CardContent className="py-4">
                        <div className="flex items-center gap-2 mb-1">
                            <Clock className="w-4 h-4 text-re-info" />
                            <span className="text-xs font-medium text-[var(--re-text-muted)]">Avg Latency</span>
                        </div>
                        <p className="text-2xl font-bold text-[var(--re-text-primary)]">{avgLatency}ms</p>
                    </CardContent>
                </Card>
                <Card className="bg-white/[0.02] border-white/[0.06]">
                    <CardContent className="py-4">
                        <div className="flex items-center gap-2 mb-1">
                            <AlertCircle className="w-4 h-4 text-re-danger" />
                            <span className="text-xs font-medium text-[var(--re-text-muted)]">Error Rate</span>
                        </div>
                        <p className="text-2xl font-bold text-[var(--re-text-primary)]">{errorRate}%</p>
                    </CardContent>
                </Card>
                <Card className="bg-white/[0.02] border-white/[0.06]">
                    <CardContent className="py-4">
                        <div className="flex items-center gap-2 mb-1">
                            <TrendingUp className="w-4 h-4 text-[var(--re-linkage)]" />
                            <span className="text-xs font-medium text-[var(--re-text-muted)]">Endpoints Hit</span>
                        </div>
                        <p className="text-2xl font-bold text-[var(--re-text-primary)]">{endpoints.length}</p>
                    </CardContent>
                </Card>
            </div>

            {/* Endpoint breakdown */}
            <Card
                className="bg-white/[0.02] border-white/[0.06] transition-opacity"
                style={{ opacity: isRefreshing ? 0.5 : 1 }}
            >
                <CardHeader>
                    <CardTitle className="text-sm text-[var(--re-text-primary)]">Endpoint Breakdown</CardTitle>
                </CardHeader>
                <CardContent>
                    {endpoints.length === 0 ? (
                        <p className="text-sm text-center py-8 text-[var(--re-text-muted)]">
                            No API activity in this time period. Make your first request to see usage data.
                        </p>
                    ) : (
                        <div className="space-y-2">
                            {endpoints.map((ep, i) => (
                                <div key={i} className="flex items-center gap-3 py-2 px-3 rounded bg-black/[0.15]">
                                    <Badge
                                        variant="outline"
                                        className="font-mono text-xs w-14 justify-center"
                                        style={{
                                            color: ep.method === 'POST' ? 'var(--re-brand)' : '#60a5fa',
                                            borderColor: ep.method === 'POST' ? 'rgba(16,185,129,0.3)' : 'rgba(96,165,250,0.3)',
                                        }}
                                    >
                                        {ep.method}
                                    </Badge>
                                    <code className="text-xs font-mono flex-1 truncate text-[var(--re-text-primary)]">{ep.endpoint}</code>
                                    <span className="text-xs tabular-nums text-[var(--re-text-muted)]">{ep.count.toLocaleString()} req</span>
                                    <span className="text-xs tabular-nums w-16 text-right text-[var(--re-text-disabled)]">{ep.avgLatency}ms</span>
                                    <span className="text-xs tabular-nums w-12 text-right" style={{ color: ep.errorRate > 5 ? '#f87171' : 'var(--re-text-disabled)' }}>
                                        {ep.errorRate.toFixed(1)}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
